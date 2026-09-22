# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Integration test suite for Rabbit simulations and Gmsh workflow."""

from pathlib import Path
import pytest

from rabbit.sims import (
    EDims,
    EElemType,
    cube_thermomech_input_path,
    dogbone_geo_path,
    dogbone_input_path,
    monoblock_geo_path,
    monoblock_input_path,
    plate_tensile_geo_path,
    plate_tensile_input_path,
    run_gmsh,
    run_rabbit,
    stc_data_path,
    stc_geo_path,
    stc_input_path,
)


def test_dataset_paths_exist() -> None:
    """Verify all simulation dataset accessors point to existing files."""
    for elem in EElemType:
        assert cube_thermomech_input_path(elem).is_file()

    assert dogbone_geo_path(EDims.TWOD).is_file()
    assert dogbone_geo_path(EDims.THREED).is_file()
    assert dogbone_input_path(EDims.TWOD).is_file()
    assert dogbone_input_path(EDims.THREED).is_file()
    assert dogbone_input_path(EDims.THREED, is_plastic=True).is_file()

    assert monoblock_geo_path().is_file()
    assert monoblock_input_path().is_file()

    assert plate_tensile_geo_path("hole2d").is_file()
    assert plate_tensile_geo_path("hole3d").is_file()
    assert plate_tensile_geo_path("notch2d").is_file()
    assert plate_tensile_geo_path("notch3d").is_file()
    assert plate_tensile_input_path("hole2d_elas").is_file()
    assert plate_tensile_input_path("hole3d_elas").is_file()

    assert stc_geo_path().is_file()
    assert stc_input_path("stc_therm_unifhf_wrad_std_ad").is_file()
    assert stc_data_path("ss316L_density_K.csv").is_file()


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
def test_cube_thermomech_execution(
    elem_type: EElemType,
    tmp_path: Path,
) -> None:
    """Verify execution of each thermo-mechanical cube element benchmark.

    Parameters
    ----------
    elem_type : EElemType
        Element topology to test.
    tmp_path : Path
        Temporary test directory fixture.
    """
    input_file: Path = cube_thermomech_input_path(elem_type)
    # Shorten end_time to 1 for quick regression verification
    override_args = ["Executioner/end_time=1"]
    res = run_rabbit(input_file, extra_args=override_args, cwd=tmp_path)

    assert res.returncode == 0
    exodus_files = list(tmp_path.glob("*.e"))
    assert len(exodus_files) >= 1
    assert exodus_files[0].stat().st_size > 0


def test_gmsh_to_moose_dogbone2d(tmp_path: Path) -> None:
    """Verify Gmsh mesh generation and MOOSE solve for 2D dogbone.

    Parameters
    ----------
    tmp_path : Path
        Temporary test directory fixture.
    """
    geo_file = dogbone_geo_path(EDims.TWOD)
    msh_file = tmp_path / "dogbone2d.msh"
    run_gmsh(geo_file, out_msh_path=msh_file, dims=EDims.TWOD, order=1)

    assert msh_file.is_file()
    assert msh_file.stat().st_size > 0

    input_file = dogbone_input_path(EDims.TWOD)
    override_args = ["Executioner/end_time=1"]
    res = run_rabbit(input_file, extra_args=override_args, cwd=tmp_path)

    assert res.returncode == 0
    exodus_files = list(tmp_path.glob("*.e"))
    assert len(exodus_files) >= 1
    assert exodus_files[0].stat().st_size > 0


def test_gmsh_to_moose_hole2d(tmp_path: Path) -> None:
    """Verify Gmsh mesh generation and MOOSE solve for plate with hole.

    Parameters
    ----------
    tmp_path : Path
        Temporary test directory fixture.
    """
    geo_file = plate_tensile_geo_path("hole2d")
    msh_file = tmp_path / "mesh2d_holeplate.msh"
    run_gmsh(geo_file, out_msh_path=msh_file, dims=EDims.TWOD, order=1)

    assert msh_file.is_file()
    assert msh_file.stat().st_size > 0

    input_file = plate_tensile_input_path("hole2d_elas")
    override_args = ["Executioner/end_time=1"]
    res = run_rabbit(input_file, extra_args=override_args, cwd=tmp_path)

    assert res.returncode == 0
    exodus_files = list(tmp_path.glob("*.e"))
    assert len(exodus_files) >= 1
    assert exodus_files[0].stat().st_size > 0


def test_binary_and_library_relocatability() -> None:
    """Verify that binary and shared libs contain no hardcoded host paths."""
    import os
    import subprocess
    from rabbit.cli import get_binary_path, get_library_dir

    rabbit_bin = get_binary_path()
    lib_dir = get_library_dir()

    def _get_rpath(elf_path: Path) -> str:
        res = subprocess.check_output(
            ["readelf", "-d", str(elf_path)], text=True
        )
        rpaths: list[str] = []
        for line in res.splitlines():
            if "(RUNPATH)" in line or "(RPATH)" in line:
                rpaths.append(line.split("[")[1].split("]")[0])
        return ":".join(rpaths)

    # 1. Binary RPATH must not contain hardcoded user or build dirs
    bin_rpath = _get_rpath(rabbit_bin)
    for forbidden in ("/home/", "/tmp/", "/opt/moose"):
        assert forbidden not in bin_rpath

    # 2. All bundled .so libraries must have relocatable RPATHs
    if lib_dir.is_dir():
        for so_file in lib_dir.glob("*.so*"):
            if so_file.is_file() and not so_file.is_symlink():
                so_rpath = _get_rpath(so_file)
                for forbidden in ("/home/", "/tmp/", "/opt/moose"):
                    assert forbidden not in so_rpath

    # 3. Dynamic linker check with MOOSE_DIR and LD_LIBRARY_PATH unset
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(
            ("MOOSE", "PETSC", "SLEPC", "LIBMESH", "LD_LIBRARY")
        )
    }
    clean_env["LD_LIBRARY_PATH"] = ""
    ldd_res = subprocess.check_output(
        ["ldd", str(rabbit_bin)], env=clean_env, text=True
    )
    for line in ldd_res.splitlines():
        if "=>" in line:
            _, target = line.split("=>", 1)
            target_path = target.strip().split(" ")[0]
            # Ensure no system MOOSE or home-directory libs leak in
            if target_path.startswith("/home/"):
                resolved_target = Path(target_path).resolve()
                assert resolved_target.is_relative_to(lib_dir.resolve())


