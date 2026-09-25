"""Windows-specific build and toolchain orchestration interface."""

from pathlib import Path
import subprocess
import sys

from .common import (
    ensure_moose_repo,
    ensure_moose_submodules,
    get_moose_dir,
)


def build_windows_stage(
    repo_dir: Path,
    stage: str = "all",
    jobs: int = 4,
    method: str = "opt",
) -> None:
    """Invoke Windows PowerShell setup for a specific stage."""
    moose_dir = get_moose_dir(repo_dir)
    ensure_moose_repo(repo_dir, moose_dir)
    ensure_moose_submodules(moose_dir)

    ps_script = repo_dir / "scripts" / "install_dependencies_windows.ps1"
    if not ps_script.is_file():
        raise FileNotFoundError(f"Script {ps_script} not found.")

    cmd = [
        "powershell.exe",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps_script),
        "-Stage",
        stage,
        "-Jobs",
        str(jobs),
        "-Method",
        method,
    ]
    subprocess.run(cmd, cwd=str(repo_dir), check=True)


def build_petsc(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build PETSc dependency on Windows."""
    build_windows_stage(repo_dir, stage="petsc")


def build_libmesh(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build libMesh dependency on Windows."""
    build_windows_stage(repo_dir, stage="libmesh")


def build_wasp(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build WASP and HIT parser on Windows."""
    build_windows_stage(repo_dir, stage="wasp")


def configure_moose(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Configure MOOSE framework on Windows."""
    build_windows_stage(repo_dir, stage="moose")


def build_windows_dependencies(
    repo_dir: Path,
    jobs: int = 4,
    method: str = "opt",
) -> None:
    """Invoke Windows PowerShell setup and dependency builder."""
    build_windows_stage(
        repo_dir,
        stage="all",
        jobs=jobs,
        method=method,
    )
