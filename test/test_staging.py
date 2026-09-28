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

from build.common import index_system_openmp_libs, stage_moose_data


def test_indexes_exact_soname(tmp_path: Path) -> None:
    """The staged SONAME (e.g. libomp.so.5) must resolve by exact filename."""
    lib = tmp_path / "libomp.so.5"
    lib.write_bytes(b"fake")
    available: dict[str, Path] = {}
    index_system_openmp_libs(
        available, patterns=(str(tmp_path / "libomp.so*"),)
    )
    if sys.platform == "darwin":
        assert available == {}
    else:
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
    if sys.platform == "darwin":
        assert available == {"libomp.so.5": repo_lib}
    else:
        assert available["libomp.so.5"] == repo_lib


def test_missing_directories_are_ignored() -> None:
    """Nonexistent search locations must not raise."""
    available: dict[str, Path] = {}
    index_system_openmp_libs(
        available, patterns=("/nonexistent-rabbit-path/libomp.so*",)
    )
    assert available == {}


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
