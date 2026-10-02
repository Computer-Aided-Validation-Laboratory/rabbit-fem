# MFEM + MPI Fixes Log (branch `mfem`)

Goal: MPI variant of rabbit with the MFEM backend compiled in (modules
unchanged — electromagnetics stays off), packaged as a minimal wheel
and verified in a clean `uv` venv on this Ubuntu machine (no sudo).

This machine has no `gh` CLI and no GitHub token, so CI runs cannot be
polled from here. The same diagnose-before-patch process is applied to
local build failures instead; CI workflow changes are kept
correct-by-construction (YAML parse-checked) until a runner proves them.

Local prostate: user-space prefixes under `~/.local` (no sudo):
`~/.local/tirpc` (XDR headers/libs), `~/.local/m4` (`m4`),
`~/.local/gfortran` (gcc-13 + gfortran toolchains),
`~/.local/mpi` (OpenMPI 4.1.6 stack + relocatable wrapper shims).
MOOSE checkout is isolated at `temp/moose-mpi` (gitignored) via
`build_rabbit.py --moose temp/moose-mpi ...` because `repo/moose/`
already holds the serial tree and `get_moose_dir` prefers it over
`$MOOSE_DIR`.

## 2026-10-01 — User-space OpenMPI with relocatable wrapper shims

- **Root cause**: no MPI anywhere on the box (no mpicc, no libmpi), and
  Debian's `mpicc.openmpi` cannot relocate (compiled-in
  `/usr/share/openmpi` data path) while `opal_wrapper` itself was
  briefly clobbered by writing through symlinks (restored by
  re-extracting `openmpi-bin`).
- **Fix (local env, no repo change)**: `apt-get download`ed
  `openmpi-{common,bin}`, `libopenmpi-{dev,3t64}` plus runtime deps
  (`libevent`, `libhwloc15`, `libpmix2t64`, `libucx0`, `libfabric1`,
  `libibverbs1`, `libnl-3-200`, `libmunge2`) into `~/.local/mpi`, with
  hand-written `mpicc`/`mpicxx`/`mpif90` shims replaying Debian's
  documented wrapper flags (`-I.../openmpi/include`,
  `-L.../openmpi/lib -lmpi[-_cxx|_mpifh] -pthread`) with the prefix
  derived from `$0` (no `$HOME`/username baked in). Shims honor
  `OMPI_CC/OMPI_CXX/OMPI_FC` (the repo points those at the Zig
  wrappers) and answer `-show`/`--showme*` for configure probes
  (PETSc, libMesh). Runtime needs
  `LD_LIBRARY_PATH=$prefix/usr/lib/x86_64-linux-gnu` and
  `OPAL_PREFIX=$prefix/usr` (the documented relocatable-install
  mechanism; without it `opal_init` fails). Verified: C compile,
  `mpirun -n 2` prints `rank 0/2, rank 1/2`. Remaining stderr noise
  about absent Infiniband components (ofi/psm) is benign (ignored).
- **Files changed**: none in repo (all under `~/.local/mpi`).
- **Verification**: `mpicc -show` prints the zigcc-based line once
  `OMPI_CC` is exported; `mpirun -n 2` hello-world converges.
- **Remaining uncertainty**: whether PETSc/libMesh configures accept
  the shims without further flags — their logs decide.

## 2026-10-01 — PETSc rejects link flags on preprocess-only probes

- **Local run**: MPI PETSc configure died with
  `RuntimeError: Cannot find a C preprocessor` after trying the legacy
  fallback `mpicc --use cpp32`.
- **Root cause**: our shims appended `-L... -lmpi -pthread` to EVERY
  invocation, including `mpicc -E`. Clang warns (`linker input unused`)
  where gcc stays silent, and PETSc's strict probe treats any stderr
  output as failure — then falls back to a legacy flag our compiler
  cannot parse. Real Debian wrappers never trigger this under gcc.
- **Fix (local shims)**: all three shims now detect non-link modes
  (`-E -c -S -M -MM --version -print-* -show*`) and omit link flags
  there (verified byte-clean `mpicc -E`); `-show`/`--showme*` unchanged.
- **Related (same session)**: system gcc broke under a globally
  exported `GCC_EXEC_PREFIX` (our prefix has no `cc1`), so the
  gfortran driver is now a wrapper script localizing that variable
  (prefix derived from `$0`), and the global env stays clean.
