# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Gold regression test for the representative electromagnetics solve.

Runs the packaged ``vector_kernels`` case and compares mesh, nodal
fields, and global postprocessors against the committed snapshot in
``test/gold/`` within floating point tolerance.

Regenerate the snapshot after an intentional physics change with:
    PYTHONPATH=src python scripts/generate_em_gold.py --force
"""

from pathlib import Path

import numpy as np
import pytest

from rabbit.exodus import load_exodus
from rabbit.sims import em_input_path, run_rabbit

GOLD_DIR = Path(__file__).resolve().parent / "gold"
EM_GOLD_CASE = "vector_kernels"
EM_GOLD_FILE = GOLD_DIR / f"em_{EM_GOLD_CASE}.npz"

# Same tolerances as the cube gold test: the solver converges to ~1e-6;
# allow an order of slack for cross-platform BLAS. Generated meshes must
# be bit-identical up to roundoff.
FIELD_RTOL = 1e-5
FIELD_ATOL = 1e-8
MESH_ATOL = 1e-12


def test_em_gold_regression(tmp_path: Path) -> None:
    """Verify the representative EM solve matches its gold snapshot."""
    if not EM_GOLD_FILE.is_file():
        pytest.fail(
            f"Gold file missing: {EM_GOLD_FILE}. Regenerate with "
            "'PYTHONPATH=src python scripts/generate_em_gold.py'."
        )
    input_file = em_input_path(EM_GOLD_CASE)
    run_rabbit(input_file, cwd=tmp_path)
    exodus_files = sorted(tmp_path.glob("*.e"))
    assert exodus_files, f"No Exodus output produced for {EM_GOLD_CASE}"

    got = load_exodus(exodus_files[0])
    gold = dict(np.load(EM_GOLD_FILE, allow_pickle=False))

    # --- Mesh: coords, connectivity, time must match (near-)exactly ---
    np.testing.assert_allclose(
        got.coords,
        gold["coords"],
        rtol=0.0,
        atol=MESH_ATOL,
        err_msg="[em] nodal coordinates differ from gold",
    )
    for key, table in got.connect.items():
        gold_key = f"connect_{key}"
        assert gold_key in gold, f"[em] gold missing {gold_key}"
        np.testing.assert_array_equal(
            table,
            gold[gold_key],
            err_msg=f"[em] connectivity {key} differs from gold",
        )
    np.testing.assert_allclose(
        got.time,
        gold["time"],
        rtol=0.0,
        atol=0.0,
        err_msg="[em] time steps differ from gold",
    )

    # --- Nodal fields: whatever the EM solve wrote ---
    assert got.node_vars, "[em] solve produced no nodal fields"
    for name in got.node_vars:
        assert f"nodal_{name}" in gold, (
            f"[em] field '{name}' missing from gold snapshot"
        )
        np.testing.assert_allclose(
            got.node_vars[name],
            gold[f"nodal_{name}"],
            rtol=FIELD_RTOL,
            atol=FIELD_ATOL,
            err_msg=f"[em] nodal field '{name}' differs from gold",
        )

    # --- Global postprocessors (compared when the gold has them) ---
    for name, values in got.glob_vars.items():
        gold_key = f"global_{name}"
        if gold_key not in gold:
            continue
        np.testing.assert_allclose(
            values,
            gold[gold_key],
            rtol=FIELD_RTOL,
            atol=FIELD_ATOL,
            err_msg=f"[em] global '{name}' differs from gold",
        )
