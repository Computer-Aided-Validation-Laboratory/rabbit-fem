"""Archive wrapper for Zig on Windows/MSYS2."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import List

from wrapper_utils import find_zig_binary, posix_to_win


def sanitize_ar_flags(arg: str) -> str:
    """Normalize ar operation flags (replace 'cq' with 'cr')."""
    if arg in ("cq", "qc", "cruq", "-cq", "-qc"):
        return arg.replace("q", "r")
    if "cq" in arg:
        return arg.replace("cq", "cr")
    return arg


def transform_ar_args(args: List[str]) -> List[str]:
    """Transform MSYS2 ar arguments, unpacking response files if needed."""
    # Handle MSVC lib syntax: lib -OUT:libname.a obj1.o obj2.o
    out_lib = None
    other_args: List[str] = []
    is_msvc_lib = False
    for a in args:
        if a.upper().startswith(("-OUT:", "/OUT:")):
            out_lib = a.split(":", 1)[1]
            is_msvc_lib = True
        elif a.startswith(("-nologo", "/nologo", "-NOLOGO", "/NOLOGO")):
            is_msvc_lib = True
            continue
        else:
            other_args.append(a)
    if is_msvc_lib and out_lib:
        args = ["cr", out_lib] + other_args

    result: List[str] = []
    for arg in args:
        if arg.startswith("@"):
            rsp_path = posix_to_win(arg[1:])
            if os.path.isfile(rsp_path):
                try:
                    content = Path(rsp_path).read_text(
                        encoding="utf-8", errors="replace"
                    )
                    tokens = shlex.split(content, posix=False)
                    for tok in tokens:
                        result.append(posix_to_win(tok))
                    continue
                except Exception:
                    pass
            result.append("@" + rsp_path)
        else:
            sanitized = sanitize_ar_flags(arg)
            result.append(posix_to_win(sanitized))
    return result


def main() -> int:
    zig_cmd = find_zig_binary() + ["ar"]
    transformed = transform_ar_args(sys.argv[1:])

    # Ensure parent directory exists for archive target
    if len(transformed) >= 2:
        archive_path = transformed[1]
        parent = os.path.dirname(archive_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    # If transformed command line exceeds Windows 30k limit, use temp rsp
    total_len = sum(len(a) + 1 for a in transformed)
    temp_rsp_path = None
    if total_len > 30000 and len(transformed) > 3:
        flags = transformed[0]
        archive = transformed[1]
        members = transformed[2:]
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".rsp"
        ) as tmp:
            tmp.write("\n".join(f'"{m}"' for m in members))
            temp_rsp_path = tmp.name
        cmd = zig_cmd + [flags, archive, f"@{temp_rsp_path}"]
    else:
        cmd = zig_cmd + transformed

    try:
        completed = subprocess.run(cmd)
        return completed.returncode
    finally:
        if temp_rsp_path and os.path.exists(temp_rsp_path):
            try:
                os.remove(temp_rsp_path)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