- **Files changed**: none in repo (all under `~/.local/`).
- **Verification**: `mpicc -E/-c` warning-free; full
  compile-link-`mpirun -n 2` cycle green; relaunched MPI build past
  the preprocessor stage into PETSc configure.
- **Remaining uncertainty**: downstream probes with other unusual flags
  — each surfaces loudly in its own configure log if so.

## 2026-10-01 — MPI-only Conduit/MFEM stages wired into the build

- **Scope**: `Makefile` module flags untouched (no EM). MFEM backend for
  MPI only: upstream MOOSE has no serial-MFEM path (48 unguarded
  `Par*` files at this pin), so `build_mfem` raises loudly when
  `RABBIT_MPI != 1`, and `configure_moose` passes `--with-mfem` for MPI
  only. `build_linux_dependencies` order for MPI:
  petsc -> libmesh -> conduit -> wasp -> mfem -> configure; serial order
  byte-identical. Conduit/MFEM use MOOSE's own installer scripts (the
  MPI path is upstream-supported, unlike the serial recipe which needed
  direct CMake). `moose_deps.txt` gains the `mfem`/`conduit` pins
  (`a7dbea1`/`6471d81`, the gitlinks at the pinned MOOSE commit) with
  matching `is_*_ready` + ensure entries. New `--build-conduit` /
  `--build-mfem` CLI flags dispatch to Linux only; other OSes raise an
  explicit unsupported error (their pipelines never call these flags,
  so their behaviour is unchanged).
- **Also re-applied here**: the `--checkout` submodule fix (mfem/conduit
  set `update = none`), the `m4`+`gfortran`+XDR fail-early preflights,
  and their regression tests — this box needs all three for any build.
  New tests pin the MPI stage order and the serial skip.
- **Platform considerations**: all MFEM logic lives in `linux.py` +
  Linux-gated dispatch; `darwin.py`/`windows.py` untouched.
- **Files changed**: `scripts/build/{common,linux}.py`,
  `build_rabbit.py`, `moose_deps.txt`,
  `test/{test_build_env,test_moose_pins}.py`, this log.
- **Verification**: 18 unit tests pass (incl. new order/pin/probe
  tests). Live proof is the running `RABBIT_MPI=1` build into
  `temp/moose-mpi`.
- **Remaining uncertainty**: PETSc-MPI configure under the shims,
  MFEM's appetite (openblas/mumps from the full PETSc), and the final
  staged-closure size.

## 2026-10-01 — Packaged MFEM sims + execution tests

- **Scope**: `src/rabbit/sims/mfem/` stages `diffusion.i` + `curlcurl.i`
  (representative Maxwell-via-MFEM case) with mesh paths adapted to the
  packaged layout (`mug.e` 200 KB, `small_fichera.mesh` 32 KB ship
  alongside) plus provenance headers. New `mfem_input_path()` /
  `mfem_mesh_path()` accessors (+ exports). `test/test_mfem.py` runs
  both cases with an absolute `Mesh/file=` override (immune to
  input-vs-cwd resolution semantics) and skips loudly when the binary
  lacks the backend (behavioural probe on `not a registered object`,
  verified against the serial binary). CSV gold for `curlcurl`
  (its outputs are CSV line-samples — MFEM has no Exodus path) comes
  after the first working MPI binary, following the repo's gold pattern.
- **Files changed**: `src/rabbit/sims/mfem/` (new),
  `src/rabbit/sims/{simulations.py,__init__.py}`,
  `test/test_mfem.py`, `test/test_simulations.py` (dataset assertions).
- **Verification**: dataset assertions pass; both MFEM tests skip with
  the documented reason until the MPI binary lands.
- **Remaining uncertainty**: HypreAMS/GMRES solve behaviour under the
  local MPI PETSc; CSV gold tolerances.

## 2026-10-01 — MPI PETSc needs flex/bison (PTScotch)

- **Local run**: MPI PETSc configure died with
  `RuntimeError: PTScotch needs flex installed` (its download builds
  scanners at configure time). Serial recipe never downloads ptscotch,
  so this is MPI-only.
- **Root cause**: environment gap (no flex/bison on the box; GitHub
  images ship them, so MPI CI is unaffected).
