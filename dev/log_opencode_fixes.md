# OpenCode CI Fixes Log

## 2026-10-05 — MPICH staging (libmpich external) + MPI smoke --oversubscribe + windows-mpi setup-msys2 input (PR #11)

- **CI runs** (all PR #11, push `a76b3c0`, ~10:05 UTC): Windows MPI
  `37294305947` (`Build PETSc` fails in Hypre `make`), MPICH
  `37294306393` (`Build Rabbit...` fails in `stage_artifacts`), MPI/MFEM
  `37294306356` (build green, `MPI: Clean-machine smoke test`
  `111729704202` fails at `mpirun -n 4`).
- **First failure addressed here**: MPICH `37294306393` staging abort
  and MPI smoke slot refusal (both root-caused from logs); plus the
  `msys2-location` warning on the Windows MPI job. The Windows Hypre
  `make` failure is diagnosed below but deliberately left unpatched
  (no speculative changes; needs build-tree evidence).

### Root cause 1 (MPICH): MPI-ecosystem libs not excluded from staging

`stage_artifacts` (`scripts/build/common.py::find_needed_libraries`)
  treats `DT_NEEDED` entries as system-external only by prefix
  (`libmpi.so`, `libmpi_cxx.so`, `libopen-pal.so`, ... — the OpenMPI
  ecosystem, left external by design with the runtime installed in
  smoke). MPICH SONAMEs (`libmpich.so.12`, `libmpichcxx.so.12`,
  `libmpichfort.so.12`, from Ubuntu `libmpich12` in
  `/usr/lib/x86_64-linux-gnu`) match none of those prefixes, so they
  fall through to `available_libs` lookup (repo/moose trees + ELF
  RPATH + OpenMP index), miss everywhere, and raise
  `FileNotFoundError: ... required shared libraries were not found`.
  Companion defect: the patchelf RPATH hardcodes the OpenMPI dir
  (`/usr/lib/x86_64-linux-gnu/openmpi/lib`) for every Linux wheel,
  which is a nonexistent path on MPICH runners.

### Why the fix addresses root cause 1

- `"libmpich"` added to `system_prefixes`: MPICH runtime stays
  external exactly like OpenMPI (smoke already installs `mpich` when
  `mpi_impl == mpich`), so staging no longer demands a vendored copy.
  Prefix form covers `.so.12`/`cxx`/`fort` variants without hardcoding
  versions or absolute paths.
- `stage_artifacts` RPATH is now MPI-aware: MPICH wheels get only the
  relocatable `$ORIGIN` entries (MPICH libs resolve via the default
  loader path); serial and OpenMPI RPATHs are byte-identical to
  before. Serial never calls `mpi_impl()` (short-circuit), Windows
  (`win32`) takes the same `else` branch as before since its
  `RABBIT_MPI_IMPL` defaults to `openmpi`.

### Root cause 2 (MPI smoke): OpenMPI slot refusal on small runners

  `mpirun -n 4` for the MFEM multi-rank proof fails with "There are not
  enough slots available" (2-slot runners). The `-n 2` leg passed only
  incidentally. OpenMPI's documented remedy is `--oversubscribe`;
  MPICH's `mpirun` has no such flag (it oversubscribes by default), so
  a blanket flag would break the MPICH leg.

### Why the fix addresses root cause 2

- `smoke.yml` sets `MPIRUN_OVERCOMMIT=--oversubscribe` unless
  `mpi_impl == mpich` (empty otherwise), applied to both `-n 2` and
  `-n 4` invocations. Serial legs never enter the branch; MPICH
  commands render identically to before. No sleeps/retries; the flag
  is the documented slot policy, not a workaround.

### Root cause 3 (Windows MPI workflow): invalid setup-msys2 input

  Job annotations on every Windows MPI run: `Unexpected input(s)
  'msys2-location'` (valid: `location`, ...). The action ignores the
  unknown key and provisions a throwaway MSYS2, while `ps1` builds in
  the image tree — wasteful and confusing. One-word fix to the
  documented input, MPI workflow only (serial green build untouched).

### Windows Hypre make failure: diagnosis, no patch yet

- Evidence from the uploaded `configure.log` (`37294305947`): Hypre
  `configure` ran with our explicit `--host=x86_64-w64-mingw32` and
  reports `checking for suffix of object files... obj` plus
  `checking for mpi.h... no` / `checking for MPI_Comm_f2c... no`,
  then `make -j4` compiles `src/utilities` (echoed `zig-cc ... -c
  F90_HYPRE_error.c` lines, no compiler diagnostics) and dies at
  `zig-ar cr libHYPRE_utilities.a F90_HYPRE_error.o ...` with
  `ar: error: F90_HYPRE_error.o: No such file or directory`.
- What this rules out: the `--host` fix worked (configure completes);
  serial PETSc (no Hypre) is unaffected. What is still unknown: why
  `mpi.h` was not found despite `-I/c/msys64/mingw64/include`
  (header installed by the same script into the same `$MsysRoot`
  tree), and why zero-object compiles return success (OBJEXT=`obj`
  vs `zig cc -target x86_64-windows-gnu` default `.o` mismatch is one
  hypothesis; swallowed diagnostics is another). Hypre's own
  `config.log` (in `externalpackages/git.hypre/src/`) is not in the
  failure artifact, so the conftest failure reason is not observable.
- Next step (next watch tick): extend the `Upload build failure logs`
  step with `moose/petsc/arch-windows-opt/externalpackages/git.hypre/src/config.log`
  (and keep the change diagnostic-only), then root-cause from real
  evidence. No build-behavior change made here.

### Platform-specific considerations

- `common.py`: Linux ELF path only in effect; `darwin` branch and
  `win32` outcome unchanged (verified by branch analysis above).
- `smoke.yml`: shell/POSIX only; Windows smoke steps untouched.
- `windows_mpi_build_and_test.yml`: single key rename; serial
  `windows_build_and_test.yml` deliberately untouched while green.
- No hardcoded paths/users/drives: MPICH match is a SONAME prefix,
  RPATH uses `$ORIGIN`/documented system dir, smoke branches on the
  existing `mpi_impl` input.

### Files changed

- `scripts/build/common.py` (`system_prefixes` + MPI-aware RPATH).
- `test/test_staging.py` (new `test_mpich_libs_treated_as_system` +
  `readelf` fake).
- `.github/workflows/smoke.yml` (`MPIRUN_OVERCOMMIT`).
- `.github/workflows/windows_mpi_build_and_test.yml`
  (`msys2-location` -> `location`).

### How to verify

- Local: `.venv/bin/python -m pytest test/test_staging.py
  test/test_build_env.py` → 31 passed (incl. the new MPICH test).
- YAML: both edited workflows parse (`yaml.safe_load`).
- CI: next MPICH round should pass `stage_artifacts` to wheel
  packaging; next MPI smoke should pass the `-n 4` MFEM proof;
  Windows MPI should lose the `msys2-location` annotation (Hypre
  `make` still expected to fail until root-caused).

### Remaining uncertainty

- Windows Hypre `make` (see above): no patch until `config.log`
  evidence. If the `mpi.h` miss is a two-tree artifact, the
  `location` fix here may already change its presentation — the next
  log will tell.

## 2026-10-05 — Windows MPI: explicit --host for Hypre download (PR #11)

- **CI run**: Windows MPI `37290786009`, `Build PETSc` failed after
  ~11 min: `Error running configure on HYPRE`. MPI detection itself
  passed (configure reached the download stage).
- **Root cause**: Hypre's autotools `config.guess` cannot determine the
  MSYS host (`checking host system type...` empty, then `configure:
  error: invalid value of canonical host`). PETSc forwards toolchain
  variables but no host, so the download configure dies before
  compiling anything.
- **Fix**: `--download-hypre-configure-arguments=--host=x86_64-w64-mingw32`
  on the MPI PETSc flags (PETSc's documented per-download passthrough;
  verified to exist in-tree at `config/package.py:1780`). Explicit and
  correct: the whole toolchain already targets `x86_64-w64-mingw32`
  (libMesh `--host` uses the same value). Serial flags untouched.
- **Files changed**:
  `scripts/install_dependencies_windows.ps1`,
  `dev/log_opencode_fixes.md`.
- **Verification**: no unit-test surface (ps1 flag string); live proof
  is the next Windows MPI round (Hypre configure proceeds to compile).
- **Remaining uncertainty**: Hypre compile/link under zig-cc wrappers
  (next stage decides, fails loudly if not).

## 2026-10-05 — Windows serial: MSYS2 mirror 429s + Windows MPI: libmsmpi.dll.a (PR #11)

- **CI runs**: serial `37287530177` failed in `Build WASP and HIT`
  setup (`C:\msys64\usr\bin\python3.exe` not recognized); MPI
  `37287529425` failed in `Build PETSc` at the MS-MPI preflight despite
  a successful pacman install.
- **Root cause (serial, external flake)**: MSYS2 mirrors returned HTTP
  429 (rate-limit) mid-transaction (`failed retrieving file ...
  error: 429`, `failed to commit transaction`), so python3 never
  installed. Nothing wrong with our code or caches — the MPI run's
  identical transaction minutes later succeeded. Genuinely externally
  flaky (the one case retries are for), same justification as the
  existing submodule-clone retries.
- **Fix (serial)**: bounded retry (5x30s) around the MSYS2 tool-ensure
  pacman call; the existing missing-tool verification stays the
  fail-loud gate. Retry triggers only on non-zero pacman exit, so green
  runs are byte-identical.
- **Root cause (MPI, our filename bug)**: the package file list
  (packages.msys2.org) shows the import lib is
  `/mingw64/lib/libmsmpi.dll.a`, not `libmsmpi.a` — headers were right,
  the lib name was assumed. (Bonus from the same listing: the package
  ships real `mpicc/mpicxx/mpif90.exe` wrappers; deliberately not
  switching to them — the zig toolchain stays single-owner for all
  compiles.)
- **Fix (MPI)**: corrected lib filename in the preflight and the PETSc
  `--with-mpi-lib` flag (`-lmsmpi` was already correct and unchanged).
- **Files changed**:
  `scripts/install_dependencies_windows.ps1`,
  `dev/log_opencode_fixes.md`.
- **Verification**: 83 unit tests pass. Live proof is the next round of
  both Windows legs.
- **Remaining uncertainty**: mirror 429 recurrence rate (retry covers
  it); PETSc acceptance of the corrected lib path.

## 2026-10-05 — rabbit-fem-mpich variant + 3.9 floor legs removed (PR #11)

- **Scope**: `rabbit-fem-mpich` mirrors the OpenMPI/MFEM stack
  (PETSc/libMesh/Conduit/WASP/MFEM, `--with-mfem`) on the MPICH
  toolchain. Audit showed MOOSE's installer scripts are MPI-generic
  (no OpenMPI assumptions), so the variant is small by construction:
  `RABBIT_MPI_IMPL=mpich` selects explicit `mpicc.mpich`/`mpicxx.mpich`/
  `mpif90.mpich` wrappers (Debian suffix convention, verified against
  this box's `.openmpi` suffixes — immune to update-alternatives
  state) with `MPICH_CC/CXX` pointing at the zig wrappers; garbage
  values fail early. Wheel publishes as `rabbit-fem-mpich` (own PyPI
  project, user-owned at release); `variant.txt` stays `mpi` (the CLI
  is impl-agnostic; `PMI_SIZE` detection already covers MPICH).
- **Isolation**: all caches carry `-mpich` keys; serial and OpenMPI
  stacks untouched (default impl is openmpi; serial never consults it).
  Smoke gains an `mpi_impl` input (default openmpi, so all existing
  callers are byte-identical) selecting the runtime package per leg.
- **Floor removal**: the three `*-floor` jobs (3.9 negative legs)
  deleted per request — the `src` guard + `requires-python` floor +
  `test_python_floor.py` stay as product behavior.
- **Files changed**: `scripts/build/{common,linux}.py`,
  `test/test_build_env.py` (impl switch tests),
  `.github/workflows/linux_mpich_build_and_test.yml` (new),
  `.github/workflows/smoke.yml` (`mpi_impl`),
  `.github/workflows/{linux,macos,windows}_build_and_test.yml`
  (floor legs removed), `dev/log_opencode_fixes.md`.
- **Verification**: all 8 workflow YAMLs parse; 52 unit tests pass.
  Live proof is PR #11 CI (cold `-mpich` dep caches expected).
- **Remaining uncertainty**: MOOSE PETSc script acceptance of the
  mpich wrappers, MPICH runtime weight — first CI round decides.

## 2026-10-05 — Windows MPI: MS-MPI landed in the wrong MSYS2 tree (PR #11)

- **CI run**: Windows MPI `37280476119`, step `Build PETSc` failed in
  ~3 min in my own preflight: `requires system MS-MPI ...
  C:\msys64\mingw64\include\mpi.h`. MSYS2 setup + MS-MPI install steps
  were all green.
- **Root cause**: two MSYS2 trees on the runner. The setup action
  installed `mingw-w64-x86_64-msmpi` into its temp tree
  (`D:\a\_temp\setup-msys2\msys64` — proven: `installing
  mingw-w64-x86_64-msmpi...` in its log), but the ps1 builds with the
  detected `$MsysRoot` (image install `C:\msys64`), which never got the
  package. A workflow package list can only feed the action's tree, so
  it can never satisfy a build rooted elsewhere.
- **Fix**: single owner — the ps1 installs `mingw-w64-x86_64-msmpi`
  itself into `$MsysRoot` when the header/lib are absent (same ensure
  pattern as the existing tool installs, exit code checked loudly),
  keeping the fail-early throw when still absent. Removed the package
  from the workflow install list (dead weight feeding the wrong tree).
  Serial paths untouched (block is `$IsMpi`-gated; pre-existing silent
  pacman behaviour left as-is).
- **Files changed**:
  `scripts/install_dependencies_windows.ps1`,
  `.github/workflows/windows_mpi_build_and_test.yml`,
  `dev/log_opencode_fixes.md`.
- **Verification**: workflow YAML parses; 81 unit tests pass (+3
  skips; sim/gold need a built binary). Live proof is the next Windows
  MPI round (ps1 installs msmpi into `C:\msys64`, PETSc configure runs).
- **Remaining uncertainty**: pacman weight on the image tree; PETSc
  acceptance of the flags — the next round decides.

## 2026-10-05 — Windows MPI first go (branch windows-mpi, PR #11)

- **Scope**: initial Windows MPI variant assuming system MPI (MS-MPI), no
  MFEM (the MPI/MFEM backend stays Linux-only). New `windows_mpi_...`
  workflow: own `windows-mpi-*` cache keys (never shares state with the
  serial Windows stack), MS-MPI via `mpi4py/setup-mpi@v1` (SDK+runtime,
  `mpiexec` on PATH) plus MinGW import lib/headers via
  `mingw-w64-x86_64-msmpi` (the zig toolchain targets
  `x86_64-windows-gnu`, so the MinGW `.a` links cleanly — no
  space-in-path MSVC `.lib` quoting games). `ps1` changes are strictly
  gated on `$IsMpi = ($env:RABBIT_MPI -eq "1")`: PETSc
  `--with-mpi=1 --with-mpi-compilers=0` + explicit include/lib (MS-MPI
  ships no mpicc wrappers) + `--download-hypre=1` (MPI suite runs
  without the serial ILU fallback); libMesh `--with-mpi` via
  CPPFLAGS/LDFLAGS with the Hypre requirement kept; `variant.txt`
  `mpi` vs `serial`. Serial expansions verified identical (only
  whitespace delta). Test suite + `mpiexec -n 2` HEX8 proof; no
  compat/floor/mamba/smoke legs until the build is green.
- **CI cost note**: `scripts/**` is in the serial Windows wheel+dep
  keys, so serial cold-rebuilds once (standard file-granular cost).
- **Files changed**: `scripts/install_dependencies_windows.ps1`,
  `.github/workflows/windows_mpi_build_and_test.yml` (new),
  `dev/log_opencode_fixes.md`.
- **Verification**: workflow YAML parses; 50 unit tests pass; serial
  ps1 expansions traced identical. Live proof is PR #11 CI.
- **Remaining uncertainty**: PETSc/libMesh acceptance of the MS-MPI
  flags, Hypre download weight on MSYS, `mpiexec`/firewall behaviour —
  each fails loudly in its own step if so.

## 2026-10-02 — MPI/MFEM: cached MooseConfig.h without conf_vars.mk (PR #10)

- **CI run**: MPI/MFEM run `36992181427`, step `Build Rabbit, stage artifacts, and build wheel`: framework compile dies with `Moose.h:378: fatal error: 'mfem.hpp' file not found`, while every dep cache (PETSc/libMesh/Conduit/WASP/MFEM/MooseConfig) reported `Cache hit`.
- **Root cause**: cache-restore/build-script interaction, same class as the Sep-25 macOS PNG fix. The MOOSE-config cache stores only `MooseConfig.h` (the MFEM *decision*), never the generated `conf_vars.mk` that carries the matching `ENABLE_MFEM`/`MFEM_DIR` *flags* (moose.mk pulls MFEM via `$(MFEM_DIR)/share/mfem/config.mk`). On the fresh runner the restored header defines `MOOSE_MFEM_ENABLED` but `MFEM_DIR` is empty, so no `-I` reaches the compiler. Proven in the log: all six `-mpi-` keys hit, `Configure MOOSE` skipped, `conf_vars.mk` in no cache path and never mentioned. Sibling-run cache sharing under identical keys (same code) rules out cross-version poisoning.
- **Fix (structural, MPI-scoped)**: (1) `mpi_build_and_test.yml` caches `moose/conf_vars.mk` with the header (restore+save), so decision and flags travel together; (2) new `check_cached_moose_config()` in `linux.py`, called from `configure_moose`, deletes both files when the header claims MFEM but `conf_vars.mk` is missing or its `MFEM_DIR/include/mfem.hpp` does not exist — self-healing against already-poisoned saves. Serial headers never define the marker, so serial runs pass through byte-identical (variant isolation preserved). Workflow file is not hashed into dep keys, so no extra rebuilds beyond the one fresh configure.
- **De-poisoning**: deleted the header-only `linux-mpi-mooseconfig-efa943...` cache entry so the next run configures fresh and saves both files (old-recipe orphans remain unreachable).
- **Files changed**: `scripts/build/linux.py`, `test/test_build_env.py` (4 guard tests), `.github/workflows/mpi_build_and_test.yml`, `dev/log_opencode_fixes.md`.
- **Verification**: 19/19 `test_build_env` pass; live proof is the next MPI round (configure re-runs once, then `mfem.hpp` resolves and the framework links).
- **Remaining uncertainty**: none on mechanism.

## 2026-10-02 — Windows: XDR fallback test used non-portable path compare (PR #10)

- **CI run**: Windows `36982854740`, step `Run test suite`: `1 failed, 90 passed, 4 skipped` — the single failure is `test_linux_xdr_probe_falls_back_to_system_tirpc_include` (my own test from the Linux XDR fix, not product code).
- **Root cause**: test-harness portability bug. The test mocked `Path.is_dir` with `str(self) == "/usr/include/tirpc"`, but `str(WindowsPath)` renders backslashes (`\usr\include\tirpc`), so the comparison is False on Windows, the tirpc candidate is skipped, and the probe raises. Classic `/` vs `\` defect; proven locally with `PureWindowsPath` (`str` mismatches, `as_posix()` matches).
- **Fix (test-only)**: the probe-loop test now monkeypatches `_xdr_include_candidates` to a deterministic `[[], ["-I/usr/include/tirpc"]]` (no filesystem mock at all); candidate-builder coverage moved to a new test using `self.as_posix() == ...`, which normalizes separators on every platform. Assertions unchanged in strength.
- **Platform considerations**: test-only change; production `check_xdr_headers` already behaves correctly on Windows (the tirpc dir never exists there, so the candidate is skipped). Linux/macOS behavior unchanged.
- **Files changed**: `test/test_build_env.py`, `dev/log_opencode_fixes.md`.
- **Verification**: 25 passed (`test_build_env` + `test_moose_pins`) locally; `PureWindowsPath` simulation confirms old compare fails / new one matches. Live proof is the next Windows round (full suite green).
- **Remaining uncertainty**: none on mechanism.

## 2026-10-02 — MPI/MFEM vs serial variant isolation (PR #10 follow-up)

- **Context**: serial Linux `Build PETSc` log showed `Initializing missing MOOSE git submodules: ['petsc', 'libmesh', 'framework/contrib/wasp', 'framework/contrib/conduit', 'framework/contrib/mfem']` — the serial build was fetching MFEM/Conduit sources it never compiles against.
- **Root cause**: `ensure_moose_submodules` unconditionally required conduit+mfem, so any MFEM-side submodule/pin breakage could red the serial pipeline (and serial paid the fetch cost every cold build). Same coupling in `verify_moose_deps`, which checked MPI-only pins even for serial trees.
- **Fix**: new `_MPI_ONLY_MOOSE_DEPS = frozenset({"mfem", "conduit"})`; `ensure_moose_submodules` and `verify_moose_deps` skip those unless `is_mpi_build()` (RABBIT_MPI=1). Serial order is byte-identical to pre-MFEM (petsc/libmesh/wasp); MPI still materializes all five. `--checkout` flag kept unconditionally (harmless for serial, required for MPI's `update = none` submodules). CI already isolates via separate runners and `-serial`/`-mpi` cache keys — this closes the script-level coupling.
- **Platform considerations**: `scripts/build/common.py` only (shared, variant-gated — not OS-gated since MPI is Linux-only and darwin/windows callers are always serial, so they correctly skip too). No workflow/cache-key changes.
- **Files changed**: `scripts/build/common.py`, `test/test_moose_pins.py` (MPI ensure test pinned to RABBIT_MPI=1; new serial-skip + verify isolation tests), `dev/log_opencode_fixes.md`.
- **Verification**: 24 passed (`test_moose_pins` + `test_build_env`). Live proof: next serial round initializes only 3 submodules; next MPI round still gets all 5.
- **Remaining uncertainty**: none on mechanism. Same-tree dual-variant local builds remain unsupported (isolation via separate checkouts/runners, per existing convention).

## 2026-10-02 — Linux XDR preflight rejected healthy libtirpc-dev layout (PR #10)

- **CI run**: PR #10 Linux `36981263647`, step `Build libMesh` failed in ~1s: `RuntimeError: XDR (rpc) headers not found by the build compiler ... Install libtirpc-dev`, despite the workflow installing `libtirpc-dev`.
- **Root cause**: preflight bug, not a missing package. On Debian/Ubuntu `libtirpc-dev` ships headers under `/usr/include/tirpc` (there is no `/usr/include/rpc/rpc.h`), so a bare `#include <rpc/rpc.h>` compile always fails. libMesh's own `CONFIGURE_XDR` knows this and retries with `-I/usr/include/tirpc -ltirpc`; our `check_xdr_headers` only tried the bare compile, so it false-positived on a machine that would have built fine.
- **Fix**: probe mirrors libMesh's fallback order via new `_xdr_include_candidates()`: bare compile first, then env-derived prefixes (`TIRPC_DIR`, `CONDA_PREFIX/include/tirpc`, matching MOOSE's `configure_libmesh.sh`) and the documented `/usr/include/tirpc` system path (same `-I` libMesh tries). Non-existent dirs are skipped, so no bogus `-I` is passed. Compile-only (`-c`) is unchanged — the link half (`-ltirpc`) stays libMesh configure's job.
- **Platform considerations**: `scripts/build/linux.py` only; darwin/windows untouched. `/usr/include/tirpc` is a distro-documented location (also hard-coded in libMesh), not a runner-specific path; env prefixes keep conda/custom installs working via standard variables.
- **Files changed**: `scripts/build/linux.py`, `test/test_build_env.py` (new tirpc-fallback regression test), `dev/log_opencode_fixes.md`.
- **Verification**: 14/14 `test_build_env.py` pass (incl. new fallback + existing pass/fail probe tests); 42 passed across `test_build_env/test_moose_pins/test_variant`. Live proof is the next Linux round (preflight passes, libMesh configure runs).
- **Remaining uncertainty**: none on mechanism. If a future image lacks both the headers and the fallback dir, the probe still fails loudly naming `libtirpc-dev`.

