"""Run shell and verification commands inside a private coding workspace."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


class CodingProcessUnavailable(RuntimeError):
    """The host could not create the required process sandbox."""


def run_coding_process(
    command: list[str], root: Path, *, timeout: float, isolated: bool
) -> subprocess.CompletedProcess[str]:
    env = None
    if isolated:
        scratch = root.parent / "process-home"
        scratch.mkdir(mode=0o700, exist_ok=True)
        env = {
            "HOME": str(scratch),
            "TMPDIR": str(scratch),
            "LANG": "C",
            "PATH": os.pathsep.join([str(Path(sys.executable).parent), os.defpath]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
        runtime = [Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve()]
        if sys.platform == "darwin":
            reads = [
                Path(p)
                for p in (
                    "/System/Library",
                    "/Library/Developer",
                    "/usr",
                    "/bin",
                    "/sbin",
                    "/dev",
                    "/private/etc",
                    "/private/var/db/timezone",
                )
            ]
            profile = [
                "(version 1)",
                "(allow default)",
                "(deny network*)",
                "(deny file-read*)",
                '(allow file-read* (literal "/"))',
                '(import "system.sb")',
                "(allow file-read-metadata)",
                "(deny file-write*)",
                '(allow file-read* file-write* (subpath (param "ROOT")) (subpath (param "TMP")))',
                '(deny file-write* (subpath (param "GIT")))',
                '(allow file-write* (literal "/dev/null"))',
            ]
            args = ["-D", f"ROOT={root}", "-D", f"TMP={scratch}", "-D", f"GIT={root / '.git'}"]
            for i, path in enumerate([*reads, *runtime]):
                args.extend(["-D", f"READ{i}={path}"])
                profile.append(f'(allow file-read* (subpath (param "READ{i}")))')
            command = ["/usr/bin/sandbox-exec", *args, "-p", "\n".join(profile), *command]
        elif sys.platform.startswith("linux") and shutil.which("bwrap"):
            args = [
                "bwrap",
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
            ]
            for path in [Path(p) for p in ("/usr", "/bin", "/lib", "/lib64", "/etc")] + runtime:
                if path.exists():
                    args.extend(["--ro-bind", str(path), str(path)])
            args.extend(["--bind", str(root), str(root), "--bind", str(scratch), str(scratch)])
            if (root / ".git").exists():
                args.extend(["--ro-bind", str(root / ".git"), str(root / ".git")])
            command = [*args, "--chdir", str(root), "--", *command]
        else:
            raise CodingProcessUnavailable(
                "coding process isolation requires macOS sandbox-exec or Linux bwrap"
            )
    completed = subprocess.run(
        command, cwd=root, env=env, capture_output=True, text=True, timeout=timeout, check=False
    )
    if isolated and completed.returncode and completed.stderr.startswith(
        ("sandbox-exec:", "bwrap:")
    ):
        raise CodingProcessUnavailable(completed.stderr.strip())
    return completed
