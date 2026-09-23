"""C++ compiler wrapper for Zig on Windows/MSYS2."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import List

from wrapper_utils import find_zig_binary, posix_to_win, process_wl_arg


def transform_args(args: List[str]) -> List[str]:
    """Transform MSYS2 compiler arguments for Zig CXX."""
    result: List[str] = []
    has_target = False

    for arg in args:
        if arg in ("-target", "--target") or arg.startswith(
            ("--target=", "-target=")
        ):
            has_target = True

        # std::filesystem is in libc++ on Windows, not separate libstdc++fs
        if arg == "-lstdc++fs":
            continue

        if arg.startswith("@"):
            rsp_path = posix_to_win(arg[1:])
            if os.path.isfile(rsp_path):
                try:
                    content = Path(rsp_path).read_text(
                        encoding="utf-8", errors="replace"
                    )
                    tokens = shlex.split(content, posix=False)
                    for tok in tokens:
                        result.extend(transform_args([tok]))
                    continue
                except Exception:
                    pass
            result.append("@" + rsp_path)
            continue

        if arg.startswith("-Wl,"):
            result.extend(process_wl_arg(arg))
        else:
            result.append(posix_to_win(arg))

    if not has_target:
        result = ["-target", "x86_64-windows-gnu"] + result

    for flag in (
        "-fno-sanitize=all",
        "-Wno-nullability-completeness",
        "-Wno-unused-command-line-argument",
        "-Wno-date-time",
    ):
        if flag not in result:
            result.append(flag)

    return result


def main() -> int:
    zig_cmd = find_zig_binary() + ["c++"]
    transformed = transform_args(sys.argv[1:])

    # If transformed command line exceeds Windows 30k limit, use temp rsp
    total_len = sum(len(a) + 1 for a in transformed)
    temp_rsp_path = None
    if total_len > 30000 and len(transformed) > 3:
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".rsp"
        ) as tmp:
            tmp.write("\n".join(f'"{a}"' for a in transformed))
            temp_rsp_path = tmp.name
        cmd = zig_cmd + [f"@{temp_rsp_path}"]
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
