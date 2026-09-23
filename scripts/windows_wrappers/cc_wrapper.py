"""C compiler wrapper for Zig on Windows/MSYS2."""

import subprocess
import sys
from typing import List

from wrapper_utils import find_zig_binary, posix_to_win, process_wl_arg


def transform_args(args: List[str]) -> List[str]:
    """Transform MSYS2 compiler arguments for Zig CC."""
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

        if arg.startswith("-Wl,"):
            result.extend(process_wl_arg(arg))
        else:
            result.append(posix_to_win(arg))

    if not has_target:
        result = ["-target", "x86_64-windows-gnu"] + result

    return result


def main() -> int:
    zig_cmd = find_zig_binary() + ["cc"]
    transformed = transform_args(sys.argv[1:])
    completed = subprocess.run(zig_cmd + transformed)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
