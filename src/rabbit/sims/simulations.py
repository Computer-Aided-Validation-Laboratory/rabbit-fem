# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Simulation dataset accessors and mesh/execution helpers for rabbit."""

from enum import Enum
from importlib.resources import files
import os
from pathlib import Path
import subprocess


class EDims(Enum):
    """Spatial dimensionality enumeration."""

    TWOD = "2D"
    THREED = "3D"

    def __str__(self) -> str:
        return self.value


class EElemType(Enum):
    """Element type enumeration for cube benchmarks."""

    TET4 = "TET4"
    TET10 = "TET10"
    TET14 = "TET14"
    HEX8 = "HEX8"
    HEX20 = "HEX20"
    HEX27 = "HEX27"

    def __str__(self) -> str:
        return self.value


class DataSetError(Exception):
    """Raised when simulation datasets or geometry files cannot be resolved."""


SimDataError = DataSetError


def _sim_path(*parts: str) -> Path:
    """Return an installed path below the :mod:`rabbit.sims` package."""
    return Path(files("rabbit.sims").joinpath(*parts))


# ------------------------------------------------------------------------------
# Cube Thermomechanical Benchmarks
# ------------------------------------------------------------------------------


def cube_thermomech_input_path(elem_type: EElemType) -> Path:
    """Get path to the cube thermo-mechanical MOOSE input file (.i).

    Parameters
    ----------
    elem_type : EElemType
        Element topology for the benchmark.

    Returns
    -------
    Path
        Path to the requested .i simulation file.
    """
    filename = f"cube_thermomech_{elem_type.value}.i"
    target = _sim_path("cube_thermomech", filename)
    if not target.is_file():
        raise DataSetError(f"Cube simulation file not found: {target}")
    return target


# ------------------------------------------------------------------------------
# Dogbone Tensile Benchmark
# ------------------------------------------------------------------------------


def dogbone_geo_path(dims: EDims = EDims.TWOD) -> Path:
    """Get path to the dogbone geometry Gmsh file (.geo).

    Parameters
    ----------
    dims : EDims, default=EDims.TWOD
        Dimensionality of the dogbone geometry (2D or 3D).

    Returns
    -------
    Path
        Path to the requested .geo geometry file.
    """
    stem = "dogbone2d" if dims == EDims.TWOD else "dogbone3d"
    target = _sim_path("dogbone", f"{stem}.geo")
    if not target.is_file():
        raise DataSetError(f"Dogbone geometry file not found: {target}")
    return target


def dogbone_input_path(
    dims: EDims = EDims.TWOD,
    *,
    is_plastic: bool = False,
) -> Path:
    """Get path to the dogbone simulation input file (.i).

    Parameters
    ----------
    dims : EDims, default=EDims.TWOD
        Dimensionality of the simulation (2D or 3D).
    is_plastic : bool, default=False
        If True, returns the elastoplastic input file (3D only).

    Returns
    -------
    Path
        Path to the requested .i simulation file.
    """
    if dims == EDims.TWOD:
        if is_plastic:
            raise DataSetError("2D plastic dogbone case is not available.")
        target = _sim_path("dogbone", "dogbone2d_elas.i")
    else:
        filename = (
            "dogbone3d_plas_ad.i" if is_plastic else "dogbone3d_elas.i"
        )
        target = _sim_path("dogbone", filename)

    if not target.is_file():
        raise DataSetError(f"Dogbone input file not found: {target}")
    return target


# ------------------------------------------------------------------------------
# Monoblock Thermomechanical Case
# ------------------------------------------------------------------------------


def monoblock_geo_path() -> Path:
    """Get path to the monoblock divertor Gmsh geometry file (.geo).

    Returns
    -------
    Path
        Path to monoblock3d_mesh.geo.
    """
    target = _sim_path("monoblock_thermomech", "monoblock3d_mesh.geo")
    if not target.is_file():
        raise DataSetError(f"Monoblock geo file not found: {target}")
    return target


def monoblock_input_path() -> Path:
    """Get path to the monoblock thermo-mechanical input file (.i).

    Returns
    -------
    Path
        Path to monoblock3d_thermomech.i.
    """
    target = _sim_path("monoblock_thermomech", "monoblock3d_thermomech.i")
    if not target.is_file():
        raise DataSetError(f"Monoblock input file not found: {target}")
    return target


# ------------------------------------------------------------------------------
# Plate Tensile Cases (Hole & Notch)
# ------------------------------------------------------------------------------


def plate_tensile_geo_path(case_name: str) -> Path:
    """Get path to a plate tensile Gmsh geometry file (.geo).

    Parameters
    ----------
    case_name : str
        Name of the case (e.g. 'hole2d', 'hole3d', 'notch2d', 'notch3d').

    Returns
    -------
    Path
        Path to the .geo file.
    """
    mapping: dict[str, str] = {
        "hole2d": "hole2d_plate_mesh.geo",
        "hole3d": "hole3d_mesh_plate.geo",
        "notch2d": "notch2d_mesh.geo",
        "notch3d": "notch3d_mesh.geo",
    }
    filename = mapping.get(case_name, f"{case_name}.geo")
    target = _sim_path("plate_tensile", filename)
    if not target.is_file():
        raise DataSetError(f"Plate tensile geo file not found: {target}")
    return target


