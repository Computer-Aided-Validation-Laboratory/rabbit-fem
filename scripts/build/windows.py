"""Windows-specific build and toolchain orchestration interface."""

from pathlib import Path
import subprocess
import sys


def build_windows_dependencies(
    repo_dir: Path,
    jobs: int = 4,
    method: str = "opt",
) -> None:
    """Invoke Windows PowerShell setup and dependency builder."""
    ps_script = repo_dir / "scripts" / "install_dependencies_windows.ps1"
    if not ps_script.is_file():
        raise FileNotFoundError(f"Script {ps_script} not found.")

    cmd = [
        "powershell.exe",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps_script),
        "-Jobs",
        str(jobs),
        "-Method",
        method,
    ]
    subprocess.run(cmd, cwd=str(repo_dir), check=True)
