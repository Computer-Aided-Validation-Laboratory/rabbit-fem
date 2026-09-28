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
import subprocess
import sys
from pathlib import Path


def get_binary_path() -> Path:
    """Locate the packaged rabbit binary."""
    base_dir = Path(__file__).resolve().parent
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    candidates = [
        base_dir / "bin" / f"rabbit{exe_suffix}",
        base_dir / "bin" / f"rabbit-opt{exe_suffix}",
        base_dir.parent.parent / f"rabbit-opt{exe_suffix}",
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


def _variant_marker_path() -> Path:
    """Path of the build-variant marker written at staging time."""
    return Path(__file__).resolve().parent / "variant.txt"


def is_mpi_binary() -> bool:
    """Whether the packaged binary was built with MPI support.

    Reads the ``variant.txt`` marker written at staging time (``mpi`` or
    ``serial``). Wheels built before the marker existed predate the serial
    variant: those are MPI builds everywhere except Windows, which has
    always been serial.
    """
    try:
        marker = _variant_marker_path().read_text(encoding="utf-8")
    except OSError:
        return sys.platform != "win32"
    return marker.strip().lower() == "mpi"


def mpi_launch_size() -> int:
    """Number of MPI ranks in the current launch, or 1 when serial."""
    for var in ("OMPI_COMM_WORLD_SIZE", "PMI_SIZE"):
        try:
            size = int(os.environ.get(var, "1"))
        except ValueError:
            continue
        if size > 1:
            return size
    return 1


def format_cli_args(raw_args: list[str]) -> list[str]:
    """Normalize CLI arguments, adding -i if a .i file is passed directly."""
    has_input_flag = any(arg in ("-i", "--input") for arg in raw_args)
    if has_input_flag:
        formatted = list(raw_args)
    else:
        formatted = []
        input_handled = False
        for arg in raw_args:
            is_input = not arg.startswith("-") and arg.endswith(".i")
            if not input_handled and is_input:
                formatted.extend(["-i", arg])
                input_handled = True
            else:
                formatted.append(arg)

    info_flags = ("-h", "--help", "-v", "--version", "--docs", "--show-capabilities", "--registry")
    # Serial builds (PETSc MPIUNI) have no Hypre: the packaged .i files
    # request 'hypre boomeramg', so fall back to ILU unless overridden.
    if not is_mpi_binary() and not any(arg in info_flags for arg in raw_args) and not any("-pc_type" in arg for arg in formatted):
        formatted.extend(["-pc_type", "ilu"])

    return formatted


def main() -> None:
    """Run the rabbit application with forwarded CLI arguments."""
    try:
        bin_path = get_binary_path()
    except FileNotFoundError as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)

    size = mpi_launch_size()
    if size > 1 and not is_mpi_binary():
        sys.stderr.write(
            f"Error: launched with {size} MPI ranks but this rabbit "
            "binary is the serial/SMP build, which cannot run multi-rank "
            "jobs (ranks would silently compute independent serial "
            "solves). Install the MPI variant instead: "
            "pip install rabbit-fem-mpi\n"
        )
        sys.exit(2)

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
        if sys.platform == "win32":
            res = subprocess.run(args, env=env)
            sys.exit(res.returncode)
        else:
            os.execvpe(str(bin_path), args, env)
    except OSError as err:
        sys.stderr.write(f"Failed to execute rabbit binary: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
