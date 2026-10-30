# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Unit tests for MOOSE version and dependency pin handling."""

from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build.common import (
    ensure_moose_submodules,
    get_pinned_moose_deps,
    get_pinned_moose_version,
    verify_moose_deps,
)


def _make_repo(path: Path) -> None:
    """Initialize a minimal git repository with one commit."""
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
         "--allow-empty", "-m", "init"],
        cwd=str(path),
        check=True,
    )


def test_pinned_version_matches_file() -> None:
    """The loader must return the exact commit recorded in moose_version.txt."""
    import build.common as common

    repo_dir = Path(common.__file__).resolve().parent.parent.parent
    recorded = (repo_dir / "moose_version.txt").read_text(
        encoding="utf-8"
    ).strip()
    assert get_pinned_moose_version(repo_dir) == recorded
    assert len(recorded) == 40


def test_pinned_deps_parse(tmp_path: Path) -> None:
    """Lock-file parsing must skip comments/blanks and keep name order."""
    deps_file = tmp_path / "moose_deps.txt"
    deps_file.write_text(
        "# comment\n\npetsc abc123\nlibmesh def456\nmalformed\n",
        encoding="utf-8",
    )
    assert get_pinned_moose_deps(tmp_path) == {
        "petsc": "abc123",
        "libmesh": "def456",
    }


def test_verify_matches_checked_out_submodules(tmp_path: Path) -> None:
    """Materialized submodules at the pinned commits must pass silently."""
    moose_dir = tmp_path / "moose"
    petsc_dir = moose_dir / "petsc"
    petsc_dir.mkdir(parents=True)
    _make_repo(petsc_dir)
    sha = subprocess.run(
        ["git", "-C", str(petsc_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (tmp_path / "moose_deps.txt").write_text(
        f"petsc {sha}\n", encoding="utf-8"
    )
    verify_moose_deps(moose_dir, tmp_path)


def test_verify_rejects_drifted_submodule(tmp_path: Path) -> None:
    """A checked-out submodule at the wrong commit must fail loudly."""
    moose_dir = tmp_path / "moose"
    petsc_dir = moose_dir / "petsc"
    petsc_dir.mkdir(parents=True)
    _make_repo(petsc_dir)
    (tmp_path / "moose_deps.txt").write_text(
        "petsc 0000000000000000000000000000000000000000\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="pins"):
        verify_moose_deps(moose_dir, tmp_path)


def test_verify_skips_absent_submodules(tmp_path: Path) -> None:
    """Missing checkouts are the ensure steps' job, not a drift error."""
    moose_dir = tmp_path / "moose"
    moose_dir.mkdir()
    (tmp_path / "moose_deps.txt").write_text(
        "petsc abc123\nlibmesh def456\nwasp ghi789\n", encoding="utf-8"
    )
    verify_moose_deps(moose_dir, tmp_path)


def test_verify_warns_on_unverifiable_checkout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cache-restored trees with dangling git metadata must not fail."""
    moose_dir = tmp_path / "moose"
    petsc_dir = moose_dir / "petsc"
    petsc_dir.mkdir(parents=True)
    (petsc_dir / ".git").write_text(
        "gitdir: /nonexistent/modules/petsc\n", encoding="utf-8"
    )
    (tmp_path / "moose_deps.txt").write_text(
        "petsc abc123\n", encoding="utf-8"
    )
    verify_moose_deps(moose_dir, tmp_path)
    assert "cannot verify" in capsys.readouterr().out


def test_ensure_overrides_update_none_submodules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure must pass --checkout so update=none submodules materialize.

    Some MOOSE submodules (framework/contrib/mfem and
    framework/contrib/conduit) set ``update = none`` in .gitmodules, for
    which a plain ``git submodule update`` prints "Skipping submodule
    ..." even for explicitly listed paths. MPI builds materialize all
    five submodules.
    """
    import build.common as common

    monkeypatch.setenv("RABBIT_MPI", "1")
    moose_dir = tmp_path / "moose"
    moose_dir.mkdir()
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(common.subprocess, "run", fake_run)
    monkeypatch.setattr(common.time, "sleep", lambda *_: None)
    ensure_moose_submodules(moose_dir)

    updates = [c for c in commands if c[:3] == ["git", "submodule", "update"]]
    assert len(updates) == 1
    assert "--checkout" in updates[0]
    for sub in (
        "petsc",
        "libmesh",
        "framework/contrib/wasp",
        "framework/contrib/conduit",
        "framework/contrib/mfem",
    ):
        assert sub in updates[0]


def test_ensure_serial_skips_mfem_and_conduit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serial builds must not fetch the MPI-only MFEM/Conduit submodules.

    Variant isolation: a serial run fetches petsc/libmesh/wasp only, so
    MFEM-side submodule breakage cannot red the serial pipeline (and the
    serial recipe stays byte-identical to pre-MFEM).
    """
    import build.common as common

    monkeypatch.delenv("RABBIT_MPI", raising=False)
    moose_dir = tmp_path / "moose"
    moose_dir.mkdir()
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(common.subprocess, "run", fake_run)
    monkeypatch.setattr(common.time, "sleep", lambda *_: None)
    ensure_moose_submodules(moose_dir)

    updates = [c for c in commands if c[:3] == ["git", "submodule", "update"]]
    assert len(updates) == 1
    for sub in ("petsc", "libmesh", "framework/contrib/wasp"):
        assert sub in updates[0]
    for sub in ("framework/contrib/conduit", "framework/contrib/mfem"):
        assert sub not in updates[0]


def test_verify_serial_ignores_mfem_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serial verification must skip MPI-only dep pins (and vice versa)."""
    monkeypatch.delenv("RABBIT_MPI", raising=False)
    moose_dir = tmp_path / "moose"
    mfem_dir = moose_dir / "framework" / "contrib" / "mfem"
    mfem_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=str(mfem_dir), check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
         "-q", "--allow-empty", "-m", "init"],
        cwd=str(mfem_dir),
        check=True,
    )
    (tmp_path / "moose_deps.txt").write_text(
        "mfem 0000000000000000000000000000000000000000\n",
        encoding="utf-8",
    )
    verify_moose_deps(moose_dir, tmp_path)


def test_verify_mpi_catches_mfem_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MPI verification must still pin the MFEM commit."""
    monkeypatch.setenv("RABBIT_MPI", "1")
    moose_dir = tmp_path / "moose"
    mfem_dir = moose_dir / "framework" / "contrib" / "mfem"
    mfem_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=str(mfem_dir), check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
         "-q", "--allow-empty", "-m", "init"],
        cwd=str(mfem_dir),
        check=True,
    )
    (tmp_path / "moose_deps.txt").write_text(
        "mfem 0000000000000000000000000000000000000000\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="mfem"):
        verify_moose_deps(moose_dir, tmp_path)
