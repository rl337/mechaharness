"""Release identity must survive branch movement and matching-tag retries."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.release_candidate import git, validate_candidate


def commit(root: Path) -> str:
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Release tests",
        "-c",
        "user.email=release@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "candidate",
    )
    return git(root, "rev-parse", "HEAD")


@pytest.mark.parametrize(
    "case",
    ["valid", "matching_tag", "wrong_tag", "dirty", "untracked", "wrong_sha", "version_mismatch"],
)
def test_release_candidate_identity(tmp_path: Path, case: str) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "src/mechaharness").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('version = "1.2.3"\n')
    init = tmp_path / "src/mechaharness/__init__.py"
    init.write_text('__version__ = "1.2.3"\n')
    first = commit(tmp_path)
    if case in {"matching_tag", "wrong_tag"}:
        git(tmp_path, "tag", "v1.2.3")
    if case in {"dirty", "wrong_tag"}:
        (tmp_path / "README.md").write_text("next change")
        if case == "wrong_tag":
            commit(tmp_path)
    if case == "untracked":
        (tmp_path / "notes.txt").write_text("untracked")
    if case == "version_mismatch":
        init.write_text('__version__ = "1.2.4"\n')
        commit(tmp_path)
    expected = first if case == "wrong_sha" else git(tmp_path, "rev-parse", "HEAD")
    if case == "wrong_sha":
        expected = "0" * 40
    if case in {"valid", "matching_tag"}:
        assert validate_candidate(tmp_path, expected) == "1.2.3"
    else:
        with pytest.raises(ValueError):
            validate_candidate(tmp_path, expected)


def test_git_errors_cannot_be_reported_as_a_valid_candidate(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        validate_candidate(tmp_path, "0" * 40)


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "wrong_version",
        "untracked_source",
        "changed_source",
        "unsafe_path",
        "duplicate",
        "metadata_code",
        "missing_source",
        "archive_link",
        "wrong_name",
    ],
)
def test_built_archives_must_match_candidate(tmp_path: Path, case: str) -> None:
    import io
    import tarfile
    import zipfile

    from scripts.release_candidate import validate_archives

    git(tmp_path, "init", "-q")
    source = tmp_path / "src/mechaharness/__init__.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b'__version__ = "1.2.3"\n')
    commit(tmp_path)
    directory = tmp_path / "artifacts"
    directory.mkdir()
    metadata_version = "9.9.9" if case == "wrong_version" else "1.2.3"
    metadata = f"Metadata-Version: 2.1\nName: mechaharness\nVersion: {metadata_version}\n".encode()
    if case == "wrong_name":
        metadata = metadata.replace(b"Name: mechaharness", b"Name: unrelated")
    content = b"changed" if case == "changed_source" else source.read_bytes()
    with zipfile.ZipFile(directory / "package.whl", "w") as wheel:
        wheel.writestr("mechaharness/__init__.py", content)
        wheel.writestr("mechaharness-1.2.3.dist-info/METADATA", metadata)
        if case == "unsafe_path":
            wheel.writestr("../escape.py", b"content")
        if case == "duplicate":
            wheel.writestr("mechaharness/__init__.py", content)
        if case == "untracked_source":
            wheel.writestr("mechaharness/local_notes.py", b"private local content")
    if case == "missing_source":
        with zipfile.ZipFile(directory / "package.whl", "w") as wheel:
            wheel.writestr("mechaharness-1.2.3.dist-info/METADATA", metadata)
    with tarfile.open(directory / "package.tar.gz", "w:gz") as sdist:
        if case == "metadata_code":
            member = tarfile.TarInfo("mechaharness-1.2.3/src/mechaharness.egg-info/hidden.py")
            sdist.addfile(member, io.BytesIO(b""))
        if case == "archive_link":
            member = tarfile.TarInfo("mechaharness-1.2.3/link")
            member.type = tarfile.SYMTYPE
            member.linkname = "outside"
            sdist.addfile(member)
        for name, value in {
            "PKG-INFO": metadata,
            "src/mechaharness/__init__.py": source.read_bytes(),
        }.items():
            member = tarfile.TarInfo("mechaharness-1.2.3/" + name)
            member.size = len(value)
            sdist.addfile(member, io.BytesIO(value))
    if case == "valid":
        validate_archives(tmp_path, directory, "1.2.3")
    else:
        with pytest.raises(ValueError):
            validate_archives(tmp_path, directory, "1.2.3")


@pytest.mark.parametrize(
    "case,state",
    [
        ("present", "present"),
        ("missing", "missing"),
        ("draft", None),
        ("prerelease", None),
        ("wrong_tag", None),
        ("unauthorized", None),
        ("network", None),
    ],
)
def test_release_retry_requires_confirmed_absence_or_matching_published_release(
    case, state
) -> None:
    import json

    from scripts.release_candidate import release_response_state

    payload = {"tag_name": "v1.2.3", "draft": False, "prerelease": False}
    if case == "draft":
        payload["draft"] = True
    if case == "prerelease":
        payload["prerelease"] = True
    if case == "wrong_tag":
        payload["tag_name"] = "v9.9.9"
    status = "404" if case == "missing" else "401" if case == "unauthorized" else "200"
    response = f"HTTP/2.0 {status}\r\ncontent-type: application/json\r\n\r\n" + json.dumps(payload)
    if case == "network":
        response = ""
    if state is None:
        with pytest.raises(ValueError):
            release_response_state(response, "1.2.3")
    else:
        assert release_response_state(response, "1.2.3") == state
