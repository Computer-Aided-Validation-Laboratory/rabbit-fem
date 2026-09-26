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


def _write_cached_config(
    moose_dir: Path,
    with_png: bool = True,
    with_vars: bool = True,
    vars_have_headers: bool = True,
) -> Path:
    """Stage a fake cached MOOSE config plus optional flags file."""
    cfg = moose_dir / "framework" / "include" / "base" / "MooseConfig.h"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "#define MOOSE_HAVE_LIBPNG 1\n" if with_png else "// no png\n",
        encoding="utf-8",
    )
    inc = moose_dir / "sys_include"
    inc.mkdir(exist_ok=True)
    (inc / "png.h").write_bytes(b"fake")
    vars_mk = moose_dir / "conf_vars.mk"
    if with_vars:
        flag = f"-I{inc}" if vars_have_headers else "-I/missing"
        vars_mk.write_text(
            f"libPNG_LIBS       := -lpng\nlibPNG_INCLUDE    := {flag}\n",
            encoding="utf-8",
        )
    return cfg


def test_cached_config_consistent_is_kept(tmp_path: Path) -> None:
    """A consistent cached config must survive untouched."""
    moose_dir = tmp_path / "moose"
    cfg = _write_cached_config(moose_dir)
    darwin.check_cached_moose_config(moose_dir)
    assert cfg.is_file()


def test_cached_config_without_png_is_kept(tmp_path: Path) -> None:
    """A cached config with PNG disabled needs no flags file."""
    moose_dir = tmp_path / "moose"
    cfg = _write_cached_config(moose_dir, with_png=False, with_vars=False)
    darwin.check_cached_moose_config(moose_dir)
    assert cfg.is_file()


def test_cached_config_missing_vars_heals(tmp_path: Path) -> None:
    """Header without its flags file (the CI failure) must be removed."""
    moose_dir = tmp_path / "moose"
    cfg = _write_cached_config(moose_dir, with_vars=False)
    darwin.check_cached_moose_config(moose_dir)
    assert not cfg.exists()


def test_cached_config_broken_flags_heals(tmp_path: Path) -> None:
    """Header with flags pointing nowhere must be removed with them."""
    moose_dir = tmp_path / "moose"
    cfg = _write_cached_config(moose_dir, vars_have_headers=False)
    darwin.check_cached_moose_config(moose_dir)
    assert not cfg.exists()
    assert not (moose_dir / "conf_vars.mk").exists()


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


