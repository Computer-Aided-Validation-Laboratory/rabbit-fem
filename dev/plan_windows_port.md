# Rabbit Windows Port Plan

## Goal

Port **Rabbit** — a minimal MOOSE distribution containing only the framework, Heat Transfer, and Solid Mechanics — to native Windows using the same Zig acquisition strategy already used by `rabbit-fem` on Ubuntu.

The Windows build should use:

- `ziglang==0.16.0` from PyPI
- Zig C/C++ compiler drivers
- the exact MOOSE / PETSc / libMesh / WASP revisions already used by Rabbit
- genuine MOOSE `.i` input files
- minimal Windows-specific patching
- a final redistributable Python wheel

The core design rule remains:

> **Rabbit == MOOSE**

Rabbit should remain a minimal MOOSE application/distribution, not a forked FE framework, alternate parser, or compatibility layer.

---

## General Porting Rules

Work through each gate sequentially.

Do not proceed to the next gate until the current layer:

1. configures,
2. builds,
3. runs a meaningful verification test.

Prefer:

- configuration changes,
- build-system fixes,
- thin compiler wrappers,
- small portability patches,

over modifying upstream runtime logic.

Any upstream patch must be:

- isolated,
- documented,
- justified,
- as small as possible.

Do **not**:

- reimplement PETSc functionality,
- reimplement libMesh functionality,
- replace the MOOSE/WASP parser,
- introduce Rabbit-specific `.i` syntax,
- create a large Windows-specific MOOSE fork.

### Anti-rabbit-hole rule

After **three materially different attempts at the same structural blocker**, stop and produce a blocker report containing:

- failing component,
- exact command,
- full relevant error,
- suspected cause,
- fixes attempted,
- smallest upstream change apparently required.

Do not continue speculative modifications indefinitely.

---

# Gate 1 — Compile PETSc with Zig on Native Windows

This is the first serious compatibility gate.

## Objective

Build the exact PETSc revision required by the existing Rabbit/MOOSE checkout using:

```text
ziglang==0.16.0
```

with no separately installed C/C++ compiler used for compilation.

## Environment

Use native Windows.

MSYS2 MinGW64 may be used for:

- shell utilities,
- Make,
- Python-compatible configure scripts,
- Unix-like tooling expected by PETSc.

However, compilation itself must be performed by Zig.

Install Zig through Python:

```powershell
python -m pip install ziglang==0.16.0
python -m ziglang version
```

Expected:

```text
0.16.0
```

Do not rely on another `zig.exe` being installed globally.

## Compiler Preflight

Before attempting PETSc, verify that the compiler entry points work in the exact environment PETSc will use.

### C

```powershell
python -m ziglang cc hello.c -o hello.exe
.\hello.exe
```

### C++

```powershell
python -m ziglang c++ hello.cpp -o hello_cpp.exe
.\hello_cpp.exe
```

Also verify, if useful:

- static library creation,
- DLL creation,
- linking C++ executables,
- filesystem access,
- basic threading.

This is not a separate gate. It is a preflight so that PETSc failures can be attributed to PETSc/configuration rather than Zig itself.

## Initial PETSc Configuration

Keep the first build as small as possible.

Target approximately:

```text
CC  = Zig C
CXX = Zig C++
FC  = disabled

MPI = disabled initially
shared libraries = disabled initially
optional packages = disabled
minimal BLAS/LAPACK
```

Conceptually:

```text
CC  -> python -m ziglang cc
CXX -> python -m ziglang c++
FC  -> 0
```

PETSc may not accept a multiword compiler command cleanly. If necessary, create thin wrapper scripts such as:

```text
zig-cc.cmd
zig-cxx.cmd
```

that forward arguments to:

```text
python -m ziglang cc
python -m ziglang c++
```

## Verification

Build and run at least one real PETSc example that performs a solve.

The test must execute as a native Windows `.exe`.

## Decision

### PASS

Proceed if:

- PETSc configures,
- PETSc builds,
- a PETSc solve runs successfully.

### AMBER

Continue if the problems are limited to:

- compiler detection,
- executable naming,
- shell quoting,
- path handling,
- small Windows portability fixes,
- thin compiler wrappers.

### STOP

Stop and reassess if:

- PETSc fundamentally requires a compiler/runtime combination Zig cannot provide,
- substantial PETSc runtime source changes are required,
- the port begins to require maintaining a large PETSc fork.

---

# Gate 2 — Build libMesh Against Zig-Built PETSc

## Objective

Build the exact libMesh revision pinned by the same MOOSE checkout against the PETSc from Gate 1.

Do not introduce MPI yet.

## Configuration

