# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Example 4: Mesh and run the 3D monoblock thermo-mechanical simulation."""

from pathlib import Path
import tempfile

from rabbit.sims import (
    EDims,
    monoblock_geo_path,
    monoblock_input_path,
    run_gmsh,
    run_rabbit,
)


def main() -> None:
    """Generate monoblock 3D mesh via Gmsh and run thermo-mechanical solve."""
    geo_path: Path = monoblock_geo_path()
    input_path: Path = monoblock_input_path()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        msh_path = tmp_path / "monoblock3d.msh"

        print(f"Generating mesh from {geo_path.name} -> {msh_path.name}...")
        run_gmsh(geo_path, out_msh_path=msh_path, dims=EDims.THREED, order=2)

        print(f"Running simulation: {input_path.name}...")
        result = run_rabbit(input_path, cwd=tmp_path)
        print(f"Process completed with exit code: {result.returncode}")
        outputs = list(tmp_path.glob("*.e"))
        print(f"Generated output files: {[f.name for f in outputs]}")


if __name__ == "__main__":
    main()