def test_patch_skip_warns_when_source_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Skipped patches (source tree absent) must be loud, not silent.

    Regression guard for the CI failure where the Rabbit step patched
    before the framework tree was materialized: every patch skipped
    silently, and the build died later with 'no member named
    transform' deep in the tinyhttp compile.
    """
    repo_dir = tmp_path / "repo"
    (repo_dir / "patches" / "macos").mkdir(parents=True)
    for patch in (
        REAL_PATCH,
        REAL_LIBMESH_PATCH,
        REAL_WASP_PATCH,
        REAL_TINYHTTP_PATCH,
    ):
        shutil.copy(patch, repo_dir / "patches" / "macos" / patch.name)

    darwin.apply_macos_patches(tmp_path / "moose", repo_dir)

    out = capsys.readouterr().out
    for patch in (
        "poly2tri.patch",
        "libmesh.patch",
        "wasp.patch",
        "tinyhttp.patch",
    ):
        assert patch in out
        assert "WARNING" in out


@pytest.mark.skipif(
    shutil.which("patch") is None, reason="patch utility not available"
)
def test_prepare_ensures_sources_before_patching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prepare_darwin_rabbit_sources must materialize before patching."""
    calls: list[str] = []

    def fake_ensure(repo_dir: Path, moose_dir: Path) -> None:
        calls.append("ensure")
        target = (
            moose_dir / "framework" / "contrib" / "tinyhttp"
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

    monkeypatch.setattr(darwin, "ensure_moose_repo", fake_ensure)

    repo_dir = tmp_path / "repo"
    (repo_dir / "patches" / "macos").mkdir(parents=True)
    shutil.copy(
        REAL_TINYHTTP_PATCH,
        repo_dir / "patches" / "macos" / REAL_TINYHTTP_PATCH.name,
    )

    darwin.prepare_darwin_rabbit_sources(repo_dir, tmp_path / "moose")

    assert calls == ["ensure"]
    patched = (
        tmp_path / "moose" / "framework" / "contrib" / "tinyhttp"
        / "include" / "tinyhttp" / "http.h"
    ).read_text(encoding="utf-8")
    assert "#include <algorithm>" in patched
    assert "#include <functional>" in patched


def test_relink_rewrites_staged_refs_to_rpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staged Mach-O artifacts must reference staged libs via @rpath.

    Regression guard for the CI failure where the staged macOS binary
    kept an absolute LC_LOAD_DYLIB to
    test/lib/librabbit_test-opt.0.dylib: adding RPATHs is not enough
    because the macOS linker records absolute build paths (unlike ELF
    SONAMEs), so the shipped tree only ran on the build machine.
    """
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "librabbit_test-opt.0.dylib").write_bytes(b"fake-a")
    (lib_dir / "libmesh_opt.dylib").write_bytes(b"fake-b")
    staged_bin = tmp_path / "rabbit"
    staged_bin.write_bytes(b"fake-bin")

    otool_outputs = {
        "rabbit": (
            "rabbit:\n"
            "\t/Users/runner/work/rabbit-fem/test/lib/librabbit_test-opt.0.dylib (compat 0.0.0)\n"
            "\t@rpath/libmesh_opt.dylib (compat 0.0.0)\n"
            "\t/usr/lib/libSystem.B.dylib (compat 1.0.0)\n"
            "\t/opt/homebrew/opt/open-mpi/lib/libmpi.40.dylib (compat 0.0.0)\n"
        ),
        "librabbit_test-opt.0.dylib": (
            "librabbit_test-opt.0.dylib:\n"
            "\t/Users/runner/work/rabbit-fem/moose/libmesh/installed/lib/libmesh_opt.dylib (compat 0.0.0)\n"
            "\t/usr/lib/libc++.1.dylib (compat 1.0.0)\n"
        ),
        "libmesh_opt.dylib": (
            "libmesh_opt.dylib:\n"
            "\t/usr/lib/libSystem.B.dylib (compat 1.0.0)\n"
        ),
    }

    def _rpath_cmd(name: str, path: str) -> str:
        return (
            f"{name}:\n"
            "Load command 1\n"
            "      cmd LC_RPATH\n"
            f"  cmdsize 48\n          path {path} (offset 12)\n"
            "Load command 2\n"
            "      cmd LC_SEGMENT_64\n"
        )

    # Rabbit carries an absolute Homebrew RPATH (the CI failure) and
    # no canonical entry; libmesh already has exactly the canonical
    # entry; the test lib has no RPATH at all.
    otool_l_outputs = {
        "rabbit": _rpath_cmd("rabbit", "/opt/homebrew/opt/hdf5-mpi/lib"),
        "librabbit_test-opt.0.dylib": (
            "librabbit_test-opt.0.dylib:\n"
            "Load command 0\n"
            "      cmd LC_SEGMENT_64\n"
        ),
        "libmesh_opt.dylib": _rpath_cmd("libmesh_opt.dylib", "@loader_path"),
    }
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        assert kwargs.get("check") is True
        if cmd[0] == "otool":
            name = Path(cmd[-1]).name
            if "-l" in cmd:
                return subprocess.CompletedProcess(cmd, 0, otool_l_outputs[name])
            return subprocess.CompletedProcess(cmd, 0, otool_outputs[name])
        assert cmd[0] == "install_name_tool"
        return subprocess.CompletedProcess(cmd, 0, "")

    monkeypatch.setattr(darwin.subprocess, "run", fake_run)

    darwin.relink_darwin_staged_artifacts(staged_bin, lib_dir)

    id_calls = [c for c in calls if "-id" in c]
    assert sorted(c[2] for c in id_calls) == [
        "@rpath/libmesh_opt.dylib",
        "@rpath/librabbit_test-opt.0.dylib",
    ]

    change_calls = [c for c in calls if "-change" in c]
    # (old, new, target) triples actually rewritten.
    rewritten = [(c[2], c[3], Path(c[4]).name) for c in change_calls]
    assert (
        "/Users/runner/work/rabbit-fem/test/lib/librabbit_test-opt.0.dylib",
        "@rpath/librabbit_test-opt.0.dylib",
        "rabbit",
    ) in rewritten
    assert (
        "/Users/runner/work/rabbit-fem/moose/libmesh/installed/lib/libmesh_opt.dylib",
        "@rpath/libmesh_opt.dylib",
        "librabbit_test-opt.0.dylib",
    ) in rewritten
    # Already-relocatable (@rpath), system (/usr/lib), and non-staged
    # shared (/opt/homebrew MPI) references must be left untouched.
    for old, _new, _target in rewritten:
        assert old.startswith("/Users/runner")

    delete_calls = [c for c in calls if "-delete_rpath" in c]
    assert [
        (c[2], Path(c[3]).name) for c in delete_calls
    ] == [("/opt/homebrew/opt/hdf5-mpi/lib", "rabbit")]

    add_calls = [c for c in calls if "-add_rpath" in c]
    added = [(c[2], Path(c[3]).name) for c in add_calls]
    # Binary lacked its canonical entry; libmesh already had it;
    # the test lib needed its canonical entry.
    assert ("@loader_path/../lib", "rabbit") in added
    assert ("@loader_path", "librabbit_test-opt.0.dylib") in added
    assert not [a for a in added if a[1] == "libmesh_opt.dylib"]
