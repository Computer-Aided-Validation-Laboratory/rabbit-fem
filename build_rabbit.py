# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Build and package the rabbit MOOSE distribution.

Single entry point to build upstream MOOSE dependencies, compile RabbitApp
using the Zig compiler toolchain, stage relocatable libraries, build standalone
wheels, and run test verification.
"""

import argparse
import glob
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def find_python_exe() -> str:
    """Return the current python executable path."""
    return sys.executable


def detect_system_include_flags(wrapper_dir: Path) -> list[str]:
    """Detect system GCC libstdc++ and OpenMP include paths with idirafter."""
    flags: list[str] = ["-nostdinc++"]

    cxx_dirs = sorted(glob.glob("/usr/include/c++/*"))
    if cxx_dirs:
        latest_cxx = cxx_dirs[-1]
        cxx_ver = Path(latest_cxx).name
        flags.append(f"-I{latest_cxx}")

        arch_cxx = f"/usr/include/x86_64-linux-gnu/c++/{cxx_ver}"
        if Path(arch_cxx).is_dir():
            flags.append(f"-I{arch_cxx}")

        backward_cxx = f"{latest_cxx}/backward"
        if Path(backward_cxx).is_dir():
            flags.append(f"-I{backward_cxx}")

    # OpenMP header isolation
    inc_dir = wrapper_dir / "include"
    inc_dir.mkdir(parents=True, exist_ok=True)
    omp_candidates = glob.glob(
        "/usr/lib/gcc/x86_64-linux-gnu/*/include/omp.h"
    )
    if omp_candidates:
        omp_target = inc_dir / "omp.h"
        if not omp_target.exists():
            shutil.copy2(omp_candidates[-1], omp_target)
        flags.append(f"-I{inc_dir}")

    flags.append("-idirafter /usr/include")
    flags.append("-idirafter /usr/include/x86_64-linux-gnu")
    return flags


def setup_zig_wrappers(repo_dir: Path) -> tuple[Path, Path]:
    """Create wrapper scripts for zig cc using ziglang without libcxx."""
    wrapper_dir = repo_dir / ".zig_wrappers"
    wrapper_dir.mkdir(parents=True, exist_ok=True)

    py_exe = find_python_exe()
    inc_flags = " ".join(detect_system_include_flags(wrapper_dir))
    warn_flags = (
        "-Wno-date-time -Wno-error=date-time "
        "-Wno-ignored-attributes -Wno-unused-command-line-argument "
        "-fno-sanitize=all"
    )

    zigcc_path = wrapper_dir / "zigcc"
    zigcxx_path = wrapper_dir / "zigcxx"

    cc_template = (
        "#!/bin/bash\n"
        "extra_link=\"\"\n"
        "filtered_args=()\n"
        "for arg in \"$@\"; do\n"
        "    if [ \"$arg\" = \"-shared\" ]; then\n"
        "        extra_link=\"-nostartfiles\"\n"
        "    fi\n"
        "    if [ \"$arg\" != \"-lstdc++\" ] && "
        "[ \"$arg\" != \"-lstdc++fs\" ]; then\n"
        "        filtered_args+=(\"$arg\")\n"
        "    fi\n"
        "done\n"
        f"exec {py_exe} -m ziglang cc -stdlib=libstdc++ {inc_flags} "
        "\"${filtered_args[@]}\" $extra_link -Wl,--allow-shlib-undefined "
        f"{warn_flags}\n"
    )

    cxx_template = (
        "#!/bin/bash\n"
        "is_compile=0\n"
        "extra_link=\"\"\n"
        "filtered_args=()\n"
        "for arg in \"$@\"; do\n"
        "    if [ \"$arg\" = \"-c\" ] || [ \"$arg\" = \"-E\" ] || "
        "[ \"$arg\" = \"-S\" ]; then\n"
        "        is_compile=1\n"
        "    fi\n"
        "    if [ \"$arg\" = \"-shared\" ]; then\n"
        "        extra_link=\"-nostartfiles\"\n"
        "    fi\n"
        "    if [ \"$arg\" != \"-lstdc++\" ] && "
        "[ \"$arg\" != \"-lstdc++fs\" ]; then\n"
        "        filtered_args+=(\"$arg\")\n"
        "    fi\n"
        "done\n"
        "if [ \"$is_compile\" -eq 1 ]; then\n"
        f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ {inc_flags} "
        "\"${filtered_args[@]}\" "
        f"{warn_flags}\n"
        "else\n"
        f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ {inc_flags} "
        "\"${filtered_args[@]}\" $extra_link "
        "/usr/lib/x86_64-linux-gnu/libstdc++.so.6 "
        "/usr/lib/x86_64-linux-gnu/libgcc_s.so.1 "
        f"-Wl,--allow-shlib-undefined {warn_flags}\n"
        "fi\n"
    )

    zigcc_path.write_text(cc_template)
    zigcxx_path.write_text(cxx_template)

    zigcc_path.chmod(0o755)
    zigcxx_path.chmod(0o755)

    return zigcc_path, zigcxx_path


def get_moose_dir(
    repo_dir: Path, custom_path: str | None = None
) -> Path:
    """Locate MOOSE directory from argument, local repo, env, or home."""
    if custom_path:
        return Path(custom_path).expanduser().resolve()

    local_moose = repo_dir / "moose"
    if local_moose.is_dir() and (local_moose / "framework").is_dir():
        return local_moose.resolve()

    env_dir = os.environ.get("MOOSE_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()

    return (repo_dir / "moose").resolve()



def build_moose_dependencies(moose_dir: Path) -> None:
    """Clone upstream MOOSE (if missing) and compile PETSc, libMesh, WASP."""
    jobs = os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4))
    print("=" * 60)
    print(f" Setting up MOOSE and dependencies at: {moose_dir}")
    print(f" Parallel jobs: {jobs}")
    print("=" * 60)

    if not moose_dir.is_dir():
        print("Cloning upstream MOOSE repository...")
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/idaholab/moose.git",
                str(moose_dir),
            ],
            check=True,
        )
    else:
        print(f"MOOSE repository found at {moose_dir}")

    # 1. Build PETSc
    print("--> Building PETSc...")
    petsc_env = dict(os.environ)
    petsc_env.pop("PETSC_DIR", None)
    petsc_env.pop("PETSC_ARCH", None)
    subprocess.run(
        [
            "./scripts/update_and_rebuild_petsc.sh",
            "--skip-submodule-update",
            "--CXXOPTFLAGS=-O3",
            "--COPTFLAGS=-O3",
            "--FOPTFLAGS=-O3",
        ],
        cwd=str(moose_dir),
        env=petsc_env,
        check=True,
    )

    # 2. Build libMesh
    print("--> Building libMesh...")
    libmesh_env = dict(os.environ)
    libmesh_env["METHODS"] = "opt"
    subprocess.run(
        [
            "./scripts/update_and_rebuild_libmesh.sh",
            "--with-mpi",
        ],
        cwd=str(moose_dir),
        env=libmesh_env,
        check=True,
    )

    # 3. Build WASP
    print("--> Building WASP parser...")
    subprocess.run(
        ["./scripts/update_and_rebuild_wasp.sh"],
        cwd=str(moose_dir),
        check=True,
    )

    # 4. Configure MOOSE
    print("--> Configuring MOOSE...")
    subprocess.run(
        ["./configure", "--with-derivative-size=89"],
        cwd=str(moose_dir),
        check=True,
    )

    print("=" * 60)
    print(" MOOSE dependencies built and configured successfully!")
    print("=" * 60)


def build_rabbit_binary(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> Path:
    """Compile RabbitApp and link rabbit-opt."""
    if not moose_dir.is_dir():
        raise FileNotFoundError(
            f"MOOSE directory {moose_dir} does not exist. "
            "Run with --moose first."
        )


    env = dict(os.environ)
    env["PATH"] = f"{repo_dir / '.venv' / 'bin'}:{env.get('PATH', '')}"
    env["PYTHONNOUSERSITE"] = "1"
    env["MOOSE_DIR"] = str(moose_dir)
    env["METHODS"] = "opt"
    env["OMPI_CC"] = str(zigcc_path)
    env["OMPI_CXX"] = str(zigcxx_path)
    env["CC"] = "mpicc"
    env["CXX"] = "mpicxx"

    jobs = os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4))
    cmd = ["make", f"-j{jobs}"]

    print(f"Building RabbitApp with MOOSE_DIR={moose_dir} ({jobs} jobs)...")
    subprocess.run(cmd, cwd=str(repo_dir), env=env, check=True)

    main_obj = repo_dir / "src" / ".libs" / "main.x86_64-pc-linux-gnu.opt.o"
    if not main_obj.is_file():
        main_obj = repo_dir / "src" / "main.x86_64-pc-linux-gnu.opt.o"

    libmesh_dir = moose_dir / "libmesh" / "installed"
    petsc_dir = moose_dir / "petsc" / "arch-moose"
    wasp_dir = moose_dir / "framework" / "contrib" / "wasp" / "install"

    output_bin = repo_dir / "rabbit-opt"

    omp_lib = ""
    omp_candidates = glob.glob("/opt/rocm-*/lib/llvm/lib-debug/libomp.so")
    if omp_candidates:
        omp_lib = omp_candidates[-1]
    elif (repo_dir / "src" / "rabbit" / "lib" / "libomp.so").is_file():
        omp_lib = str(repo_dir / "src" / "rabbit" / "lib" / "libomp.so")

    link_cmd = [
        find_python_exe(),
        "-m",
        "ziglang",
        "c++",
        "-target",
        "x86_64-linux-gnu",
        "-O3",
        "-rdynamic",
        str(main_obj),
        "-o",
        str(output_bin),
        "-Wl,--no-as-needed",
        f"-L{repo_dir}/src/rabbit/lib",
        f"-L{repo_dir}/lib/.libs",
        "-lrabbit-opt",
        f"-L{moose_dir}/framework/.libs",
        "-lmoose-opt",
        f"-L{moose_dir}/modules/solid_mechanics/lib/.libs",
        "-lsolid_mechanics-opt",
        f"-L{moose_dir}/modules/heat_transfer/lib/.libs",
        "-lheat_transfer-opt",
        f"-L{moose_dir}/modules/contact/lib/.libs",
        "-lcontact-opt",
        f"-L{moose_dir}/modules/shifted_boundary_method/lib/.libs",
        "-lshifted_boundary_method-opt",
        f"-L{moose_dir}/modules/ray_tracing/lib/.libs",
        "-lray_tracing-opt",
        f"-L{moose_dir}/modules/module_loader/lib/.libs",
        f"-L{wasp_dir}/lib",
        "-lwaspcore",
        "-lwaspddi",
        "-lwaspexpr",
        "-lwasphalite",
        "-lwasphit",
        "-lwasphive",
        "-lwaspjson",
        "-lwasplsp",
        "-lwaspplot",
        "-lwaspsiren",
        "-lwaspson",
        f"-L{moose_dir}/framework/contrib/hit/.libs",
        "-lhit-opt",
        f"-L{libmesh_dir}/lib",
        "-lmesh_opt",
        "-ltimpi_opt",
        f"-L{petsc_dir}/lib",
        "-lpetsc",
        "-L/usr/lib/x86_64-linux-gnu/openmpi/lib",
        "-lmpi_cxx",
        "-lmpi",
        "/usr/lib/x86_64-linux-gnu/libstdc++.so.6",
    ]
    if omp_lib:
        link_cmd.append(omp_lib)

    link_cmd.extend([
        "-Wl,--as-needed",
        "-Wl,--allow-shlib-undefined",
        "-Wl,-rpath,$ORIGIN/../lib",
        "-Wl,-rpath,/usr/lib/x86_64-linux-gnu/openmpi/lib",
    ])

    print("Linking rabbit-opt executable with zig toolchain...")
    subprocess.run(link_cmd, check=True)

    if not output_bin.is_file():
        raise FileNotFoundError(
            f"Expected binary {output_bin} was not built."
        )
    return output_bin


def find_needed_libraries(
    binary_path: Path,
    available_libs: dict[str, Path],
) -> dict[str, Path]:
    """Find all needed sonames and map them to their concrete file paths."""
    resolved_libs: dict[str, Path] = {}
    queue: list[Path] = [binary_path]
    visited_binaries: set[Path] = set()

    system_prefixes = (
        "libc.so",
        "libm.so",
        "libdl.so",
        "libpthread.so",
        "librt.so",
        "libstdc++.so",
        "libgcc_s.so",
        "libmpi.so",
        "libmpi_cxx.so",
        "libopen-pal.so",
        "libopen-rte.so",
        "libhwloc.so",
        "libevent",
        "libz.so",
        "libtirpc.so",
        "libgfortran.so",
        "libgomp.so",
        "libudev.so",
        "libkrb5",
        "libk5crypto",
        "libcom_err",
        "libcap.so",
        "libkeyutils",
        "libresolv.so",
        "libgssapi_krb5",
    )

    while queue:
        current = queue.pop(0)
        if current in visited_binaries:
            continue
        visited_binaries.add(current)

        try:
            cmd = ["readelf", "-d", str(current)]
            res = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            for line in res.stdout.splitlines():
                if "NEEDED" not in line:
                    continue
                match = re.search(r"\[(.*)\]", line)
                if not match:
                    continue
                soname = match.group(1)
                if soname.startswith(system_prefixes):
                    continue

                if soname not in resolved_libs:
                    if soname in available_libs:
                        real_path = available_libs[soname].resolve()
                        resolved_libs[soname] = real_path
                        queue.append(real_path)
        except Exception:
            pass

    return resolved_libs


def stage_artifacts(
    repo_dir: Path,
    moose_dir: Path,
    binary_path: Path,
) -> None:
    """Stage executable and minimal shared libraries into src/rabbit."""
    bin_target_dir = repo_dir / "src" / "rabbit" / "bin"
    lib_target_dir = repo_dir / "src" / "rabbit" / "lib"

    if lib_target_dir.is_dir():
        shutil.rmtree(lib_target_dir)
    lib_target_dir.mkdir(parents=True, exist_ok=True)
    bin_target_dir.mkdir(parents=True, exist_ok=True)

    dest_bin = bin_target_dir / "rabbit"
    shutil.copy2(binary_path, dest_bin)
    dest_bin.chmod(0o755)

    available_libs: dict[str, Path] = {}
    for search_root in [repo_dir, moose_dir]:
        for p in search_root.rglob("*.so*"):
            if p.is_file() and not p.name.endswith((".son", ".i")):
                available_libs[p.name] = p

    resolved_libs = find_needed_libraries(binary_path, available_libs)

    omp_candidates = glob.glob("/opt/rocm-*/lib/llvm/lib-debug/libomp.so")
    if omp_candidates:
        resolved_libs["libomp.so"] = Path(omp_candidates[-1]).resolve()

    for soname, real_path in resolved_libs.items():
        dest = lib_target_dir / soname
        shutil.copy2(real_path, dest)

    print("Stripping debug symbols from libraries and executable...")
    subprocess.run(["strip", "--strip-all", str(dest_bin)], check=False)
    for f in lib_target_dir.glob("*.so*"):
        if f.is_file():
            subprocess.run(["strip", "--strip-unneeded", str(f)], check=False)

    patchelf_bin = "patchelf"
    for cand in (
        shutil.which("patchelf"),
        Path(sys.prefix) / "bin" / "patchelf",
        repo_dir / ".venv" / "bin" / "patchelf",
    ):
        if cand and Path(cand).is_file():
            patchelf_bin = str(cand)
            break

    rpath_app = "$ORIGIN/../lib:/usr/lib/x86_64-linux-gnu/openmpi/lib"
    rpath_lib = "$ORIGIN:/usr/lib/x86_64-linux-gnu/openmpi/lib"

    subprocess.run(
        [patchelf_bin, "--set-rpath", rpath_app, str(dest_bin)],
        check=True,
    )
    for f in lib_target_dir.glob("*.so*"):
        if f.is_file():
            subprocess.run(
                [patchelf_bin, "--set-rpath", rpath_lib, str(f)],
                check=True,
            )


    print(
        f"Staged rabbit binary and {len(resolved_libs)} libraries "
        f"at {dest_bin}"
    )


def build_wheel(repo_dir: Path) -> Path:
    """Build standalone Python wheel package and tag as manylinux."""
    print("--> Building standalone wheel package...")
    uv_bin = shutil.which("uv")
    if uv_bin:
        cmd = ["uv", "build", "--wheel"]
    else:
        cmd = [find_python_exe(), "-m", "build", "--wheel"]

    subprocess.run(cmd, cwd=str(repo_dir), check=True)
    dist_dir = repo_dir / "dist"
    wheels = sorted(dist_dir.glob("*.whl"), key=os.path.getmtime)
    if not wheels:
        raise FileNotFoundError("No .whl package generated in dist/")
    raw_whl = wheels[-1]

    # Retag from py3-none-any to manylinux platform tag
    if "none-any" in raw_whl.name:
        platform_tag = (
            "manylinux_2_35_x86_64.manylinux_2_38_x86_64.linux_x86_64"
        )
        print(f"--> Retagging wheel for Linux platform: {platform_tag}")
        wheel_bin = shutil.which("wheel") or str(
            repo_dir / ".venv" / "bin" / "wheel"
        )
        subprocess.run(
            [
                wheel_bin,
                "tags",
                f"--platform-tag={platform_tag}",
                "--remove",
                str(raw_whl),
            ],
            check=True,
        )
        wheels = sorted(dist_dir.glob("*.whl"), key=os.path.getmtime)
        latest_whl = wheels[-1]
    else:
        latest_whl = raw_whl

    size_mb = latest_whl.stat().st_size / (1024 * 1024)
    print(f"Wheel package ready: {latest_whl.name} ({size_mb:.2f} MB)")
    return latest_whl



def run_tests(repo_dir: Path) -> None:
    """Run pytest suite against staged package."""
    print("--> Running pytest suite...")
    subprocess.run(
        [find_python_exe(), "-m", "pytest", "test/test_simulations.py", "-v"],
        cwd=str(repo_dir),
        check=True,
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
        help="Generate only the zig cc wrapper toolchain scripts.",
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
    zigcc_path, zigcxx_path = setup_zig_wrappers(repo_dir)
    if args.setup_wrappers:
        print(f"Generated Zig CC wrappers at {zigcc_path.parent}")
        return

    # Determine custom MOOSE path if passed
    custom_moose = None
    if args.moose and args.moose != "default":
        custom_moose = args.moose
    moose_dir = get_moose_dir(repo_dir, custom_moose)

    # 2. If --moose or --all requested, build MOOSE dependencies
    if args.moose is not None or args.all:
        build_moose_dependencies(moose_dir)
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
