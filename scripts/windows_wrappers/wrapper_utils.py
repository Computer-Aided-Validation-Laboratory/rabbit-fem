"""Utility functions for Windows Zig toolchain wrappers.

Converts MSYS2 POSIX drive paths to Windows paths and handles
linker archive extraction and response file unpacking.
"""

import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import List, Optional

_msys_root: Optional[str] = None


def get_msys_root() -> str:
    """Dynamically determine MSYS2 root directory without hardcoding."""
    global _msys_root
    if _msys_root is not None:
        return _msys_root

    env_root = os.environ.get("MSYS2_ROOT") or os.environ.get("MSYS_ROOT")
    if env_root and os.path.isdir(env_root):
        _msys_root = env_root.replace("\\", "/").rstrip("/")
        return _msys_root

    try:
        res = subprocess.run(
            ["cygpath", "-m", "/"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            _msys_root = res.stdout.strip().replace("\\", "/").rstrip("/")
            return _msys_root
    except Exception:
        pass

    for cand in (
        "C:/msys64",
        "D:/msys64",
        "C:/tools/msys64",
        "D:/tools/msys64",
    ):
        if os.path.isdir(cand):
            _msys_root = cand
            return _msys_root

    _msys_root = "C:/msys64"
    return _msys_root


def posix_to_win(path: str) -> str:
    """Convert MSYS2 POSIX paths to Windows native paths."""
    msys_root = get_msys_root()

    def repl(m: re.Match) -> str:
        prefix = m.group(1)
        body = m.group(2)
        # If prefix ends with a colon (e.g. D:), body is already part of a Windows drive path
        if prefix.rstrip().endswith(":"):
            return f"{prefix}{body}"
        # Drive letter path: /c/... or /d/...
        m_drive = re.match(r"^/([a-zA-Z])(/.*)?$", body)
        if m_drive:
            drive = m_drive.group(1).upper()
            rest = m_drive.group(2) or ""
            return f"{prefix}{drive}:{rest}"
        # MSYS system mount path: /tmp, /usr, /etc, /var, /opt, /home
        m_sys = re.match(r"^/(tmp|usr|etc|var|opt|home)(/.*)?$", body)
        if m_sys:
            return f"{prefix}{msys_root}/{m_sys.group(1)}{m_sys.group(2) or ''}"
        return f"{prefix}{body}"

    return re.sub(
        r"(^|[-A-Za-z0-9_=,:\'\"\( ]*?)(/[-A-Za-z0-9_.~+/@]+)",
        repl,
        path,
    )


def process_wl_arg(arg: str) -> List[str]:
    """Extract .a and .lib archive files from -Wl, flags.

    Zig's CLI rejects static archives inside -Wl, with
    'error: unsupported linker arg'. Preserves options like
    --out-implib whose argument may end in .a.
    """
    parts = arg[4:].split(",")
    normal_parts: List[str] = []
    archive_args: List[str] = []
    skip_next = False
    for idx, part in enumerate(parts):
        if skip_next:
            skip_next = False
            continue
        part_win = posix_to_win(part)
        if part in ("--out-implib", "-out-implib"):
            normal_parts.append(part)
            if idx + 1 < len(parts):
                normal_parts.append(posix_to_win(parts[idx + 1]))
                skip_next = True
            continue
        if part.startswith(("--out-implib=", "-out-implib=")):
            normal_parts.append(posix_to_win(part))
            continue
        if part_win.endswith(".a") or part_win.endswith(".lib"):
            archive_args.append(part_win)
        else:
            normal_parts.append(part_win)
    out_args: List[str] = []
    if normal_parts:
        out_args.append("-Wl," + ",".join(normal_parts))
    out_args.extend(archive_args)
    return out_args


def find_zig_binary() -> List[str]:
    """Locate zig executable or python -m ziglang fallback."""
    # Check if zig executable is in PATH
    zig_in_path = shutil.which("zig")
    if zig_in_path:
        return [zig_in_path]

    # Check virtual environment site-packages
    venv_root = Path(sys.executable).parent.parent
    site_zig = venv_root / "Lib" / "site-packages" / "ziglang" / "zig.exe"
    if site_zig.is_file():
        return [str(site_zig)]

    # Fallback to python module execution
    return [sys.executable, "-m", "ziglang"]
