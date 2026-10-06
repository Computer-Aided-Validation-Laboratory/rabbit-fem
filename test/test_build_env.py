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
    monkeypatch.delenv("RABBIT_MPI_IMPL", raising=False)
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = linux_mod.get_linux_tool_env(zigcc, zigcxx)
    assert env["CC"] == "mpicc"
    assert env["CXX"] == "mpicxx"
    assert env["OMPI_CC"] == str(zigcc)
    assert env["OMPI_CXX"] == str(zigcxx)


def test_linux_mpich_uses_suffixed_wrappers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MPICH builds select explicit .mpich wrappers (alternatives-proof)."""
    from build.common import mpi_fortran_wrapper, mpi_impl

    monkeypatch.setenv("RABBIT_MPI", "1")
    monkeypatch.setenv("RABBIT_MPI_IMPL", "mpich")
    assert mpi_impl() == "mpich"
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = linux_mod.get_linux_tool_env(zigcc, zigcxx)
    assert env["CC"] == "mpicc.mpich"
    assert env["CXX"] == "mpicxx.mpich"
    assert env["MPICH_CC"] == str(zigcc)
    assert env["MPICH_CXX"] == str(zigcxx)
    assert "OMPI_CC" not in env
    assert "OMPI_CXX" not in env
    assert mpi_fortran_wrapper() == "mpif90.mpich"


def test_linux_mpich_defaults_ucx_without_infiniband(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MPICH builds avoid UCX/IB probing unless the caller opts in.

    Regression protection for the CI failure where MFEM's FindPETSc
    try_run aborted in MPI_Init (UCX ibv_create_srq failed) on runners
    without working InfiniBand: Ubuntu MPICH is ch4:ucx, and the probe
    failure depends on runner hardware.
    """
    monkeypatch.setenv("RABBIT_MPI", "1")
    monkeypatch.setenv("RABBIT_MPI_IMPL", "mpich")
    monkeypatch.delenv("UCX_TLS", raising=False)
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = linux_mod.get_linux_tool_env(zigcc, zigcxx)
    assert env["UCX_TLS"] == "tcp,self,sm"


def test_linux_mpich_respects_caller_ucx_tls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit UCX_TLS (e.g. multi-node IB users) always wins."""
    monkeypatch.setenv("RABBIT_MPI", "1")
    monkeypatch.setenv("RABBIT_MPI_IMPL", "mpich")
    monkeypatch.setenv("UCX_TLS", "ib")
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = linux_mod.get_linux_tool_env(zigcc, zigcxx)
    assert env["UCX_TLS"] == "ib"


def test_linux_openmpi_leaves_ucx_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The UCX default is MPICH-only; OpenMPI behavior is untouched."""
    monkeypatch.setenv("RABBIT_MPI", "1")
    monkeypatch.delenv("RABBIT_MPI_IMPL", raising=False)
    monkeypatch.delenv("UCX_TLS", raising=False)
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    env = linux_mod.get_linux_tool_env(zigcc, zigcxx)
    assert "UCX_TLS" not in env


def test_mpi_impl_defaults_openmpi_and_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset impl means OpenMPI; garbage fails early, not deep in CMake."""
    from build.common import mpi_fortran_wrapper, mpi_impl

    monkeypatch.delenv("RABBIT_MPI_IMPL", raising=False)
    assert mpi_impl() == "openmpi"
    monkeypatch.delenv("RABBIT_MPI", raising=False)
    assert mpi_fortran_wrapper() == "mpif90"
    monkeypatch.setenv("RABBIT_MPI_IMPL", "bogus-mpi")
    with pytest.raises(RuntimeError, match="RABBIT_MPI_IMPL"):
        mpi_impl()


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


def test_linux_build_tools_pass_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tool preflight passes when all gated tools resolve on PATH."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    linux_mod.check_build_tools()


def test_linux_build_tools_name_missing_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tool preflight names missing tools instead of deep build errors."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="m4"):
        linux_mod.check_build_tools()


def test_linux_build_tools_names_fortran_when_only_it_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing Fortran compiler must be named (test plugins need it)."""
    import shutil

    def fake_which(name: str) -> str | None:
        return None if name == "gfortran" else f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    with pytest.raises(RuntimeError, match="gfortran"):
        linux_mod.check_build_tools()


