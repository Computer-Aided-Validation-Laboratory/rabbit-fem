# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Command-line interface wrapper for rabbit MOOSE binary."""

import os
import sys
from pathlib import Path


def get_binary_path() -> Path:
    """Locate the packaged rabbit binary."""
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "bin" / "rabbit",
        base_dir / "bin" / "rabbit-opt",
        base_dir.parent.parent / "rabbit-opt",
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        "Rabbit executable not found. Please ensure rabbit-fem is built "
        "and installed properly."
    )


def get_library_dir() -> Path:
    """Locate the packaged shared libraries directory."""
    base_dir = Path(__file__).resolve().parent
    return base_dir / "lib"


def format_cli_args(raw_args: list[str]) -> list[str]:
    """Normalize CLI arguments, adding -i if a .i file is passed directly."""
    has_input_flag = any(arg in ("-i", "--input") for arg in raw_args)
    if has_input_flag:
        return raw_args

    formatted: list[str] = []
    input_handled = False
    for arg in raw_args:
        is_input = not arg.startswith("-") and arg.endswith(".i")
        if not input_handled and is_input:
            formatted.extend(["-i", arg])
            input_handled = True
        else:
            formatted.append(arg)
    return formatted


def main() -> None:
    """Run the rabbit application with forwarded CLI arguments."""
    try:
        bin_path = get_binary_path()
    except FileNotFoundError as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)

    lib_dir = get_library_dir()
    env = dict(os.environ)
    if lib_dir.is_dir():
        curr_ld = env.get("LD_LIBRARY_PATH", "")
        if curr_ld:
            env["LD_LIBRARY_PATH"] = f"{lib_dir}:{curr_ld}"
        else:
            env["LD_LIBRARY_PATH"] = str(lib_dir)

    processed_args = format_cli_args(sys.argv[1:])
    args = [str(bin_path)] + processed_args
    try:
        os.execvpe(str(bin_path), args, env)
    except OSError as err:
        sys.stderr.write(f"Failed to execute rabbit binary: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