## 2026-09-30 — Mamba smoke legs: built wheel via conda-managed env (py 3.13, all OSes)

- **Context**: CI was uv-only while colleague Mac failures were conda-based; no leg covered the conda install path (activation env vars, site-packages layout). Narrow by design, not a second matrix.
- **Scope**: new `<os>-mamba` jobs (Linux/macOS/Windows) reuse the just-built wheel artifact on a clean runner, create a `python=3.13 pip` env via `mamba-org/setup-micromamba@v2`, pip-install the wheel, and run `--version` + HEX8 `end_time=1` solve asserting `.e` output. 3.13 chosen deliberately: it is the primary build/test interpreter, so the installer is the only variable. Solve-only (no gold — covered 5x per OS via uv), no moose-from-mamba build, no checkout, same env-stripping as uv smoke. MPI workflow untouched (Linux-only variant, out of scope).
- **Platform considerations**: per-file native shells (bash Linux/macOS, pwsh Windows); Linux/macOS legs install the same system MPI runtimes the uv smoke requires; Windows leg success-asserts every native call immediately (the floor `$LASTEXITCODE` lesson). No shared code touched; no cache keys affected.
- **Files changed**: `.github/workflows/{linux,macos,windows}_build_and_test.yml`, `dev/log_opencode_fixes.md`.
- **Verification**: workflow YAML parses. Live proof is the next PR round (three ~5 min legs, no rebuild).
- **Remaining uncertainty**: `setup-micromamba@v2` API drift (action pinned at major v2); first run confirms `create-args`/`micromamba run -n` behavior on all three runners.

## 2026-09-30 — windows-floor green assertions but red step: trailing $LASTEXITCODE

- **CI run**: PR #8 Windows `36700028150`, job `Windows: Python 3.9 floor message` failed in `Floor: Assert clear error on Python 3.9` — yet the log shows the guard working exactly as designed (`RuntimeError: rabbit-fem requires Python 3.10 or newer (running 3.9.25)...`) followed by our own `Floor guard OK` line, then `Process completed with exit code 1`.
- **Root cause**: test-harness bug in the new pwsh step, not product. The probe `& $UVPY -c "import rabbit"` exits 1 by design, and pwsh keeps that native exit in `$LASTEXITCODE` past the subsequent `Write-Host`; GitHub fails pwsh steps on a nonzero trailing `$LASTEXITCODE`, so the step reported the probe's exit instead of its own verdict. The bash floor legs are immune (they end on `echo`, exit 0). Same-hazard audit: the Windows smoke solve block ends on success paths with `$LASTEXITCODE -eq 0` (each native call is immediately asserted), and the failure-comment step only runs on already-failed jobs — both left untouched.
- **Fix**: explicit `exit 0` as the last line of the floor assertion (both failure modes already `exit 1` above, so it only runs on success), with a comment recording the pwsh rule. Windows-only file; Linux/macOS behavior byte-identical. This is explicit verdict reporting, not error masking.
- **Files changed**: `.github/workflows/windows_build_and_test.yml`, `dev/log_opencode_fixes.md`.
- **Verification**: YAML parses; logic re-traced against the failed log (probe RC=1 → skip first branch; message match → skip second; `exit 0`). No local pwsh runner here — live proof is the next PR round (floor leg green in ~1 min, no rebuild needed).
- **Remaining uncertainty**: none on mechanism.

## 2026-09-30 — Windows compat legs run the HEX8/HEX20 gold comparison too

