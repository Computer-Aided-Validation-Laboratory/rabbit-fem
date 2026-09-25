# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Unit tests for the macOS build orchestration.

Regression protection for the macOS CI failure where libMesh's bundled
NetGen sources do not compile against newer Homebrew LLVM libc++ paired
with the Xcode SDK (SDK math.h isnan/isinf/signbit function-like macros
break <complex> parsing in nglib's gzstream.cpp). Rabbit never uses
NetGen, so the macOS libMesh build disables it via the documented
libMesh configure option.
"""

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build.darwin as darwin

REPO_ROOT = Path(darwin.__file__).resolve().parent.parent.parent
REAL_PATCH = REPO_ROOT / "patches" / "macos" / "poly2tri.patch"
REAL_LIBMESH_PATCH = REPO_ROOT / "patches" / "macos" / "libmesh.patch"


def _run_build_libmesh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[list[str]]:
    """Run darwin.build_libmesh with all side effects mocked out."""
    commands: list[list[str]] = []

    def fake_run(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(
        darwin, "ensure_moose_repo", lambda *args: None
    )
    monkeypatch.setattr(
        darwin, "ensure_moose_submodules", lambda *args: None
    )
    monkeypatch.setattr(darwin.subprocess, "run", fake_run)

    repo_dir = tmp_path / "repo"
    moose_dir = tmp_path / "moose"
    repo_dir.mkdir(exist_ok=True)
    moose_dir.mkdir(exist_ok=True)
    darwin.build_libmesh(
        repo_dir, moose_dir, Path("zigcc"), Path("zigcxx")
    )
    return commands


def test_libmesh_disables_netgen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The macOS libMesh configure must skip the NetGen contrib package."""
    commands = _run_build_libmesh(tmp_path, monkeypatch)
    assert len(commands) == 1
    assert "--disable-netgen" in commands[0]
    assert "--with-mpi" in commands[0]


def test_libmesh_skipped_when_already_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A completed libMesh install must not trigger any build command."""
    commands = _run_build_libmesh(tmp_path, monkeypatch)
    assert len(commands) == 1
    lib_dir = tmp_path / "moose" / "libmesh" / "installed" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "libmesh_opt.a").write_bytes(b"fake")

    commands2 = _run_build_libmesh(tmp_path, monkeypatch)
    assert commands2 == []


@pytest.mark.skipif(
    shutil.which("patch") is None, reason="patch utility not available"
)
def test_poly2tri_patch_applies_to_pristine_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The macOS poly2tri patch must apply to the real pinned sources.

    Uses a scratch copy of the repository's own shapes.h so the local
    checkout (possibly mid-build) is never modified.
    """
    assert REAL_PATCH.is_file()
    content = REAL_PATCH.read_text(encoding="utf-8")
    assert "poly2tri/poly2tri/common/shapes.h" in content
    assert "#include <ostream>" in content

    repo_dir = tmp_path / "repo"
    target = (
        tmp_path
        / "moose"
        / "libmesh"
        / "contrib"
        / "poly2tri"
        / "poly2tri"
        / "poly2tri"
        / "common"
    )
    target.mkdir(parents=True)
    shutil.copy(
        REPO_ROOT
        / "moose"
        / "libmesh"
        / "contrib"
        / "poly2tri"
        / "poly2tri"
        / "poly2tri"
        / "common"
        / "shapes.h",
        target / "shapes.h",
    )
    (repo_dir / "patches" / "macos").mkdir(parents=True)
    shutil.copy(REAL_PATCH, repo_dir / "patches" / "macos" / REAL_PATCH.name)

    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)
    patched = (target / "shapes.h").read_text(encoding="utf-8")
    assert "#include <ostream>" in patched

    # Second application must be a tolerated no-op (idempotent for
    # cache-hit runs that re-invoke the build).
    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)
    assert (target / "shapes.h").read_text(
        encoding="utf-8"
    ) == patched


@pytest.mark.skipif(
    shutil.which("patch") is None, reason="patch utility not available"
)
def test_libmesh_patch_applies_to_pristine_tree(tmp_path: Path) -> None:
    """The macOS libMesh patch must apply to the real pinned sources."""
    assert REAL_LIBMESH_PATCH.is_file()
    content = REAL_LIBMESH_PATCH.read_text(encoding="utf-8")
    assert "include/base/dof_object.h" in content
    assert "#include <iterator>" in content

    repo_dir = tmp_path / "repo"
    target = tmp_path / "moose" / "libmesh" / "include" / "base"
    target.mkdir(parents=True)
    shutil.copy(
        REPO_ROOT
        / "moose"
        / "libmesh"
        / "include"
        / "base"
        / "dof_object.h",
        target / "dof_object.h",
    )
    (repo_dir / "patches" / "macos").mkdir(parents=True)
    shutil.copy(
        REAL_LIBMESH_PATCH, repo_dir / "patches" / "macos" / REAL_LIBMESH_PATCH.name
    )

    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)
    patched = (target / "dof_object.h").read_text(encoding="utf-8")
    assert "#include <iterator>" in patched

    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)
    assert (target / "dof_object.h").read_text(
        encoding="utf-8"
    ) == patched