- **Fix (repo)**: `check_build_tools()` gains an `mpi:` flag adding
  `flex`/`bison` for MPI only (serial devs are not forced to install
  them), called as `check_build_tools(mpi=is_mpi_build())` from
  `build_petsc`, with pass/serial-ignore/MPI-require tests.
- **Fix (local)**: `apt-get download flex bison libfl-dev` →
  `~/.local/flexbison` on `PATH` (+ its lib dir on `LIBRARY_PATH` for
  `-lfl`); flex needs `m4` at runtime (already on `PATH`).
- **Files changed**: `scripts/build/linux.py`,
  `test/test_build_env.py`, this log.
- **Verification**: 20 unit tests pass; relaunched MPI build into
  PETSc configure (the `CC=mpicc Ignoring it!` lines are PETSc's
  standard env notice — the MPI CI flow this mirrors is proven).
- **Remaining uncertainty**: kokkos/libceed/umpire download weight in
  this PETSc; MFEM's openblas/mumps expectations.

## 2026-10-01 — PTScotch needs Fortran mpi.mod (mpif90 include path)

- **Local run**: with flex/bison present, PTScotch's build failed with
  `Fatal Error: Cannot open module file 'mpi.mod'`.
- **Root cause**: our `mpif90` shim only passed the C MPI include dir;
  Debian ships the Fortran `.mod` files under a compiler-versioned dir
  (`lib/.../fortran/gfortran-mod-15/openmpi`) — the same variable its
  own mpifort wrapper uses for `includedir`.
- **Fix (local shim)**: added that dir to the shim's `-I` flags.
- **Files changed**: none in repo (`~/.local/mpi/usr/bin/mpif90`).
- **Verification**: Fortran `use mpi` compiles and `mpirun -n 2` runs;
  relaunched MPI build.
- **Remaining uncertainty**: none on mechanism.

## 2026-10-01 — MFEM CMake needs FC=mpif90 for FindMPI

- **Local run**: MOOSE's `update_and_rebuild_mfem.sh` died in CMake
  configure: `Could NOT find MPI_Fortran` (missing
  `MPI_mpi_mpifh_LIBRARY MPI_mpi_LIBRARY MPI_Fortran_WORKS`). C and C++
  MPI were found — only the Fortran leg failed.
- **Root cause**: the stage env sets `CC=mpicc`/`CXX=mpicxx` but no
  Fortran MPI compiler, so CMake probed plain `gfortran` and found no
  MPI Fortran libs with it.
- **Fix (repo, `linux.py::build_mfem`)**: `tool_env["FC"] = "mpif90"`,
  mirroring how `CC`/`CXX` already select the MPI wrappers. Linux/MPI
  only; serial and other OSes untouched.
- **Files changed**: `scripts/build/linux.py`.
- **Verification**: MFEM configured (MPI_C/CXX/Fortran all found),
  compiled to 100%, and installed: `libmfem-opt.so` +
  `libmfem-common-opt.so` (+ un-suffixed symlinks, per-method config
  header) in `framework/contrib/mfem/installed`. GSLIB fetch, NetCDF
  (libMesh) + HDF5 (PETSc) both resolved.
- **Remaining uncertainty**: framework compile against parallel MFEM
  (running now); staged-closure size.

## 2026-10-01 — MOOSE configured with MFEM, framework building

- **State**: `temp/moose-mpi/conf_vars.mk` has `ENABLE_MFEM := true`
  with the isolated `MFEM_DIR`; `MooseConfig.h` defines
  `MOOSE_MFEM_ENABLED`. Full `--all` (RABBIT_MPI=1) launched: deps all
  short-circuit, framework unity compiling under `mpicxx`-via-zig.
- **Files changed**: none (build running).
- **Remaining uncertainty**: link (Hypre/MUMPS/SuperLU MPI libs),
  staged size, MFEM solve proof, CSV gold.

## 2026-10-01 — Prefix bison needs BISON_PKGDATADIR + M4

- **Local run**: PTScotch's `parser_yy.y` step failed:
  `bison: ... /usr/share/bison/m4sugar/m4sugar.m4: cannot open`,
  then (datadir fixed) `m4 subprocess failed`.
- **Root cause**: user-local bison looks for its sugar files and its
  `m4` subprocess at compiled `/usr/...` paths, both absent here.
