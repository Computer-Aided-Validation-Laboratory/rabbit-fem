# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Pin per-OS build environments so one OS cannot break another.

Each OS module owns its compiler selection and library search paths.
These tests lock that contract per RABBIT_MPI variant: editing the Linux
pipe must not change macOS behaviour and vice versa.
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build import darwin as darwin_mod
from build import linux as linux_mod


def _fake_wrappers(tmp_path: Path) -> tuple[Path, Path]:
    """Nonexistent-but-plausible wrapper paths (env builders need names)."""
    return tmp_path / "zigcc", tmp_path / "zigcxx"


def test_linux_mpi_uses_mpi_wrappers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux MPI builds compile through mpicc redirected at Zig."""
    monkeypatch.setenv("RABBIT_MPI", "1")
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = linux_mod.get_linux_tool_env(zigcc, zigcxx)
    assert env["CC"] == "mpicc"
    assert env["CXX"] == "mpicxx"
    assert env["OMPI_CC"] == str(zigcc)
    assert env["OMPI_CXX"] == str(zigcxx)


def test_linux_serial_bypasses_mpi_wrappers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux serial builds must never reference mpicc."""
    monkeypatch.delenv("RABBIT_MPI", raising=False)
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = linux_mod.get_linux_tool_env(zigcc, zigcxx)
    assert env["CC"] == str(zigcc)
    assert env["CXX"] == str(zigcxx)
    assert "OMPI_CC" not in env
    assert "OMPI_CXX" not in env
    assert "mpicc" not in env["CC"]
    assert "mpicxx" not in env["CXX"]


def test_darwin_mpi_keeps_hdf5_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """macOS MPI builds retain the Homebrew MPI/HDF5 search paths."""
    monkeypatch.setenv("RABBIT_MPI", "1")
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = darwin_mod.get_darwin_tool_env(zigcc, zigcxx)
    assert env["CC"] == "mpicc"
    assert env["HDF5_DIR"].endswith("opt/hdf5-mpi")
    assert "hdf5-mpi" in env["CMAKE_LIBRARY_PATH"]
    assert "hdf5-mpi" in env["CPATH"]


def test_darwin_serial_hides_mpi_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """macOS serial builds must not offer any MPI package for discovery.

    Regression protection for the CI failure where serial libMesh
    enabled parallel netCDF support after finding open-mpi headers, then
    compiled mpi.h into TUs that clash with the serial build.
    """
    monkeypatch.delenv("RABBIT_MPI", raising=False)
    for key in (
        "CMAKE_LIBRARY_PATH",
        "CMAKE_PREFIX_PATH",
        "LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "CPATH",
        "LDFLAGS",
        "CPPFLAGS",
    ):
        monkeypatch.delenv(key, raising=False)
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = darwin_mod.get_darwin_tool_env(zigcc, zigcxx)
    assert env["CC"] == str(zigcc)
    assert "HDF5_DIR" not in env
    for key in (
        "CMAKE_LIBRARY_PATH",
        "CMAKE_PREFIX_PATH",
        "LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "CPATH",
        "LDFLAGS",
        "CPPFLAGS",
    ):
        assert "hdf5-mpi" not in env[key], key
        assert "open-mpi" not in env[key], key
    # The bare brew prefix must not appear as a search entry either;
    # only the explicit compiler-support formulae stay.
    for key in ("LIBRARY_PATH", "CPATH", "LDFLAGS", "CPPFLAGS"):
        assert "/opt/homebrew/lib" not in env[key], key
        assert "/opt/homebrew/include" not in env[key], key


def test_linux_build_tools_pass_when_m4_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tool preflight passes when all gated tools resolve on PATH."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    linux_mod.check_build_tools()


def test_linux_build_tools_name_missing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tool preflight names the missing tool instead of a deep build error."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="m4"):
        linux_mod.check_build_tools()


def test_linux_build_tools_names_fortran_when_only_it_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing Fortran compiler must be named (module test plugins need it)."""
    import shutil

    def fake_which(name: str) -> str | None:
        return None if name == "gfortran" else f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    with pytest.raises(RuntimeError, match="gfortran"):
        linux_mod.check_build_tools()


def test_linux_xdr_probe_passes_when_headers_compile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The XDR preflight passes when the wrapper compiles <rpc/rpc.h>."""
    import subprocess

    zigcc, _ = _fake_wrappers(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert str(zigcc) in args[0][0]
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(linux_mod.subprocess, "run", fake_run)
    linux_mod.check_xdr_headers(zigcc)


def test_linux_xdr_probe_names_package_when_headers_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The XDR preflight fails early naming libtirpc-dev, not deep in configure."""
    import subprocess

    zigcc, _ = _fake_wrappers(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 1, "", "fatal error")

    monkeypatch.setattr(linux_mod.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="libtirpc-dev"):
        linux_mod.check_xdr_headers(zigcc)
