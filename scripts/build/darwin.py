"""macOS-specific build, Homebrew toolchain, and dependency logic."""

import glob
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .common import (
    ensure_moose_repo,
    ensure_moose_submodules,
)


def setup_darwin_toolchain(repo_dir: Path) -> tuple[Path, Path]:
    """Create wrapper scripts for Homebrew LLVM/clang toolchain on macOS."""
    wrapper_dir = repo_dir / ".zig_wrappers"
    wrapper_dir.mkdir(parents=True, exist_ok=True)

    zigcc_path = wrapper_dir / "zigcc"
    zigcxx_path = wrapper_dir / "zigcxx"

    llvm_clang = (
        sorted(glob.glob("/opt/homebrew/opt/llvm*/bin/clang"))
        + sorted(glob.glob("/usr/local/opt/llvm*/bin/clang"))
    )
    clang_candidates = (
        llvm_clang + ([shutil.which("clang")] if shutil.which("clang") else [])
    )
    clangxx_candidates = (
        [p.replace("clang", "clang++") for p in llvm_clang]
        + ([shutil.which("clang++")] if shutil.which("clang++") else [])
    )

    if not (clang_candidates and clangxx_candidates):
        raise RuntimeError("Clang compiler not found for macOS build.")

    c_compiler = clang_candidates[0]
    cxx_compiler = clangxx_candidates[0]

    cc_template = f"#!/bin/bash\nexec {c_compiler} \"$@\"\n"
    cxx_template = f"#!/bin/bash\nexec {cxx_compiler} \"$@\"\n"

    zigcc_path.write_text(cc_template)
    zigcxx_path.write_text(cxx_template)

    zigcc_path.chmod(0o755)
    zigcxx_path.chmod(0o755)

    return zigcc_path, zigcxx_path


def build_darwin_dependencies(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build PETSc, libMesh, WASP, and configure MOOSE on macOS."""
    jobs = os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4))
    print("=" * 60)
    print(f" Setting up MOOSE and dependencies (macOS) at: {moose_dir}")
    print(f" Parallel jobs: {jobs}")
    print("=" * 60)

    ensure_moose_repo(repo_dir, moose_dir)
    ensure_moose_submodules(moose_dir)

    tool_env = dict(os.environ)
    tool_env["OMPI_CC"] = str(zigcc_path)
    tool_env["OMPI_CXX"] = str(zigcxx_path)
    tool_env["CC"] = "mpicc"
    tool_env["CXX"] = "mpicxx"

    brew_prefix = (
        "/opt/homebrew" if Path("/opt/homebrew").is_dir() else "/usr/local"
    )
    llvm_prefix = f"{brew_prefix}/opt/llvm"
    omp_prefix = f"{brew_prefix}/opt/libomp"
    hdf5_prefix = f"{brew_prefix}/opt/hdf5-mpi"
    bison_prefix = f"{brew_prefix}/opt/bison"
    flex_prefix = f"{brew_prefix}/opt/flex"

    tool_env["HDF5_DIR"] = hdf5_prefix
    tool_env["PATH"] = (
        f"{bison_prefix}/bin:{flex_prefix}/bin:"
        f"{llvm_prefix}/bin:{brew_prefix}/bin:"
        + os.environ.get("PATH", "")
    )
    tool_env["CMAKE_LIBRARY_PATH"] = (
        f"{llvm_prefix}/lib:{omp_prefix}/lib:"
        f"{hdf5_prefix}/lib:{brew_prefix}/lib"
    )
    tool_env["CMAKE_PREFIX_PATH"] = (
        f"{llvm_prefix}:{omp_prefix}:{hdf5_prefix}:{brew_prefix}:"
        + os.environ.get("CMAKE_PREFIX_PATH", "")
    )
    tool_env["LIBRARY_PATH"] = (
        f"{llvm_prefix}/lib:{omp_prefix}/lib:"
        f"{hdf5_prefix}/lib:{brew_prefix}/lib:"
        + os.environ.get("LIBRARY_PATH", "")
    )
    tool_env["DYLD_LIBRARY_PATH"] = (
        f"{llvm_prefix}/lib:{omp_prefix}/lib:"
        f"{hdf5_prefix}/lib:{brew_prefix}/lib:"
        + os.environ.get("DYLD_LIBRARY_PATH", "")
    )
    tool_env["CPATH"] = (
        f"{llvm_prefix}/include:{omp_prefix}/include:"
        f"{hdf5_prefix}/include:{brew_prefix}/include:"
        + os.environ.get("CPATH", "")
    )
    ldflags = (
        f"-L{llvm_prefix}/lib -Wl,-rpath,{llvm_prefix}/lib "
        f"-L{omp_prefix}/lib -Wl,-rpath,{omp_prefix}/lib "
        f"-L{hdf5_prefix}/lib -Wl,-rpath,{hdf5_prefix}/lib "
        f"-L{brew_prefix}/lib "
        + os.environ.get("LDFLAGS", "")
    ).strip()
    tool_env["LDFLAGS"] = ldflags
    cppflags = (
        f"-I{llvm_prefix}/include -I{omp_prefix}/include "
        f"-I{hdf5_prefix}/include -I{brew_prefix}/include "
        + os.environ.get("CPPFLAGS", "")
    ).strip()
    tool_env["CPPFLAGS"] = cppflags

    # 1. Build PETSc (disabling unused GPU and heavy packages)
    print("--> Building PETSc...")
    petsc_env = dict(tool_env)
    petsc_env.pop("PETSC_DIR", None)
    petsc_env.pop("PETSC_ARCH", None)
    petsc_cmd = [
        "./scripts/update_and_rebuild_petsc.sh",
        "--skip-submodule-update",
        "--CXXOPTFLAGS=-O3",
        "--COPTFLAGS=-O3",
        "--FOPTFLAGS=-O3",
        "--download-strumpack=0",
        "--with-strumpack=0",
        "--download-kokkos=0",
        "--with-kokkos=0",
        "--download-kokkos-kernels=0",
        "--with-kokkos-kernels=0",
        "--download-libceed=0",
        "--with-libceed=0",
        "--download-umpire=0",
        "--with-umpire=0",
    ]
    subprocess.run(
        petsc_cmd,
        cwd=str(moose_dir),
        env=petsc_env,
        check=True,
    )

    # 2. Build libMesh
    print("--> Building libMesh with OpenMPI toolchain...")
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
    print(" MOOSE macOS dependencies built and configured successfully!")
    print("=" * 60)