- **Report**: reviewer asked why Windows compat skips field comparison — it should match within floating point tolerance like the other OSes.
- **Root cause**: no product reason; it was workflow-scope economy. The original `run-gold` step was bash-only (`if: inputs.platform != 'windows'`), so `windows-compat` pinned `run-gold: false` to avoid a second shell spelling. The comparison itself (`test/test_cube_gold.py`: temperature, disp_x/y/z, strains, mesh, time, globals vs `test/gold/*.npz`) is platform-agnostic and already runs on Windows in the primary build job's suite (Python 3.13) — only the 3.10–3.14 compat legs skipped it.
- **Fix**: new pwsh `Smoke (windows): Gold regression (HEX8 + HEX20)` step in `smoke.yml` (same `-k "HEX8 or HEX20"` selection and tolerances, `throw` on nonzero exit, no masked errors) plus conditional `pytest numpy netCDF4` install in the Windows smoke venv; `windows-compat` now passes `run-gold: true`. Tolerances deliberately unchanged (`FIELD_RTOL=1e-5`, `FIELD_ATOL=1e-8`): the solver converges to ~1e-6 and the order of slack covers cross-platform BLAS differences (MSVC vs clang). Tightening to 1e-6 needs passing-margin evidence first — the newly-enabled Windows legs will provide it.
- **Files changed**: `.github/workflows/smoke.yml`, `.github/workflows/windows_build_and_test.yml`, `dev/log_opencode_fixes.md`.
- **Verification**: workflow YAML parses; unit suite unaffected (no product/test-code change). Live proof is the next PR round (Windows compat legs executing the gold step).
- **Remaining uncertainty**: whether all Windows interp legs pass at 1e-5 (expected yes — primary already does on 3.13); if margins are wide, a follow-up can evaluate 1e-6.

## 2026-09-30 — Python 3.10 floor + cross-version compat matrix + macOS re-sign/diagnostics (colleague Mac reports)