Enable only what Rabbit needs.

Target approximately:

```text
libMesh
  + PETSc
  + core FE functionality
  + threading
  + required mesh I/O
  + required result/output I/O

  - unnecessary optional dependencies
```

Do not aggressively optimise package size yet.

## Verification

Build a minimal libMesh test or example that:

1. creates a mesh,
2. defines an FE problem,
3. assembles a system,
4. solves through PETSc,
5. produces numerical output,
6. preferably writes a result file.

## Decision

### PASS

Proceed if the resulting native Windows executable works correctly.

### AMBER

Continue if fixes are limited to:

- POSIX path assumptions,
- shell commands,
- compiler identification,
- minor portability changes,
- small substitutions for Unix convenience APIs.

### STOP

Stop and reassess if:

- libMesh requires pervasive Unix-only runtime behaviour,
- the Windows port requires broad architectural changes,
- maintaining libMesh would effectively require a permanent Windows fork.

This is one of the major project kill gates.

---

# Gate 3 — Build WASP and Prove Genuine MOOSE `.i` Parsing

## Objective

Build the exact WASP revision used by MOOSE and verify that normal MOOSE input files parse correctly.

This gate protects the design rule:

> **Rabbit == MOOSE**

Rabbit must use the genuine MOOSE input parser.

## Verification

Use WASP to parse at least one existing Rabbit/MOOSE `.i` file.

Preferably test:

- a very small input,
- the existing thermal acceptance input,
- syntax errors,
- nested MOOSE blocks.

## Decision

### PASS

Proceed if standard MOOSE input parsing works correctly.

### AMBER

Continue for small build or portability fixes.

### STOP

Stop if genuine WASP support would require:

- replacing the parser,
- implementing a Rabbit-specific parser,
- changing `.i` syntax semantics.

---

# Gate 4 — Build a Minimal Upstream MOOSE Test Application

## Objective

Build the smallest practical upstream MOOSE application against the already-proven Windows dependency stack.

Do **not** build Rabbit yet.

This isolates the MOOSE runtime and build system from Rabbit-specific configuration.

## Verification

Run something equivalent to:

```powershell
moose_test.exe trivial.i
```

The input should exercise:

- genuine MOOSE parsing,
- object construction,
- execution,
- a minimal solve.

## Decision

### PASS

Proceed if an ordinary MOOSE executable runs correctly.

At this point, native Windows Rabbit becomes highly plausible.

### AMBER

Continue if the remaining issues are primarily:

- Makefile assumptions,
- shell utilities,
- Unix paths,
- symlinks,
- `rm`,
- archive/linker command differences,
- small build-system patches.

### STOP

Stop and reassess if core MOOSE runtime code has pervasive POSIX-only dependencies with no sensible Windows replacement.

This is another major kill gate.

---

# Gate 5 — Build Rabbit with Heat Transfer Only

## Objective

Introduce the actual `RabbitApp`, but keep the physics scope minimal.

Build:

```text
MOOSE framework
+
Heat Transfer
```

## Verification

Run the same thermal `.i` input used by the known-good Ubuntu Rabbit build:

```powershell
rabbit.exe thermal.i
```

Do not test only for successful execution.

Compare numerical results against Linux.

Suggested comparison quantities:

- maximum temperature,
- selected nodal temperatures,
- total heat flux,
- any scalar postprocessor already available.

## Acceptance

Windows and Linux results should agree within a sensible numerical tolerance.

---

# Gate 6 — Add Solid Mechanics

## Objective

Enable the Solid Mechanics module and run the existing Rabbit solid-mechanics acceptance case.

## Verification

Run:

```powershell
rabbit.exe solid_mechanics.i
```

Compare against the Linux reference:

- displacement,
- reaction force,
- stress,
- strain,
- selected postprocessor values.

## Decision

### PASS

This is the main project-success gate.

If this passes, native Windows Rabbit is technically viable.

### STOP

If Solid Mechanics introduces a structural dependency that cannot be resolved without large upstream changes, isolate and document the exact dependency before deciding whether to continue.

---

# Gate 7 — Verify Shared-Memory Threading

## Objective

Prove that Windows Rabbit can use workstation multicore parallelism without requiring MPI.

Test:

```powershell
rabbit.exe model.i --n-threads=1
rabbit.exe model.i --n-threads=2
rabbit.exe model.i --n-threads=4
rabbit.exe model.i --n-threads=8
```

## Measure

Check:

- numerical consistency,
- successful execution,
- wall-clock time.

Do not require perfect scaling.

The gate is simply that the threaded MOOSE/libMesh execution path works correctly.

---

# Gate 8 — Add MPI

