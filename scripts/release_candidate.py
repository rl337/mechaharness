"""Verify immutable release identity and built archive contents before tagging."""

from __future__ import annotations

import argparse
import ast
import json
import re
import stat
import subprocess
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def release_version(root: Path) -> str:
    project = (root / "pyproject.toml").read_text()
    match = re.search(r'^version = "([^"]+)"$', project, re.MULTILINE)
    if match is None or not re.fullmatch(r"\d+\.\d+\.\d+", match[1]):
        raise ValueError("release version must be a final X.Y.Z version")
    tree = ast.parse((root / "src/mechaharness/__init__.py").read_text())
    declarations = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
    ]
    if declarations != [match[1]]:
        raise ValueError("pyproject.toml and package __version__ disagree")
    return match[1]


def validate_candidate(root: Path, expected_sha: str) -> str:
    if git(root, "rev-parse", "HEAD") != expected_sha:
        raise ValueError("checkout does not match the selected candidate SHA")
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("candidate has modified or untracked files")
    version = release_version(root)
    tags = git(root, "tag", "--list", f"v{version}")
    if tags and git(root, "rev-parse", f"v{version}^{{commit}}") != expected_sha:
        raise ValueError("version tag already belongs to a different commit; choose a new version")
    return version


def validate_member_names(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise ValueError("archive contains duplicate member names")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("archive contains an unsafe member path")


def release_response_state(response: str, version: str) -> str:
    """Distinguish an absent release from API errors or an unexpected release state."""
    headers, separator, body = response.replace("\r\n", "\n").partition("\n\n")
    first = headers.splitlines()[0].split() if headers else []
    if len(first) < 2 or not first[0].startswith("HTTP/"):
        raise ValueError("release API returned no valid HTTP status")
    if first[1] == "404":
        return "missing"
    if first[1] != "200" or not separator:
        raise ValueError("release API failed; do not infer that the release is absent")
    release = json.loads(body)
    if (
        release.get("tag_name") != f"v{version}"
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("existing release has an unexpected tag or publication state")
    return "present"


def validate_archives(root: Path, directory: Path, version: str) -> None:
    """Reject unexpected versions, untracked source files and modified packaged code."""
    tracked = set(git(root, "ls-files", "-z").split("\0"))
    archives = list(directory.iterdir())
    wheels = [p for p in archives if p.suffix == ".whl"]
    sdists = [p for p in archives if p.name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1 or len(archives) != 2:
        raise ValueError("release needs exactly one wheel and one source archive")
    for path in archives:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as wheel:
                validate_member_names(wheel.namelist())
                if any(stat.S_ISLNK(info.external_attr >> 16) for info in wheel.infolist()):
                    raise ValueError("release archives must not contain links")
                entries = [(n, wheel.read(n)) for n in wheel.namelist() if not n.endswith("/")]
            metadata_prefix = f"mechaharness-{version}.dist-info/"
            allowed_metadata = {
                "METADATA",
                "WHEEL",
                "RECORD",
                "entry_points.txt",
                "top_level.txt",
                "licenses/LICENSE",
                "LICENSE",
            }
            for name, _ in entries:
                if ".dist-info/" in name and (
                    not name.startswith(metadata_prefix)
                    or name[len(metadata_prefix) :] not in allowed_metadata
                ):
                    raise ValueError("unexpected wheel metadata member")
            metadata = [b for n, b in entries if n.endswith(".dist-info/METADATA")]
            sources = [("src/" + n, b) for n, b in entries if ".dist-info/" not in n]
        else:
            with tarfile.open(path) as sdist:
                entries = []
                members = sdist.getmembers()
                validate_member_names([member.name for member in members])
                for member in members:
                    if member.name.split("/", 1)[0] != f"mechaharness-{version}":
                        raise ValueError("unexpected source archive root")
                    if member.issym() or member.islnk():
                        raise ValueError("release archives must not contain links")
                    if member.isfile():
                        handle = sdist.extractfile(member)
                        assert handle is not None
                        entries.append((member.name.split("/", 1)[-1], handle.read()))
            metadata = [b for n, b in entries if n == "PKG-INFO"]
            generated = {"PKG-INFO", "setup.cfg"} | {
                "src/mechaharness.egg-info/" + name
                for name in (
                    "PKG-INFO",
                    "SOURCES.txt",
                    "dependency_links.txt",
                    "entry_points.txt",
                    "requires.txt",
                    "top_level.txt",
                )
            }
            sources = [(n, b) for n, b in entries if n not in generated]
        if len(metadata) != 1:
            raise ValueError("archive needs exactly one package metadata record")
        package_metadata = BytesParser().parsebytes(metadata[0])
        if package_metadata["Version"] != version or package_metadata["Name"] != "mechaharness":
            raise ValueError("archive metadata version does not match candidate")
        expected_package = {
            name
            for name in tracked
            if name.startswith("src/mechaharness/")
            and (name.endswith(".py") or name.endswith("/py.typed"))
        }
        if not expected_package.issubset({name for name, _ in sources}):
            raise ValueError("archive is missing tracked package source or typing marker")
        for name, content in sources:
            source = root / name
            if (
                name not in tracked
                or source.is_symlink()
                or root.resolve() not in source.resolve().parents
                or source.read_bytes() != content
            ):
                raise ValueError(f"archive contains untracked or changed source: {name!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--release-response", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = validate_candidate(root, args.expected_sha)
    if args.dist is not None:
        validate_archives(root, args.dist, version)
    if args.release_response is not None:
        print("release_state=" + release_response_state(args.release_response.read_text(), version))
    print(f"version={version}")
    print(f"sha={args.expected_sha}")


if __name__ == "__main__":
    main()
