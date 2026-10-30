# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Unit tests for the Windows Zig compiler wrappers.

Regression protection for the Windows MPI CI failure where Hypre's
``make`` died at ``zig-ar`` with ``F90_HYPRE_error.o: No such file or
directory`` even though every compile exited 0 with no diagnostics:
``zig cc -target x86_64-windows-gnu -c foo.c`` writes ``foo.obj`` by
default (verified with zig 0.16.0), while POSIX Makefiles that omit
``-o`` expect ``foo.o``. The wrappers restore the ``<stem>.o``
convention for bare ``-c`` compiles.
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "windows_wrappers"),
)

from cc_wrapper import transform_args as cc_transform
from cxx_wrapper import transform_args as cxx_transform
from wrapper_utils import ensure_default_object_output, mpi_include_args


def test_bare_c_compile_gets_default_object() -> None:
    """``-c foo.c`` without ``-o`` gains ``-o foo.o``."""
    out = ensure_default_object_output(["-c", "foo.c"])
    assert out[-2:] == ["-o", "foo.o"]


def test_explicit_output_untouched() -> None:
    """An explicit ``-o`` (separate or joined) is never overridden."""
    assert ensure_default_object_output(["-c", "foo.c", "-o", "foo.obj"]) == [
        "-c",
        "foo.c",
        "-o",
        "foo.obj",
    ]
    assert ensure_default_object_output(["-c", "foo.c", "-ofoo.obj"]) == [
        "-c",
        "foo.c",
        "-ofoo.obj",
    ]


def test_link_command_untouched() -> None:
    """Link lines (no ``-c``) gain no ``-o``."""
    args = ["foo.c", "-o", "foo.exe"]
    assert ensure_default_object_output(args) == args
    args = ["foo.o", "bar.o", "-o", "foo.exe"]
    assert ensure_default_object_output(args) == args


def test_preprocess_only_untouched() -> None:
    """``-E``/``-S``/``-M`` modes emit no object file."""
    for mode in ("-E", "-S", "-M", "-MM"):
        args = ["-c", mode, "foo.c"]
        assert ensure_default_object_output(args) == args


def test_multiple_sources_untouched() -> None:
    """``-c`` with several sources cannot share one ``-o``."""
    args = ["-c", "a.c", "b.c"]
    assert ensure_default_object_output(args) == args


def test_non_source_untouched() -> None:
    """Headers and objects are not compile inputs."""
    assert ensure_default_object_output(["-c", "foo.h"]) == ["-c", "foo.h"]
    assert ensure_default_object_output(["-c"]) == ["-c"]


def test_windows_and_msys_paths_use_basename() -> None:
    """Matching GCC, ``cc -c dir/foo.c`` writes ``./foo.o``."""
    out = ensure_default_object_output(["-c", "D:\\a\\src\\foo.c"])
    assert out[-2:] == ["-o", "foo.o"]
    out = ensure_default_object_output(["-c", "/d/a/src/foo.c"])
    assert out[-2:] == ["-o", "foo.o"]


def _output_pair(out: list[str]) -> list[str]:
    """Locate the ``-o <file>`` pair wherever it sits."""
    idx = out.index("-o")
    return out[idx : idx + 2]


def test_cc_wrapper_end_to_end() -> None:
    """Hypre-style compile line through the real C transform."""
    out = cc_transform(
        ["-fPIC", "-g", "-O3", "-DHAVE_CONFIG_H", "-c", "F90_HYPRE_error.c"]
    )
    assert _output_pair(out) == ["-o", "F90_HYPRE_error.o"]
    assert out[:2] == ["-target", "x86_64-windows-gnu"]


def test_cxx_wrapper_end_to_end() -> None:
    """The C++ wrapper applies the same convention."""
    out = cxx_transform(["-g", "-O3", "-c", "device_utils.cpp"])
    assert _output_pair(out) == ["-o", "device_utils.o"]


def test_wrappers_leave_explicit_output_alone() -> None:
    """Explicit ``-o`` survives both wrapper transforms."""
    out = cc_transform(["-c", "general.c", "-o", "general.obj"])
    assert "-o" in out
    assert "general.obj" in out
    assert "general.o" not in out


def test_mpi_include_unset_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serial builds (env unset) see no extra ``-I``."""
    monkeypatch.delenv("RABBIT_MPI_INCLUDE", raising=False)
    assert mpi_include_args() == []


def test_mpi_include_converted_to_win(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The MS-MPI dir arrives as a converted ``-I`` argument."""
    monkeypatch.setenv("RABBIT_MPI_INCLUDE", "/c/msys64/mingw64/include")
    assert mpi_include_args() == ["-IC:/msys64/mingw64/include"]


def test_cc_wrapper_appends_mpi_include(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: env dir lands on the transformed command line."""
    monkeypatch.setenv("RABBIT_MPI_INCLUDE", "/c/msys64/mingw64/include")
    out = cc_transform(["-c", "foo.c"])
    assert "-IC:/msys64/mingw64/include" in out
