# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Generate gold reference data for cube thermo-mechanical regression tests.

Runs each ``cube_thermomech_*`` case with a short ``end_time`` override,
reads the resulting Exodus output with :mod:`rabbit.exodus`, and stores a
compressed ``.npz`` snapshot per element type under ``test/gold/``.

Usage:
    PYTHONPATH=src python scripts/generate_cube_gold.py [--elem HEX8]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "src"))

from rabbit.exodus import load_exodus  # noqa: E402
from rabbit.sims import EElemType, cube_thermomech_input_path, run_rabbit  # noqa: E402

GOLD_DIR = REPO_DIR / "test" / "gold"
END_TIME = "1"


def generate_one(elem_type: EElemType, *, force: bool = False) -> Path:
    """Run one cube case and write its gold ``.npz`` snapshot."""
    out_path = GOLD_DIR / f"cube_thermomech_{elem_type.value}.npz"
    if out_path.is_file() and not force:
        print(f"Gold exists, skipping (use --force to overwrite): {out_path}")
        return out_path

    import numpy as np

    input_file = cube_thermomech_input_path(elem_type)
    with tempfile.TemporaryDirectory(prefix="rabbit_gold_") as tmp:
        tmp_path = Path(tmp)
        run_rabbit(
            input_file,
            extra_args=[f"Executioner/end_time={END_TIME}"],
            cwd=tmp_path,
        )
        exodus_files = sorted(tmp_path.glob("*.e"))
        if not exodus_files:
            raise FileNotFoundError(f"No Exodus output for {elem_type}")
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
    import numpy as np  # noqa: F811

    np.savez_compressed(out_path, **payload)
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    return out_path


def main() -> None:
    """Generate gold snapshots for the requested element types."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--elem",
        default="all",
        help="Element type (e.g. HEX8) or 'all' (default).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing gold files.",
    )
    args = parser.parse_args()

    if args.elem.lower() == "all":
        elem_types = list(EElemType)
    else:
        elem_types = [EElemType(args.elem.upper())]

    for elem_type in elem_types:
        generate_one(elem_type, force=args.force)


if __name__ == "__main__":
    main()
