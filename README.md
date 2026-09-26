# rabbit-fem

`rabbit-fem` is a lightweight, standalone Python distribution of the [MOOSE](https://mooseframework.inl.gov/) (Multiphysics Object-Oriented Simulation Environment) finite element framework, tailored specifically for **thermal**, **solid mechanics**, and **contact** simulation.

Packaged as a self-contained Python wheel (~60 MB), `rabbit-fem` provides a drop-in `rabbit` command-line executable and Python dataset API that runs MOOSE simulations without requiring external MOOSE or libMesh system installations.

---

## Key Features

- **Focused Thermo-Mechanical Physics**: Preconfigured with `SolidMechanics`, `HeatTransfer`, `Contact`, `RayTracing`, and `ShiftedBoundaryMethod` modules.
- **Self-Contained & Relocatable**: Ships stripped binaries and shared libraries with relocatable linkage (`$ORIGIN` RPATHs on Linux, `@loader_path` on macOS, fully static executable on Windows) and zero external MOOSE dependency at runtime.
- **Drop-In CLI**: Execute MOOSE input files using `rabbit input.i` or `rabbit -i input.i`.
- **Packaged Simulation Datasets**: Includes standard benchmarks and Gmsh geometry scripts accessible directly through Python.
- **Zig Toolchain Orchestration**: Compiled and linked using `zig cc` / `zig c++` via `ziglang`.

---

## Installation

Install from PyPI:

```bash
# Using pip
pip install rabbit-fem

# Using uv
uv pip install rabbit-fem
```

Or install a locally built wheel (see [Build from Source](#build-from-source)):

```bash
# Using pip
pip install dist/rabbit_fem-*.whl

# Using uv
uv pip install dist/rabbit_fem-*.whl
```

Requires Python 3.10+ (CI builds and tests with Python 3.13).

---

## Usage

### 1. Running Simulations with the `rabbit` CLI

Execute any MOOSE `.i` input file directly from your terminal:

```bash
# Run a packaged thermo-mechanical benchmark directly
rabbit -i $(python -c "from rabbit.sims import cube_thermomech_input_path, EElemType; print(cube_thermomech_input_path(EElemType.HEX8))")

# Or run any local MOOSE simulation
rabbit simulation.i
```

Useful flags (forwarded to the MOOSE application):

```bash
rabbit --version
rabbit --help
```

Run in parallel using OpenMPI (Linux/macOS):

```bash
mpirun -n 4 rabbit simulation.i
```

### 2. Python Dataset and Simulation Runner API

`rabbit-fem` packages simulation files and provides helpers to locate inputs, generate meshes with Gmsh, and execute solves:

```python
from rabbit.sims import (
    EElemType,
    cube_thermomech_input_path,
    run_rabbit,
)

# Locate packaged HEX8 thermo-mechanical cube input
input_file = cube_thermomech_input_path(EElemType.HEX8)

# Execute rabbit on the simulation
result = run_rabbit(input_file)
print("Simulation completed with return code:", result.returncode)
```

---

## Examples

Runnable example scripts demonstrating Gmsh mesh generation and MOOSE simulation execution are located in [`src/rabbit/examples/`](src/rabbit/examples/):

- [`ex0_cube.py`](src/rabbit/examples/ex0_cube.py) — 3D thermo-mechanical cube benchmark on structured HEX8 elements.
- [`ex1_dogbone.py`](src/rabbit/examples/ex1_dogbone.py) — 2D tensile dogbone mesh generation in Gmsh and linear elastic solve.
- [`ex2_tensile_plate.py`](src/rabbit/examples/ex2_tensile_plate.py) — 2D plate with a central hole mesh in Gmsh and elastic tension solve.
- [`ex3_stc_thermal.py`](src/rabbit/examples/ex3_stc_thermal.py) — 3D single thermal component (STC) with radiation and temperature-dependent conductivity.
- [`ex4_monoblock_thermomech.py`](src/rabbit/examples/ex4_monoblock_thermomech.py) — 3D monoblock fusion component mesh generation and coupled thermo-mechanical solve.

Run any example with:

```bash
uv run python src/rabbit/examples/ex0_cube.py
uv run python src/rabbit/examples/ex1_dogbone.py
```

---

## Testing

Run the full test suite from the repository root:

```bash
# Entire suite (unit, simulation, relocatability, gold regression)
pytest test/ -v

# Or via the build orchestrator (same suite)
uv run python build_rabbit.py --test
```

The suite includes:

- **Simulation tests** (`test/test_simulations.py`) — execute packaged benchmarks (cube, dogbone, plate) and verify Exodus output is produced.
- **Relocatability tests** — verify the staged binary carries no hardcoded build-tree paths and runs from an isolated directory.
- **Gold regression tests** (`test/test_cube_gold.py`) — run every `cube_thermomech_*` element case (HEX8/20/27, TET4/10/14) and compare mesh, nodal fields (temperature, displacement, strain), and postprocessors against committed snapshots in [`test/gold/`](test/gold/) within floating point tolerance. Field data is read with the minimal vendored Exodus II reader in [`src/rabbit/exodus.py`](src/rabbit/exodus.py).

After an intentional physics change, regenerate the gold snapshots locally and commit the result:

```bash
PYTHONPATH=src python scripts/generate_cube_gold.py --force
```

Every CI build workflow additionally runs a **clean-venv smoke test** on the already-built wheel: it installs `dist/*.whl` into a fresh virtual environment outside the repo with build environment variables stripped, checks `rabbit --version`, audits linkage for missing libraries, and executes a real HEX8 solve. This catches missing bundled shared libraries that the build-tree test suite cannot see.

---

## Build from Source

### Overview

`rabbit-fem` builds on **Linux** (Ubuntu 22.04+ or compatible), **native Windows** (x86_64), and **macOS** (Apple Silicon and Intel) using the Zig C/C++ compiler from `ziglang==0.16.0`. Compilation is split into five discrete, cacheable stages (also mirrored by the CI dependency caches):

```mermaid
flowchart TD
    S1["Stage 1: PETSc<br/><code>--build-petsc</code>"] --> S2["Stage 2: libMesh<br/><code>--build-libmesh</code>"]
    S2 --> S3["Stage 3: WASP & HIT<br/><code>--build-wasp</code>"]
    S3 --> S4["Stage 4: MOOSE Config<br/><code>--configure-moose</code>"]
    S4 --> S5["Stage 5: Rabbit & Wheel<br/><code>--wheel --test</code>"]
```

| OS | Build driver | Output wheel |
|---|---|---|
| Linux x86_64 | `build_rabbit.py` | `manylinux_2_38_x86_64` |
| Windows x86_64 | `install_dependencies_windows.ps1` + `build_rabbit.py --wheel-only` | `win_amd64` |
| macOS arm64 / x86_64 | `build_rabbit.py` | `macosx_14_0_arm64` / `macosx_13_0_x86_64` |

Upstream MOOSE sources are pinned (`moose_version.txt` plus the `moose_deps.txt` lock for PETSc/libMesh/WASP) so rebuilds are reproducible.

---

### Linux Build & Testing

#### Prerequisites (Linux)

- **OS**: Linux x86_64 (Ubuntu 22.04+ or compatible)
- **System packages**: `build-essential`, `gfortran`, `libopenmpi-dev`, `openmpi-bin`, `patchelf`, `libtirpc-dev`, `libomp-dev`, `libglu1-mesa`
- **Python**: Python 3.10+ with [`uv`](https://docs.astral.sh/uv/)

```bash
sudo apt-get update && sudo apt-get install -y \
    build-essential gfortran libopenmpi-dev openmpi-bin patchelf libtirpc-dev libomp-dev libglu1-mesa

# Set up Python environment
uv venv .venv
uv pip install ziglang==0.16.0 wheel packaging pyyaml jinja2 pytest gmsh numpy netCDF4
```

#### Step 1: Upstream MOOSE Dependencies

Compile all dependencies at once:

```bash
uv run python build_rabbit.py --moose
```

Or execute individual stages independently:

```bash
uv run python build_rabbit.py --build-petsc
uv run python build_rabbit.py --build-libmesh
uv run python build_rabbit.py --build-wasp
uv run python build_rabbit.py --configure-moose
```

#### Step 2: Build Rabbit, Stage Artifacts & Package Wheel

Compiles RabbitApp with the Zig toolchain, strips symbols, rewrites RPATHs with `patchelf`, packages the `.whl` into `dist/`, and runs tests:

```bash
uv run python build_rabbit.py --wheel --test
```

---

### Windows Build & Testing

#### Prerequisites (Windows)

1. **Python 3.10+** (with [`uv`](https://docs.astral.sh/uv/)):
   ```powershell
   winget install astral-sh.uv
   ```
2. **Git Long Paths**:
   ```powershell
   git config --global core.longpaths true
   ```
3. **MSYS2** (used strictly for Unix shell utilities and GNU Make needed by PETSc/libMesh/MOOSE configure and build scripts; compilation itself is handled by Zig):
   ```powershell
   winget install --id MSYS2.MSYS2 --source winget
   C:\msys64\usr\bin\pacman.exe -S --needed --noconfirm make diffutils patch python m4 git cmake
   ```

#### 1-Step Automated Windows Build

Run the automated PowerShell build script from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_dependencies_windows.ps1
```

This script:
- Creates and sets up `.venv` with `uv`.
- Installs Python dependencies (`ziglang`, `packaging`, `pyyaml`, `jinja2`, `pytest`, `gmsh`, `wheel`, `numpy`, `netCDF4`).
- Configures and builds **PETSc**, **libMesh**, **WASP**, and the **MOOSE** framework using the Zig C/C++ compiler.
- Compiles and links `rabbit-opt.exe` with Heat Transfer, Solid Mechanics, Contact, Ray Tracing, and Shifted Boundary Method.
- Stages `rabbit.exe` into `src/rabbit/bin/` and executes the simulation test suite.

#### Running Tests on Windows

Once the environment and binary are built, you can run the test suite in several ways:

1. **Using `uv run`** (Recommended):
   ```powershell
   uv run pytest test/ -v
   ```
   or using the build script:
   ```powershell
   uv run python build_rabbit.py --test
   ```

2. **Using `.venv` directly**:
   ```powershell
   $env:PYTHONPATH = "src"
   .\.venv\Scripts\python.exe -m pytest test/ -v
   ```

#### Building the Standalone Windows Wheel

To package the staged executable into a distributable wheel:

```powershell
uv run python build_rabbit.py --wheel-only --test
```

This generates `dist/rabbit_fem-*-py3-none-win_amd64.whl` (fully self-contained, ~56 MB).

#### Windows PowerShell Stages

`scripts/install_dependencies_windows.ps1` accepts the `-Stage` parameter:

```powershell
# Build individual stages
powershell -ExecutionPolicy Bypass -File scripts\install_dependencies_windows.ps1 -Stage petsc
powershell -ExecutionPolicy Bypass -File scripts\install_dependencies_windows.ps1 -Stage libmesh
powershell -ExecutionPolicy Bypass -File scripts\install_dependencies_windows.ps1 -Stage wasp
powershell -ExecutionPolicy Bypass -File scripts\install_dependencies_windows.ps1 -Stage moose
powershell -ExecutionPolicy Bypass -File scripts\install_dependencies_windows.ps1 -Stage rabbit
powershell -ExecutionPolicy Bypass -File scripts\install_dependencies_windows.ps1 -Stage test

# Full pipeline
powershell -ExecutionPolicy Bypass -File scripts\install_dependencies_windows.ps1 -Stage all
```

---

### macOS Build & Testing

#### Prerequisites (macOS)

- **OS**: macOS on Apple Silicon (arm64) or Intel (x86_64)
- **Homebrew packages**: `open-mpi`, `gcc`, `llvm`, `libomp`, `libpng`, `hdf5-mpi`, `bison`, `flex`, `pkgconf`, `cmake`
- **Python**: Python 3.10+ with [`uv`](https://docs.astral.sh/uv/)

```bash
brew install open-mpi gcc llvm libomp libpng hdf5-mpi bison flex pkgconf cmake

# Set up Python environment
uv venv .venv
uv pip install ziglang==0.16.0 wheel packaging pyyaml jinja2 pytest gmsh numpy netCDF4
```

#### Build Stages

The macOS build follows the same five stages as Linux, driven by `build_rabbit.py` (macOS-specific compiler flags and portability patches live in `scripts/build/darwin.py` and `patches/macos/`):

```bash
# Individual stages
uv run python build_rabbit.py --build-petsc
uv run python build_rabbit.py --build-libmesh
uv run python build_rabbit.py --build-wasp
uv run python build_rabbit.py --configure-moose

# Build Rabbit, package wheel, and test
uv run python build_rabbit.py --wheel --test
```

---

### `build_rabbit.py` Command Reference

| Command / Flag | Description |
|---|---|
| `--build-petsc` | Build only upstream PETSc dependency stage |
| `--build-libmesh` | Build only upstream libMesh dependency stage |
| `--build-wasp` | Build only upstream WASP parser and HIT utility stage |
| `--configure-moose` | Run only MOOSE framework configuration stage (`MooseConfig.h`) |
| `--moose [PATH]` | Build all upstream MOOSE dependencies (PETSc, libMesh, WASP) |
| `--setup-wrappers` | Generate only compiler wrapper scripts in `.zig_wrappers/` |
| `[default]` | Compile Rabbit and stage relocatable binaries in `src/rabbit/` |
| `--wheel` | Compile Rabbit, stage artifacts, and build wheel in `dist/` |
| `--wheel-only` | Package existing staged artifacts into `dist/*.whl` without recompiling |
| `--test` / `--tests` | Run pytest simulation and relocatability test suite (`test/`) |
| `--all` | Full pipeline: MOOSE build, Rabbit build, staging, wheel, and tests |

Alternatively, `zig build` delegates to the same orchestrator (`build.zig` runs `build_rabbit.py` with the default Rabbit build step):

```bash
zig build
```

---

## License

`rabbit-fem` is distributed under the GNU Lesser General Public License v2.1 (LGPL-2.1), matching the MOOSE framework license. See [`LICENSE`](LICENSE) for details.
