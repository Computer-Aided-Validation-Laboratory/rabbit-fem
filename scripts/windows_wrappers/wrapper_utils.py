"""Utility functions for Windows Zig toolchain wrappers.

Converts MSYS2 POSIX drive paths to Windows paths and handles
linker archive extraction and response file unpacking.
"""

import os
from pathlib import Path
import re
import shlex
import shutil
import sys
from typing import List


def posix_to_win(path: str) -> str:
    """Convert MSYS2 POSIX paths (/c/... or /d/...) to Windows paths."""
    # Match /c/foo or /C/foo
    match = re.match(r"^/([a-zA-Z])/(.*)", path)
    if match:
        return f"{match.group(1).upper()}:/{match.group(2)}"
    # Match flags like -I/c/foo or -L/d/foo
    match_flag = re.match(r"^(-[ILWp])(?::)?/([a-zA-Z])/(.*)", path)
    if match_flag:
        return (
            f"{match_flag.group(1)}"
            f"{match_flag.group(2).upper()}:/{match_flag.group(3)}"
        )
    return path


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
