# EMFEM Fixes Log (rabbit-fem + MFEM backend + electromagnetics)

New variant goal: local serial MOOSE build with the MFEM backend and the
electromagnetics module, packaged as a standalone wheel that installs and
runs in a clean `uv` venv with no visibility of the local MOOSE checkout.
MPI explicitly out of scope for now; wheel target < 100 MB if possible.

Note on CI polling: this machine has no `gh` CLI and no GitHub token, so
CI runs cannot be polled from here. The same diagnose-before-patch process
is applied to local build failures instead; CI workflow changes are kept
correct-by-construction (YAML parse-checked) until a runner proves them.

Note on `pyproject.toml`/`uv.lock` (2026-10-01 ~13:07): both files changed
during this session WITHOUT an edit from this work (`version 2026.9.7 ->
2026.10.0`, lock re-resolution) — no bump script or hook in the repo does
this, so it was an external edit (likely a parallel release bump). Left
untouched deliberately; the 2026.10.0 wheel below was built after it.
`uv.lock` churn is `uv run` re-resolving a lock that was already stale
(it still said `requires-python >=3.9` after the 3.10 floor).

## 2026-10-01 — Enabled electromagnetics + pinned MFEM/Conduit commits

- **Root cause**: `Makefile` set `ELECTROMAGNETICS := no` and the repo had
  no MFEM/Conduit stages at all, so the new variant could not build.
- **Fix**: `ELECTROMAGNETICS := yes` in `Makefile` (no C++ change needed:
  `RabbitApp::registerAll` goes through `ModulesApp`, which registers
  whatever the Makefile enables). Added `mfem a7dbea1...` and
  `conduit 6471d81...` pins to `moose_deps.txt` — the exact gitlink SHAs
  recorded at the pinned MOOSE commit `975c9a1` (verified via a probe
  clone: `git ls-tree HEAD framework/contrib/{mfem,conduit}`), plus both
  paths in `_MOOSE_DEP_SUBMODULES`, `is_conduit_ready()` /
  `is_mfem_ready()` helpers, and both paths in `ensure_moose_submodules`.
  `verify_moose_deps` now guards all five upstream commits.
- **Platform considerations**: Makefile + pins are shared (per-OS
  divergence here would just be duplicated truth). No OS-specific code.
- **Files changed**: `Makefile`, `moose_deps.txt`,
  `scripts/build/common.py`, `test/test_moose_pins.py` (existing tests
  still pass; new pins verified live: `verify_moose_deps` prints pins OK
  with all five submodules at their pinned commits).
- **Verification**: probe clone `ls-tree` output matches the new pins;
  `verify_moose_deps` passes on the local checkout.
- **Remaining uncertainty**: none on pins.

## 2026-10-01 — Serial MFEM/Conduit stages bypass the MPI-only MOOSE scripts

- **Root cause**: MOOSE's `update_and_rebuild_mfem.sh` hardcodes
  `-DMFEM_USE_MPI=YES` and requires artifacts of the full MPI PETSc
  (OpenBLAS lib, MUMPS/SuperLU/HYPRE/METIS dirs) that the serial recipe
  deliberately does not build (serial PETSc is MPIUNI + f2cblaslapack).
  Running that script for the serial variant can never succeed.
