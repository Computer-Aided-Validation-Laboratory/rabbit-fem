# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Gold regression test for the representative MFEM solve.

Runs the packaged ``curlcurl`` Maxwell-via-MFEM case (singleton rank,
so partitioning is deterministic) and compares its CSV line samples
against the committed snapshot in ``test/gold/`` within tolerance.
Skips loudly on binaries without the MFEM backend.

Regenerate the snapshot after an intentional physics change with:
    PYTHONPATH=src python scripts/generate_mfem_gold.py --force
"""

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_mfem import _mfem_backend_available  # noqa: E402
from rabbit.sims import mfem_input_path, mfem_mesh_path, run_rabbit  # noqa: E402

GOLD_DIR = Path(__file__).resolve().parent / "gold"
MFEM_GOLD_CASE = "curlcurl"
MFEM_GOLD_FILE = GOLD_DIR / f"mfem_{MFEM_GOLD_CASE}.npz"

#: CSV outputs of the curlcurl case, relative to the run directory.
GOLD_CSVS = (
    "OutputData/CurlCurl/curlcurl_line_sample_e_field_0001.csv",
    "OutputData/CurlCurl/curlcurl_line_sample_db_dt_field_0001.csv",
)

# GMRES l_tol is 1e-12 on O(1) fields; allow the repo-standard slack
# for cross-platform BLAS.
FIELD_RTOL = 1e-5
FIELD_ATOL = 1e-8


def _csv_key(rel: str) -> str:
    """Snapshot key prefix for one CSV output path."""
    return Path(rel).name.removesuffix(".csv")


def test_mfem_gold_regression(tmp_path: Path) -> None:
    """Verify the MFEM Maxwell solve matches its gold snapshot."""
    if not _mfem_backend_available():
        pytest.skip(
            "MFEM backend not compiled into this binary "
            "(serial builds exclude it; see dev/log_mfem_mpi.md)."
        )
    if not MFEM_GOLD_FILE.is_file():
        pytest.fail(
            f"Gold file missing: {MFEM_GOLD_FILE}. Regenerate with "
            "'PYTHONPATH=src python scripts/generate_mfem_gold.py'."
        )
    input_file = mfem_input_path(MFEM_GOLD_CASE)
    mesh_file = mfem_mesh_path(MFEM_GOLD_CASE)
    run_rabbit(
        input_file,
        extra_args=[f"Mesh/file={mesh_file}"],
        cwd=tmp_path,
    )
    gold = dict(np.load(MFEM_GOLD_FILE, allow_pickle=False))
    for rel in GOLD_CSVS:
        csv_path = tmp_path / rel
        assert csv_path.is_file(), f"Missing CSV output {rel}"
        lines = csv_path.read_text(encoding="utf-8").splitlines()
        header = [h.strip() for h in lines[0].split(",")]
        values = np.loadtxt(csv_path, delimiter=",", skiprows=1)
        key = _csv_key(rel)
        assert list(gold[f"{key}__header"]) == header, (
            f"[{rel}] CSV columns differ from gold"
        )
        np.testing.assert_allclose(
            values,
            gold[f"{key}__values"],
            rtol=FIELD_RTOL,
            atol=FIELD_ATOL,
            err_msg=f"[{rel}] CSV values differ from gold",
        )
