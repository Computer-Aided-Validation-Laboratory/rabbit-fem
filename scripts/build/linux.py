"""Linux-specific build, toolchain configuration, and dependency logic."""

import glob
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .common import (
    ensure_moose_repo,
    ensure_moose_submodules,
    find_python_exe,
)


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


def setup_linux_toolchain(repo_dir: Path) -> tuple[Path, Path]:
    """Create wrapper scripts for zig cc / clang toolchain on Linux."""
    wrapper_dir = repo_dir / ".zig_wrappers"
    wrapper_dir.mkdir(parents=True, exist_ok=True)

    zigcc_path = wrapper_dir / "zigcc"
    zigcxx_path = wrapper_dir / "zigcxx"

    clang_candidates = (
        [shutil.which("clang")] if shutil.which("clang") else []
    ) + sorted(glob.glob("/opt/rocm-*/lib/llvm/bin/clang"))
    clangxx_candidates = (
        [shutil.which("clang++")] if shutil.which("clang++") else []
    ) + sorted(glob.glob("/opt/rocm-*/lib/llvm/bin/clang++"))

    if clang_candidates and clangxx_candidates:
        c_compiler = clang_candidates[0]
        cxx_compiler = clangxx_candidates[0]
        cc_template = (
            "#!/bin/bash\n"
            f"exec {c_compiler} \"$@\"\n"
        )
        cxx_template = (
            "#!/bin/bash\n"
            f"exec {cxx_compiler} \"$@\"\n"
        )
    else:
        py_exe = find_python_exe()
        inc_flags = " ".join(detect_system_include_flags(wrapper_dir))
        warn_flags = (
            "-Wno-date-time -Wno-error=date-time "
            "-Wno-ignored-attributes -Wno-unused-command-line-argument "
            "-fno-sanitize=all"
        )
        omp_candidates = (
            glob.glob("/opt/rocm-*/lib/llvm/lib/libomp.so")
            + glob.glob("/opt/rocm-*/lib/llvm/lib-debug/libomp.so")
            + glob.glob("/usr/lib/llvm-*/lib/libomp.so")
        )
        omp_link_flag = (
            f"-x none {omp_candidates[0]}" if omp_candidates else ""
        )

        cc_template = (
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
            f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ "
            f"{inc_flags} "
            "\"${filtered_args[@]}\" "
            f"{warn_flags}\n"
            "else\n"
            f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ "
            f"{inc_flags} "
            + '"${filtered_args[@]}" $extra_link '
            + f"{omp_link_flag} "
            "-Wl,--allow-shlib-undefined "
            f"{warn_flags}\n"
            "fi\n"
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
            f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ "
            f"{inc_flags} "
            "\"${filtered_args[@]}\" "
            f"{warn_flags}\n"
            "else\n"
            f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ "
            f"{inc_flags} "
            + '"${filtered_args[@]}" $extra_link -x none '
            + "/usr/lib/x86_64-linux-gnu/libstdc++.so.6 "
            "/usr/lib/x86_64-linux-gnu/libgcc_s.so.1 "
            f"{omp_link_flag} "
            f"-Wl,--allow-shlib-undefined {warn_flags}\n"
            "fi\n"
        )

    zigcc_path.write_text(cc_template)
    zigcxx_path.write_text(cxx_template)

    zigcc_path.chmod(0o755)
    zigcxx_path.chmod(0o755)

    return zigcc_path, zigcxx_path


def build_linux_dependencies(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build PETSc, libMesh, WASP, and configure MOOSE on Linux."""
    jobs = os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4))
    print("=" * 60)
    print(f" Setting up MOOSE and dependencies (Linux) at: {moose_dir}")
    print(f" Parallel jobs: {jobs}")
    print("=" * 60)

    ensure_moose_repo(repo_dir, moose_dir)
    ensure_moose_submodules(moose_dir)

    tool_env = dict(os.environ)
    tool_env["OMPI_CC"] = str(zigcc_path)
    tool_env["OMPI_CXX"] = str(zigcxx_path)
    tool_env["CC"] = "mpicc"
    tool_env["CXX"] = "mpicxx"
    tool_env["CMAKE_LIBRARY_PATH"] = "/usr/lib/x86_64-linux-gnu"
    tool_env["CMAKE_PREFIX_PATH"] = (
        "/usr/lib/x86_64-linux-gnu:"
        + os.environ.get("CMAKE_PREFIX_PATH", "")
    )
    tool_env["LIBRARY_PATH"] = (
        "/usr/lib/x86_64-linux-gnu:"
        + os.environ.get("LIBRARY_PATH", "")
    )

    # 1. Build PETSc
    print("--> Building PETSc...")
    petsc_env = dict(tool_env)
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
    print("--> Building libMesh with Zig toolchain...")
    libmesh_env = dict(tool_env)
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
        env=tool_env,
        check=True,
    )

    # 4. Configure MOOSE
    print("--> Configuring MOOSE...")
    subprocess.run(
        ["./configure", "--with-derivative-size=89"],
        cwd=str(moose_dir),
        env=tool_env,
        check=True,
    )

    print("=" * 60)
    print(" MOOSE Linux dependencies built and configured successfully!")
    print("=" * 60)
