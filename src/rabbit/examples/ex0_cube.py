# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Example 0: Run the thermo-mechanical cube benchmark (HEX8)."""

from pathlib import Path
import tempfile

from rabbit.sims import (
    EElemType,
    cube_thermomech_input_path,
    run_rabbit,
)


def main() -> None:
    """Execute the HEX8 thermo-mechanical cube simulation."""
    input_path: Path = cube_thermomech_input_path(EElemType.HEX8)
    print(f"Running cube benchmark: {input_path}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = run_rabbit(input_path, cwd=tmp_path)
        print(f"Process completed with exit code: {result.returncode}")
        outputs = list(tmp_path.glob("*.e"))
        print(f"Generated output files: {[f.name for f in outputs]}")


if __name__ == "__main__":
    main()
