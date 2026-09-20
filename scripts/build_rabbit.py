#!/usr/bin/env python3
"""Build and package the rabbit MOOSE distribution.

Uses zig cc via ziglang as the compiler toolchain, compiles
RabbitApp, strips binaries, and stages artifacts for wheel packaging.
"""

import glob
import os
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
        "-Wno-ignored-attributes -Wno-unused-command-line-argument"
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
        "    if [ \"$arg\" != \"-lstdc++\" ]; then\n"
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
        "    if [ \"$arg\" != \"-lstdc++\" ]; then\n"
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
    omp_lib = repo_dir / "src" / "rabbit" / "lib" / "libomp.so"
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
        f"-L{libmesh_dir}/lib", "-lmesh_opt", "-ltimpi_opt",
        f"-L{petsc_dir}/lib", "-lpetsc",
        "-L/usr/lib/x86_64-linux-gnu/openmpi/lib", "-lmpi_cxx", "-lmpi",
        "/usr/lib/x86_64-linux-gnu/libstdc++.so.6",
        str(omp_lib),
        "-Wl,--as-needed",
        "-Wl,--allow-shlib-undefined",
        "-Wl,-rpath,$ORIGIN/../lib",
        "-Wl,-rpath,/usr/lib/x86_64-linux-gnu/openmpi/lib",
    ]

    print("Linking rabbit-opt executable with zig toolchain...")
    subprocess.run(link_cmd, check=True)

    if not output_bin.is_file():
        raise FileNotFoundError(
            f"Expected binary {output_bin} was not built."
        )
    return output_bin


def stage_artifacts(
    repo_dir: Path,
    moose_dir: Path,
    binary_path: Path,
) -> None:
    """Stage executable and libraries into src/rabbit for packaging."""
    bin_target_dir = repo_dir / "src" / "rabbit" / "bin"
    lib_target_dir = repo_dir / "src" / "rabbit" / "lib"
    bin_target_dir.mkdir(parents=True, exist_ok=True)
    lib_target_dir.mkdir(parents=True, exist_ok=True)

    dest_bin = bin_target_dir / "rabbit"
    shutil.copy2(binary_path, dest_bin)
    dest_bin.chmod(0o755)

    # Collect shared libraries
    libmesh_dir = moose_dir / "libmesh" / "installed" / "lib"
    petsc_dir = moose_dir / "petsc" / "arch-moose" / "lib"
    wasp_dir = moose_dir / "framework" / "contrib" / "wasp" / "install" / "lib"

    so_sources: list[Path] = []
    so_sources.extend((repo_dir / "lib").rglob("*.so*"))
    so_sources.extend((moose_dir / "framework").rglob("*.so*"))

    active_modules = [
        "solid_mechanics",
        "heat_transfer",
        "contact",
        "shifted_boundary_method",
        "ray_tracing",
        "module_loader",
    ]
    for mod in active_modules:
        mod_lib = moose_dir / "modules" / mod / "lib"
        if mod_lib.is_dir():
            so_sources.extend(mod_lib.rglob("*.so*"))

    if libmesh_dir.is_dir():
        so_sources.extend(libmesh_dir.rglob("*.so*"))
    if petsc_dir.is_dir():
        so_sources.extend(petsc_dir.rglob("*.so*"))
    if wasp_dir.is_dir():
        so_sources.extend(wasp_dir.rglob("*.so*"))

    for f in so_sources:
        if f.suffix in [".son", ".i"] or not f.name.startswith("lib"):
            continue
        dest = lib_target_dir / f.name
        if f.is_file() and not f.is_symlink():
            shutil.copy2(f, dest)
        elif f.is_symlink():
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            try:
                dest.symlink_to(f.readlink())
            except Exception:
                pass

    # Bundle libomp if present
    omp_candidates = glob.glob("/opt/rocm-*/lib/llvm/lib-debug/libomp.so")
    if omp_candidates:
        shutil.copy2(omp_candidates[-1], lib_target_dir / "libomp.so")

    # Strip libraries and executable
    print("Stripping debug symbols from libraries and executable...")
    subprocess.run(["strip", "--strip-all", str(dest_bin)], check=False)
    for f in lib_target_dir.glob("*.so*"):
        if f.is_file() and not f.is_symlink() and f.name.startswith("lib"):
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
        if f.is_file() and not f.is_symlink() and f.name.startswith("lib"):
            subprocess.run(
                [patchelf_bin, "--set-rpath", rpath_lib, str(f)],
                check=False,
            )

    print(f"Staged rabbit binary at {dest_bin}")


def main() -> None:
    """Main build orchestration entry point."""
    repo_dir = Path(__file__).resolve().parent.parent
    zigcc_path, zigcxx_path = setup_zig_wrappers(repo_dir)

    moose_dir = get_moose_dir(repo_dir)
    binary_path = build_rabbit_binary(
        repo_dir, moose_dir, zigcc_path, zigcxx_path
    )
    stage_artifacts(repo_dir, moose_dir, binary_path)
    print("Rabbit build and staging completed successfully.")


if __name__ == "__main__":
    main()
