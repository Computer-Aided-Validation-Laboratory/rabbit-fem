#!/usr/bin/env python3
"""Build and package the rabbit MOOSE distribution.

Uses zig cc via ziglang as the compiler toolchain, compiles
RabbitApp, strips binaries, and stages minimal artifacts for wheel packaging.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


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


def get_moose_dir(repo_dir: Path) -> Path:
    """Locate MOOSE directory from environment or standard locations."""
    env_dir = os.environ.get("MOOSE_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()

    submodule_dir = repo_dir / "moose"
    if submodule_dir.is_dir() and (submodule_dir / "framework").is_dir():
        return submodule_dir.resolve()

    home_moose = Path.home() / "moose"
    if home_moose.is_dir():
        return home_moose.resolve()

    raise FileNotFoundError(
        "MOOSE directory not found. Please set MOOSE_DIR environment variable."
    )


def build_rabbit_binary(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> Path:
    """Compile RabbitApp and link rabbit-opt."""
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
        find_python_exe(), "-m", "ziglang", "c++",
        "-target", "x86_64-linux-gnu",
        "-O3",
        "-rdynamic",
        str(main_obj),
        "-o", str(output_bin),
        "-Wl,--no-as-needed",
        f"-L{repo_dir}/src/rabbit/lib",
        f"-L{repo_dir}/lib/.libs", "-lrabbit-opt",
        f"-L{moose_dir}/framework/.libs", "-lmoose-opt",
        f"-L{moose_dir}/modules/solid_mechanics/lib/.libs",
        "-lsolid_mechanics-opt",
        f"-L{moose_dir}/modules/heat_transfer/lib/.libs",
        "-lheat_transfer-opt",
        f"-L{moose_dir}/modules/contact/lib/.libs", "-lcontact-opt",
        f"-L{moose_dir}/modules/shifted_boundary_method/lib/.libs",
        "-lshifted_boundary_method-opt",
        f"-L{moose_dir}/modules/ray_tracing/lib/.libs", "-lray_tracing-opt",
        f"-L{moose_dir}/modules/module_loader/lib/.libs",
        f"-L{wasp_dir}/lib",
        "-lwaspcore", "-lwaspddi", "-lwaspexpr", "-lwasphalite",
        "-lwasphit", "-lwasphive", "-lwaspjson", "-lwasplsp",
        "-lwaspplot", "-lwaspsiren", "-lwaspson",
        f"-L{moose_dir}/framework/contrib/hit/.libs", "-lhit-opt",
        f"-L{libmesh_dir}/lib", "-lmesh_opt", "-ltimpi_opt",
        f"-L{petsc_dir}/lib", "-lpetsc",
        "-L/usr/lib/x86_64-linux-gnu/openmpi/lib", "-lmpi_cxx", "-lmpi",
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
                if soname.startswith(("libc.so", "libm.so", "libdl.so",
                                      "libpthread.so", "librt.so",
                                      "libstdc++.so", "libgcc_s.so",
                                      "libmpi.so", "libmpi_cxx.so",
                                      "libopen-pal.so", "libopen-rte.so",
                                      "libhwloc.so", "libevent",
                                      "libz.so", "libtirpc.so",
                                      "libgfortran.so", "libgomp.so",
                                      "libudev.so", "libkrb5", "libk5crypto",
                                      "libcom_err", "libcap.so", "libkeyutils",
                                      "libresolv.so", "libgssapi_krb5")):
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

    # Reset staging directories to remove obsolete / duplicate files
    if lib_target_dir.is_dir():
        shutil.rmtree(lib_target_dir)
    lib_target_dir.mkdir(parents=True, exist_ok=True)
    bin_target_dir.mkdir(parents=True, exist_ok=True)

    dest_bin = bin_target_dir / "rabbit"
    shutil.copy2(binary_path, dest_bin)
    dest_bin.chmod(0o755)

    # Build lookup map of all available .so files in moose and rabbit repos
    available_libs: dict[str, Path] = {}
    for search_root in [repo_dir, moose_dir]:
        for p in search_root.rglob("*.so*"):
            if p.is_file() and not p.name.endswith((".son", ".i")):
                available_libs[p.name] = p

    resolved_libs = find_needed_libraries(binary_path, available_libs)

    # Copy libomp if available
    omp_candidates = glob.glob("/opt/rocm-*/lib/llvm/lib-debug/libomp.so")
    if omp_candidates:
        resolved_libs["libomp.so"] = Path(omp_candidates[-1]).resolve()

    for soname, real_path in resolved_libs.items():
        dest = lib_target_dir / soname
        shutil.copy2(real_path, dest)

    # Strip debug symbols
    print("Stripping debug symbols from libraries and executable...")
    subprocess.run(["strip", "--strip-all", str(dest_bin)], check=False)
    for f in lib_target_dir.glob("*.so*"):
        if f.is_file():
            subprocess.run(["strip", "--strip-unneeded", str(f)], check=False)

    # Patch RPATHs with patchelf
    patchelf_bin = shutil.which("patchelf") or "patchelf"
    rpath_app = "$ORIGIN/../lib:/usr/lib/x86_64-linux-gnu/openmpi/lib"
    rpath_lib = "$ORIGIN:/usr/lib/x86_64-linux-gnu/openmpi/lib"

    subprocess.run(
        [patchelf_bin, "--set-rpath", rpath_app, str(dest_bin)],
        check=False,
    )
    for f in lib_target_dir.glob("*.so*"):
        if f.is_file():
            subprocess.run(
                [patchelf_bin, "--set-rpath", rpath_lib, str(f)],
                check=False,
            )

    print(
        f"Staged rabbit binary and {len(resolved_libs)} libraries "
        f"at {dest_bin}"
    )


def main() -> None:
    """Main build orchestration entry point."""
    repo_dir = Path(__file__).resolve().parent.parent
    zigcc_path, zigcxx_path = setup_zig_wrappers(repo_dir)

    if "--setup-wrappers" in sys.argv:
        print(f"Generated Zig CC wrappers at {zigcc_path.parent}")
        return

    moose_dir = get_moose_dir(repo_dir)
    binary_path = build_rabbit_binary(
        repo_dir, moose_dir, zigcc_path, zigcxx_path
    )
    stage_artifacts(repo_dir, moose_dir, binary_path)
    print("Rabbit build and staging completed successfully.")


if __name__ == "__main__":
    main()