def test_linux_build_tools_serial_ignores_flex_bison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serial builds must not require flex/bison (MPI-only PETSc need)."""
    import shutil

    def fake_which(name: str) -> str | None:
        return None if name in ("flex", "bison") else f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    linux_mod.check_build_tools(mpi=False)


def test_linux_build_tools_mpi_requires_flex_bison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MPI builds fail early naming flex/bison (PTScotch needs them)."""
    import shutil

    def fake_which(name: str) -> str | None:
        return None if name in ("flex", "bison") else f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", fake_which)
    with pytest.raises(RuntimeError, match="flex"):
        linux_mod.check_build_tools(mpi=True)


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


def test_linux_xdr_probe_falls_back_to_system_tirpc_include(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The XDR preflight accepts Debian/Ubuntu libtirpc-dev layout.

    Regression for the Linux CI failure where the bare
    ``#include <rpc/rpc.h>`` probe failed despite ``libtirpc-dev`` being
    installed: on Debian/Ubuntu the headers live under
    ``/usr/include/tirpc`` (libMesh's own configure tries
    ``-I/usr/include/tirpc``), so the preflight must try it too instead
    of rejecting a healthy machine.
    """
    import subprocess

    zigcc, _ = _fake_wrappers(tmp_path)
    calls: list[list[str]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = list(args[0])
        calls.append(cmd)
        if "-I/usr/include/tirpc" in cmd:
            return subprocess.CompletedProcess(args[0], 0, "", "")
        return subprocess.CompletedProcess(args[0], 1, "", "fatal error")

    monkeypatch.setattr(linux_mod.subprocess, "run", fake_run)
    # Deterministic candidates: exercise the probe loop without any
    # filesystem dependence (no Path.is_dir mock, which is a
    # `/` vs `\` portability trap on Windows).
    monkeypatch.setattr(
        linux_mod, "_xdr_include_candidates", lambda: [[], ["-I/usr/include/tirpc"]]
    )
    linux_mod.check_xdr_headers(zigcc)
    assert len(calls) == 2
    assert "-I/usr/include/tirpc" in calls[1]


def test_linux_xdr_candidates_include_system_tirpc_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The candidate builder offers -I/usr/include/tirpc when it exists.

    `as_posix()` keeps the mock portable: `str(WindowsPath)` uses
    backslashes, so a plain string compare against the forward-slash
    literal never matches on Windows.
    """
    for key in ("TIRPC_DIR", "CONDA_PREFIX"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        linux_mod.Path,
        "is_dir",
        lambda self: self.as_posix() == "/usr/include/tirpc",
    )
    assert linux_mod._xdr_include_candidates() == [[], ["-I/usr/include/tirpc"]]


def _write_moose_config(moose_dir: Path, *, mfem_enabled: bool) -> Path:
    """Materialize a minimal MooseConfig.h with/without the MFEM marker."""
    cfg = moose_dir / "framework" / "include" / "base" / "MooseConfig.h"
    cfg.parent.mkdir(parents=True)
    marker = "#define MOOSE_MFEM_ENABLED 1\n" if mfem_enabled else ""
    cfg.write_text(f"// fake config\n{marker}", encoding="utf-8")
    return cfg


def test_linux_cached_config_serial_passes_through_without_vars_mk(
    tmp_path: Path,
) -> None:
    """Serial configs never carry the MFEM marker, so no flags are needed."""
    moose_dir = tmp_path / "moose"
    cfg = _write_moose_config(moose_dir, mfem_enabled=False)
    linux_mod.check_cached_moose_config(moose_dir)
    assert cfg.is_file()


def test_linux_cached_config_mfem_kept_when_flags_usable(
    tmp_path: Path,
) -> None:
    """A cached MFEM config with a matching conf_vars.mk must survive."""
    moose_dir = tmp_path / "moose"
    cfg = _write_moose_config(moose_dir, mfem_enabled=True)
    mfem_inc = moose_dir / "mfem" / "include"
    mfem_inc.mkdir(parents=True)
    (mfem_inc / "mfem.hpp").write_text("// fake\n", encoding="utf-8")
    (moose_dir / "conf_vars.mk").write_text(
        f"ENABLE_MFEM       := true\nMFEM_DIR          := {moose_dir / 'mfem'}\n",
        encoding="utf-8",
    )
    linux_mod.check_cached_moose_config(moose_dir)
    assert cfg.is_file()


def test_linux_cached_config_mfem_dropped_when_vars_mk_missing(
    tmp_path: Path,
) -> None:
    """MFEM decision without flags must force a fresh configure.

    Regression for the MPI CI failure where a cached MooseConfig.h
    (MFEM enabled) restored without conf_vars.mk and the framework build
    died with 'mfem.hpp file not found'.
    """
    moose_dir = tmp_path / "moose"
    cfg = _write_moose_config(moose_dir, mfem_enabled=True)
    assert not (moose_dir / "conf_vars.mk").exists()
    linux_mod.check_cached_moose_config(moose_dir)
    assert not cfg.exists()


def test_linux_cached_config_mfem_dropped_when_mfem_dir_broken(
    tmp_path: Path,
) -> None:
    """A conf_vars.mk pointing at headers that do not exist must not pass."""
    moose_dir = tmp_path / "moose"
    cfg = _write_moose_config(moose_dir, mfem_enabled=True)
    vars_mk = moose_dir / "conf_vars.mk"
    vars_mk.write_text(
        "ENABLE_MFEM       := true\nMFEM_DIR          := /nonexistent/prefix\n",
        encoding="utf-8",
    )
    linux_mod.check_cached_moose_config(moose_dir)
    assert not cfg.exists()
    assert not vars_mk.exists()


def _record_stages(
    monkeypatch: pytest.MonkeyPatch, names: list[str]
) -> list[str]:
    """Replace build stages with recorders; return the call order log."""
    order: list[str] = []

    def make_fake(name: str) -> object:
        def fake(*args: object, **kwargs: object) -> None:
            order.append(name)

        return fake

    for name in names:
        monkeypatch.setattr(linux_mod, name, make_fake(name))
    return order


_MPI_STAGE_NAMES = (
    "build_petsc",
    "build_libmesh",
    "build_conduit",
    "build_wasp",
    "build_mfem",
    "configure_moose",
)


def test_linux_mpi_builds_conduit_and_mfem_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MPI dependency builds include Conduit/MFEM around WASP."""
    monkeypatch.setenv("RABBIT_MPI", "1")
    order = _record_stages(monkeypatch, list(_MPI_STAGE_NAMES))
    linux_mod.build_linux_dependencies(tmp_path, tmp_path, tmp_path, tmp_path)
    assert order == list(_MPI_STAGE_NAMES)


def test_linux_serial_skips_conduit_and_mfem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serial builds keep the original PETSc/libMesh/WASP/configure order."""
    monkeypatch.delenv("RABBIT_MPI", raising=False)
    order = _record_stages(monkeypatch, list(_MPI_STAGE_NAMES))
    linux_mod.build_linux_dependencies(tmp_path, tmp_path, tmp_path, tmp_path)
    assert order == [
        "build_petsc",
        "build_libmesh",
        "build_wasp",
        "configure_moose",
    ]


def _record_petsc_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    """Run build_petsc with everything stubbed; return the script argv."""
    monkeypatch.setattr(linux_mod, "ensure_moose_repo", lambda *a: None)
    monkeypatch.setattr(linux_mod, "ensure_moose_submodules", lambda *a: None)
    monkeypatch.setattr(linux_mod, "check_build_tools", lambda **k: None)
    recorded: list[str] = []

    def fake_run(
        cmd: list[str], **kwargs: object
    ) -> object:
        recorded.extend(cmd)
        return None

    monkeypatch.setattr(linux_mod.subprocess, "run", fake_run)
    zigcc, zigcxx = _fake_wrappers(tmp_path)
    linux_mod.build_petsc(tmp_path, tmp_path, zigcc, zigcxx)
    return recorded


def test_linux_mpi_pins_mpi_compilers_for_petsc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PETSc must be told its MPI compilers as configure arguments.

    Regression protection: PETSc's configure ignores CC/CXX env (it
    warns and auto-detects bare ``mpicc``), so on multi-MPI machines
    the MPI variant silently configured the wrong MPI (libMesh then
    died with "configured with Open MPI ... non-Open MPI mpi.h").
    """
    monkeypatch.setenv("RABBIT_MPI", "1")
    monkeypatch.delenv("RABBIT_MPI_IMPL", raising=False)
    cmd = _record_petsc_command(tmp_path, monkeypatch)
    assert "--with-cc=mpicc" in cmd
    assert "--with-cxx=mpicxx" in cmd
    assert "--with-fc=mpif90" in cmd
    assert "--with-mpiexec=mpiexec" in cmd


def test_linux_mpich_pins_suffixed_compilers_for_petsc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MPICH variant pins the explicit .mpich wrappers."""
    monkeypatch.setenv("RABBIT_MPI", "1")
    monkeypatch.setenv("RABBIT_MPI_IMPL", "mpich")
    cmd = _record_petsc_command(tmp_path, monkeypatch)
    assert "--with-cc=mpicc.mpich" in cmd
    assert "--with-cxx=mpicxx.mpich" in cmd
    assert "--with-fc=mpif90.mpich" in cmd
    assert "--with-mpiexec=mpiexec.mpich" in cmd
