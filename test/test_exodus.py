# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Unit tests for the vendored Exodus II reader."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rabbit.exodus import _decode_names


def _name_table(rows: list[bytes], width: int = 33) -> np.ndarray:
    """Pack byte strings into a 2D |S1 array like netCDF4 returns."""
    table = np.zeros((len(rows), width), dtype=np.uint8)
    for i, row in enumerate(rows):
        chunk = row[:width]
        table[i, : len(chunk)] = np.frombuffer(chunk, dtype=np.uint8)
    return table.view("|S1").reshape(len(rows), width)


def test_decode_names_null_padded() -> None:
    """NUL-padded names decode to their content."""
    raw = _name_table([b"temperature\x00\x00", b"disp_x\x00"])
    assert _decode_names(raw) == ["temperature", "disp_x"]


def test_decode_names_ignores_garbage_after_nul() -> None:
    """Heap garbage past the NUL terminator must not break decoding.

    Observed in electromagnetics output: short vector-component names
    (``u_y``) followed by uninitialized writer memory containing
    non-UTF-8 bytes.
    """
    raw = _name_table(
        [
            b"u_x\x00",
            b"u_y\x00\xb9\x99\x99\x99\x99\xa0\x3f\xc9",
        ]
    )
    assert _decode_names(raw) == ["u_x", "u_y"]


def test_decode_names_space_padded() -> None:
    """Space-padded names without NULs still strip cleanly."""
    raw = _name_table([b"temperature   ", b"disp_x     "])
    assert _decode_names(raw) == ["temperature", "disp_x"]
