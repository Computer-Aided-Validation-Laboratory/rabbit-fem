# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Generate gold reference data for the representative MFEM regression test.

Runs the ``curlcurl`` Maxwell-via-MFEM case (singleton rank for
deterministic partitioning), reads its CSV line samples, and stores a
compressed ``.npz`` snapshot under ``test/gold/``. Requires an
MFEM-enabled (MPI-variant) binary.

Usage:
    PYTHONPATH=src python scripts/generate_mfem_gold.py [--force]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "src"))

from rabbit.sims import mfem_input_path, mfem_mesh_path, run_rabbit  # noqa: E402

GOLD_DIR = REPO_DIR / "test" / "gold"
MFEM_GOLD_CASE = "curlcurl"

#: CSV outputs of the curlcurl case, relative to the run directory.
GOLD_CSVS = (
    "OutputData/CurlCurl/curlcurl_line_sample_e_field_0001.csv",
    "OutputData/CurlCurl/curlcurl_line_sample_db_dt_field_0001.csv",
)


def _read_csv_numbers(path: Path) -> tuple[list[str], "object"]:
    """Read a MOOSE CSV (header row + numeric rows) into header + array."""
    import numpy as np

    lines = path.read_text(encoding="utf-8").splitlines()
    header = [h.strip() for h in lines[0].split(",")]
    values = np.loadtxt(path, delimiter=",", skiprows=1)
    return header, values


def generate(force: bool = False) -> Path:
    """Run the representative MFEM case and write its gold snapshot."""
    import numpy as np

    out_path = GOLD_DIR / f"mfem_{MFEM_GOLD_CASE}.npz"
    if out_path.is_file() and not force:
        print(f"Gold exists, skipping (use --force to overwrite): {out_path}")
        return out_path

    input_file = mfem_input_path(MFEM_GOLD_CASE)
    mesh_file = mfem_mesh_path(MFEM_GOLD_CASE)
    with tempfile.TemporaryDirectory(prefix="rabbit_mfem_gold_") as tmp:
        tmp_path = Path(tmp)
        run_rabbit(
            input_file,
            extra_args=[f"Mesh/file={mesh_file}"],
            cwd=tmp_path,
        )
        payload: dict[str, object] = {}
        for rel in GOLD_CSVS:
            csv_path = tmp_path / rel
            if not csv_path.is_file():
                raise FileNotFoundError(f"No CSV output at {csv_path}")
            header, values = _read_csv_numbers(csv_path)
            key = Path(rel).name.removesuffix(".csv")
            payload[f"{key}__header"] = np.array(header)
            payload[f"{key}__values"] = values

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, **payload)
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    return out_path


def main() -> None:
    """Generate the MFEM gold snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing gold file.",
    )
    args = parser.parse_args()
    generate(force=args.force)


if __name__ == "__main__":
    main()
