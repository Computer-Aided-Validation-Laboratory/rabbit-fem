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
REAL_WASP_PATCH = REPO_ROOT / "patches" / "macos" / "wasp.patch"
REAL_TINYHTTP_PATCH = REPO_ROOT / "patches" / "macos" / "tinyhttp.patch"


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


class _FakePkgConfig:
    """Minimal pkg-config stand-in for libpng consistency checks."""

    def __init__(
        self,
        exists_code: int = 1,
        cflags: str = "",
        path: str = "/fake/bin/pkg-config",
    ) -> None:
        self.exists_code = exists_code
        self.cflags = cflags
        self.path = path
        self.calls: list[list[str]] = []

    def which(self, name: str, path: object = None) -> str | None:
        assert name == "pkg-config"
        return self.path

    def run(
        self, cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        if "--exists" in cmd:
            return subprocess.CompletedProcess(cmd, self.exists_code)
        return subprocess.CompletedProcess(cmd, 0, self.cflags)


def _patch_pkg_config(
    monkeypatch: pytest.MonkeyPatch, fake: _FakePkgConfig
) -> None:
    monkeypatch.setattr(shutil, "which", fake.which)
    monkeypatch.setattr(subprocess, "run", fake.run)


def test_libpng_absent_disables_quietly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No libpng metadata means MOOSE configures without PNG: no error."""
    fake = _FakePkgConfig(exists_code=1)
    _patch_pkg_config(monkeypatch, fake)
    darwin.check_libpng_consistency({"PATH": "/fake/bin"})
    assert any("--exists" in c for c in fake.calls)


def test_libpng_with_headers_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consistent libpng install (headers where flags point) passes."""
    inc = tmp_path / "include"
    inc.mkdir()
    (inc / "png.h").write_bytes(b"fake")
    fake = _FakePkgConfig(exists_code=0, cflags=f"-I{inc}")
    _patch_pkg_config(monkeypatch, fake)
    darwin.check_libpng_consistency({"PATH": "/fake/bin"})


def test_libpng_without_headers_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata without headers (the CI failure) must fail loudly."""
    inc = tmp_path / "include"
    inc.mkdir()
    fake = _FakePkgConfig(exists_code=0, cflags=f"-I{inc}")
    _patch_pkg_config(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="png.h"):
        darwin.check_libpng_consistency({"PATH": "/fake/bin"})


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


@pytest.mark.skipif(
    shutil.which("patch") is None, reason="patch utility not available"
)
def test_wasp_patch_applies_to_pristine_tree(tmp_path: Path) -> None:
    """The macOS WASP patch must apply to the real pinned sources."""
    assert REAL_WASP_PATCH.is_file()
    content = REAL_WASP_PATCH.read_text(encoding="utf-8")
    assert "waspcore/Format.h" in content
    assert "#include <type_traits>" in content

    repo_dir = tmp_path / "repo"
    target = tmp_path / "moose" / "framework" / "contrib" / "wasp" / "waspcore"
    target.mkdir(parents=True)
    shutil.copy(
        REPO_ROOT
        / "moose"
        / "framework"
        / "contrib"
        / "wasp"
        / "waspcore"
        / "Format.h",
        target / "Format.h",
    )
    (repo_dir / "patches" / "macos").mkdir(parents=True)
    shutil.copy(
        REAL_WASP_PATCH, repo_dir / "patches" / "macos" / REAL_WASP_PATCH.name
    )

    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)
    patched = (target / "Format.h").read_text(encoding="utf-8")
    assert "#include <type_traits>" in patched

    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)
    assert (target / "Format.h").read_text(encoding="utf-8") == patched


@pytest.mark.skipif(
    shutil.which("patch") is None, reason="patch utility not available"
)
def test_tinyhttp_patch_applies_to_pristine_tree(tmp_path: Path) -> None:
    """The macOS tinyhttp patch must apply to the real pinned sources."""
    assert REAL_TINYHTTP_PATCH.is_file()
    content = REAL_TINYHTTP_PATCH.read_text(encoding="utf-8")
    assert "include/tinyhttp/http.h" in content
    assert "#include <algorithm>" in content
    assert "#include <functional>" in content

    repo_dir = tmp_path / "repo"
    target = (
        tmp_path / "moose" / "framework" / "contrib" / "tinyhttp"
        / "include" / "tinyhttp"
    )
    target.mkdir(parents=True)
    shutil.copy(
        REPO_ROOT
        / "moose"
        / "framework"
        / "contrib"
        / "tinyhttp"
        / "include"
        / "tinyhttp"
        / "http.h",
        target / "http.h",
    )
    (repo_dir / "patches" / "macos").mkdir(parents=True)
    shutil.copy(
        REAL_TINYHTTP_PATCH,
        repo_dir / "patches" / "macos" / REAL_TINYHTTP_PATCH.name,
    )

    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)
    patched = (target / "http.h").read_text(encoding="utf-8")
    assert "#include <algorithm>" in patched
    assert "#include <functional>" in patched

    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)
    assert (target / "http.h").read_text(encoding="utf-8") == patched