def plate_tensile_input_path(case_name: str) -> Path:
    """Get path to a plate tensile simulation input file (.i).

    Parameters
    ----------
    case_name : str
        Simulation case stem (e.g. 'hole2d_elas', 'hole3d_elas',
        'notch2d_elas', 'notch3d_elas', 'hole2d_plas', etc.).

    Returns
    -------
    Path
        Path to the .i file.
    """
    filename = (
        case_name if case_name.endswith(".i") else f"{case_name}.i"
    )
    target = _sim_path("plate_tensile", filename)
    if not target.is_file():
        raise DataSetError(f"Plate tensile input file not found: {target}")
    return target


# ------------------------------------------------------------------------------
# STC Thermal Benchmark Cases
# ------------------------------------------------------------------------------


def stc_geo_path() -> Path:
    """Get path to the STC geometry Gmsh file (.geo).

    Returns
    -------
    Path
        Path to stc_astested.geo.
    """
    target = _sim_path("stc", "stc_astested.geo")
    if not target.is_file():
        raise DataSetError(f"STC geo file not found: {target}")
    return target


def stc_input_path(case_name: str = "stc_therm_unifhf_wrad_std_ad") -> Path:
    """Get path to an STC simulation input file (.i).

    Parameters
    ----------
    case_name : str, default='stc_therm_unifhf_wrad_std_ad'
        Input file name or stem.

    Returns
    -------
    Path
        Path to the .i file.
    """
    filename = (
        case_name if case_name.endswith(".i") else f"{case_name}.i"
    )
    target = _sim_path("stc", filename)
    if not target.is_file():
        raise DataSetError(f"STC input file not found: {target}")
    return target


def stc_data_path(filename: str) -> Path:
    """Get path to an STC material data CSV file.

    Parameters
    ----------
    filename : str
        CSV filename in stc/data/.

    Returns
    -------
    Path
        Path to the data file.
    """
    target = _sim_path("stc", "data", filename)
    if not target.is_file():
        raise DataSetError(f"STC data file not found: {target}")
    return target


# ------------------------------------------------------------------------------
# Gmsh and Simulation Runner Utilities
# ------------------------------------------------------------------------------


def run_gmsh(
    geo_path: Path | str,
    *,
    out_msh_path: Path | str | None = None,
    dims: EDims = EDims.THREED,
    order: int = 1,
) -> Path:
    """Generate a finite element mesh file using Gmsh.

    Parameters
    ----------
    geo_path : Path | str
        Path to the input .geo script.
    out_msh_path : Path | str | None, optional
        Target .msh output path. If None, generated in the current working
        directory with the same stem and .msh suffix.
    dims : EDims, default=EDims.THREED
        Spatial dimension for mesh generation.
    order : int, default=1
        Element polynomial order (1 for linear, 2 for quadratic).

    Returns
    -------
    Path
        Path to the generated .msh file.
    """
    try:
        import gmsh
    except ImportError as err:
        raise ImportError(
            "Gmsh Python module is required. Install with 'pip install gmsh'."
        ) from err

    geo_p = Path(geo_path).resolve()
    if not geo_p.is_file():
        raise DataSetError(f"Gmsh geometry file not found: {geo_p}")

    if out_msh_path is None:
        out_p = Path.cwd() / f"{geo_p.stem}.msh"
    else:
        out_p = Path(out_msh_path).resolve()

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(geo_p))
        dim_num = 2 if dims == EDims.TWOD else 3
        gmsh.model.mesh.generate(dim_num)
        if order > 1:
            gmsh.model.mesh.setOrder(order)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(out_p))
    finally:
        gmsh.finalize()

    return out_p


def run_rabbit(
    input_path: Path | str,
    *,
    extra_args: list[str] | None = None,
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute the rabbit binary on a MOOSE input file.

    Parameters
    ----------
    input_path : Path | str
        Path to the .i simulation input file.
    extra_args : list[str] | None, optional
        Additional CLI arguments passed to rabbit.
    cwd : Path | str | None, optional
        Working directory for the simulation run.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Result of the subprocess execution.
    """
    from rabbit.cli import get_binary_path, get_library_dir

    bin_path = get_binary_path()
    lib_dir = get_library_dir()
    env = dict(os.environ)
    if lib_dir.is_dir():
        curr_ld = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = (
            f"{lib_dir}:{curr_ld}" if curr_ld else str(lib_dir)
        )

    cmd = [str(bin_path), "-i", str(input_path)]
    if extra_args:
        cmd.extend(extra_args)

    work_dir = Path(cwd).resolve() if cwd else Path.cwd()
    return subprocess.run(
        cmd,
        cwd=str(work_dir),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
