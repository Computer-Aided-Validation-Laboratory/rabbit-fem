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
import sys
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


def test_binary_and_library_relocatability(tmp_path: Path) -> None:
    """Verify that binary and shared libs contain no hardcoded host paths and run relocated."""
    import os
    import shutil
    import struct
    import subprocess
    from rabbit.cli import get_binary_path, get_library_dir
    from rabbit.sims import cube_thermomech_input_path, EElemType

    rabbit_bin = get_binary_path()
    lib_dir = get_library_dir()

    if sys.platform == "win32":
        # 1. Audit PE Import Directory: zero compiler or MSYS2 DLL dependencies
        def _get_pe_imported_dlls(exe_path: Path) -> list[str]:
            with open(exe_path, "rb") as f:
                dos = f.read(64)
                if len(dos) < 64 or dos[:2] != b"MZ":
                    return []
                pe_offset = struct.unpack("<I", dos[60:64])[0]
                f.seek(pe_offset)
                if f.read(4) != b"PE\x00\x00":
                    return []
                f.seek(pe_offset + 4 + 20)
                is_64 = struct.unpack("<H", f.read(2))[0] == 0x20B
                import_rva_offset = pe_offset + 24 + (120 if is_64 else 104)
                f.seek(import_rva_offset)
                import_rva, _ = struct.unpack("<II", f.read(8))
                if not import_rva:
                    return []

                f.seek(pe_offset + 4 + 2)
                num_sections = struct.unpack("<H", f.read(2))[0]
                f.seek(pe_offset + 4 + 16)
                opt_header_size = struct.unpack("<H", f.read(2))[0]
                sections = []
                f.seek(pe_offset + 24 + opt_header_size)
                for _ in range(num_sections):
                    sec = f.read(40)
                    vsize, vaddr, rsize, raddr = struct.unpack("<IIII", sec[8:24])
                    sections.append((vaddr, vsize, raddr, rsize))

                def _rva_to_offset(rva: int) -> int | None:
                    for vaddr, vsize, raddr, _ in sections:
                        if vaddr <= rva < vaddr + vsize:
                            return raddr + (rva - vaddr)
                    return None

                import_offset = _rva_to_offset(import_rva)
                dlls = []
                if import_offset:
                    f.seek(import_offset)
                    while True:
                        desc = f.read(20)
                        if len(desc) < 20 or desc == b"\x00" * 20:
                            break
                        _, _, _, name_rva, _ = struct.unpack("<IIIII", desc)
                        name_offset = _rva_to_offset(name_rva)
                        if name_offset:
                            cur = f.tell()
                            f.seek(name_offset)
                            dll_name = b""
                            while True:
                                ch = f.read(1)
                                if ch in (b"\x00", b""):
                                    break
                                dll_name += ch
                            dlls.append(dll_name.decode("utf-8", errors="ignore"))
                            f.seek(cur)
                return dlls

        dlls = _get_pe_imported_dlls(rabbit_bin)
        assert dlls, "No PE imports found in rabbit binary"
        forbidden_substrings = (
            "msys", "cygwin", "mingw", "libgcc", "libstdc", "libwinpthread", "libgfortran"
        )
        for dll in dlls:
            dll_lower = dll.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in dll_lower, f"Forbidden DLL '{dll}' imported by rabbit binary"

        # 2. Test out-of-tree execution in an isolated directory without build environment on PATH
        isolated_dir = tmp_path / "rabbit_isolated"
        isolated_dir.mkdir(parents=True, exist_ok=True)
        isolated_bin = isolated_dir / "rabbit.exe"
        shutil.copy2(rabbit_bin, isolated_bin)

        clean_env = {
            "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
            "PATH": r"C:\Windows\System32;C:\Windows",
        }
        res_version = subprocess.run(
            [str(isolated_bin), "--version"],
            env=clean_env,
            capture_output=True,
            text=True,
            cwd=str(isolated_dir),
        )
        assert res_version.returncode == 0
        assert "Application Version" in res_version.stdout

        # 3. Test solve execution from isolated directory
        input_path = cube_thermomech_input_path(EElemType.HEX8)
        res_solve = subprocess.run(
            [str(isolated_bin), "-i", str(input_path), "Executioner/end_time=1", "-pc_type", "ilu"],
            env=clean_env,
            capture_output=True,
            text=True,
            cwd=str(isolated_dir),
        )
        assert res_solve.returncode == 0
        exodus_files = list(isolated_dir.glob("*.e"))
        assert len(exodus_files) >= 1
        assert exodus_files[0].stat().st_size > 0

    elif sys.platform == "darwin":
        # macOS Mach-O relocatability checks via otool
        def _get_linked_libs(macho_path: Path) -> list[str]:
            res = subprocess.check_output(
                ["otool", "-L", str(macho_path)], text=True
            )
            libs: list[str] = []
            for line in res.splitlines()[1:]:
                stripped = line.strip()
                if stripped:
                    libs.append(stripped.split()[0])
            return libs

        def _get_rpaths(macho_path: Path) -> list[str]:
            res = subprocess.check_output(
                ["otool", "-l", str(macho_path)], text=True
            )
            rpaths: list[str] = []
            in_rpath = False
            for line in res.splitlines():
                stripped = line.strip()
                if stripped == "cmd LC_RPATH":
                    in_rpath = True
                elif stripped.startswith("cmd "):
                    in_rpath = False
                elif in_rpath and stripped.startswith("path "):
                    rpaths.append(stripped.split()[1])
                    in_rpath = False
            return rpaths

        # 1. Linked libraries must not contain hardcoded user or build dirs
        linked_libs = _get_linked_libs(rabbit_bin)
        assert linked_libs, "No linked libraries found in rabbit binary"
        for dep in linked_libs:
            if dep.startswith("@"):
                continue
            for forbidden in ("/Users/", "/home/", "/tmp/", "/opt/moose"):
                assert forbidden not in dep, (
                    f"Forbidden hardcoded path '{dep}' linked by rabbit binary"
                )

        # 2. All RPATHs on the binary and bundled dylibs must be
        # @loader_path-relative (never absolute build directories)
        macho_files = [rabbit_bin]
        if lib_dir.is_dir():
            macho_files.extend(
                f
                for f in lib_dir.glob("*.dylib*")
                if f.is_file() and not f.is_symlink()
            )
        for macho_file in macho_files:
            for rpath in _get_rpaths(macho_file):
                assert rpath.startswith("@loader_path"), (
                    f"Non-relocatable RPATH '{rpath}' in {macho_file.name}"
                )
                for forbidden in ("/Users/", "/home/", "/tmp/", "/opt/moose"):
                    assert forbidden not in rpath

        # 3. Relocated execution: copy binary and bundled libs to an
        # isolated directory, strip build environment variables, and run
        # a real solve there. Mirror the staged bin/ + lib/ sibling
        # layout: the binary's RPATH is @loader_path/../lib, so a
        # nested lib/ dir would resolve @rpath outside the copy.
        isolated_dir = tmp_path / "rabbit_isolated"
        isolated_bin_dir = isolated_dir / "bin"
        isolated_lib = isolated_dir / "lib"
        isolated_bin_dir.mkdir(parents=True, exist_ok=True)
        isolated_lib.mkdir(parents=True, exist_ok=True)
        isolated_bin = isolated_bin_dir / "rabbit"
        shutil.copy2(rabbit_bin, isolated_bin)
        if lib_dir.is_dir():
            for staged_lib in lib_dir.glob("*.dylib*"):
                if staged_lib.is_file():
                    shutil.copy2(staged_lib, isolated_lib / staged_lib.name)
        os.chmod(isolated_bin, 0o755)

        clean_env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(
                ("MOOSE", "PETSC", "SLEPC", "LIBMESH", "LD_LIBRARY", "DYLD_")
            )
        }
        res_version = subprocess.run(
            [str(isolated_bin), "--version"],
            env=clean_env,
            capture_output=True,
            text=True,
            cwd=str(isolated_dir),
        )
        assert res_version.returncode == 0
        assert "Application Version" in res_version.stdout

        input_path = cube_thermomech_input_path(EElemType.HEX8)
        res_solve = subprocess.run(
            [str(isolated_bin), "-i", str(input_path)],
            env=clean_env,
            capture_output=True,
            text=True,
            cwd=str(isolated_dir),
        )
        assert res_solve.returncode == 0
        exodus_files = list(isolated_dir.glob("*.e"))
        assert len(exodus_files) >= 1
        assert exodus_files[0].stat().st_size > 0

    else:
        # Linux ELF relocatability checks
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
                if target_path.startswith("/home/"):
                    resolved_target = Path(target_path).resolve()
                    assert resolved_target.is_relative_to(lib_dir.resolve())


