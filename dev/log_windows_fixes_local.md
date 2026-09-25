# Local Windows Build Fixes & CI Divergence Analysis

This document logs all issues encountered during clean local builds on Windows and provides an in-depth technical analysis of why GitHub Actions CI previously broke repeatedly despite local builds succeeding.

---

## 1. Clean Local Rebuild Log (September 24, 2026)

### Target Environment
- **OS**: Windows 10/11 x86_64
- **MSYS2 Root**: `C:\msys64`
- **Compiler Drivers**: Zig 0.16.0 (`python -m ziglang cc / c++`) targeting `x86_64-windows-gnu`
- **Python**: 3.13.14 (`.venv`)

### Execution Record

| Stage | Action | Status | Issues Encountered / Fixes |
|-------|--------|--------|----------------------------|
| **Pre-Build Cleanup** | `git reset --hard` & `git clean -fdx` across root and all submodules (`petsc`, `libmesh`, `wasp`, `moose`). | **PASSED** | Clean pristine baseline established. |
| **Stage 1: PETSc** | Configured and built PETSc with `f2cblaslapack=1` and `zig-cc`/`zig-cxx`. | **PASSED** | Built `moose/petsc/arch-windows-opt/lib/libpetsc.a` (84.8 MB) using `patches/windows/petsc.patch`. 0 local interventions needed. |
| **Stage 2: libMesh** | Submodule checkout, symlink conversion, configure, and compilation. | **PASSED** | **Fix**: `scripts/install_dependencies_windows.ps1` previously passed `--with-petsc=...` instead of setting `PETSC_DIR` and `PETSC_ARCH` environment/command-line variables. This caused libMesh configure to disable PETSc (`#undef HAVE_PETSC`). Updated install script to export and pass `PETSC_DIR` and `PETSC_ARCH`, restoring full PETSc support (`#define HAVE_PETSC 1`). Built and installed `moose/libmesh/installed/lib/libmesh_opt.a`. |
| **Stage 3: WASP & HIT** | CMake configure & build with Make and `hit.exe` compiler. | **PASSED** | **Fix 1**: `scripts/install_dependencies_windows.ps1` patch application lacked `|| true` on WASP, NetCDF, and METIS, causing re-runs to fail when patches were already present. Added `|| true` to all patch steps.<br>**Fix 2**: `cc_wrapper.py` and `cxx_wrapper.py` stripped `-MD` as an MSVC flag, leaving `-MT <target>` arguments orphaned as positional compiler inputs, which broke CMake TryCompile with `failed to open object ...: FileNotFound`. Removed `-MD`/`-MT` from `msvc_flags` (preserving GCC/Clang dependency generation) and ensured parent directories are auto-created for `-o` / `-MF` / archive outputs. Built `hit.exe`. |
| **Stage 4: MOOSE Config** | MOOSE framework configure (`--with-derivative-size=89`). | **PASSED** | Generated `MooseConfig.h`. |
| **Stage 5: Rabbit App & Wheel** | Application build, staging `rabbit.exe`, wheel packaging & pytest verification. | **PASSED** | **Fix 1 (Unity generator)**: `userobjects_Unity.C` truncated due to MSYS2 subshell limits in GNU Make. Created `moose/scripts/make_unity.py`.<br>**Fix 2 (Nemesis_IO)**: Guarded uncompiled Nemesis copy methods in `SolutionUserObjectBase.C` with `LIBMESH_HAVE_NEMESIS_API`.<br>**Fix 3 (Data directory check)**: `Registry::determineDataFilePath` called `ifstream` on directory paths, failing on Windows. Switched to `std::filesystem::exists`.<br>**Fix 4 (Range check integer overflow)**: `InputParameters::parameterRangeCheck` upcast `unsigned int` to 32-bit signed `long` on Windows (LLP64), causing `UINT_MAX` to overflow to `-1` and fail `time_step_interval > 0`. Switched upcast type to `Real` (`double`).<br>**Result**: Built `rabbit-opt.exe` and `rabbit_fem-2026.9.0-py3-none-win_amd64.whl` (26.82 MB). All 10 pytest simulation cases passed (100%). |

---

## 2. Why Local Windows Builds Work vs Why CI Was So Brittle

The reason the build succeeded locally while breaking in GitHub Actions CI comes down to **nine fundamental architectural divergence vectors** between a persistent local Windows machine and an ephemeral GitHub Actions `windows-latest` runner:

### Vector 1: Workspace Drive Letters & POSIX Mount Resolution
- **Local Machine**: The workspace resides on the primary system drive `C:\Users\longb\rabbit-fem` (`/c/Users/longb/...`).
- **GitHub Actions Runner**: The workspace is mounted on an auxiliary drive `D:\a\rabbit-fem\rabbit-fem` (`/d/a/rabbit-fem/...`).
- **Why CI Broke**:
  1. **CMake Dependency Scanner (`compiler_depend.make`)**: `zig cc` outputs raw `D:/a/...` paths into Make dependency files. GNU Make interprets the colon `D:` as a rule separator, throwing `*** multiple target patterns. Stop.` on CI. On C drive, depending on MSYS mount aliases, this behaved differently.
  2. **MSYS System Mounts (`/tmp` vs `/d/tmp`)**: Under MSYS2, temporary files are placed in `/tmp`. When `zig-ar` (a Windows native tool) ran on CI, passing `/tmp/obj.o` caused it to look in `D:/tmp/obj.o` (which does not exist) rather than `C:/msys64/tmp/obj.o`.
  3. **PETSc `libraries.py`**: Checked `if libName[0].startswith('/'):` to extract the directory name. When passed `D:/a/...`, it skipped directory extraction and failed to locate BLAS/LAPACK libraries.

