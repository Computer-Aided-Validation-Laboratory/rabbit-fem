# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Example 3: Mesh and run the steady-state STC thermal simulation."""

from pathlib import Path
import shutil
import tempfile

from rabbit.sims import (
    EDims,
    run_gmsh,
    run_rabbit,
    stc_geo_path,
    stc_input_path,
)


def main() -> None:
    """Generate STC 3D mesh via Gmsh and run steady-state thermal solve."""
    geo_path: Path = stc_geo_path()
    input_path: Path = stc_input_path("stc_therm_unifhf_wrad_std_ad")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        msh_path = tmp_path / "stc_astested.msh"

        # Copy data directory into the working directory for tabular properties
        data_src = input_path.parent / "data"
        if data_src.is_dir():
            shutil.copytree(data_src, tmp_path / "data")

        print(f"Generating mesh from {geo_path.name} -> {msh_path.name}...")
        run_gmsh(geo_path, out_msh_path=msh_path, dims=EDims.THREED, order=2)

        print(f"Running simulation: {input_path.name}...")
        result = run_rabbit(input_path, cwd=tmp_path)
        print(f"Process completed with exit code: {result.returncode}")
        outputs = list(tmp_path.glob("*.e"))
        print(f"Generated output files: {[f.name for f in outputs]}")


if __name__ == "__main__":
    main()
