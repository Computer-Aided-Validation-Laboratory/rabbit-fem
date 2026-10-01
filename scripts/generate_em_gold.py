# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Generate gold reference data for the representative EM regression test.

Runs the ``vector_kernels`` electromagnetics case, reads the resulting
Exodus output with :mod:`rabbit.exodus`, and stores a compressed
``.npz`` snapshot under ``test/gold/``.

Usage:
    PYTHONPATH=src python scripts/generate_em_gold.py [--force]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "src"))

from rabbit.exodus import load_exodus  # noqa: E402
from rabbit.sims import em_input_path, run_rabbit  # noqa: E402

GOLD_DIR = REPO_DIR / "test" / "gold"
EM_GOLD_CASE = "vector_kernels"


def generate(force: bool = False) -> Path:
    """Run the representative EM case and write its gold snapshot."""
    out_path = GOLD_DIR / f"em_{EM_GOLD_CASE}.npz"
    if out_path.is_file() and not force:
        print(f"Gold exists, skipping (use --force to overwrite): {out_path}")
        return out_path

    import numpy as np

    input_file = em_input_path(EM_GOLD_CASE)
    with tempfile.TemporaryDirectory(prefix="rabbit_em_gold_") as tmp:
        tmp_path = Path(tmp)
        run_rabbit(input_file, cwd=tmp_path)
        exodus_files = sorted(tmp_path.glob("*.e"))
        if not exodus_files:
            raise FileNotFoundError(f"No Exodus output for {EM_GOLD_CASE}")
        data = load_exodus(exodus_files[0])

    payload: dict[str, object] = {
        "coords": data.coords,
        "time": data.time,
        "node_var_names": np.array(sorted(data.node_vars)),
        "glob_var_names": np.array(sorted(data.glob_vars)),
    }
    for key, arr in data.connect.items():
        payload[f"connect_{key}"] = arr
    for name, arr in data.node_vars.items():
        payload[f"nodal_{name}"] = arr
    for name, arr in data.glob_vars.items():
        payload[f"global_{name}"] = arr

    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(out_path, **payload)
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    return out_path


def main() -> None:
    """Generate the EM gold snapshot."""
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
