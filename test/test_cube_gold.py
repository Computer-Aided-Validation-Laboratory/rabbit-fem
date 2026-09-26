# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Gold regression tests for cube thermo-mechanical solves.

Runs each ``cube_thermomech_*`` element case and compares mesh, nodal
fields (temperature, displacement, strain) and global postprocessors
against committed snapshots in ``test/gold/`` within floating point
tolerance.

Regenerate snapshots after intentional physics changes with:
    PYTHONPATH=src python scripts/generate_cube_gold.py --force
"""

from pathlib import Path

import numpy as np
import pytest

from rabbit.exodus import load_exodus
from rabbit.sims import EElemType, cube_thermomech_input_path, run_rabbit

GOLD_DIR = Path(__file__).resolve().parent / "gold"

# Solver converges to ~1e-6; allow an order of slack for cross-platform BLAS.
FIELD_RTOL = 1e-5
FIELD_ATOL = 1e-8
# Generated meshes must be bit-identical up to roundoff.
MESH_ATOL = 1e-12

CHECK_FIELDS = (
    "temperature",
    "disp_x",
    "disp_y",
    "disp_z",
    "strain_xx",
    "strain_yy",
    "strain_zz",
    "strain_xy",
    "strain_yz",
    "strain_xz",
)


def _load_gold(elem_type: EElemType) -> dict:
    """Load the gold snapshot payload for one element type."""
    gold_file = GOLD_DIR / f"cube_thermomech_{elem_type.value}.npz"
    if not gold_file.is_file():
        pytest.fail(
            f"Gold file missing: {gold_file}. Regenerate with "
            "'PYTHONPATH=src python scripts/generate_cube_gold.py'."
        )
    return dict(np.load(gold_file, allow_pickle=False))


@pytest.mark.parametrize(
    "elem_type",
    [
        EElemType.HEX8,
        EElemType.HEX20,
        EElemType.HEX27,
        EElemType.TET4,
        EElemType.TET10,
        EElemType.TET14,
    ],
)
def test_cube_gold_regression(elem_type: EElemType, tmp_path: Path) -> None:
    """Verify solve output matches the gold snapshot within tolerance."""
    input_file: Path = cube_thermomech_input_path(elem_type)
    run_rabbit(
        input_file, extra_args=["Executioner/end_time=1"], cwd=tmp_path
    )
    exodus_files = sorted(tmp_path.glob("*.e"))
    assert exodus_files, f"No Exodus output produced for {elem_type}"

    got = load_exodus(exodus_files[0])
    gold = _load_gold(elem_type)

    # --- Mesh: coords, connectivity, time must match (near-)exactly ---
    np.testing.assert_allclose(
        got.coords,
        gold["coords"],
        rtol=0.0,
        atol=MESH_ATOL,
        err_msg=f"[{elem_type}] nodal coordinates differ from gold",
    )
    for key, table in got.connect.items():
        gold_key = f"connect_{key}"
        assert gold_key in gold, f"[{elem_type}] gold missing {gold_key}"
        np.testing.assert_array_equal(
            table,
            gold[gold_key],
            err_msg=f"[{elem_type}] connectivity {key} differs from gold",
        )
    np.testing.assert_allclose(
        got.time,
        gold["time"],
        rtol=0.0,
        atol=0.0,
        err_msg=f"[{elem_type}] time steps differ from gold",
    )

    # --- Nodal fields: temperature, displacement, strain ---
    for name in CHECK_FIELDS:
        assert name in got.node_vars, (
            f"[{elem_type}] field '{name}' missing from Exodus output "
            f"(have {sorted(got.node_vars)})"
        )
        assert f"nodal_{name}" in gold, (
            f"[{elem_type}] field '{name}' missing from gold snapshot"
        )
        np.testing.assert_allclose(
            got.node_vars[name],
            gold[f"nodal_{name}"],
            rtol=FIELD_RTOL,
            atol=FIELD_ATOL,
            err_msg=f"[{elem_type}] nodal field '{name}' differs from gold",
        )

    # --- Global postprocessors ---
    for name, values in got.glob_vars.items():
        gold_key = f"global_{name}"
        if gold_key not in gold:
            continue
        np.testing.assert_allclose(
            values,
            gold[gold_key],
            rtol=FIELD_RTOL,
            atol=FIELD_ATOL,
            err_msg=f"[{elem_type}] global '{name}' differs from gold",
        )