### Vector 2: `uname` Output and MSYS2 Environment Names
- **Local MSYS2**: Depending on how MSYS2 bash was launched or configured, `uname` often reported `MINGW64_NT` or matched local expectations.
- **CI MSYS2 (`setup-msys2` action)**: `uname` reports `MSYS_NT-10.0-20348`.
- **Why CI Broke**: Upstream `moose.mk` had `ifeq ($(UNAME10), MINGW64_NT)`. Because the string did not match `MSYS_NT`, MOOSE generated raw POSIX paths (`/d/a/...`) inside unity `#include` statements. Windows Clang cannot resolve POSIX mount paths, throwing `'file not found'` errors on CI.

### Vector 3: Ephemeral Clean-Room Tooling vs Persistent Site-Packages
- **Local Machine**: Tools like `packaging`, `pyyaml`, `jinja2`, and `m4` were previously installed in the Python/MSYS2 environment.
- **CI Runner**: Every CI run starts with a completely blank MSYS2 and Python image.
- **Why CI Broke**: Scripts like `get_repo_revision.py` and WASP build tools crashed immediately on CI with `ModuleNotFoundError: No module named 'packaging'` because they assumed host development packages were pre-installed.

### Vector 4: Submodule Git Symlinks on NTFS
- **Local Machine**: Windows Developer Mode or git checkout settings may handle symlink clones differently, or symlinks were resolved in earlier interactive sessions.
- **CI Runner**: `actions/checkout` with `submodules: recursive` checks out symlinks as plain text files containing relative paths (e.g. `eigen/eigen` contains `gitshim`).
- **Why CI Broke**: LibMesh headers failed to find Eigen (`Householder: No such file or directory`) until explicit recursive symlink resolution scripts were integrated.

### Vector 5: POSIX vs Windows C Runtime (UCRT)
- **Local Machine**: The Zig toolchain targets `x86_64-windows-gnu` and links the Windows CRT.
- **CI Runner**: When CI invoked MSYS2 `python3-config` during MOOSE build steps, it pulled in Cygwin/MSYS2 POSIX headers (`<sys/select.h>`, POSIX signal masks), which do not exist in the Windows CRT. This broke Python C extensions (`_pycapabilities.so`) until they were stubbed for NT targets.

### Vector 6: Link-Time System Dependencies
- **Why CI Broke**: On clean Windows links, Zig Clang requires explicit Windows system libraries (`-lws2_32`, `-lcrypt32`, `-lshlwapi`, `-liphlpapi`, `-lpsapi`, `-ladvapi32`, `-luser32`) to satisfy socket, cryptography, process, and security APIs called by PETSc and libMesh. On local builds, these were sometimes satisfied by implicit link paths that were missing on bare CI runners.

### Vector 7: Subshell Process Spawning Limits in GNU Make Unity Rules
- **Problem**: Upstream `moose.mk` unity build rule (`unity_file_rule`) executed `$(foreach srcfile,$(sort $(2)),$(shell echo '#include "'$(shell cygpath -m $(srcfile))'"' >> $@))`. In directories with large numbers of source files (e.g., `userobjects` with 78 files), evaluating two `$(shell ...)` calls per file spawned 156 subshells in a tight synchronous loop inside GNU make on MSYS2. This exhausted MSYS2 process/pipe resources, silently truncating `userobjects_Unity.C` after 49 files and omitting critical base classes (`UserObjectInterface`, `UserObjectBase`, `SolutionUserObjectBase`, etc.), causing link-time undefined symbols.
- **Fix**: Replaced the makefile subshell loop with a dedicated, atomic Python helper script (`moose/scripts/make_unity.py`) that normalizes file paths and generates the complete unity source file in a single fast process.

### Vector 8: Windows Data Directory Readability Validation
- **Problem**: `Registry::determineDataFilePath` called `MooseUtils::checkFileReadable` on the `data` directory. On Windows, opening a directory handle with `std::ifstream` always fails, triggering fatal startup termination during static registration.
- **Fix**: Replaced `checkFileReadable` with `std::filesystem::exists` and graceful fallback.

### Vector 9: Windows LLP64 Data Model vs Range Check Integer Sign Overflow
- **Problem**: On Windows (LLP64), `sizeof(long)` is 4 bytes (32-bit signed), unlike Linux (LP64) where `long` is 8 bytes. `InputParameters::parameterRangeCheck` upcast `unsigned int` to `long`. When parameters were initialized to `std::numeric_limits<unsigned int>::max()` (4,294,967,295), the 32-bit cast overflowed to `-1`, causing valid default ranges (like `time_step_interval > 0`) to fail at simulation launch.
- **Fix**: Upcast `unsigned int` and `unsigned long` to `Real` (`double`), preserving the full unsigned range without sign overflow.

---

## 3. Current Remediation Strategy

All nine divergence vectors are now unified directly into the repository scripts and patch files:
1. **`scripts/windows_wrappers/wrapper_utils.py`**: Intercepts all paths, normalizes both `C:` and `D:` drives (`/d/...` -> `D:/...`), and resolves `/tmp` -> `C:/msys64/tmp`.
2. **`moose/scripts/make_unity.py` & `patches/windows/moose.patch`**: Fast, reliable unity file generation without MSYS2 subshell exhaustion.
3. **`patches/windows/petsc.patch`**: Broadens library path parsing in `libraries.py` to handle both POSIX and Windows drive letters.
4. **`patches/windows/wasp.patch`**: Sets `CMAKE_DEPENDS_USE_COMPILER FALSE` to prevent CMake from writing drive-letter colons into Makefiles.
5. **`scripts/install_dependencies_windows.ps1`**: Installs all required MSYS2 packages (`diffutils`, `make`, `patch`, `m4`, `git`, `python`, `cmake`) idempotently.