- **Fix (local env)**: `BISON_PKGDATADIR=$prefix/usr/share/bison` (the
  documented override) and `M4=$prefix/usr/bin/m4`; verified by
  generating `parser_yy.c` from the actual PTScotch grammar.
- **Files changed**: none in repo (build env only).
- **Verification**: `BISON_OK` on the real grammar file; relaunched MPI
  build.
- **Remaining uncertainty**: further prefix-path assumptions in other
  downloaded tools — each fails loudly with its missing path if so.

## 2026-10-01 — Prefix libgomp.a shadows system libgomp.so (STRUMPACK)

- **Local run**: `Error running make on STRUMPACK`:
  `ld.lld: error: relocation R_X86_64_TPOFF32 ... cannot be used with
  -shared`, defined in `~/.local/gfortran/.../libgomp.a`.
- **Root cause**: the gfortran prefix dir on global `LIBRARY_PATH`
  holds a static non-PIC `libgomp.a` with no `.so` beside it, so the
  linker takes it instead of continuing to the system shared
  `libgomp.so`. Same shadowing family as the earlier dangling-symlink
  failures, one layer up (archive vs shared instead of missing target).
- **Fix (local env)**: dropped the gcc-lib dir from global
  `LIBRARY_PATH` — the gfortran wrapper's scoped `GCC_EXEC_PREFIX`
  already gives the driver its own `-L` (verified: exe link, `-shared`
  link, and hello-run all still pass). Rule of thumb earned here:
  prefix lib dirs on `LIBRARY_PATH` must each contain the `.so`
  for every `.a` they expose, or stay off the global path.
- **Files changed**: none in repo (build env only).
- **Verification**: gfortran links pass without the dir; relaunched MPI
  build.
- **Remaining uncertainty**: other static-only archives in prefix lib
  dirs hit the same way — the link error names them exactly if so.

## 2026-10-01 — -lgfortran needs a shadow-free home (OpenBLAS)

- **Local run**: `Error running make on .../git.openblas`:
  `ld.lld: error: unable to find library -lgfortran`.
- **Root cause**: removing the gcc-lib dir from `LIBRARY_PATH` (the
  libgomp.a fix) also removed the only `libgfortran.so` from the link
  search. The two needs conflict in one directory (static `libgomp.a`
  must stay invisible, shared `libgfortran.so` must stay visible).
- **Fix (local env)**: created `libgfortran.so ->
  libgfortran.so.5[.0.0]` inside the runtime dir
  (`~/.local/gfortran/usr/lib/x86_64-linux-gnu/`, which holds no
  archives) and put THAT dir on `LIBRARY_PATH` instead. Verified the
  gfortran exe/shared links still pass. (System already provides
  `libgomp.so`, so `-lgomp` was never at risk once the shadow lifted.)
- **Files changed**: none in repo (one symlink + build env).
- **Verification**: gfortran link+run green; relaunched MPI build.
- **Remaining uncertainty**: none new — back to the long PETSc phase.

## 2026-10-01 — cc1 for the prefix gfortran (MFEM FindMPI Fortran)

- **Local run**: MOOSE's `update_and_rebuild_mfem.sh` died in CMake
  configure: `Could NOT find MPI_Fortran`, with
  `gfortran-13: fatal error: cannot execute 'cc1'` in the probe.
- **Root cause**: the user-local gfortran prefix ships `f951` but no
  `cc1` (Ubuntu splits the C backend into another package), and the
  wrapper-scoped `GCC_EXEC_PREFIX` hides the system `/usr/libexec`
  from the driver's program search. CMake's Fortran-MPI probe drives a
  compile through it that needs `cc1`.
- **Fix (local env)**: symlinked the matching system
  `/usr/libexec/gcc/x86_64-linux-gnu/13/cc1{,plus}` (same 13.3.0) into
  the prefix libexec dir. Machine-local and documented; CI images have
  complete toolchains.
- **Files changed**: none in repo (two symlinks under `~/.local/`).
- **Verification**: probe passes; MFEM configure completed.
- **Remaining uncertainty**: none on mechanism.

## 2026-10-01 — MFEM built, configured, and linked into the MPI app