- **Fix**: new `build_conduit` (reuses MOOSE's conduit script — it is
  already MPI-agnostic) and `build_mfem` stages in `scripts/build/linux.py`
  and `scripts/build/darwin.py`. Serial MFEM configures MFEM's CMake
  directly (precedent: `_build_petsc_serial` already bypasses MOOSE's
  PETSc script for the same reason): shared libs, `Release` + `-opt`
  postfix to match what `moose.mk` links (`-lmfem-opt -lmfem-common-opt`),
  `MFEM_USE_MPI/METIS/CEED/PETSC/SLEPC/SUPERLU/MUMPS/STRUMPACK/PUMI=NO`,
  `CONDUIT+GSLIB(fetch)+NETCDF(libMesh)=YES`, testing/examples/miniapps
  off, then builds + installs only `miniapps/common` (it is configured
  `EXCLUDE_FROM_ALL`, exactly as MOOSE's script assumes), plus the
  per-method `_config-opt.hpp` move and un-suffixed lib symlinks the MOOSE
  script performs. MPI MFEM raises loudly (unsupported, not silently
  degraded). `configure_moose` now passes `--with-mfem` (MOOSE records
  `MFEM_DIR=framework/contrib/mfem/installed` — no validation, just the
  path). Order: petsc -> libmesh -> conduit -> wasp -> mfem -> configure
  (matches upstream install docs). New `--build-conduit` / `--build-mfem`
  CLI flags in `build_rabbit.py` with per-OS dispatch.
- **Platform considerations**: Linux and macOS implementations are
  separate functions per file (compartmentalised; no shared MFEM helper
  to keep OS tool-env differences explicit). Windows `build_conduit` /
  `build_mfem` raise `RuntimeError` stating the backend is unsupported
  there yet — the Windows build still compiles the electromagnetics
  module itself (MFEM-guarded sources are excluded without
  `--with-mfem`), so the shared `Makefile` flip does not break it.
  Windows MFEM (MFEM CMake under MSYS/Zig) is follow-up work needing a
  Windows machine to prove.
- **Files changed**: `scripts/build/{linux,darwin,windows}.py`,
  `build_rabbit.py`, `README.md` (7 stages, module list).
- **Verification**: `build_rabbit.py --help` shows the new flags;
  `--setup-wrappers` works; unit suite passes. Live proof is the local
  serial build in progress (conduit + MFEM stages have not run yet).
- **Remaining uncertainty**: (1) whether `MFEM_USE_NETCDF=YES` resolves
  against serial libMesh without an HDF5 provider — cmake configure is
  cheap, so the faithful port was tried first; a failure names the exact
  missing piece; (2) macOS MFEM flags are a mechanical mirror, unproven
  until macOS CI runs; (3) staged wheel size with libmfem + conduit.

## 2026-10-01 — ensure_moose_submodules silently skipped mfem/conduit

- **CI/local run**: first local `--moose` run checked out petsc/libmesh/wasp
  then started PETSc configure, while the log showed
  `Skipping submodule 'framework/contrib/conduit'` /
  `Skipping submodule 'framework/contrib/mfem'`.
- **Root cause**: `framework/contrib/{mfem,conduit}` set `update = none`
  in MOOSE's `.gitmodules`. A plain `git submodule update --init
  --recursive <paths>` honors that default and skips them even when
  explicitly listed. ( Gitlink verification: the paths were in `needed`,
  yet git printed "Skipping".) MOOSE's own
  `update_and_rebuild_{mfem,conduit}.sh` scripts pass `--checkout`,
  which overrides the default — our helper did not.
- **Fix**: added `--checkout` to the update command in
  `ensure_moose_submodules` (one flag; `--recursive` retained for
  nested submodules inside petsc/libmesh/conduit). For submodules
  without `update = none` this is the default strategy, so behaviour is
  unchanged there. Proven live: conduit then checked out at `6471d81`
  with its nested `blt`/`uberenv` submodules, and mfem at `a7dbea1`.
- **Platform considerations**: shared git behavior, all OSes benefit
  (Windows ps1 uses its own submodule commands — untouched).
- **Files changed**: `scripts/build/common.py`,
  `test/test_moose_pins.py` (new
  `test_ensure_overrides_update_none_submodules` asserting `--checkout`
  and all five paths in the update command).
- **Verification**: new test passes (7/7 in file); live checkout of both
  submodules at their pinned SHAs; `verify_moose_deps` prints pins OK.
- **Remaining uncertainty**: none on mechanism.

## 2026-10-01 — libMesh configure failed: XDR headers missing (local env gap)

- **Local run**: `build_libmesh` failed in
  `./scripts/update_and_rebuild_libmesh.sh --disable-petsc-hypre-required`
  with `configure: error: *** XDR was not found, but --enable-xdr-required
  was specified` (plus `checking for XDR support via libtirpc... no`).
- **Root cause**: environment gap, not a code bug — MOOSE's
  `scripts/configure_libmesh.sh` hardcodes `--enable-xdr-required`
  (verified upstream, line 56), and this machine has no `libtirpc-dev`
  (`/usr/include/tirpc` absent; glibc >= 2.28 ships no RPC headers).
  CI installs `libtirpc-dev` (already in the workflow apt lists and the
  README prerequisites), so CI is unaffected. Would fail identically on
  `main` — not caused by the EM/MFEM changes.
- **Fix (repo, all users)**: new `check_xdr_headers()` preflight in
  `scripts/build/linux.py`, called at the top of `build_libmesh`: it
  compiles `#include <rpc/rpc.h>` with the actual wrapper compiler, so
  headers from any legitimate source (system package, conda prefix,
  `CPATH`) satisfy it — it tests the invariant libMesh depends on,
  not fixed paths. On failure it raises naming `libtirpc-dev`
  immediately instead of after a long configure. Precedent:
  `check_libpng_consistency` on macOS does the same class of gate.
  Linux-only; macOS/Windows flows untouched.
- **Fix (local machine, no repo change)**: no sudo here, so the Ubuntu
  `libtirpc-dev` + `libtirpc3t64` .debs were fetched with `apt-get
  download` and extracted to `~/.local/tirpc`; the build runs with
  `CPATH=~/.local/tirpc/usr/include/tirpc:...` and
  `LIBRARY_PATH=~/.local/tirpc/usr/lib/x86_64-linux-gnu` (both honored
  by clang through the wrappers for probes, autoconf configures, and
  links). The probe passes with this prefix; `-ltirpc` link + run
  verified directly.
- **Platform considerations**: preflight lives in `linux.py` only.
  Staging needs no change: if the closure references libtirpc it is
  bundled like any other non-system NEEDED lib (same on CI).
- **Files changed**: `scripts/build/linux.py`, `test/test_build_env.py`
  (pass/fail probe tests), this log.
- **Verification**: 13/13 build-env + pins tests pass; live probe passes
  with the prefix and (by construction) on CI images with the package.
  Live proof is the relaunched local build now past XDR into libMesh
  configure.
- **Remaining uncertainty**: whether the libMesh *link* finds `-ltirpc`
  via `LIBRARY_PATH` alone (configure's `--with-xdr-lib` was not set;
  MOOSE only special-cases `$CONDA_PREFIX`). The build log decides; if
  the link fails the fix is `-L` via `LDFLAGS`, still env-only.

## 2026-10-01 — libMesh bundled netcdf configure failed: m4 missing

- **Local run**: with XDR resolved, libMesh configure died in the bundled
  netcdf sub-configure with
  `configure: error: Cannot find m4 utility. Install m4 and try again.`
- **Root cause**: same class as XDR — environment gap, not a code bug.
  GitHub's Ubuntu images pre-install `m4`; this box has no `m4`
  (nor sudo to install it). Would fail identically on `main`.
- **Fix (repo)**: new `check_build_tools()` in `scripts/build/linux.py`
  (currently gates only the proven-missing `m4` via `shutil.which`;
  no speculative tool checks), called from `build_libmesh` next to the
  XDR probe. Linux-only.
- **Fix (local, no repo change)**: `apt-get download m4`, extracted to
  `~/.local/m4`, `PATH=$HOME/.local/m4/usr/bin:$PATH` for the build
  (the preflight honors `PATH`, so it passes unmodified).
- **Files changed**: `scripts/build/linux.py`, `test/test_build_env.py`
  (present/missing `m4` tests), this log.
- **Verification**: 10/10 build-env tests pass. Audited remaining tools:
  `cmake`/`make`/`patch`/`git` present; `pkg-config`/`bison`/`flex`/
  `gfortran`/`ninja` absent but not required by the serial recipe
  (MOOSE handles missing pkg-config by building without PNG; WASP needs
  no bison/flex; serial PETSc/libMesh need no Fortran; ninja optional).
  Live proof is the relaunched build now past netcdf into libMesh's C++
  feature checks.
- **Remaining uncertainty**: none on mechanism; next unknown tool (if
  any) fails loudly at its own stage.

## 2026-10-01 — MPI pipeline must skip the unsupported MFEM backend

- **Root cause (anticipated, not yet failed)**: `configure_moose` passed
  `--with-mfem` unconditionally and `build_linux_dependencies` always ran
  conduit+mfem, but `build_mfem` raises for `RABBIT_MPI=1` — wiring the
  new stages naively would break the existing MPI pipeline, which is
  explicitly out of scope for this variant.
- **Fix**: `build_linux_dependencies` / `build_darwin_dependencies` skip
  the conduit+mfem stages under `RABBIT_MPI=1` with an explicit NOTE,
  and `configure_moose` omits `--with-mfem` there (the MPI rabbit keeps
  the newly enabled electromagnetics module, just without the MFEM
  backend — EM sources are `MFEM_ENABLED`-guarded upstream). Direct
  `--build-mfem --mpi` still fails loudly via the existing guard.
- **Platform considerations**: same gating shape in `linux.py` and
  `darwin.py` (their tool envs differ, the variant policy does not);
  Windows needs no change (its ps1 never built MFEM).
- **Files changed**: `scripts/build/{linux,darwin}.py`,
  `build_rabbit.py` (`--moose` help text),
  `test/test_build_env.py` (serial stage-order test + MPI skip test).
- **Verification**: 15/15 build-env + pins tests pass.
- **Remaining uncertainty**: none; MPI CI leg proves it on the next run.

## 2026-10-01 — MFEM CMake failed: no HDF5 for its NetCDF support

- **Local run**: with PETSc/libMesh/Conduit/WASP built, `_build_mfem_serial`
  died in CMake configure:
  `*** HDF5 not found. Please set HDF5_DIR` via
  `FindNetCDF -> mfem_find_package(HDF5 C HL)`.
- **Root cause**: the serial recipe provided no HDF5 anywhere (serial
  PETSc used only f2cblaslapack; no system HDF5 on this box or on CI
  runners), while `MFEM_USE_NETCDF=YES` unconditionally requires HDF5
  C+HL at configure time.
- **Why not `MFEM_USE_NETCDF=NO`**: verified in MFEM sources that this
  would cripple mesh I/O, not just lose a feature. MOOSE's
  `MFEMFileMesh` calls `mfem::Mesh(filename)`, whose Loader routes
  NetCDF-magic (`CDF`) files — i.e. Exodus `.e` files — exclusively
  through the `MFEM_USE_NETCDF`-guarded Cubit/Genesis reader
  (`mesh.cpp` aborts otherwise: "NetCDF support requires configuration
  with MFEM_USE_NETCDF=YES"). MOOSE's own MFEM tests (e.g.
  `test/tests/mfem/kernels/diffusion.i` with `../mesh/mug.e`) depend on
  it. Disabling would trade a configure error for broken solves.
- **Fix (portable, in-recipe)**: serial PETSc now adds
  `--download-hdf5=1 --with-hdf5-fortran-bindings=0 --with-zlib`
  (mirrors upstream `configure_petsc.sh`, which downloads HDF5 when no
  system copy is found; system `zlib.h` is present wherever
  build-essential is), and serial MFEM passes
  `-DHDF5_DIR=<petsc>/arch-moose` (same layout as upstream's
  `update_and_rebuild_mfem.sh`). HDF5 is therefore built from source on
  every machine/CI runner — no apt/Homebrew assumption. Applied to both
  `linux.py` and `darwin.py` serial PETSc/MFEM.
- **Local staleness handling**: the recipe change busts CI dep-cache keys
  (cold rebuild there, correct), but the local `arch-moose` tree predates
  it, so it was removed once manually (`rm -rf moose/petsc/arch-moose`).
  libMesh was intentionally NOT rebuilt: its configure embedded the old
  PETSc link line, but libMesh objects reference no HDF5 symbols
  (its own HDF5 detection found nothing either way), and MFEM/rabbit get
  HDF5 flags from MFEM's `config.mk`. If a downstream link names HDF5,
  rebuilding libMesh is the documented fallback.
- **Platform considerations**: same flags both OSes; macOS serial env
  already hides brew HDF5, so the in-arch download is the only provider
  there too. Windows untouched (no MFEM).
- **Files changed**: `scripts/build/{linux,darwin}.py` (PETSc flags,
  MFEM `HDF5_DIR`, docstrings), this log.
- **Verification**: `libmesh/installed` provides NetCDF
  (`libnetcdf.so.13`, v3-only per `libnetcdf.settings` — sufficient:
  ExodusII is NetCDF-3); system has zlib headers and no HDF5, matching
  the download path. Live proof is the relaunched build (PETSc+hdf5
  rebuild in progress).
- **Remaining uncertainty**: GSLIB fetch at MFEM configure (network;
  worked for all submodule fetches so far) and the `miniapps/common`
  target shape (verified `EXCLUDE_FROM_ALL` still configures the subdir,
  matching MOOSE's script assumption).

## 2026-10-01 — Dependency pipeline green locally (HDF5 resolution works)

- **Result**: relaunched `--moose` completed end to end:
  serial PETSc (with downloaded HDF5: `arch-moose/lib/libhdf5.so`
  present), libMesh, Conduit, WASP, serial MFEM, MOOSE configure.
- **MFEM as built**: `MFEM_USE_NETCDF/CONDUIT/GSLIB=YES`,
  `MFEM_USE_HDF5=NO` (HDF5 as external TPL, matching upstream layout);
  `MFEM_EXT_LIBS` links conduit/conduit_blueprint/conduit_relay (conduit
  install), netcdf (libMesh install), hdf5_hl+hdf5 (PETSc arch) with
  proper `-rpath/-L`. Both `libmfem-opt.so` and `libmfem-common-opt.so`
  produced. `conf_vars.mk`: `ENABLE_MFEM := true`,
  `MFEM_DIR := .../framework/contrib/mfem/installed`; `MooseConfig.h`:
  `MOOSE_MFEM_ENABLED 1`; serial `MPI_Comm` fallback present.
- **Files changed**: none (this entry records the outcome).
- **Verification**: file + grep checks above; GSLIB fetch succeeded;
  NetCDF resolved against libMesh + PETSc HDF5 exactly as designed.
- **Remaining uncertainty**: framework/rabbit compile with the new
  modules (running as `--wheel`); staged closure contents and wheel
  size; clean-venv isolated solve.

## 2026-10-01 — VERDICT: serial MFEM backend impossible at this MOOSE pin

- **Local run**: `--wheel` framework compile died in
  `framework/build/unity_src/mfem_Unity...` with 20 errors of the form
  `no type named 'ParMesh' in namespace 'mfem'`,
  `no member named 'ParBilinearForm'`, `no type named 'HypreParMatrix'`.
- **Root cause**: MOOSE's MFEM wrapper layer is written exclusively
  against MFEM's MPI-parallel API. 48 files under
  `framework/{src,include}/mfem` use `ParMesh`/`Par*Form`/`HypreParMatrix`
  with ZERO `MFEM_USE_MPI`/`LIBMESH_HAVE_MPI` guards, and serial MFEM
  (`MFEM_USE_MPI=NO`) provides no `Par*` classes at all. Upstream design
  confirms it: `MFEMMesh::buildMesh` unconditionally builds
  `mfem::ParMesh(MPI comm, ...)`, `MFEMProblem` calls `mfem::Hypre::Init()`,
  and upstream unit tests construct `ParMesh(MPI_COMM_WORLD, ...)`.
  No header trick or flag can conjure parallel classes from a serial
  MFEM. This is an upstream limitation, not a recipe bug: any
  serial-MFEM MOOSE build fails identically.
- **Why this surfaced now**: the serial MFEM *library* builds fine
  (proven: `libmfem-opt.so` + `libmfem-common-opt.so` with
  Conduit/GSLIB/NetCDF/HDF5) — the incompatibility is between MOOSE's
  MFEM *sources* and serial MFEM *headers*, which only meet at framework
  compile time.
- **Decision**: the serial core tool ships the electromagnetics module
  (zero MFEM references — pure libMesh physics, serial-safe) WITHOUT the
  MFEM backend (`framework/src/mfem` is per-file
  `MOOSE_MFEM_ENABLED`-guarded and compiles to empty TUs without
  `--with-mfem`; verified every file carries the guard). The serial
  Conduit/MFEM stages, HDF5 PETSc flags, and mfem/conduit pins are
  reverted — they have no serial consumer (keeping them would be green
  theater: built libs nobody can link). The MFEM backend's real home is
  the MPI variant (full MPI PETSc + MOOSE's own `update_and_rebuild_mfem.sh`
  MPI path + `--with-mfem`), tracked as follow-up work. All recipes and
  diagnoses in this log are preserved so that follow-up starts from
  proven ground.
- **Electromagnetics module check**: `grep -rl mfem/MFEM` over
  `modules/electromagnetics/{src,include}` returns nothing, and its
  tests (e.g. `vector_kernels.i`: Nédélec libMesh elements, generated
  mesh, `-pc_type lu`) are serial-safe by construction.
- **Files changed**: `scripts/build/{linux,darwin,windows}.py`
  (MFEM/Conduit stages, HDF5 flags, `--with-mfem` removed),
  `build_rabbit.py` (flags/dispatch removed), `moose_deps.txt` (pins
  removed), `README.md` (stages + backend claims corrected), tests
  updated; KEPT: `Makefile` EM=yes, `--checkout` fix + test, XDR/m4
  preflights + tests (all variant-independent value).
- **Verification**: pending — reconfigure without `--with-mfem`,
  framework rebuild, EM proof solve, wheel + clean-venv test.
- **Remaining uncertainty**: none on the verdict itself. If upstream
  MOOSE ever gains a serial MFEM path, this log's recipe (Conduit,
  GSLIB fetch, libMesh-NetCDF + PETSc-HDF5, `-opt` postfix handling,
  `miniapps/common` build) is the starting point.

## 2026-10-01 — Pivot executed: EM-serial tree is minimal again
- **Revert**: `darwin.py`, `windows.py`, `build_rabbit.py`,
  `moose_deps.txt`, `uv.lock` restored to `main`;
  `linux.py`/`common.py`/`README.md`/`test/test_build_env.py` restored
  then keepers re-applied. Final diff vs `main`: `Makefile`
  (`ELECTROMAGNETICS=yes`), `README.md` (EM in description + module
  list), `scripts/build/common.py` (`--checkout` + comment),
  `scripts/build/linux.py` (`check_build_tools` + `check_xdr_headers` +
  call), `test/test_build_env.py` (m4 + XDR probe tests),
  `test/test_moose_pins.py` (`--checkout` test), plus this log.
  Net result of the session so far if the EM build proves out: +155/-3
  lines, all variant-independent.
- **Local tree surgery for the pivot**: removed
  `moose/framework/include/base/MooseConfig.h` + `moose/conf_vars.mk`
  (were `--with-mfem`), ran `make -C moose/framework clobber` (stale
  objects carried MFEM `-I`/`-D` flags that `make` cannot see as
  changed), relaunched the full `--all` pipeline. Kept on disk but
  unused: MFEM/Conduit installs, HDF5-enabled PETSc (inert extra lib;
  fresh checkouts per the reverted recipe build PETSc without HDF5 —
  nothing references it).
- **Verification**: 48 unit tests pass; electromagnetics unity TUs
  (`kernels`, `materials`, `interfacekernels`, `auxkernels`, `bcs`)
  compiling in the running build.
- **Remaining uncertainty**: link + EM proof solve + wheel.

## 2026-10-01 — Default make needs Fortran for module test plugins

- **Local run**: `--all` failed at
  `modules/solid_mechanics/test/plugins/elastic-opt.plugin` with
  `make: no: No such file or directory`.
- **Root cause**: environment gap. No Fortran compiler on this box, so
  libMesh configured with `FC=no` (`libmesh-config --fc` prints `no`);
  `framework/build.mk` records that via `?=` into `libmesh_F77`, and the
  `%.plugin : %.f` rule then tries to execute a program literally named
  `no`. Would fail identically on `main`; CI installs `gfortran` and the
  README lists it.
- **Fix (repo)**: `gfortran` added to `check_build_tools()` in
  `scripts/build/linux.py` (same fail-early rationale as `m4`; the
  message names the package). Linux-only.
- **Fix (local, no repo change)**: Ubuntu `gcc-13`/`gfortran-13` are
  driver-only packages, so the full set was fetched with `apt-get
  download` and extracted to `~/.local/gfortran`: `gcc-13`,
  `gfortran-13`, `gcc-13-x86-64-linux-gnu` (cc1 + `liblto_plugin.so`),
  `gfortran-13-x86-64-linux-gnu` (f951), `libgcc-13-dev` (crt*.o),
  `libgfortran-13-dev` (link symlink), `libgfortran5` (runtime target of
  that symlink — same dangling-symlink class as the tirpc `.so`).
  Build env adds `PATH=~/.local/gfortran/usr/bin`,
  `GCC_EXEC_PREFIX=~/.local/gfortran/usr/lib/gcc/` (subprogram lookup),
  appends the gcc lib dir to `LIBRARY_PATH`, plus a `gfortran` symlink
  for the `-13`-suffixed driver. Two follow-on failures proved the
  chain: first the `-dev` symlink dangled (fixed by the runtime .deb),
  then `libmesh_F77/F90=gfortran` env overrides were needed because
  `build.mk` had already captured `no` from the Fortran-less libMesh
  configure (`?=` yields to environment, so no libMesh rebuild was
  required). Verified directly: Fortran hello-world link+run and a
  `-shared -fPIC` link of the actual `elastic.f` plugin source.
- **Platform considerations**: preflight is Linux-only; macOS runners
  install `gcc` (provides gfortran) and Windows MSYS handling is
  untouched.
- **Files changed**: `scripts/build/linux.py`, `test/test_build_env.py`
  (present / missing / fortran-only-missing cases), this log.
- **Verification**: 9/9 build-env tests pass; the relaunched build is
  past the plugins into module unity TUs.
- **Remaining uncertainty**: whether further Fortran bits (other test
  plugins) behave the same way — the build log decides; the mechanism
  is now uniform.

## 2026-10-01 — Packaged EM + MFEM sims with smoke and gold tests

- **Request**: stage MOOSE EM/MFEM test inputs as packaged sims for CI
  smoke tests, with one representative gold case each.
- **EM (fully delivered)**: `src/rabbit/sims/em/` holds 6 upstream inputs
  (byte-identical plus a provenance header), with two packaging
  adaptations found by testing, not assumed: (1) a `file_base =
  <case>_out` bare name was added to each `[Outputs]` block — without
  it MOOSE defaults the output base to the input file's directory, so
  installed users would write (or fail to write) into read-only
  site-packages, and the first test run polluted the source tree with
  `.e`/`.csv` outputs (cleaned); (2) `scalar_complex_helmholtz.i` was
  REMOVED from the set — it needs the test-only `MMSTestFunc` object
  (`not a registered object`; rabbit deliberately ships no MOOSE test
  objects), which no packaging can satisfy. Remaining `EM_CASES` (5)
  all converge serially. New `em_input_path()` accessor (+ exports),
  `test/test_electromagnetics.py` runs each case (rc 0 + `.e` present),
  `scripts/generate_em_gold.py` + `test/gold/em_vector_kernels.npz`
  (8.7 KB) + `test/test_em_gold.py` mirror the cube gold pattern for
  the representative `vector_kernels` case. `smoke.yml` run-gold legs
  (all three OSes) now also run `test_em_gold.py` — no solve-step
  changes, so MPI/mamba legs are untouched.
- **MFEM (staged, backend-gated)**: `src/rabbit/sims/mfem/` holds
  `diffusion.i` + `curlcurl.i` (mesh paths adapted to the packaged
  layout) plus `mug.e` (200 KB) + `small_fichera.mesh` (32 KB), with
  `mfem_input_path()` / `mfem_mesh_path()` accessors. `test/test_mfem.py`
  runs both cases with an absolute `Mesh/file=` override (immune to
  input-vs-cwd resolution semantics) but SKIPS loudly on binaries
  without the backend — the probe is behavioural and portable (rejects
  on `is not a registered object`, verified against the serial binary).
  NO MFEM gold `.npz` is committed: no runnable MFEM binary exists, and
  fabricating or borrowing one would make the baseline meaningless. The
  gold file + `test_mfem_gold.py` (same shape as `test_em_gold.py`) are
  explicit follow-up items for the MPI-variant work.
- **Reader fix the EM gold exposed**: `src/rabbit/exodus.py::_decode_names`
  crashed (`UnicodeDecodeError: 0xb9`) on EM output — the writer leaves
  uninitialized heap bytes (recognizable double bit-patterns) after the
  NUL terminator of short vector-component names (`u_y`). Fix truncates
  each name at the first NUL before strict-decoding (padding is never
  content; real content still decodes strictly). New
  `test/test_exodus.py` pins null/space/garbage padding. The existing
  HEX8 cube gold still passes with the new decoder (no regression).
  Debugging note: `ndarray.tolist()` on `|S1` drops NULs ( depletion via
  bytes-scalar conversion), so the fix uses `tobytes()`.
- **Packaging fix the wheel audit exposed**: hatchling honors
  `.gitignore` when selecting package files, so `*.e` (mug.e) and
  `*.msh` (stc/monoblock/plate meshes — a PRE-EXISTING bug: no `.msh`
  ever shipped) were silently absent from wheels. Added
  `!src/rabbit/sims/**/*.e` and `!src/rabbit/sims/**/*.msh` next to the
  existing csv negation. Verified in the rebuilt wheel (mug.e + 4 .msh
  present; no stray outputs).
- **Platform considerations**: all sim/test changes are
  platform-agnostic (generated meshes, portable probe, same gold
  tolerances as cube). Windows runs the same EM cases (Makefile-shared
  EM, serial LU).
- **Files changed**: `src/rabbit/sims/{em,mfem}/` (new),
  `src/rabbit/sims/{simulations.py,__init__.py}` (accessors),
  `test/{test_electromagnetics,test_mfem,test_em_gold,test_exodus}.py`,
  `test/test_simulations.py` (dataset assertions),
  `scripts/generate_em_gold.py` (new), `test/gold/em_vector_kernels.npz`
  (new), `src/rabbit/exodus.py` (NUL truncation), `.gitignore`
  (sims negations), `.github/workflows/smoke.yml` (gold legs).
- **Verification**: full suite 93 passed + 2 skipped (MFEM); EM gold
  passes; clean venv on the final wheel: `--version`, HEX8 solve, EM
  solve, MFEM accessor resolution all green.
- **Remaining uncertainty**: none for EM. MFEM execution + gold await
  the MPI-variant backend.

## Watch items (not fixed here)

- **Test-tree pollution**: the full-suite gmsh tests left
  `sims/dogbone/dogbone2d.msh` and `sims/plate_tensile/mesh2d_holeplate.msh`
  in the source tree (deleted). Pre-existing behaviour, but the new
  sims `*.msh` wheel negation makes a dirty tree shippable — CI is
  safe (wheel builds before tests run), local `--wheel-only` after a
  test run is not. A test-hygiene pass (force all generated outputs
  under `tmp_path`) is a separate issue.
- **`pyproject.toml`/`uv.lock` external edits** (see header note): left
  untouched; confirm with whoever bumped the version before committing.
- **Final wheels in `dist/`**: `rabbit_fem-2026.9.7` (40.7 MB, proof
  wheel with 2 inert HDF5 libs from the recipe detour) and
  `rabbit_fem-2026.10.0` (41.3 MB, clean recipe + packaged sims). Both
  verified working; neither is committed (`dist/` is gitignored).
