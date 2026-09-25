"""Ranlib wrapper for Zig on Windows/MSYS2."""

import subprocess
import sys
from typing import List

from wrapper_utils import find_zig_binary, posix_to_win


def transform_ranlib_args(args: List[str]) -> List[str]:
    """Transform MSYS2 ranlib arguments to Windows paths."""
    return [posix_to_win(arg) for arg in args]


def main() -> int:
    zig_cmd = find_zig_binary() + ["ranlib"]
    transformed = transform_ranlib_args(sys.argv[1:])
    completed = subprocess.run(zig_cmd + transformed)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
