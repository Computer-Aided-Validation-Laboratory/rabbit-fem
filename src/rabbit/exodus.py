# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Minimal Exodus II output reader for Rabbit regression testing.

Adapted from the Exodus utilities in ``./refs/``:

* ``refs/exodusloader.py`` — pyvale (MIT, (C) 2025 The Computer Aided
  Validation Team, Authors: Lloyd Fletcher, Rory Spencer).
* ``refs/exodusio.py`` — riley ``ExodusSim``/``load_exodus`` structure.

Only the subset needed for gold regression tests is vendored here
(coords, element connectivity, nodal fields, global vars, time) so the
runtime package depends solely on ``netCDF4`` and ``numpy`` with no
``pyvale``/``riley`` imports.
"""

from dataclasses import dataclass, field
from pathlib import Path

import netCDF4 as nc
import numpy as np


class ExodusError(ValueError):
    """Raised when an Exodus II file cannot be loaded or validated."""


@dataclass
class ExodusData:
    """Nodal/global data loaded from an Exodus II file.

    Attributes
    ----------
    coords : numpy.ndarray
        Nodal coordinates of shape ``(N, 3)`` and dtype ``float64``.
    connect : dict of str to numpy.ndarray
        Element connectivity tables keyed by ``connect1``, ``connect2``,
        ... (1-based node indices, as stored in the file).
    node_vars : dict of str to numpy.ndarray
        Nodal fields keyed by variable name, each of shape ``(N, T)``.
    glob_vars : dict of str to numpy.ndarray
        Global (postprocessor) variables keyed by name, each of shape
        ``(T,)``.
    time : numpy.ndarray
        Simulation times of shape ``(T,)``.
    """

    coords: np.ndarray
    connect: dict[str, np.ndarray] = field(default_factory=dict)
    node_vars: dict[str, np.ndarray] = field(default_factory=dict)
    glob_vars: dict[str, np.ndarray] = field(default_factory=dict)
    time: np.ndarray = field(default_factory=lambda: np.zeros((0,)))


def _decode_names(raw: np.ndarray) -> list[str]:
    """Decode a 2D Exodus char array into a list of names."""
    chars = raw.view(f"S{raw.shape[-1]}").reshape(raw.shape[:-1])
    return [str(s).strip() for s in np.char.decode(chars, "utf-8")]


def _read_names(dataset: nc.Dataset, key: str) -> list[str] | None:
    """Read a name table (e.g. ``name_nod_var``) or return None."""
    if key not in dataset.variables:
        return None
    return _decode_names(np.array(dataset.variables[key][:, :]))


def _get_var(dataset: nc.Dataset, key: str) -> np.ndarray:
    """Read a numeric variable transposed to ``(..., T)`` convention."""
    return np.array(dataset.variables[key][:]).T


def load_exodus(path: str | Path) -> ExodusData:
    """Load coords, connectivity, nodal and global vars from an Exodus file.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to the ``*.e`` Exodus II file.

    Returns
    -------
    ExodusData
        Loaded mesh and field data. Nodal fields have shape ``(N, T)``,
        global fields shape ``(T,)``.

    Raises
    ------
    ExodusError
        If the file does not exist or contains no coordinates.
    """
    exodus_file = Path(path)
    if not exodus_file.is_file():
        raise ExodusError(f"Exodus file not found: {exodus_file}")

    data = ExodusData(coords=np.zeros((0, 3)))
    with nc.Dataset(str(exodus_file), mode="r") as ds:
        # --- Coordinates (missing dims are zero-padded, as in pyvale) ---
        xyz = []
        for key in ("coordx", "coordy", "coordz"):
            xyz.append(_get_var(ds, key) if key in ds.variables else None)
        n_nodes = max(
            (a.shape[0] for a in xyz if a is not None), default=0
        )
        if n_nodes == 0:
            raise ExodusError(f"No coordinates in '{exodus_file}'.")
        cols = [
            a if a is not None else np.zeros((n_nodes,))
            for a in xyz
        ]
        data.coords = np.ascontiguousarray(
            np.vstack(cols).T, dtype=np.float64
        )

        # --- Connectivity tables connect1, connect2, ... ---
        idx = 1
        while f"connect{idx}" in ds.variables:
            data.connect[f"connect{idx}"] = np.ascontiguousarray(
                _get_var(ds, f"connect{idx}")
            )
            idx += 1

        # --- Nodal variables ---
        nod_names = _read_names(ds, "name_nod_var") or []
        for i, name in enumerate(nod_names, start=1):
            key = f"vals_nod_var{i}"
            if key in ds.variables:
                arr = _get_var(ds, key)
                if arr.ndim == 1:
                    arr = arr[:, None]
                data.node_vars[name] = np.ascontiguousarray(
                    arr, dtype=np.float64
                )

        # --- Global variables ---
        glo_names = _read_names(ds, "name_glo_var") or []
        if glo_names and "vals_glo_var" in ds.variables:
            glo_all = np.array(ds.variables["vals_glo_var"][:])
            for i, name in enumerate(glo_names):
                data.glob_vars[name] = np.ascontiguousarray(
                    glo_all[:, i], dtype=np.float64
                )

        # --- Time ---
        if "time_whole" in ds.variables:
            data.time = np.ascontiguousarray(
                np.array(ds.variables["time_whole"][:]), dtype=np.float64
            )

    return data


__all__ = ["ExodusData", "ExodusError", "load_exodus"]
