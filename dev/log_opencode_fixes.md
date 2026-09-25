# OpenCode CI Fixes Log

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
