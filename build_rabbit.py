# -----------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# -----------------------------------------------------------------------------

"""Build and package the rabbit MOOSE distribution.

Single entry point to build upstream MOOSE dependencies, compile RabbitApp
using the Zig / Clang compiler toolchain, stage relocatable libraries, build
standalone wheels, and run test verification across Linux, macOS, and Windows.
"""

import argparse
import os
from pathlib import Path
import sys

from scripts.build.common import (
    build_rabbit_binary,
    build_wheel,
    get_moose_dir,
    run_tests,
    stage_artifacts,
)


def setup_toolchain_wrappers(repo_dir: Path) -> tuple[Path, Path]:
    """Dispatch toolchain wrapper creation to OS-specific handler."""
    if sys.platform == "darwin":
        from scripts.build.darwin import setup_darwin_toolchain

        return setup_darwin_toolchain(repo_dir)
    elif sys.platform == "win32":
        # Windows uses PowerShell wrapper setup in install_dependencies_windows.ps1
        wrappers_dir = repo_dir / ".zig_wrappers"
        return wrappers_dir / "zig-cc", wrappers_dir / "zig-cxx"
    else:
        from scripts.build.linux import setup_linux_toolchain

        return setup_linux_toolchain(repo_dir)


def build_dependencies(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Dispatch dependency compilation to OS-specific handler."""
    if sys.platform == "darwin":
        from scripts.build.darwin import build_darwin_dependencies

        build_darwin_dependencies(
            repo_dir, moose_dir, zigcc_path, zigcxx_path
        )
    elif sys.platform == "win32":
        from scripts.build.windows import build_windows_dependencies

        jobs = int(os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4)))
        build_windows_dependencies(repo_dir, jobs=jobs)
    else:
        from scripts.build.linux import build_linux_dependencies

        build_linux_dependencies(
            repo_dir, moose_dir, zigcc_path, zigcxx_path
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line flags for build_rabbit."""
    parser = argparse.ArgumentParser(
        description="Unified build orchestrator for rabbit-fem."
    )
    parser.add_argument(
        "--moose",
        nargs="?",
        const="default",
        default=None,
        metavar="PATH",
        help=(
            "Clone and build upstream MOOSE dependencies "
            "(PETSc, libMesh, WASP). Optionally provide path to MOOSE."
        ),
    )
    parser.add_argument(
        "--setup-wrappers",
        action="store_true",
        help="Generate only the compiler wrapper toolchain scripts.",
    )
    parser.add_argument(
        "--wheel",
        action="store_true",
        help=(
            "Build the standalone Python wheel package in dist/ "
            "after staging."
        ),
    )
    parser.add_argument(
        "--wheel-only",
        action="store_true",
        help=(
            "Package existing staged artifacts into dist/*.whl "
            "without recompiling."
        ),
    )
    parser.add_argument(
        "--test",
        "--tests",
        dest="test",
        action="store_true",
        help="Run pytest simulation and relocatability test suite.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Execute full pipeline: MOOSE setup, rabbit build, "
            "staging, wheel, and tests."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Main build orchestration entry point."""
    args = parse_args()
    repo_dir = Path(__file__).resolve().parent

    # If only wheel packaging of existing staged artifacts was requested
    if args.wheel_only:
        build_wheel(repo_dir)
        if args.test:
            run_tests(repo_dir)
        return

    # If only tests requested
    if args.test and not (args.moose or args.wheel or args.all):
        run_tests(repo_dir)
        return

    # 1. Generate toolchain wrappers
    zigcc_path, zigcxx_path = setup_toolchain_wrappers(repo_dir)
    if args.setup_wrappers:
        print(f"Generated toolchain wrappers at {zigcc_path.parent}")
        return

    # Determine custom MOOSE path if passed
    custom_moose = None
    if args.moose and args.moose != "default":
        custom_moose = args.moose
    moose_dir = get_moose_dir(repo_dir, custom_moose)

    # 2. If --moose or --all requested, build MOOSE dependencies
    if args.moose is not None or args.all:
        build_dependencies(
            repo_dir, moose_dir, zigcc_path, zigcxx_path
        )
        if args.moose is not None and not args.all and not args.wheel:
            return

    # 3. Build and Stage Rabbit
    binary_path = build_rabbit_binary(
        repo_dir, moose_dir, zigcc_path, zigcxx_path
    )
    stage_artifacts(repo_dir, moose_dir, binary_path)

    # 4. Build wheel package if requested
    if args.wheel or args.all:
        build_wheel(repo_dir)

    # 5. Run test suite if requested
    if args.test or args.all:
        run_tests(repo_dir)

    print("Rabbit build pipeline completed successfully.")


if __name__ == "__main__":
    main()
