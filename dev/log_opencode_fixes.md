# OpenCode CI Fixes Log

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