- **Result**: `FC=mpif90` (repo fix in `linux.py::build_mfem`) unblocked
  CMake `find_package(MPI)` Fortran; MFEM compiled to 100% and
  installed both `libmfem-opt.so` and `libmfem-common-opt.so` (plus
  un-suffixed symlinks and per-method config header, as MOOSE's script
  does). GSLIB fetched, NetCDF (libMesh) + HDF5 (PETSc) resolved.
  `conf_vars.mk` in the isolated `temp/moose-mpi` tree has
  `ENABLE_MFEM := true`; full `--all` (RABBIT_MPI=1) then compiled the
  framework with the MFEM sources active and linked `rabbit-opt`.
- **Verification**: `MFEM_ENABLED` in config; 90/90 tests incl. both
  MFEM execution solves (diffusion + curlcurl converge).
- **Remaining uncertainty**: staged-closure size (below).

## 2026-10-01 — Wheel size audit: 87.87 MB, floor for this recipe

- **Result**: `rabbit_fem_mpi-...-manylinux_2_38_x86_64.whl` is
  **87.87 MB** (baseline MPI wheel without MFEM: 76.2 MB on PyPI).
  Largest staged libs (stripped, zero debug sections): libmoose 60.6,
  openblas 34.3, mfem 32.6, petsc 30.8, kokkoskernels 20.9, mesh 20.2,
  solid_mechanics 17.6, strumpack 16.3, hypre 8.0, conduit_bp 7.4,
  hdf5 6.0 (MB uncompressed; zip brings the total down). 59 libs, every
  one in the `DT_NEEDED` closure — nothing staged that isn't linked.
- **Decision**: no recipe surgery. Shrinking further would mean dropping
  PETSc downloads (kokkos/kernels, strumpack, slepc) or static-linking
  games, each diverging from MOOSE's tested MPI configuration for
  megabytes that don't change the <100 MB verdict (12 MB margin).
  Reported as the honest minimum with the breakdown above.
- **Files changed**: none.
- **Remaining uncertainty**: none.

## 2026-10-01 — MFEM CSV gold + clean-venv MPI proof

- **Gold**: `curlcurl.i` writes CSV line samples only (MFEM has no
  Exodus path), so `scripts/generate_mfem_gold.py` stores both sample
  files' numeric arrays in `test/gold/mfem_curlcurl.npz` (7.5 KB) and
  `test/test_mfem_gold.py` compares headers exactly + values at the
  repo-standard 1e-5/1e-8. Singleton rank keeps partitioning
  deterministic. Generated with the MPI binary; test passes.
- **Clean venv** (fresh `uv` venv, build env stripped, system MPI
  replaced by the documented local deviation `LD_LIBRARY_PATH` to the
  prefix — CI/user machines use real `openmpi-bin` via the staged
  `/usr/lib/.../openmpi/lib` RPATH fallback instead): installed wheel
  `--version` OK; HEX8 singleton OK; MFEM curlcurl singleton OK;
  `mpirun -n 2` HEX8 multi-rank converges with postprocessors + `.e`;
  `mpirun -n 2` MFEM diffusion converges with CSV outputs.
- **Packaging fix this exposed**: the reinstalled wheel lacked `mug.e`
  — hatch honors `.gitignore`, which ignores `*.e` (and `*.msh`: the
  stc/monoblock `.msh` meshes never shipped either — pre-existing).
  Added `!src/rabbit/sims/**/*.e` + `!...msh` next to the existing csv
  negation; rebuilt wheel verified to contain `mug.e` + 4 `.msh` and no
  stray outputs. Final wheel: 90.74 MB.
- **CI**: `mpi_build_and_test.yml` gains Conduit + MFEM cache/build
  stages (same exact-key pattern, `-mpi` keys); the MPI-only smoke
  branch gains an MFEM singleton solve (serial legs untouched — they
  cannot run it). Serial/macOS/Windows workflows untouched.
- **Files changed**: `scripts/generate_mfem_gold.py` (new),
  `test/{test_mfem_gold.py,gold/mfem_curlcurl.npz}`,
  `.gitignore`, `.github/workflows/{mpi_build_and_test,smoke}.yml`,
  `README.md` (MPI+MFEM note), this log.
- **Verification**: full suite 91 passed, 0 skipped; YAML parses;
  wheel contents audited file-by-file.
- **Remaining uncertainty**: live CI proof (unavailable from here).