Do this only after SMP Rabbit works.

## Objective

Add Windows MPI support without making it a prerequisite for basic workstation Rabbit.

MS-MPI is the preferred initial route.

## Verification

First test multiple ranks:

```powershell
mpiexec -n 2 rabbit.exe model.i
```

Then test hybrid execution:

```powershell
mpiexec -n 2 rabbit.exe model.i --n-threads=4
```

## Decision

### PASS

Proceed with MPI-capable Rabbit packaging.

### AMBER

If MPI works but requires special runtime setup, document it and continue.

### STOP MPI ONLY

If MPI becomes a major packaging or ABI problem, do **not** automatically kill Windows Rabbit.

A native Windows build with working SMP remains valuable.

---

# Gate 9 — Reproduce the Existing Rabbit Build Orchestration

## Objective

Make the successful manual Windows build follow the same broad architecture already used by `rabbit-fem` on Linux.

The desired build chain is:

```text
Python build environment
       |
       +-- ziglang==0.16.0
       |
       +-- build PETSc
       +-- build libMesh
       +-- build WASP
       +-- build Rabbit
       |
       `-- stage runtime
```

## Requirements

- no globally installed Zig required,
- compiler comes from `ziglang==0.16.0`,
- dependency revisions remain pinned,
- build steps are scripted,
- build is repeatable from a clean checkout.

---

# Gate 10 — Make Rabbit Relocatable

## Objective

Turn the build into a redistributable Windows runtime.

Create something conceptually like:

```text
rabbit-dist/
├── rabbit.exe
├── required DLLs
└── required runtime resources
```

## Verification

Copy the directory somewhere completely unrelated to the build tree, for example:

```text
C:\Temp\rabbit-dist\
```

Then run:

```powershell
C:\Temp\rabbit-dist\rabbit.exe thermal.i
```

and:

```powershell
C:\Temp\rabbit-dist\rabbit.exe solid_mechanics.i
```

## It Must Not Depend On

- `MOOSE_DIR`,
- `PETSC_DIR`,
- `LIBMESH_DIR`,
- the source checkout,
- the build directory,
- Zig,
- MSYS2 paths,
- developer-only DLLs,
- compiler installation directories.

This is the point where a successful build becomes a distributable application.

---

# Gate 11 — Produce the Windows Python Wheel

## Objective

Package the relocatable runtime into a Windows wheel.

Target:

```text
rabbit_fem-X.Y.Z-py3-none-win_amd64.whl
```

Conceptually:

```text
rabbit/
├── cli.py
└── bin/
    ├── rabbit.exe
    └── required DLLs
```

The Python CLI should remain thin.

Its job should be:

1. locate the bundled `rabbit.exe`,
2. forward arguments,
3. propagate the return code.

Do not add a new FE abstraction layer.

## Verification

Use a clean Python installation/environment with:

- no Zig,
- no MOOSE checkout,
- no PETSc,
- no libMesh,
- no MSYS2 dependency on `PATH`.

Then:

```powershell
pip install rabbit_fem-....whl
rabbit thermal.i
rabbit solid_mechanics.i
```

Both must work.

---

# Gate 12 — Size and Dependency Pruning

Only optimise package size after the complete Windows build works.

## Hard Requirement

```text
compressed wheel < 100 MB
```

## Engineering Targets

```text
Hard limit:        <100 MB
Preferred target:  <80 MB
Stretch target:    <50 MB
```

## Remove Where Possible

- debug symbols,
- headers,
- tests,
- examples,
- static archives not required at runtime,
- unused MOOSE modules,
- unused PETSc solver packages,
- development tools,
- unnecessary runtime libraries,
- duplicate libraries.

Do not introduce new failures merely to chase the stretch target.

---

# Major Kill Gates

The three most important structural compatibility gates are:

```text
Gate 1
PETSc + Zig on Windows
       |
       v
Gate 2
libMesh + Zig-built PETSc
       |
       v
Gate 4
Actual MOOSE runtime
```

If all three pass, Rabbit itself should be relatively straightforward because Rabbit deliberately remains a minimal MOOSE application.

---

# Success Definition

The Windows port is complete when a clean Windows machine can do:

```powershell
pip install rabbit-fem
rabbit model.i
```

and run an ordinary MOOSE-compatible thermal or solid-mechanics `.i` file using the bundled native Windows Rabbit executable.

The final user should not need:

- MOOSE,
- PETSc,
- libMesh,
- Zig,
- MSYS2,
- a C/C++ compiler,
- a developer shell.

Rabbit should remain recognisably and technically MOOSE, only distributed as a compact thermal and solid-mechanics application.
