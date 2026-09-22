# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Example 2: Mesh and run the 2D elastic plate with hole simulation."""

from pathlib import Path
import tempfile

from rabbit.sims import (
    EDims,
    plate_tensile_geo_path,
    plate_tensile_input_path,
    run_gmsh,
    run_rabbit,
)


def main() -> None:
    """Generate plate mesh with hole via Gmsh and run elastic simulation."""
    geo_path: Path = plate_tensile_geo_path("hole2d")
    input_path: Path = plate_tensile_input_path("hole2d_elas")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        msh_path = tmp_path / "mesh2d_holeplate.msh"

        print(f"Generating mesh from {geo_path.name} -> {msh_path.name}...")
        run_gmsh(geo_path, out_msh_path=msh_path, dims=EDims.TWOD, order=1)

        print(f"Running simulation: {input_path.name}...")
        result = run_rabbit(input_path, cwd=tmp_path)
        print(f"Process completed with exit code: {result.returncode}")
        outputs = list(tmp_path.glob("*.e"))
        print(f"Generated output files: {[f.name for f in outputs]}")


if __name__ == "__main__":
    main()
