# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Unit tests for wheel staging library resolution.

Regression protection for the Linux CI failure where ``stage_artifacts``
aborted with ``required shared libraries were not found: libomp.so.5``:
the OpenMP runtime is a documented system dependency outside the source
trees, so its SONAME must resolve from canonical system locations.
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build.common import (
    _DARWIN_HOMEBREW_RUNTIME_PATTERNS,
    find_needed_libraries,
    index_system_openmp_libs,
    stage_moose_data,
)


def test_indexes_exact_soname(tmp_path: Path) -> None:
    """The staged SONAME (e.g. libomp.so.5) must resolve by exact filename."""
    lib = tmp_path / "libomp.so.5"
    lib.write_bytes(b"fake")
    available: dict[str, Path] = {}
    index_system_openmp_libs(
        available, patterns=(str(tmp_path / "libomp.so*"),)
    )
    assert available["libomp.so.5"] == lib


def test_repository_entries_take_precedence(tmp_path: Path) -> None:
    """Vendored libraries must never be overridden by system ones."""
    system_lib = tmp_path / "libomp.so.5"
    system_lib.write_bytes(b"fake")
    repo_lib = tmp_path / "repo-libomp.so.5"
    repo_lib.write_bytes(b"fake")
    available: dict[str, Path] = {"libomp.so.5": repo_lib}
    index_system_openmp_libs(
        available, patterns=(str(tmp_path / "libomp.so*"),)
    )
    assert available["libomp.so.5"] == repo_lib


def test_missing_directories_are_ignored() -> None:
    """Nonexistent search locations must not raise."""
    available: dict[str, Path] = {}
    index_system_openmp_libs(
        available, patterns=("/nonexistent-rabbit-path/libomp.so*",)
    )
    assert available == {}


def test_darwin_indexes_system_libs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """macOS must index the OpenMP runtime like Linux does.

    Regression protection for the clean-machine smoke failure where the
    wheel's rabbit linked absolute
    ``/opt/homebrew/opt/llvm/lib/libomp.dylib`` (dyld abort): the old
    darwin early-return left that reference unstaged.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    lib = tmp_path / "libomp.dylib"
    lib.write_bytes(b"fake")
    available: dict[str, Path] = {}
    index_system_openmp_libs(
        available, patterns=(str(tmp_path / "libomp.dylib"),)
    )
    assert available["libomp.dylib"] == lib


def test_darwin_default_patterns_cover_homebrew() -> None:
    """Default macOS patterns must cover brew prefixes and runtime providers.

    Every absolute Homebrew reference in the serial binary (OpenMP from
    llvm/libomp, libpng from the PNG-support brew install) must resolve
    to a staged `@rpath` lib; anything else fails loudly at staging.
    """
    joined = "\n".join(_DARWIN_HOMEBREW_RUNTIME_PATTERNS)
    for prefix in ("/opt/homebrew", "/usr/local"):
        assert prefix in joined
    for provider in ("opt/llvm", "opt/libomp", "opt/libpng"):
        assert provider in joined


def _fake_otool(output: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route build.common's otool invocation to canned output."""
    import subprocess

    class _Result:
        stdout = output

    def _run(cmd: list[str], **kwargs: object) -> _Result:
        assert cmd[:2] == ["otool", "-L"]
        return _Result()

    monkeypatch.setattr(subprocess, "run", _run)


def test_darwin_unresolved_dep_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absolute macOS dep outside every index must be reported.

    The old darwin branch silently dropped such references, so staging
    shipped a wheel whose dyld failure only surfaced on clean machines.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    binary = tmp_path / "rabbit"
    binary.write_bytes(b"fake")
    _fake_otool(
        "/path/to/rabbit:\n"
        "\t/opt/homebrew/opt/llvm/lib/libomp.dylib (compatibility version 1.0.0)\n"
        "\t/usr/lib/libc++.1.dylib (compatibility version 1.0.0)\n",
        monkeypatch,
    )
    resolved, unresolved = find_needed_libraries(binary, {})
    assert resolved == {}
    assert unresolved == {"libomp.dylib"}


def test_darwin_indexed_dep_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An indexed macOS dep must resolve to its real path for staging."""
    monkeypatch.setattr(sys, "platform", "darwin")
    binary = tmp_path / "rabbit"
    binary.write_bytes(b"fake")
    lib = tmp_path / "libomp.dylib"
    lib.write_bytes(b"fake")
    _fake_otool(
        "/path/to/rabbit:\n"
        "\t/opt/homebrew/opt/llvm/lib/libomp.dylib (compatibility version 1.0.0)\n",
        monkeypatch,
    )
    resolved, unresolved = find_needed_libraries(
        binary, {"libomp.dylib": lib}
    )
    assert unresolved == set()
    assert resolved["libomp.dylib"] == lib.resolve()


def _fake_readelf(output: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route build.common's readelf invocation to canned output."""
    import subprocess

    class _Result:
        stdout = output

    def _run(cmd: list[str], **kwargs: object) -> _Result:
        assert cmd[:2] == ["readelf", "-d"]
        return _Result()

    monkeypatch.setattr(subprocess, "run", _run)


def test_mpich_libs_treated_as_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MPICH runtime libs must stay external like the OpenMPI ones.

    Regression protection for the MPICH CI failure where
    ``stage_artifacts`` aborted with ``required shared libraries were
    not found: libmpich.so.12, libmpichcxx.so.12, libmpichfort.so.12``:
    the wheel links the system MPI ecosystem externally (smoke installs
    libmpich12), so these SONAMEs resolve to no staged copy.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    binary = tmp_path / "rabbit"
    binary.write_bytes(b"fake")
    _fake_readelf(
        " 0x0000000000000001 (NEEDED)             Shared library: [libmpich.so.12]\n"
        " 0x0000000000000001 (NEEDED)             Shared library: [libmpichcxx.so.12]\n"
        " 0x0000000000000001 (NEEDED)             Shared library: [libmpichfort.so.12]\n"
        " 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]\n",
        monkeypatch,
    )
    resolved, unresolved = find_needed_libraries(binary, {})
    assert resolved == {}
    assert unresolved == set()


def _write_data_tree(root: Path) -> None:
    """Create fake moose/framework/data and solid_mechanics/data trees."""
    framework_data = root / "moose" / "framework" / "data"
    framework_data.mkdir(parents=True)
    (framework_data / "model.pt").write_bytes(b"fake")
    sm_data = root / "moose" / "modules" / "solid_mechanics" / "data"
    sm_data.mkdir(parents=True)
    (sm_data / "table.json").write_bytes(b"fake")


def test_stage_moose_data_copies_share_tree(tmp_path: Path) -> None:
    """Both data dirs must land at <pkg>/share/<name>/data.

    Regression protection for the PyPI-install failure where the binary
    aborted with "Failed to determine data file path for 'moose'":
    MOOSE resolves ``<exe>/../share/<name>/data`` first, so the wheel
    must ship it.
    """
    _write_data_tree(tmp_path)
    stage_moose_data(tmp_path, tmp_path / "moose")
    assert (
        tmp_path / "src" / "rabbit" / "share" / "moose" / "data" / "model.pt"
    ).is_file()
    assert (
        tmp_path
        / "src"
        / "rabbit"
        / "share"
        / "solid_mechanics"
        / "data"
        / "table.json"
    ).is_file()


def test_stage_moose_data_missing_source_raises(tmp_path: Path) -> None:
    """A wheel built without data files must fail loudly, not silently."""
    with pytest.raises(FileNotFoundError, match="data directory missing"):
        stage_moose_data(tmp_path, tmp_path / "moose")
