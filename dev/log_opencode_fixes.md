# OpenCode CI Fixes Log

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
- **Change (diagnostic + permanent fail-early guard, Windows-only)**: new read-only preflight in `scripts/install_dependencies_windows.ps1` §10 before `make` — prints `libmesh-config --cxx/--cppflags/--include`, asserts `--include` mentions `petsc` (clear error otherwise), and asserts `arch-windows-opt/include/petscconf.h` + `petsc/include/petscsys.h` exist. Verified locally by emulating the PowerShell→bash expansion and running happy / no-PETSc / missing-script scenarios (exits 0/1/1 with the intended messages; `bash -n` clean).
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