- **Reports**: (1) system Python 3.9 venv dies at import with `TypeError: unsupported operand type(s) for |` from `rabbit/sims/simulations.py:293` (`geo_path: Path | str`); (2) conda/brew Pythons 3.12–3.14 (plus venvs off them) die with `zsh: killed rabbit ...` even for bare `rabbit` (also `cube_thermomech_HEX20.i`).
- **Root cause (1)**: packaging-metadata bug, not a Mac bug. The codebase uses PEP 604 `X | Y` annotations (evaluated at `def` time, 3.10+) in `src/rabbit/sims/simulations.py`, `src/rabbit/exodus.py`, `scripts/build/common.py`, while `pyproject.toml` declared `requires-python = ">=3.9"`, so pip installs on 3.9 and import explodes deep inside. 3.9 is EOL since Oct 2025 — the floor was simply wrong.
- **Fix (1)**: `requires-python = ">=3.10"` plus a fail-fast guard at the top of `src/rabbit/__init__.py` (runs before any submodule import, since importing `rabbit.sims` executes the parent `__init__ first) raising `RuntimeError` naming the 3.10 floor — covers installs that bypass pip metadata (conda copies, direct checkouts). New `test/test_python_floor.py` pins the declared floor (regex-parsed, no `tomllib`, so the test itself runs on 3.10), the importability of the PEP 604 modules, and guard-before-import ordering.
- **Root cause (2), hypothesis pending evidence**: `killed` is kernel SIGKILL, distinct from all previous dyld aborts. Prime suspect is the missing re-sign: `relink_darwin_staged_artifacts()` rewrites Mach-O load commands via `install_name_tool` and never re-signed (`grep codesign` was empty); on Apple Silicon that invalidates the signature and the kernel SIGKILLs the binary off-builder. Arch mismatch and quarantine are backups — deliberately not patched blindly.
- **Fix (2a, structural)**: ad-hoc re-sign (`codesign --force -s -` over staged binary + libs, `check=True`, explicit `RuntimeError` if `codesign` absent) at the end of the darwin-only relink; Linux/Windows paths untouched. Existing relink unit test extended (mocked `which`, asserts all three files signed with `--force -s -`).
- **Fix (2b, CI catcher)**: new macOS-only `Mach-O diagnostics` step in `smoke.yml` (facts only: `uname -m`, `file`, `lipo -info`, `otool -L`, `codesign -dv` informational branch, then direct binary exec that names exit 137/SIGKILL loudly). `--version`/solve steps remain the gates; no `|| true` masking (informational commands guarded by `command -v`/explicit branches, failures after that `exit 1` with messages).
- **Compat matrix (the asked feature)**: `smoke.yml` gains `python-version` (default `3.13`, so release/MPI callers are behavior-identical) and `run-gold` inputs. Each OS workflow gains `<os>-compat` (matrix 3.10/3.11/3.12/3.14 reusing the just-built wheel: install + audit + `--version` + HEX8 solve + HEX8/HEX20 gold regression via existing `test/test_cube_gold.py`; Windows legs solve-only, gold covered on Linux/macOS + primary suite) and `<os>-floor` (3.9 negative leg asserting the clear floor message, needs no artifact). Gold checkout is sparse (`test` + `pyproject.toml`, no submodules; `moose/` is gitignored so the no-in-tree clean-machine invariant holds). Build once, test many — no per-version rebuild.
- **Files changed**: `pyproject.toml`, `src/rabbit/__init__.py`, `test/test_python_floor.py` (new), `scripts/build/darwin.py`, `test/test_darwin.py`, `.github/workflows/{smoke,linux_build_and_test,macos_build_and_test,windows_build_and_test}.yml`, `dev/log_opencode_fixes.md`.
- **Verification**: 62 unit tests pass (incl. 3 new floor + extended relink test); all four workflow YAMLs parse; `git diff --check` clean. Live proof is the next PR round (compat/floor/diagnostics legs). Local repro of the 3.9 message needs a 3.9 interpreter (not installed here).
- **Remaining uncertainty**: the exact kernel kill reason on the colleague's machine (signature vs arch vs quarantine) — the diagnostics leg is designed to answer it on the first run. MPI workflow untouched (Linux-only, out of scope); `macos-15-intel` leg is future work if arch mismatch is confirmed. Cache cost: `pyproject.toml` is in every wheel key so all OSes rebuild the app stage once (deps stay cached); `darwin.py` is additionally in the mac dep keys so macOS cold-rebuilds deps once.

## 2026-09-29 — Release check globbed hyphenated MPI wheel name (nothing was missing)

- **CI run**: release `36546376398` (v2026.9.6) failed in `Verify all required platform wheels are present`: `Found 2 Linux, 1 Windows, 1 macOS and 0 MPI ... Missing rabbit-fem-mpi wheel`, yet `dist/` plainly contained `rabbit_fem_mpi-2026.9.6-...-manylinux_2_38_x86_64.whl`.
- **Root cause**: check-script bug, not a missing artifact. The Linux/Windows/macOS counts glob platform tags (`*manylinux*`, `*win_amd64*`, `*macosx*`), which survive wheel-filename normalization verbatim — but the MPI count globbed the distribution name with hyphens (`rabbit-fem-mpi-*.whl`), while PEP 427 normalizes it to `rabbit_fem_mpi-*.whl` on disk. The download step worked; only the assertion could never match.
- **Fix**: `mpi_count` now globs `dist/rabbit_fem_mpi-*.whl`, with a comment recording the normalization rule. No other hyphenated filename references exist (artifact *names* like `rabbit-fem-mpi-wheel` are unaffected — only wheel *filenames* normalize).
- **Files changed**: `.github/workflows/release.yml`, `dev/log_opencode_fixes.md` (one commit).
- **Verification**: YAML parses; replayed the exact check against the four real filenames from the failed run's `dist/` listing — old glob counts 0 (reproduces the failure), new glob counts 1 and the full block passes.
- **Re-release note**: re-running the failed jobs would reuse the pre-fix SHA, so the fix must reach `main` first; then move the unpublished `v2026.9.6` tag to the new merge commit and push it to retrigger (`publish` never ran, so nothing consumed the tag). Expect a full cold rebuild on main (release jobs are restore-only and main has no dep caches yet).

## 2026-09-29 — Green board on afb85c2 (all four pipelines + smokes)

- **Runs** (PR #6, SHA `afb85c2`): Linux `36530439070` success (1h08m, incl. smoke), macOS `36530439027` success (42m, incl. smoke), Windows `36530438997` success (42m), MPI `36530438983` success (1h55m, incl. smoke). The mac serial wheel is now genuinely self-contained (bundled `libomp.dylib` + `libpng16.16.dylib`, no `-lX11`, `--with-x=0` PETSc) and the dep-cache fallback trap is closed on every OS.
- **Files changed**: none (this entry only).

## 2026-09-28 — macOS staging names libpng16 as the next absolute brew dep

- **CI runs**: macOS `36445828175` + `36447732261` (both carry the libomp fix) fail identically in `Build Rabbit, stage artifacts, and build wheel`: `FileNotFoundError: Cannot create a standalone wheel; required shared libraries were not found: libpng16.16.dylib`.
- **Root cause**: same class as libomp — the serial binary links Homebrew libpng (from the `brew install libpng` added for the MOOSE PNG-configure fix) by absolute path, and only libomp had been allowlisted for staging. The new loud-unresolved behavior worked as designed: it named the exact missing lib at build time instead of shipping another dyld time-bomb.
- **Fix**: renamed `_DARWIN_OPENMP_PATTERNS` → `_DARWIN_HOMEBREW_RUNTIME_PATTERNS` (explicit per-lib allowlist so each external runtime stays a conscious bundling decision) and added `libpng16*.dylib` under both brew prefixes. If further absolute brew deps hide behind libpng, staging names each one in turn.
- **CI cost note**: `common.py` is in the serial/MPI dep keys again, so one more cold dep round on Linux-serial, Linux-MPI and macOS-serial; Windows untouched.
- **Files changed**: `scripts/build/common.py`, `test/test_staging.py`, `dev/log_opencode_fixes.md` (batched in one commit to avoid retrigger spam).
- **Verification**: 75 unit tests pass; live proof is the next mac round (staging includes both `libomp.dylib` and `libpng16.16.dylib`, smoke `--version` on a brew-less runner).
- **Remaining uncertainty**: further absolute brew deps behind libpng (e.g. a brew zlib instead of system libz) — staging will name them if so.

## 2026-09-28 — Linux cold rebuild hit GitLab outage (external flake, no code change)

- **CI run**: Linux `36445828196` (SHA `595edc9`) failed at 5 min in `Build PETSc`: `git submodule update` could not clone `libmesh/contrib/eigen/git` — `fatal: remote error: GitLab is currently unable to handle this request due to load`, repeated across git's internal retries and our 5×30s backoff in `ensure_moose_submodules` (the 30s gaps are visible in the clone timestamps; the attempt lines share a timestamp only due to stdout buffering). Linux was green before solely because warm caches never reached the clone step; the `common.py` key-bust forced a cold checkout into the outage window.
- **Response**: no code change — the retry logic worked as designed and the outage outlasted it (genuinely externally flaky, the one case retries are for). Probed GitLab recovery (`git ls-remote` OK), then re-triggered: `gh run rerun --failed` was refused by the API ("workflow file may be broken"), so ran `gh workflow run "Linux: Build Wheel and Test" --ref dev` (same HEAD); the original PR run also restarted. Both validate identical code; duplicate cache saves under the same keys are harmless (caches are immutable, content identical).
- **Files changed**: none (this entry only).
- **Remaining uncertainty**: none on cause. If GitLab outages recur, consider raising `max_attempts`/backoff — deliberately not tuned on a single data point.

## 2026-09-28 — macOS wheel omits Homebrew libomp (dyld abort on clean machines)

- **CI run**: macOS smoke `36442246527` (SHA `cf0bcfb`; build+tests green) — clean-venv `--version` dies: `dyld: Library not loaded: /opt/homebrew/opt/llvm/lib/libomp.dylib ... Abort trap: 6`.
- **Root cause**: two layered defects in the shared staging code, both asymmetries with the Linux path. (1) `index_system_openmp_libs` early-returned on darwin, so the Linux fix that bundles the OpenMP runtime was never ported: the mac linker records the absolute brew path and nothing staged it. (2) The darwin branch of `find_needed_libraries` silently dropped unresolvable deps (no `unresolved_libs.add` like the Linux branch), so staging shipped the time-bomb instead of failing loudly; the smoke otool audit only forbids `/Users|/home|/tmp|/opt/moose`, so `/opt/homebrew` sailed through. Build-machine tests are blind to this (brew llvm is installed there) — same blind-spot class as the PyPI data-file bug.
- **Fix**: `index_system_openmp_libs` now defaults per platform (`_DARWIN_OPENMP_PATTERNS` covers arm64+Intel prefixes × llvm+libomp providers; explicit `patterns` still overrides for tests), so `libomp.dylib` resolves, stages, and relinks to `@rpath` via the existing darwin relink — the serial wheel becomes genuinely self-contained, matching Linux (`libomp.so.5`) and the README claim. Darwin unresolved deps are now recorded, so `stage_artifacts` raises `FileNotFoundError` naming any future absolute brew dep instead of shipping it. Linux/Windows behavior unchanged (same Linux defaults/selection; win32 never exercises this path).
- **CI cost note**: `common.py` is in the Linux-serial, Linux-MPI and macOS-serial dep keys, so all three cold-rebuild deps once (no fallback to blunt it — that is the point); Windows keys don't hash it. One-time cost for wheels that are actually relocatable.
- **Files changed**: `scripts/build/common.py`, `test/test_staging.py` (old darwin early-return assertions replaced; 4 new tests incl. mocked-otool unresolved/resolved), `dev/log_opencode_fixes.md`.
- **Verification**: 75 unit tests pass; `git diff --check` clean; live proof is the next mac round (staging must include `libomp.dylib`, smoke `--version` on a brew-less runner).
- **Remaining uncertainty**: whether the serial mac binary carries further absolute brew deps behind libomp — the new loud failure names each one if so; dyld only reports the first missing lib.

## 2026-09-28 — macOS isolated solve aborts: darwin test branch omits serial ILU override

- **CI run**: macOS `36433969215` (SHA `35d577e`) — full product pipeline green for the first time on serial mac (cold PETSc with `--with-x=0`, libMesh link, WASP, MOOSE config, Rabbit, wheel), then `Run test suite` fails at 61 min: `test_binary_and_library_relocatability` (darwin step 3) — isolated solve returns `-6` (SIGABRT) seconds after isolated `--version` passes.
- **Root cause**: test-harness inconsistency, proven locally. The HEX8 input requests `hypre boomeramg`; serial PETSc ships no Hypre, so the raw binary aborts with `PETSC ERROR: Unable to find requested PC type hypre`. Local repro on the serial `rabbit-opt`: without `-pc_type ilu` → abort (rc=134); with it → rc=0 plus Exodus output. Every other serial solve path already compensates — `run_rabbit` auto-injects `-pc_type ilu` (all 9 in-place sim tests pass through it) and the win32 isolated-solve branch carries `"Executioner/end_time=1", "-pc_type", "ilu"` — but the darwin branch invokes the relocated binary directly with bare `[-i, input]`, the only path missing both flags. (Missing `end_time=1` did not cause the abort — the abort was immediate — but the full-length solve would needlessly slow the test.)
- **Fix**: darwin isolated solve now passes `"Executioner/end_time=1", "-pc_type", "ilu"`, byte-identical to the win32 invocation. Test-only change, darwin branch; win32/Linux branches untouched (Linux has no isolated solve).
- **Files changed**: `test/test_simulations.py` (darwin step-3 invocation only), `dev/log_opencode_fixes.md`.
- **Verification**: 71 unit tests pass; local serial binary aborts without / converges with the flag pair; live proof is the next mac round (step 3 solve). Next run also skips all dep stages (PETSc/libMesh/WASP/MooseConfig now cached under current keys), so ~15–20 min instead of 61.
- **Remaining uncertainty**: none on mechanism.

## 2026-09-28 — Dep-cache prefix fallbacks silently keep stale trees (X11 fix never built)

- **CI runs**: macOS `36429923149` (SHA `60a4ee1`, contains the `--with-x=0` fix) still fails at the libMesh link with `ld: library 'X11' not found`; the PETSc linklibs in its own log still carry `-lX11`. Linux `36429998002` on the same recipe went green.
- **Root cause**: cache-restore + build-script interaction, not the flag. The `--with-x=0` change busted the exact dep-cache key, but `restore-keys: <prefix>-` fell back to the *old* poisoned PETSc tree; `build_petsc` then saw `libpetsc.dylib` and short-circuited with `[OK] PETSc already built`, so the new configure never ran. The `Save` step (gated on exact `cache-hit != true`, which a fallback hit satisfies) then stored the stale tree under the *new* key — re-poisoning it for all later runs. Proven in logs: `Cache hit for restore-key: macos-serial-petsc-bca64...` → `[OK] PETSc already built` → `Cache saved with key: macos-serial-petsc-66307...`; identical chain on Linux (`linux-serial-petsc-c813...` fallback → already-built → save under `47a5...`). Linux stayed green only because `-lX11` resolves on Ubuntu, not because it rebuilt.
- **Fix (structural, all OSes)**: removed all 32 `restore-keys` prefix fallbacks from dependency-cache restores in `macos/linux/mpi/windows_build_and_test.yml` and `release.yml` (16 blocks there), with a rationale comment per job. A key miss now means the recipe changed, so any older tree would be stale by definition — a miss cold-rebuilds, which is what a recipe change requires. Exact-hit behavior is unchanged, so green OSes keep their fast path; each file's change is confined to its own workflow (compartmentalised per OS). Release restores included: a stale fallback there would ship stale release binaries, and a genuine miss there should fail loudly instead.
- **De-poisoning**: deleted the three stale exact-key entries that fallback restores had saved — `macos-serial-petsc-66307...`, `linux-serial-petsc-47a5...`, `linux-serial-libmesh-47a5...` (libMesh embeds PETSc's link line, so it must rebuild against the X11-free PETSc too). Kept `*-wasp/mooseconfig` and all MPI/Windows entries: those recipes are unchanged, so their content is current. Old-recipe orphans remain in storage but are unreachable without fallbacks (GitHub evicts unused caches).
- **CI cost note**: one cold rebuild of the serial PETSc (+ Linux serial libMesh) stages on mac/Linux; MPI/Windows exact-hit and skip.
- **Files changed**: `.github/workflows/{macos,linux,mpi,windows_build_and_test,release}.yml`, `dev/log_opencode_fixes.md`.
- **Verification**: all 6 workflow files YAML-parse; `git diff --check` clean; unit suite 71 passed (no test references cache keys); live proof is the next mac round (PETSc must genuinely configure — look for `--with-x` in the configure line, then a libMesh link without `-lX11`).
- **Remaining uncertainty**: local dev checkouts with pre-existing `./moose*` trees have the same short-circuit staleness and must rebuild manually once; an in-script recipe stamp (cf. `check_cached_moose_config`) would close that loop but is future work.

## 2026-09-28 — macOS serial link: PETSc bakes unresolvable -lX11 (shared serial recipe)

- **CI run**: macOS `36422829623` (PR #6) — serial libMesh link dies: `ld: library 'X11' not found`.
- **Root cause**: my serial PETSc configure (both OSes) lets PETSc detect system X11 and record `-lX11` in `PETSC_WITH_EXTERNAL_LIB` with no resolving `-L`; the flag then poisons every downstream libMesh/app link. Verified in the local serial tree's `petscvariables`. Same latent issue exists in MPI PETSc (untouched — green everywhere, out of scope).
- **Fix**: `--with-x=0` in both `_build_petsc_serial` functions (Linux + Darwin). Headless Rabbit solves never use X11 viewers; matches the Windows recipe, which already passes it. Deliberately shared code: the recipe is identical, and per-OS divergence here would just be two copies of one flag.
- **CI cost note**: the flag change busts serial dep keys (correct — artifacts must rebuild) and, since MPI keys hash the same files, the MPI stack rebuilds once too despite unchanged MPI flags. One-time cost of file-granular cache keys.
- **Files changed**: `scripts/build/{linux,darwin}.py`, `dev/log_opencode_fixes.md`.
- **Verification**: unit suite green; live proof is the next mac round (libMesh link without `-lX11`).
- **Remaining uncertainty**: none on mechanism.

## 2026-09-28 — macOS serial finds MPI brew stack; OS isolation hardened

- **CI run**: macOS `36416368229` (PR #6) — serial libMesh build dies in `exodusII_io_helper.C`: bundled `netcdf_par.h` pulls `/opt/homebrew/include/mpi.h`, whose declarations clash with the serial `typedef int MPI_Comm` fallback.
- **Root cause**: two compounding causes. (1) The mac build env still installed `open-mpi`/`hdf5-mpi` and the serial `darwin.py` env kept the bare brew prefix on every search path, so serial libMesh configure discovered the MPI stack and enabled parallel-netCDF support a serial build must never see. Neutralising only HDF5 was insufficient. (2) Structural: nothing pinned per-OS build behaviour, so shared-file edits (the serial flip in `common.py`) broke other OSes silently — same story as the Linux `mpicc`/cache-key failure one round earlier.
- **Fix**: mac build envs (`macos_build_and_test.yml`, release `build-macos`) no longer install `open-mpi`/`hdf5-mpi`; serial `get_darwin_tool_env` strips the bare brew prefix from all search paths (llvm/omp/bison/flex stay explicit); MPI-mode output verified byte-identical in shape to the pre-change env. New `test/test_build_env.py` pins each OS tool env per variant (Linux: mpicc vs direct wrappers; macOS: HDF5/MPI presence vs absence, including hostile ambient env) — editing one OS pipe now breaks its own test, not another OS's build.
- **Platform considerations**: darwin.py + mac workflows only; Linux/Windows behaviour byte-identical (their tests prove it). The `darwin.py` touch busts the Linux/mac wheel keys (they hash `scripts/build/**`), so both rebuild the app stage once; dep caches are unaffected.
- **Files changed**: `.github/workflows/{macos_build_and_test,release}.yml`, `scripts/build/darwin.py`, `test/test_build_env.py` (new), `dev/log_opencode_fixes.md`.
- **Verification**: 55 unit tests pass (incl. hostile-env run); live proof is the next mac round (cold serial libMesh with no MPI in sight).
- **Remaining uncertainty**: whether serial mac libMesh configure wants anything else the MPI stack used to provide (e.g. serial netcdf — bundled in contrib, expected fine); the build log decides.

## 2026-09-28 — Windows: serial-patch unit test cannot spawn patch binary (scoped out)

- **CI run**: Windows `36411602373` (PR #6) — `66 passed, 1 failed` in `Run test suite`: new `test_apply_serial_patches_idempotent` dies in `CreateProcess` with `WinError 2`, while the Darwin patch tests on the same runner (same `patch` lookup) pass.
- **Root cause**: test-scope bug, exact spawn mechanism undetermined from here. Windows patching (including every serial fallback the Windows binary needs) is owned end-to-end by `install_dependencies_windows.ps1`, which applies unconditionally — `apply_serial_patches` is unreachable in all automated Windows flows, and the `patch` binary is only ever consumed on POSIX. The helper now resolves the binary via `shutil.which` (fail-fast `RuntimeError` instead of `WinError 2`), adds `-r -` parity with the proven Darwin invocation, and the `build_rabbit_binary` call site is gated to non-Windows; the unit test skips on win32 with that reason. No coverage lost where the code runs (Linux/macOS exercise it).
- **Side effect to expect**: touching `scripts/build/common.py` busts the Windows wheel-cache key, so the next Windows run rebuilds fully (~40 min) instead of cache-hitting.
- **Files changed**: `scripts/build/common.py`, `test/test_variant.py`, `dev/log_opencode_fixes.md`.
- **Verification**: 45 unit tests pass locally; live proof is the next Windows round.
- **Remaining uncertainty**: why `CreateProcess('patch', …)` fails while the Darwin tests spawn it fine on the same runner — moot for CI now, would only matter to a Windows dev hand-running `build_rabbit.py --wheel`, who gets the explicit error.

## 2026-09-28 — Serial/SMP default + rabbit-fem-mpi variant (feature build, verified locally)

- **Goal**: default `rabbit-fem` MPI-free (SMP via `--n-threads`), opt-in `rabbit-fem-mpi` (Linux-only phase 1). `[mpi]` extras cannot swap binaries, so two PyPI distributions; `rabbit-fem-mpi` name verified available (PyPI 404), pending trusted publisher still to add.
- **Build switch**: `RABBIT_MPI=1` env (or `--mpi`/`--no-mpi` flags); default serial. `linux.py`: serial tool env drops mpicc wrappers, PETSc configures directly (`--with-mpi=0 --with-fc=0`, f2cblaslapack, shared) since MOOSE's petsc script hardcodes `--with-mpi=1` + MPI-only downloads; libMesh omits `--with-mpi` (explicit `--disable-mpi` makes libMesh drop PETSc entirely per its own macro — found empirically) and overrides `--enable-petsc-hypre-required`. `darwin.py`: mechanical mirror plus HDF5 neutralisation so serial PETSc cannot link brew hdf5-mpi (unproven on hardware; mac CI decides). `build_rabbit_binary`: serial uses zig wrappers directly. Same `arch-moose` in both variants; isolation is via separate checkouts/runners, never shared trees.
- **Serial porting fixes** (all prefigured by the Windows port): `ensure_serial_mpi_fallback()` appends the `MPI_Comm`/`MPI_COMM_WORLD` fallback to generated `MooseConfig.h` (serial only, idempotent); `patches/serial/moose.patch` (new, 4 files / 34 insertions: `MemoryUtils.C` + `SMAAspUserUtilities.h` mpi.h guards, `SolutionUserObjectBase.C` Nemesis guards ported from the Windows patch hunks that applied cleanly at this pin, `SendBuffer.h` forceSend MPI guard) applied idempotently from `build_rabbit_binary` in serial mode.
- **Runtime**: `src/rabbit/variant.txt` marker staged per variant (ps1 stages `serial`; pre-marker wheels fall back to platform inference); ILU fallback keyed off the marker instead of `win32`; CLI + `run_rabbit` refuse multi-rank launches of serial builds (exit 2 / RuntimeError pointing at `rabbit-fem-mpi`); `build_wheel` renames to `rabbit-fem-mpi` for MPI builds.
- **Local proof (this machine, ./temp/)**: serial stack built in `./temp/moose-serial` (pinned SHAs verified); serial `rabbit_fem-2026.9.6` wheel (38 MB, zero MPI/HDF5 linkage by readelf); clean-venv install solves HEX8 (returncode 0) and `--n-threads=2` reports `Num Threads: 2` with bit-identical fields vs 1 thread; MPI `rabbit_fem_mpi-2026.9.6` wheel clean-venv installed, `mpirun -n 2` reports `Num Processors: 2` and converges. New `test/test_variant.py` (21 tests) + updated darwin MPI-flag test; full suite 67 passed.
- **CI**: `mpi_build_and_test.yml` (own `-mpi` caches, PR triggers) + `smoke.yml` `mpi:true` mode (`mpirun -n 2` solve) + serial SMP `--n-threads=2` check (Linux/macOS only; Windows libMesh is `--with-thread-model=none`); release publishes `rabbit-fem-mpi` gated on its smoke. Windows ps1 untouched apart from the variant marker (already serial).
- **Not done / watch items**: mac serial unproven (mechanical darwin changes await mac CI); local MPI relink from the Sep-25 tree fails on stale `-lhdf5` flags — pre-existing env rot, unrelated, CI builds fresh (do not `make` MPI locally; MPI staging was restored from the MPI wheel); `./temp/moose-serial` retained (~GBs) for future serial work; flipping the default is breaking for `mpirun` users of `rabbit-fem` — needs a version bump + migration note at release.
- **Files changed**: `scripts/build/{common,linux,darwin}.py`, `build_rabbit.py`, `src/rabbit/{cli.py,sims/simulations.py}`, `scripts/install_dependencies_windows.ps1`, `pyproject.toml`, `.gitignore`, `patches/serial/moose.patch` (new), `test/{test_variant.py,test_darwin.py}`, `test/test_staging.py`, `.github/workflows/{mpi_build_and_test.yml,smoke.yml,release.yml}`, `README.md`, `dev/log_opencode_fixes.md`.

## 2026-09-28 — Smoke fails on missing MPI runtimes (system dependency, not a packaging bug)

- **CI runs**: first `smoke.yml` round — Linux dies at `--version` with `libmpi_usempif08.so.40: cannot open shared object file` (exit 127); macOS aborts in dyld on `/opt/homebrew/opt/hdf5-mpi/lib/libhdf5_hl.320.dylib`.
- **Root cause**: neither is a packaging regression. The wheel deliberately links the MPI ecosystem externally on both platforms: Linux `find_needed_libraries` excludes `libmpi*`/`libopen-*` via `system_prefixes` (staged RPATH even falls back to the system openmpi lib dir), and macOS intentionally leaves Homebrew MPI/HDF5 absolute (prior deliberate decision). Fresh smoke runners install no MPI, so even serial runs fail at load time. The smoke jobs replicated a bare machine but omitted the documented runtime prerequisite the wheel is designed against.
- **Fix (CI-only, no product change)**: `smoke.yml` now installs the runtime before solving — `openmpi-bin` via apt on Linux, `open-mpi hdf5-mpi` via brew on macOS — and runs the `ldd`/`otool` linkage audit *before* `--version` so missing-library failures diagnose cleanly. Bundling MPI/HDF5 into the wheels instead was rejected: `mpirun`-based parallel runs (documented in README) require a version-matched system MPI anyway, so bundling `libmpi` while using the system launcher risks lockstep breakage.
- **Docs**: README Installation gains a "Runtime system requirements" section (Linux: `openmpi-bin`; macOS: `open-mpi hdf5-mpi`; Windows: none, fully static).
- **Files changed**: `.github/workflows/smoke.yml`, `README.md`, `dev/log_opencode_fixes.md` (this entry).
- **Verification**: strict duplicate-key YAML parse over all five workflow files; live proof is the next smoke round. Deliberately no local binary runs for this CI-only change.
- **Remaining uncertainty**: whether any third runtime lib beyond the MPI closure is missing on bare machines — the reordered audit-then-version sequence will name it exactly if so.

## 2026-09-28 — PyPI install fails "Failed to determine data file path for 'moose'" (product bug + CI blind spot)

- **Report**: clean `pip install rabbit-fem==2026.9.5` into a fresh venv aborts at startup in `Registry::determineDataFilePath` for `'moose'` (then would hit `'solid_mechanics'` next: `SolidMechanicsApp.C` also calls `registerAppDataFilePath`).
- **Root cause (product)**: `determineDataFilePath` tries `<exe>/../share/<name>/data` first, then falls back to absolute in-tree paths baked in at compile time. The wheel staged `bin/` + `lib/` only — no `share/` — so on any machine other than the builder both lookups fail.
- **Root cause (CI blind spot)**: every existing check runs on the machine that just built the binary, where the baked in-tree path (`/home/runner/work/.../moose/...`) still exists — the fallback silently rescues the missing installed path. Same-machine smoke tests and the build-tree suite therefore cannot see this failure class.
- **Fix (product)**: new `stage_moose_data()` in `scripts/build/common.py` (called from `stage_artifacts`) stages `moose/framework/data` and `moose/modules/solid_mechanics/data` to `src/rabbit/share/<name>/data`; same staging added to `install_dependencies_windows.ps1` §11b; `src/rabbit/share/` gitignored; `src/rabbit/share/**/*` added to wheel `artifacts`; `src/rabbit/share` added to all wheel-cache paths.
- **Fix (CI)**: new reusable `.github/workflows/smoke.yml` (`workflow_call`, CI-only): fresh runner, no checkout (hence no `moose/` tree), downloads the exact wheel artifact, clean uv venv install, `--version` + `ldd`/`otool` audit + real HEX8 `cube_thermomech` solve. Wired as `*-smoke` jobs in all three build workflows (runs on every PR, no rebuild) and in `release.yml` with `publish` gated on all three smoke jobs.
- **Files changed**: `scripts/build/common.py`, `scripts/install_dependencies_windows.ps1`, `pyproject.toml`, `.gitignore`, `test/test_staging.py` (2 new unit tests), `.github/workflows/{smoke.yml,linux,macos,windows_build_and_test.yml,release.yml}`.
- **Verification**: rebuilt wheel contains `rabbit/share/{moose,solid_mechanics}/data` (4 files); with both in-tree data dirs hidden, a HEX8 `end_time=1` solve converges (returncode 0, `.e` produced) — the installed path resolves; in-tree data restored intact; `test_staging` + `test_moose_pins` → 11 passed; all workflow YAML parses with correct job/call structure. Live proof is the next CI round (smoke jobs) and the next PyPI install.
- **Remaining uncertainty**: none on mechanism. Whether any other runtime file class (e.g. module `.json` outside `data/`) is install-path-sensitive will surface in the fresh-runner smoke solve.

## 2026-09-28 — All OS: darwin patch tests fail where submodule sources absent (test bug exposed by wider suite)

- **CI runs**: first 3-OS release — Linux and macOS `Run test suite` fail identically (`3 failed, 38 passed`): `test_poly2tri/libmesh/wasp_patch_applies_to_pristine_tree` die in `shutil.copy` with `FileNotFoundError` for `moose/libmesh/.../shapes.h`, `moose/libmesh/.../dof_object.h`, `moose/.../wasp/.../Format.h`.
- **Root cause**: test-harness assumption, not product. The three tests copy real files out of the local `moose/` submodule checkouts, but `moose/` is gitignored (not a submodule) — its content exists only when a build step materialized it. `release.yml` restores built artifacts only (`installed/`, `arch-*/`, `MooseConfig.h`), never submodule sources, so the files are absent. Previously `run_tests` ran only `test_simulations.py`, hiding the assumption; widening it to `test/` exposed it. (The tinyhttp sibling passed because `moose/framework` *is* materialized via the shallow framework fetch.)
- **Fix**: new `_require_pinned_source()` helper in `test/test_darwin.py` — `pytest.skip` with the missing path when the pinned source is not materialized, applied at the three `shutil.copy` sites. Same precedent as the file's existing absent-source handling and `verify_moose_deps`' unverifiable-checkout warning. Build-and-test workflows (which materialize sources) still exercise the patches; release jobs skip cleanly.
- **Platform considerations**: test-only change, OS-independent; no product or workflow files touched.
- **Files changed**: `test/test_darwin.py` (helper + 3 call sites), `dev/log_opencode_fixes.md` (this entry).
- **Verification**: full `test_darwin.py` → 16 passed locally (sources present, patches genuinely exercised); helper probed against absent path → `Skipped`; absent-path behavior is exactly the release-runner state. Next release round is the live proof (expect `3 skipped, 38 passed` there, full pass in build-and-test).
- **Remaining uncertainty**: none on mechanism.

## 2026-09-25 — Green matrix on bfc941d (all three OS)

- **Runs**: macOS `36184794144` (16m), Linux `36184794342` (22m), Windows `36184794498` (41m) — all `success` on commit `bfc941d`, including `Run test suite` on each OS. The four fixes above (ensure-before-patch, `@rpath` relink, RPATH strip, isolated-layout mirror) compose to a fully green matrix with warm caches.

## 2026-09-25 — macOS: isolated-run copy used nested lib/ layout (test bug)

- **CI run**: macOS `36182628495` (failed at 18m in `Run test suite`, `9 passed, 1 failed`) — steps 1 (linked paths) and 2 (RPATHs) green; step 3 isolated `--version` died SIGABRT: `dyld: Library not loaded: @rpath/librabbit_test-opt.0.dylib`.
- **Root cause**: test-harness layout bug, not product. Staging lays out `bin/rabbit` + `lib/` as siblings with binary RPATH `@loader_path/../lib`. The darwin test copied the binary to `<iso>/rabbit` and libs to `<iso>/lib/` (nested), so `@rpath` resolved to `<iso>/../lib` — outside the copy. The staged tree and wheel were consistent all along (all 9 sim tests run the staged binary in place).
- **Fix**: darwin step 3 now mirrors the staged sibling layout (`<iso>/bin/rabbit` + `<iso>/lib/`). No product change; the relocation invariant under test is unchanged, only the harness copy is faithful.
- **Platform considerations**: test-only, darwin branch; win32/Linux branches untouched.
- **Files changed**: `test/test_simulations.py` (darwin step-3 layout only).
- **Verification**: unit suite 25 passed; `py_compile`; layout correctness by construction (`@loader_path=ISO/bin` → `../lib=ISO/lib`). Full proof is the next mac round (step 3 runs the whole staged closure relocated).
- **Remaining uncertainty**: whether further `@rpath` deps beyond the test lib surface once loading proceeds past it — step 3 will report each by name.

## 2026-09-25 — macOS: absolute Homebrew RPATHs shipped in staged tree (step 2)

- **CI run**: macOS `36180376611` (failed at 18m in `Run test suite`, `9 passed, 1 failed`) — the `@rpath` relink held (linked-path step 1 green). Step 2 failed: `Non-relocatable RPATH '/opt/homebrew/opt/hdf5-mpi/lib' in rabbit`.
- **Root cause**: the project's own `get_darwin_tool_env` injects `-Wl,-rpath,<brew-prefix>/lib` LDFLAGS, so the staged binary carries absolute Homebrew RPATHs. Absolute deps resolve without RPATH lookup and staged `@rpath` refs resolve via the canonical `@loader_path` entries, making these baked-in prefixes both redundant and hardcoded host paths in the shipped artifact. The assertion is correct; staging was incomplete.
- **Fix**: extended `relink_darwin_staged_artifacts()` — after `-id`/`-change`, it parses each staged file's LC_RPATHs (`otool -l` state machine, shared `_otool_rpaths` helper), deletes every entry not starting with `@loader_path`, and adds the canonical entry (`@loader_path/../lib` for the binary, `@loader_path` for libs) only when absent. Also removed the old `check=False` `-add_rpath` block from `stage_artifacts` (single ownership, no more duplicate-tolerance error hiding); every tool call is `check=True`.
- **Platform considerations**: darwin-only path; Linux/Windows staging untouched.
- **Files changed**: `scripts/build/darwin.py`, `scripts/build/common.py` (net deletion of the old block), `test/test_darwin.py` (extended mock test: delete of the Homebrew RPATH, canonical adds where missing, no duplicate add).
- **Verification**: 25 unit tests pass; `py_compile` + `git diff --check` clean. CI step 3 (isolated execution on the runner) is the empirical guard against over-deletion: if a staged file needed an absolute RPATH for a non-staged `@rpath` dep, dyld will fail there by name.
- **Remaining uncertainty**: whether any staged file holds an `@rpath` reference to a *non-staged* lib that relied on a now-deleted absolute RPATH — step 3 of the next mac round decides (no such ref is visible in current evidence).

## 2026-09-25 — macOS: staged binary kept absolute LC_LOAD_DYLIB (real relocatability bug)

- **CI run**: macOS `36178001268` (failed at 19m in `Run test suite`, `9 passed, 1 failed`) — the ensure-before-patch fix held (framework compiled, 40 libs staged, 45 MB wheel built, all sim tests green). The new `darwin` otool branch failed loudly as designed: `Forbidden hardcoded path '/Users/runner/.../test/lib/librabbit_test-opt.0.dylib' linked by rabbit binary`.
- **Root cause**: genuine product defect, not test overreach (verified, not assumed). The macOS linker records absolute build-tree paths in LC_ID/LC_LOAD_DYLIB, while ELF records SONAMEs resolved via RPATH — so Linux needs only `$ORIGIN` RPATHs but macOS staging must also rewrite load commands. `stage_artifacts` copied the libs and added `@loader_path` RPATHs (with `check=False`, hiding the duplicate-RPATH errors also visible in the log) but never ran `install_name_tool -change/-id`. Proven same-artifact-class on Linux: local `rabbit-opt` also links `librabbit_test-opt.so.0`, yet Linux CI is green because SONAME+RPATH resolves. The staged mac binary therefore ran only where the absolute path exists (the build machine) — the passing sim tests proved nothing about relocation.
- **Fix**: new `relink_darwin_staged_artifacts()` in `scripts/build/darwin.py`, called from the existing darwin block in `stage_artifacts`: set every staged dylib's ID to `@rpath/<basename>`, rewrite every staged reference (binary + libs) whose basename matches a staged lib to `@rpath/<basename>`. System (`/usr/lib`, `/System`) and non-staged shared deps (e.g. Homebrew MPI) untouched — same bar as Linux. All invocations `check=True` so half-relinked trees fail loudly instead of shipping dyld time-bombs. No test change needed (the assertion was correct).
- **Platform considerations**: darwin-only code path; Linux/Windows staging byte-identical (block-gated, lazy import).
- **Files changed**: `scripts/build/darwin.py` (new helper), `scripts/build/common.py` (6-line call in darwin block), `test/test_darwin.py` (1 new test with mocked otool/install_name_tool: absolute staged refs rewritten, `@rpath`/`/usr/lib`/non-staged refs untouched, `-id` set).
- **Verification**: 25 unit tests pass via repo `.venv`; `py_compile` + `git diff --check` clean. Full proof is the next mac round (steps 1–3 of the darwin relocatability test).
- **Remaining uncertainty**: whether staged libs carry additional absolute LC_RPATHs that step 2 (`@loader_path`-only assertion) will flag — deliberately left for the next round to decide empirically rather than deleting RPATHs on speculation (could break `@rpath` refs to non-staged libs).

## 2026-09-25 — macOS: Rabbit step patched before framework sources existed (ordering)

- **CI run**: macOS `36176068156` (failed at 11m in `Build Rabbit`, `tinyhttp/http.h: no member named 'transform' / no template named 'function'`) — all dep stages cache-hit and skipped. Same lean-header symptom as the earlier tinyhttp round, but the patch existed this time.
- **Root cause**: ordering bug, proven from the runner log. `build_rabbit.py::main()` called `apply_macos_patches()` *before* `build_rabbit_binary()` → `ensure_moose_repo()`. On cache-hit runs the framework tree is absent at patch time (no cache provides `moose/framework`), so every `work_dir.is_dir()` guard silently `continue`d; then `ensure_moose_repo` temp-cloned pristine MOOSE and overlaid the framework (`Initialized empty Git repository in .moose_framework_tmp`, `HEAD is now at 975c9a1c`), guaranteeing unpatched sources at compile time. Full-rebuild runs survived only because stage functions ensure-then-patch in the right order. The silent skip violated fail-early/informative behavior.
- **Fix**: new `prepare_darwin_rabbit_sources()` in `scripts/build/darwin.py` (ensure-then-patch in one named place; the later ensure inside `build_rabbit_binary` becomes a no-op), called from `build_rabbit.py::main()` behind the existing `darwin` gate. Plus `apply_macos_patches` now prints an explicit `WARNING: skipping <patch>: source dir ... not present` when a patch file exists but its tree is absent (stays a skip — dep stages legitimately run with only some trees materialized — but no longer silent).
- **Platform considerations**: macOS-only files (`scripts/build/darwin.py`, darwin-gated call in `build_rabbit.py`); Linux/Windows flows byte-identical (`ensure_moose_repo` itself is untouched cross-platform code).
- **Files changed**: `scripts/build/darwin.py`, `build_rabbit.py`, `test/test_darwin.py` (2 new tests).
- **Verification**: `test_patch_skip_warns_when_source_absent` (absent trees warn loudly, no raise); `test_prepare_ensures_sources_before_patching` (mocked ensure materializes a pristine `http.h`, helper patches it — proves materialize-before-patch ordering); full unit file → 24 passed via repo `.venv`.
- **Remaining uncertainty**: none on mechanism. Whether further lean-header TUs hide behind tinyhttp in the framework unity build is the same known loop — next CI round tells.

## 2026-09-25 — macOS: relocatability test shelled to Linux-only `readelf`

- **CI run**: macOS `36169255744` (failed at 12m in `Run test suite`, `9 passed, 1 failed`) — the actual product is green on mac: `rabbit-opt` linked, 40 libs staged, wheel built (45 MB), and all 9 sim tests passed.
- **Root cause**: `test_binary_and_library_relocatability` branched `win32` vs *everything else*, so macOS ran the Linux ELF path and died on `FileNotFoundError: 'readelf'`. Test bug, not product bug.
- **Fix**: new `darwin` branch using native `otool -L` (no hardcoded user/build dirs in linked paths) and `otool -l` (all RPATHs `@loader_path`-relative) plus relocated execution (copy binary + dylibs to an isolated dir with build env stripped, `--version` + real HEX8 solve + Exodus output) — the same three invariants as the Linux/Windows branches, expressed with platform tools. Deliberately no must-be-bundled assertion (can't distinguish legitimate shared MPI from leaks; isolated execution is the behavioral proof — same bar as the other branches).
- **Files changed**: `test/test_simulations.py` (darwin branch only; win32/Linux paths byte-identical).
- **Verification**: parser logic executed against realistic canned `otool` output (linked-lib tokenization incl. `@rpath`, LC_RPATH state machine incl. bad-path capture); `py_compile` + unit suite → 22 passed. Full proof is the mac PR round (test executes on the runner).
- **Remaining uncertainty**: none on mechanism. (Also noted but out of scope: `install_name_tool` printed errors on two staged dylibs during packaging with `check=False` — staging completed anyway; the new RPATH assertions will confirm or deny final state.)

## 2026-09-25 — macOS: `conf_vars.mk` never cached alongside `MooseConfig.h`

- **CI run**: macOS `36171696370` (failed at 10m in `Build Rabbit`, `PNGOutput.h: fatal error: 'png.h'`) — warm caches, fresh `Configure MOOSE` skipped.
- **Root cause**: only `MooseConfig.h` (the PNG on/off decision) is cached, never the generated `conf_vars.mk` that carries the matching `-I` flags (`libPNG_INCLUDE`). On cache-hit runs `-include` silently tolerates its absence, so even a correct `HAVE_LIBPNG=1` compiles with no png `-I`. Linux survives only because Ubuntu images ship `png.h` in default `/usr/include`. Proven: local `conf_vars.mk` exists purely as configure output; no workflow or script references it; the failing run restored the header and skipped configure.
- **Fix**: (1) cache `moose/conf_vars.mk` with `MooseConfig.h` (restore+save) so decision and flags travel together; (2) new `check_cached_moose_config()` runs on every `configure_moose` — if the cached header claims PNG but the flags file is missing or points nowhere with `png.h`, both are deleted so configure re-runs fresh (self-healing against already-poisoned saves; prefix-fallback restores can't re-poison). PNG-disabled configs pass through untouched.
- **Files changed**: `.github/workflows/macos_build_and_test.yml`, `scripts/build/darwin.py`, `test/test_darwin.py`.
- **Verification**: 4 new unit tests (consistent/disabled/missing-vars/broken-flags); `pytest` → 22 passed.
- **Remaining uncertainty**: none on mechanism. (Near-miss caught during edit: briefly wrote a `linux-` cache key into the macOS file — fixed before push; asymmetric key prefixes across OSes deserve a future lint.)

## 2026-09-25 — macOS: libpng metadata without headers breaks MOOSE configure contract

- **CI run**: macOS `36165248598` (failed at 10m in `Build Rabbit`; warm caches skipped all dep builds — libMesh+WASP+config previously proven green).
- **Root cause**: MOOSE `configure.ac` defines `HAVE_LIBPNG` whenever `pkg-config --exists libpng` succeeds, recording only the `-I` flags it is given. On `macos-15` runners that check succeeds but the flags point nowhere with `png.h` (headers absent), so the guarded `#include <png.h>` in `PNGOutput.h` fails deep in the framework compile. Proven fresh (not stale cache): this run's `Configure MOOSE` re-ran after a cache miss.
- **Fix, two parts**: (1) `brew install libpng` in the macOS workflow so detection finds real headers (keeps PNG feature parity with Linux instead of disabling it); (2) `check_libpng_consistency()` in `darwin.py::configure_moose` which raises with the exact cause when `-I` dirs lack `png.h`, warns when undecidable, and passes through when consistent. Part (2) matters structurally: it touches `darwin.py`, which is in every mac dep-cache key, so the stale `MooseConfig.h` (old `HAVE_LIBPNG=1`) is invalidated — a workflow-only change would have been silently ignored via cache hit. Also added the missing `moose_deps.txt` to all mac dep/wheel keys (consistency gap vs Linux/Windows).
- **Files changed**: `.github/workflows/macos_build_and_test.yml`, `scripts/build/darwin.py`, `test/test_darwin.py`.
- **Verification**: 4 new unit tests (absent/disabled, present+headers, present-without-headers raises) with mocked pkg-config; `pytest` → 18 passed; YAML parses.
- **Remaining uncertainty**: which formula currently provides the broken `.pc` (irrelevant post-fix — consistent installs pass, anything else fails loudly).

## 2026-09-25 — macOS: tinyhttp missing `#include <algorithm>`/`<functional>`

- **CI run**: macOS `36165248598` (failed at 10m in `Build Rabbit` — fast because warm caches skipped all dep builds; notably libMesh+WASP+config all green on mac for the first time).
- **Error**: `tinyhttp/http.h:186/200/384: no member named 'transform' / no template named 'function'` — header uses `std::transform`/`std::function` but includes neither. Same lean-libc++ class.
- **Fix**: `patches/macos/tinyhttp.patch` (generated via `diff -u` after learning hand-written hunks risk malformation), wired into `apply_macos_patches()`; that helper is now also invoked from `build_rabbit.py::main()` behind `sys.platform == "darwin"` so framework-level headers are patched before the Rabbit compile on every macOS flow (stages run separately in CI).
- **Files changed**: `patches/macos/tinyhttp.patch` (new), `scripts/build/darwin.py`, `build_rabbit.py` (darwin-gated call), `test/test_darwin.py`.
- **Verification**: dry-run + scratch-copy apply + idempotence; `pytest` → 15 passed.
- **Remaining uncertainty**: further lean-header TUs may surface in later rounds (same loop).

## 2026-09-25 — macOS: WASP `Format.h` missing `#include <type_traits>`

- **CI run**: macOS `36153829049` (failed at 1h7m in `Build WASP and HIT`, TU `waspexpr/ExprContext.cpp`) — libMesh incl. both prior patches built clean; failure moved into WASP.
- **Error**: `waspcore/Format.h:216: error: no member named 'is_fundamental' in namespace 'std'` — the header uses `std::is_fundamental<T>::value` but includes only `<cmath> <string> <cstring> <sstream> <iostream> <iomanip> <stdio.h>`. Same lean-libc++ class.
- **Fix**: `patches/macos/wasp.patch` (+ comment + `#include <type_traits>`, generated via `diff -u` after a hand-written hunk proved malformed), wired into the existing `apply_macos_patches()` table; that helper is now also called from `build_wasp` (WASP builds after libMesh, and CI invokes the stages separately).
- **Files changed**: `patches/macos/wasp.patch` (new), `scripts/build/darwin.py`, `test/test_darwin.py` (apply + idempotence test).
- **Verification**: dry-run + scratch-copy apply against pinned sources; `pytest` → 14 passed.
- **Remaining uncertainty**: further lean-header TUs may surface in later rounds (same loop).

## 2026-09-25 — macOS: libMesh `dof_object.h` missing `#include <iterator>`

- **CI run**: macOS `36148836952` (failed at 40m in `Build libMesh`, TU `dof_map.C`) — the poly2tri fix held (contrib built clean; failure moved into libMesh proper).
- **Error**: `include/libmesh/dof_object.h:511: error: no template named 'back_insert_iterator' in namespace 'std'` — the header uses `std::back_insert_iterator` but includes only `<cstddef> <cstring> <vector> <memory>`. Same lean-libc++ class as poly2tri.
- **Deliberately not patched blindly**: a regex sweep over libMesh+contrib flagged ~200 headers, but most are false positives (umbrella includes, and TIMPI compiled clean despite being flagged). Patching on suspicion risks unmaintainable churn; each CI-proven (file, symbol, header) triple gets exactly one include. Pre-emptive sweeping rejected in favor of precise per-round fixes.
- **Fix**: `patches/macos/libmesh.patch` (+ comment + `#include <iterator>`), wired into the existing `apply_macos_patches()` table (same idempotence contract).
- **Verification**: dry-run + scratch-copy apply against pinned sources; `pytest` → 13 passed.
- **Remaining uncertainty**: further lean-header TUs may surface in later rounds (same loop).

## 2026-09-25 — macOS: poly2tri missing `#include <ostream>` (follow-up in libMesh)

- **CI run**: macOS `36137283766` (failed at 1h38m in `Build libMesh`) — notably, the `--disable-netgen` fix worked (no Netgen errors anywhere; the build progressed over an hour past the old failure point).
- **New error, single TU**: `contrib/poly2tri/.../common/shapes.h:122: error: no type named 'ostream' in namespace 'std'` — the header declares `std::ostream& operator<<` but includes only `<cmath> <cstddef> <stdexcept> <vector>`. Older libc++ provided `ostream` transitively; LLVM 23 does not. Grep-verified this is the only header in all of poly2tri using iostream facilities, so one include fixes the whole package (no whack-a-mole). MOOSE framework itself includes poly2tri (`BoundaryLayerUtils`, `MeshTriangulationUtils`, ...), so the patch applies unconditionally in `build_libmesh`, not only when rebuilding.
- **Fix**: new `patches/macos/poly2tri.patch` (+4-line comment + `#include <ostream>`), applied idempotently via new `apply_macos_patches()` in `scripts/build/darwin.py` (exit 0 applied / 1 already-applied tolerated, >1 raises with output — same contract as the Windows patch steps, without their old `|| true` masking).
- **Files changed**: `patches/macos/poly2tri.patch` (new), `scripts/build/darwin.py`, `test/test_darwin.py` (real apply-to-scratch-copy + idempotence test).
- **Verification**: `patch -p1 --dry-run` + real apply on a scratch copy of the pinned `shapes.h` (local tree untouched); `pytest` → 12 passed.
- **Remaining uncertainty**: whether further macOS-only contrib TUs hide behind this one (same loop as before — next CI round tells).

## 2026-09-25 — Release: shared caches with build-and-test + 360 min timeouts

- **Why the v2026.9.3 release rebuilt everything**: `release.yml` used its own cache namespace (`linux/windows-moose-build-*`, own wheel keys) that no prior run had ever populated — first tag = guaranteed cold full rebuild on both runners (~1h+), not a hang.
- **Fix**: release jobs now restore the *exact* per-stage caches (same keys, paths, ids, restore-keys) as the build-and-test workflows and save nothing — build-and-test runs own population, releases consume. A release on a previously built tree restores everything and only runs tests + packaging; a cold release builds exactly as before. Applies to Linux (4 stages) and Windows (4 stages); wheel keys aligned too.
- **Timeouts**: all jobs in all four workflow files set to 360 min (GitHub-hosted max), including release publish.
- **Files changed**: `.github/workflows/{release,linux_build_and_test,windows_build_and_test,macos_build_and_test}.yml` (timeouts); `release.yml` (cache alignment, dropped release-side saves).
- **Verification**: YAML parses; no dangling step-id references; all `if:` conditions resolve to existing step ids. Live proof requires the next tag/dispatch run.

## 2026-09-25 — macOS: disable NetGen in libMesh build (SDK macro vs new libc++)

- **CI runs**: macOS `36111456669` (33m), `36110525881` (44m), `36130962168` (32m) — all fail identically in the libMesh dependency stage (`update_and_rebuild_libmesh.sh --with-mpi`).
- **Root cause**: libMesh's bundled NetGen `nglib` TU `gzstream.cpp` dies parsing Homebrew LLVM 23.1.0's libc++ `<complex>` (`expected unqualified-id` at `std::isnan`/`std::isinf` uses): the Xcode 16.4 SDK `math.h` defines `isnan`/`isinf`/`signbit` as function-like macros, which macro-expand the `std::`-qualified names during `<complex>` parsing. Only one TU fails today, but the poison (macro active before `<complex>`) is systemic to the NetGen build under this toolchain/SDK pairing. Verified the chain `gzstream.cpp` → `myadt.hpp` → `mydefs.hpp` → `ngcore.hpp` → `archive.hpp` → `<complex>`, and that NetGen pulls only `<cmath>` itself (no raw `<math.h>` to reorder).
- **Why disable instead of patch/pin**: `--disable-netgen` is a documented libMesh configure option that flows untouched through MOOSE's `update_and_rebuild_libmesh.sh` (`"$@"` forwarding, verified in-script; neither MOOSE script mentions netgen). It removes the entire failure class rather than chasing SDK-macro whims TU-by-TU (patch) and avoids pinning a floating-then-deleted Homebrew LLVM formula (brittle in the other direction). MOOSE degrades gracefully: `Capabilities` reports netgen missing, `XYZDelaunayGenerator` errors only if used — and no Rabbit sim/test/example touches NetGen or Delaunay (grep-verified; Gmsh/generated/Exodus cover all packaged meshes).
- **Platform considerations**: macOS-only file (`scripts/build/darwin.py`); Linux/Windows behavior byte-identical (no shared code touched).
- **Files changed**: `scripts/build/darwin.py` (one flag + rationale comment), `test/test_darwin.py` (new: asserts `--disable-netgen` plumbed through, asserts built-install short-circuit).
- **Verification**: flag proven real via `configure --help` on the exact pinned libmesh SHA (`90766057`, same on CI); `pytest test/test_darwin.py test/test_moose_pins.py test/test_staging.py` → 11 passed (mocked subprocess, no network/build); macOS CI on the new PR is the compile-level verifier.
- **Remaining uncertainty**: none on mechanism; whether any *transitive* MOOSE consumer needs NetGen at macOS runtime will surface in the macOS test suite (expected clean — same suite as green Linux/Windows).

## 2026-09-25 — FIX-OWN-REGRESSION: verifier raised on dangling gitlinks

- **What happened**: the `verify_moose_deps` shipped in the re-pin commit raised `RuntimeError: Cannot determine checked-out commit` whenever `git rev-parse` failed — including the *expected* cache-hit case, where `actions/cache` restores submodule content without its git dir (dangling `.git` gitlink). This red-blocked every Linux run on the re-pin commit within ~1 min (e.g. `36117932030`), and would have done the same on Windows via the ps1 hook.
- **Why the initial design was wrong**: I conflated "cannot verify" with "drifted". Cache-restored trees are a legitimate, by-design state; only a *successful* rev-parse that disagrees with the lock is drift.
- **Fix**: the rev-parse-failure branch now prints a `WARNING ... skipping pin check` and continues; mismatch still raises. Absent checkouts still skip. Added `test_verify_warns_on_unverifiable_checkout` (dangling gitlink fixture) — 9 tests pass.
- **Lesson applied**: the pre-existing green Linux run (`36115045320`, 26 min, includes the libomp fix) confirms the staging fix independently of this episode.

## 2026-09-25 — Windows: submodule init gated on libs, leaving hollow source trees

- **Root cause, fully evidenced**: `moose/` is gitignored, not a submodule, so `actions/checkout` materializes no MOOSE content; everything comes from repo code + caches. In cache-hit runs the dependency caches restore *built libs only* (`arch-windows-opt/`, `installed/`) while `moose/petsc|libmesh|.../wasp` source trees stay hollow — proven by preflight forensics (`git rev-parse` in `moose/petsc` walks up to the MOOSE SHA; `include/` absent) and by §5.6 logs (`can't find file to patch`, `Skipping ... source not present yet`, tolerated as `[OK]`). But ps1 §5.5 only initialized submodules when *libs* were missing *and* the matching stage ran, so `-Stage rabbit` never backfilled sources and the framework compile died on the missing `petscsys.h`. Full-rebuild runs passed because missing libs + missing sentinels triggered the init path.
- **Fix (Windows-only, mirrors Linux `ensure_moose_submodules` which already gates on source sentinels)**: submodule init now fires on missing *sentinel source files* (`petsc/configure`, `libmesh/configure`, `wasp/CMakeLists.txt`) regardless of Stage; afterwards a hard verification throws with the exact missing paths instead of limping on. Complete trees behave exactly as before (all sentinels present → no-op).
- **Follow-up finding from the first init-enabled round**: `git submodule update` then refused with `fatal: destination path '.../moose/petsc' already exists and is not an empty directory` — the cache restore creates `moose/petsc/` containing only `arch-windows-opt/`. The next round proved the same for WASP (`install/`+`build/` restored into hollow `wasp/`). Fix, deliberately generic this time (no per-sub special cases): any hollow submodule dir is moved *whole* to a `.__rabbit_backup` sibling so the clone can proceed, then preserved outputs are merged back child-by-child (fresh clone wins collisions with a warning); a pre-existing backup throws an explicit remove-or-move-back message instead of silently proceeding. State machine validated locally across hollow/complete/stale-backup/collision scenarios.
- **Files changed**: `scripts/install_dependencies_windows.ps1` (§5.5 only).
- **Verification**: static trace-through of hollow vs complete vs fresh trees (no pwsh available locally to execute); next cache-hit Windows round is the live test — expect `Initializing MOOSE submodules: petsc libmesh framework/contrib/wasp` followed by real patch application (`patching file ...`) instead of `can't find file` skips.
- **Remaining uncertainty**: why `actions/checkout`'s own `submodule update --init --force --recursive` completes in <1s without materializing anything (no `moose` entry in rabbit-fem — nothing to init — so this is expected behavior, not a GitHub bug; the repo-owned ensure path above is the correct fix location).

## 2026-09-25 — Re-pin MOOSE to master tip + explicit dep lock file

- **Request**: stop tracking the MOOSE default (`next`) line; target `master` at a fixed commit, plus pin all build deps explicitly so a future upstream merge cannot silently move us.
- **Findings** (verified, not assumed):
  - Old pin `73c6aa53` is 6652 commits behind `master` (`gh api .../compare/master...73c6aa53` → `behind`, `ahead: 0`), i.e. stale either way; moving to current master tip.
  - Master tip `975c9a1ca693c21bef850b7beba724e0fb703591` (2026-09-24, from `git ls-remote` + `git clone --branch master` to `/tmp`, local build untouched).
  - Dep SHAs recorded at master tip are **identical** to our current ones (`petsc 4146d835`, `libmesh 90766057`, `wasp ce25dcde` — same on both sides), so this re-pin is zero-churn for PETSc/libMesh/WASP: submodule patches need no changes.
  - `patches/windows/moose.patch` dry-run (`patch -p1 --dry-run`) against the pristine master tree: every file hunk applies exactly (no fuzz/offset); only the two gitlink hunks defer (`not a regular file`, expected without initialized submodules — same as current behavior).
- **Changes**:
  - `moose_version.txt` → `975c9a1c...`; same-SHA fallbacks updated in `scripts/build/common.py` and `scripts/install_dependencies_windows.ps1`.
  - New `moose_deps.txt` lock file (petsc/libmesh/wasp SHAs + provenance header).
  - New `get_pinned_moose_deps()` + `verify_moose_deps()` in `common.py` (strict on drifted *materialized* submodules, skips absent checkouts whose materialization belongs to ensure steps), wired into `build_rabbit.py::main()` (all Linux/macOS flows, single choke point, no signature ripples) and into `install_dependencies_windows.ps1` §5.5 (with explicit `$LASTEXITCODE` guard, since `$ErrorActionPreference` alone doesn't stop on native-command failure). Absent checkouts never false-fail.
  - `moose_deps.txt` added to all dependency + wheel cache keys in both workflows so pin moves invalidate caches (the moose-version bump alone already busts them this round → full rebuilds everywhere, validating the new tree end-to-end).
- **Verification**: `pytest test/test_moose_pins.py test/test_staging.py` → 8 passed; `verify_moose_deps` run against the real local submodules → OK; YAML parses; `git diff --check` clean.
- **Remaining uncertainty**: none on the pin itself. The pending hollow-submodule-ensure work (content-based init for cache-hit Windows runs) now targets these pins and follows next.

## 2026-09-25 — macOS: TRIAGED/QUEUED, Netgen vs Homebrew LLVM 23 libc++ (not fixed)

- **CI runs**: macOS `36111456669` (33m), `36110525881` (44m) — both fail in the libMesh dependency stage (`update_and_rebuild_libmesh.sh --with-mpi`), not in Rabbit code.
- **Error**: Netgen `nglib` `gzstream.cpp` → `myadt.hpp` → … → Homebrew LLVM 23.1.0 `c++/v1/complex:1035` → `error: expected unqualified-id` at `std::isnan(__rho)`: the macOS SDK `math.h` defines `isnan` as a function-like macro, which breaks libc++ `<complex>`.
- **Why not fixed now**: third-party (Netgen bundled in libMesh) vs toolchain/SDK incompatibility — a separate workstream from the Linux/Windows packaging failures in scope, with rabbit-hole risk (SDK pin vs Netgen patch vs disabling Netgen). Queued behind Linux/Windows green.

## 2026-09-25 — Linux: `stage_artifacts` aborts on `libomp.so.5` (dead fallback + SONAME mismatch)

- **CI runs**: Linux `36106596972`, `36110525796`, `36111456621` — identical `FileNotFoundError: Cannot create a standalone wheel; required shared libraries were not found: libomp.so.5` after a successful ~20 min `rabbit-opt` compile, in `scripts/build/common.py::stage_artifacts`.
- **First failure addressed here**: all three are the same signature; root cause verified on both sides (see below).

### Root cause

- `stage_artifacts` resolves `DT_NEEDED` entries only from `repo_dir`/`moose_dir` trees plus the binary's RPATH dirs, then raises on anything unresolved. The OpenMP runtime is a documented system dependency (`libomp-dev` installed in CI) living at `/usr/lib/x86_64-linux-gnu/`, i.e. outside all three search roots.
- The existing `omp_candidates` fallback could never fire: it sits *after* the `raise`, and it looks for `libomp.so` while the CI binary needs the versioned SONAME `libomp.so.5` (linked via default `-lomp` search, since CI runners have no `/opt/rocm-*` or `/usr/lib/llvm-*/lib/libomp.so` for the toolchain link flag).
- Why local passes: verified with `readelf` on local `rabbit-opt` — local links `/opt/rocm-7.2.4`'s `libomp.so` directly (`omp_link_flag`), so NEEDED is the unversioned `libomp.so`, which resolves via the binary's own RUNPATH (`...:/opt/rocm-7.2.4/lib/llvm/lib:...`). CI and local produce different SONAMEs for the same dependency — environment-specific behavior the staging logic did not account for.

### Why this fix addresses the root cause

- New `index_system_openmp_libs()` in `scripts/build/common.py` indexes canonical system locations (`/usr/lib/x86_64-linux-gnu/libomp.so*`, `/usr/lib/llvm-*/lib/libomp.so*`, `/opt/rocm-*/...`) keyed by exact filename, called *before* resolution. The binary's real SONAME (`libomp.so.5` on CI, `libomp.so` locally) now resolves instead of aborting. Repository/RPATH entries take precedence and are never overridden.
- Deleted the dead post-raise `omp_candidates` block (unreachable on failure; pointless duplicate-add on success).
- No hardcoded runner paths beyond standard FHS locations already used in this file; `darwin` behavior unchanged (helper no-ops, same gate as before).

### Platform-specific considerations

- Linux-only effect (`sys.platform == "darwin"` early-return; Windows doesn't use this function — its wheel bundles `rabbit.exe` with no `.so` staging). No cross-OS behavior change.

### Files changed

- `scripts/build/common.py` (helper + call site + dead-block removal).
- `test/test_staging.py` (new: exact-SONAME indexing, repo precedence, missing-dir tolerance).

### How to verify

- ` .venv/bin/python -m pytest test/test_staging.py` → 3 passed (run; uses repo venv like CI).
- Re-ran the exact new resolution path against local `rabbit-opt`: 53 resolved, 0 unresolved, `libomp.so` still via rocm RUNPATH — no regression.
- CI: next Linux run should proceed past `stage_artifacts` to wheel packaging + tests.

### Remaining uncertainty

- None on the mechanism (three identical CI occurrences + local `readelf` divergence proof). Whether the staged `libomp.so.5` + rewritten `$ORIGIN` RPATH loads correctly at runtime on a bare runner is covered by the existing relocatability test suite (`test_simulations.py`) in the same CI job.

## 2026-09-25 — Windows: Rabbit-stage read-only preflight for dependency flags (diagnosing `petscsys.h`)

- **CI run prompting this**: Windows `36111456611` (failure, 10m27s) — framework unity compile fails with `fatal error: 'petscsys.h' file not found` despite all dependency stages cache-restored and both prior fixes verifiably active in the same log.
- **Why the three failures look identical**: the ps1 failure handler appends the (stale, cache-restored, dated 05:06:12) PETSc `configure.log` tail to every failure log, and the PR comment posts only tail-100. The real error is always above the `--- PETSC CONFIGURE.LOG TAIL ---` marker. Runs `36109996543`/`36110525729` = HIT link (`std::__1`, MinGW vs libc++); `36111456611` = `petscsys.h`.
- **What static analysis established** (no fix pushed on this basis):
  - `petscsys.h` is a checkout-provided source header (`moose/petsc/include/`), so the file exists in every workspace — purely an include-flag resolution failure.
  - Converter `posix_to_win` executed locally on the exact baked flag forms (`-I/d/a/...`, `-include`, `-L`, `-Wl,-rpath,`, already-Windows inputs) — all convert correctly and idempotently; wrapper pass-through drops nothing.
  - `libmesh-config` emits fully baked absolute paths (verified against local `installed/bin/libmesh-config` structure); cache sizes stable across saves (no partial saves).
  - Not yet verifiable from logs alone whether the restored `installed/bin/libmesh-config --include` output lacks PETSc entries (stale libmesh configured without PETSc is the prime suspect, matching the historical `--with-petsc` vs `PETSC_DIR/PETSC_ARCH` incident in `dev/log_windows_fixes_local.md`).
- **Change (diagnostic + permanent fail-early guard, Windows-only)**: read-only preflight in `scripts/install_dependencies_windows.ps1` §10 before `make` — prints `libmesh-config --cxx/--cppflags/--include`, asserts `--include` mentions `petsc` via a `case` match (no `grep -q` under `pipefail`, avoiding a SIGPIPE false-failure race), prints `git rev-parse HEAD` + `petsc/include` entry count + `petscsys.h` present/MISSING, then hard-`ls`es both headers. Verified locally by emulating the PowerShell→bash expansion and running happy / missing-header / no-PETSc-flags scenarios (exits 0/2/1 with the intended messages; `bash -n` clean; no stray backticks).
- **What the first preflight round proved** (Windows `36115045299`): flags are perfect (`--include` HAS both PETSc `-I` entries) — the stale-libmesh theory is dead. Instead `moose/petsc/include/petscsys.h` itself is absent from the workspace while `arch-windows-opt/include/petscconf.h` (cache-restored) exists, even though the same run's `-Stage petsc` applied the patch inside `moose/petsc` and skipped the build on the restored `libpetsc.a`. So a cache-hit workspace can have a deficient PETSc source tree that nothing validates — the extended source-tree forensics (entry count, presence flag, submodule HEAD) in the current preflight form target exactly this; next round will characterize it.
- **How to verify**: next Windows run's `Verifying dependency include flags for Rabbit` step shows the exact flags; if the stale-libmesh theory holds it fails there with the PETSc message instead of deep in unity compilation.

## 2026-09-25 — Windows: Rabbit-stage HIT rebuild links MinGW g++ against Zig libc++ WASP libs

- **CI run**: Windows `36109996543` (failure, 8m33s) on commit `806b786` — full rebuild (all dependency stages ran and passed, including new `Ensuring * Windows patch` + `Verifying MOOSE Windows patch` steps and `Skipping pycapabilities on Windows...`).
- **Step**: `Windows: Build Rabbit application` → `make[1]: *** [Makefile:61: hit] Error 1`, then `make: *** [moose.mk:227: .../hit/hit.pyd] Error 2`.

### Root cause

- The Windows `hit` stub in `patches/windows/moose.patch` ran `cd $(HIT_DIR) && $(MAKE)` with no `CXX` override (unlike the WASP stage, which builds HIT with `CXX=zig-cxx`). The recursive make therefore linked with a MinGW `g++` from the runner `PATH` (`C:/mingw64/.../ld.exe` via `collect2.exe`), whose GNU `libstdc++` cannot link the Zig-built `libwasphit.a` (libc++ `std::__1` symbols: `ios_base::clear/init`, `cin`/`cout`/`cerr`, iostream vtables) → `undefined reference to 'std::__1::...'`.
- Symptom vs cause: looks like a WASP/HIT incompatibility with Windows, but WASP itself built fine — the failure is a toolchain mismatch in a redundant second HIT build. The WASP stage already produces a correct Zig `hit`/`hit.exe`; the Rabbit-stage rebuild adds nothing (and `hit.pyd`, like `_pycapabilities`, is a test-harness Python extension never linked into `rabbit-opt.exe`).

### Why this fix addresses the root cause

- Changed the Windows `hit` rule in `patches/windows/moose.patch` to skip the recursive `$(MAKE)`: it verifies the WASP-stage `hit.exe`/`hit` exists (failing early with `ERROR: HIT executable missing; run the WASP stage first` instead of silently proceeding) and touches `$(pyhit_LIB)`, mirroring the `pycapabilities` stub rationale. This removes the mixed-toolchain link rather than papering over it (e.g. no forced `-lstdc++`/`-lc++` juggling, no runner-specific compiler path).
- Verified without touching the local in-progress build: extracted pristine `framework/moose.mk` at the pinned commit (`73c6aa53`) to `/tmp`, extracted the `framework/moose.mk` hunks, `patch -p1 --dry-run` → exit 0 (edited hunk applies cleanly), full apply → Windows branch contains the skip rule and the `else` upstream branch is byte-identical.

### Platform-specific considerations

- Windows-only: change lives inside the existing `ifeq ($(findstring NT,...))` block of `patches/windows/moose.patch`; Linux/macOS `moose.mk` path untouched (local `moose/` is unpatched and mid-build — left alone).
- Kept LF line endings + tabs consistent with neighbouring `+` lines (`git diff --check` clean); bumped the hunk header count 19→20 for the added line.
- `test -x` works on MSYS POSIX paths used by the make recipes; both `hit.exe` (Windows) and `hit` (MSYS-stage copy) names accepted.

### Files changed

- `patches/windows/moose.patch` (Windows `hit` rule: skip rebuild, verify `hit.exe`/`hit`, touch `hit.pyd`).
- `dev/log_windows_patches.md` (documented HIT skip + MinGW/Zig libc++ rationale).

### How to verify

- Next `Windows: Build Wheel and Test` full or cache-hit run: Rabbit stage should print `Skipping HIT rebuild on Windows (using WASP-stage hit.exe)...` and proceed to compile/link `rabbit-opt.exe`. If the WASP stage regresses, the build fails early with `ERROR: HIT executable missing`.
- Scratch check (repeatable): extract `git -C moose show HEAD:framework/moose.mk`, extract `framework/moose.mk` hunks from the patch, `patch -p1 --dry-run` → 0.

### Remaining uncertainty

- Whether anything in the Rabbit link actually consumes `hit.pyd` at build time (evidence says no: prior local Windows build linked `rabbit-opt.exe` with only a touched `hit.pyd`; will confirm when a green Windows run links).
- The `framework/contrib/wasp` gitlink `-dirty` hunk in `moose.patch` can report `Hunk #1 FAILED` on re-application; tolerated (exit 1) by the §5.6 ensure step and unrelated to this fix.

## 2026-09-25 — All OS: broken `pyproject.toml` version string (fast fail)

- **CI runs**: Linux `36109996335` (failure, 1m11s), macOS `36109996320` (failure, 1m35s), and prior round `36109533928/36109533935` fast failures, all on commit `806b786` (which inherited the breakage from `0d65386`).
- **Step**: `Linux/macOS: Build Rabbit, stage artifacts, and build wheel` → `uv run python build_rabbit.py --wheel` exits 2 before any compilation.

### Root cause

- `pyproject.toml:17` read `version = "2026.9.3` (missing closing quote) — invalid TOML. `uv` fails during settings discovery: `TOML parse error at line 17, column 20 ... invalid basic string, expected '"'`.
- Symptom vs cause: all three OS fail in ~1min at the same `uv run` step, which looks like infra flakiness but is a deterministic repo syntax error.
- Why local passed: local work uses `make`/direct `.venv` python or `uv run --no-project`, bypassing project discovery; CI always uses `uv run` which parses `pyproject.toml`.

### Why this fix addresses the root cause

- One-character fix: `version = "2026.9.3"` restores valid TOML. No behaviour change, no platform branching — the same file is parsed on every OS.
- Verified with stdlib `tomllib.load` (no new dependency): parses OK, `project.version == 2026.9.3`.

### Platform-specific considerations

- None — OS-independent. Fix cures Linux, Windows (`uv run python build_rabbit.py --wheel-only` parses too), and macOS identically.

### Files changed

- `pyproject.toml` (line 17: closing quote).

### How to verify

- `python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` → OK.
- Next CI round: `uv run` steps proceed past settings discovery to actual builds on all OS.

### Remaining uncertainty

- None on this item. Known next item after unblocking: Linux `stage_artifacts` `libomp.so.5` unresolved (seen on `36106596972` before the TOML breakage masked it) — to be handled on the next watch tick.

## 2026-09-25 — Windows: patches skipped on cache-hit `-Stage rabbit` + MSYS `jinja2` missing

- **CI runs**: Windows `36106596976` (failure, 4m35s), Linux `36106596972` (failure, 16m53s) on commit `af40a1e`, plus in-progress round `36109534xxx`.
- **First failure addressed here**: Windows `36106596976`, step `Windows: Build Rabbit application`.

### Root cause (Windows)

1. `windows_build_and_test.yml` restores `PETSc`/`libMesh`/`WASP`/`MooseConfig` caches and then runs only `install_dependencies_windows.ps1 -Stage rabbit`. Source patches (`patches/windows/*.patch`, incl. `moose.patch` with the `pycapabilities` stub) were applied exclusively inside the `petsc`/`libmesh`/`wasp`/`moose` stage blocks, so a cache-hit run never patches the fresh `actions/checkout` tree. Unpatched `framework/moose.mk` then builds `moose/python/pycapabilities/_pycapabilities.so` with MSYS `/usr/include/python3.12/Python.h`, which includes POSIX-only `sys/select.h` unavailable to Zig targeting `x86_64-windows-gnu` → `fatal error: 'sys/select.h' file not found` (log `last_step.log`, job `107980431274`).
2. Same run shows `ModuleNotFoundError: No module named 'jinja2'` from `moose/scripts/versioner.py` via MSYS `/usr/bin/python3`. The script installed `packaging pyyaml` into MSYS python only when MSYS tools were missing (`if ($needsInstall)`), and never installed `jinja2`. `.venv` had `jinja2`, but `make` invokes MSYS python, not `.venv`.

Why local passed: persistent workspace ran `-Stage all` once, patches persisted, and MSYS python had been hand-provisioned earlier. CI is ephemeral + cache-restored libs without patched sources — a symptom, not a second bug.

### Why this fix addresses the root cause

- New §5.6 in `scripts/install_dependencies_windows.ps1` applies all five Windows patches **unconditionally on every invocation** (before any stage build), guarded only by `[ -f patch ] && [ -d source ]` derived from `$RepoRoot`/`$RepoRootPosix` — no hardcoded drives/users. Any Stage (`petsc`, `rabbit`, `all`) therefore sees patched sources even when caches skip earlier stages.
- Patch tolerance without error hiding: `set +e; patch -p1 -N ...; code=$?; set -e; if [ $code -gt 1 ]; then exit $code; fi`. Exit 0 (applied) and 1 (hunks already applied/skipped) succeed; exit ≥2 (real failure) aborts via existing `Invoke-MsysBash` failure path. Replaces `|| true` hiding for these steps.
- Fail-early sentinel: after patching, `grep -q 'Skipping pycapabilities on Windows' moose/framework/moose.mk`, else abort with explicit message. Tests the invariant the Rabbit link actually depends on.
- MSYS modules ensured every run: `python3 -m pip install packaging pyyaml jinja2` moved outside `if ($needsInstall)`, since a cached MSYS2 image provides tools but not pip modules, and MOOSE scripts require all three under `/usr/bin/python3`.

### Platform-specific considerations

- Windows-only file (`install_dependencies_windows.ps1`); Linux/macOS (`scripts/build/*.py`, workflows) untouched.
- No new absolute paths/drive letters: reuses `$RepoRoot`, `$RepoRootPosix`, `$MsysRoot` detection.
- `set +e/set -e` toggling required because `run_step.sh` uses `set -euo pipefail`, under which a bare `patch` exit 1 would abort before `code=$?` could be read (verified locally with exit 0/1/2 cases).
- `moose.patch` contains a `framework/contrib/wasp` gitlink hunk (`-dirty` marker); partial-application (exit 1) is tolerated, and the `moose.mk` sentinel still guarantees the load-bearing stub.

### Files changed

- `scripts/install_dependencies_windows.ps1`:
  - MSYS pip ensure: added `jinja2`, hoisted outside `$needsInstall` gate.
  - Added §5.6 unconditional patch-ensure loop (petsc, netcdf, metis, wasp, moose) + stub verification.

### How to verify

- Syntax: PowerShell string escaping reviewed (balanced quotes); bash tolerance pattern `set +e; …; code=$?; set -e; [ $code -gt 1 ]` exercised locally for exit 0/1 (tolerated) and 2 (propagates). No compilation run locally per instruction (local MOOSE build in progress).
- CI: next `Windows: Build Wheel and Test` run with cache hits should pass `Verifying MOOSE Windows patch` and proceed past `_pycapabilities` to link `rabbit-opt.exe`. Watch for `Skipping pycapabilities on Windows...` instead of `Building and linking .../_pycapabilities.so`.
- Idempotence: re-running `-Stage rabbit` twice must show patch steps succeeding via skip path and stub check passing.

### Remaining uncertainty / next

- Linux `36106596972` fails independently at `stage_artifacts`: `FileNotFoundError: ... libomp.so.5` (`scripts/build/common.py`). Untouched here (OS-compartmentalised); to be handled as the next 5-min-watch item.
- `patch -N` exit-1 lumps "already applied" with other skipped-hunk cases; sentinel check covers the critical stub, but a future patch that partially applies for other reasons would still pass tolerance and rely on build errors to surface. Acceptable for now, flagged.
- No `pwsh` available locally to lint the `.ps1`; relied on manual escaping review + CI as verifier.
