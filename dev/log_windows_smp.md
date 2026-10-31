# Windows SMP Threading Log: Rabbit-FEM

This document logs the design, diagnosis, implementation, and verification of SMP-style multi-threading support (`--n-threads=N`) for `rabbit-fem` on Windows.

---

## 1. Context & Motivation

On Linux and macOS, the serial (non-MPI) distribution of `rabbit-fem` supports multi-threaded assembly and evaluation via POSIX threads or OpenMP through libMesh's threading abstractions (`--n-threads=N`).

On Windows, the initial port (documented in `dev/log_windows_port.md`, Entry 010) explicitly passed `--with-thread-model=none` to libMesh configure in `scripts/install_dependencies_windows.ps1` to achieve an initial minimal linking baseline without external runtime DLL dependencies.

When a user runs Rabbit on Windows with `--n-threads > 1`:
```powershell
.\rabbit-opt.exe -i input.i --n-threads=2
```
Execution immediately aborts in `moose/framework/src/base/MooseApp.C`:
```text
*** ERROR ***
You specified --n-threads > 1, but there is no threading model active!
```

---

## 2. Diagnosis & Root Cause Analysis

1. **MOOSE Guard Check**:
   `moose/framework/src/base/MooseApp.C:1100`:
   ```cpp
   #if !LIBMESH_USING_THREADS
     if (libMesh::command_line_value("--n-threads", 1) > 1)
       mooseError("You specified --n-threads > 1, but there is no threading model active!");
   #endif
   ```
   When libMesh is built with `--with-thread-model=none`, `LIBMESH_USING_THREADS` is `#undef USING_THREADS` in `libmesh_config.h`. Any `--n-threads > 1` triggers a fatal error.

2. **Why OpenMP is Not Viable on Windows with Zig**:
   The Windows toolchain uses Zig's bundled Clang/LLVM (`zig cc` / `zig c++` targeting `x86_64-windows-gnu`). Probing `-fopenmp`:
   ```powershell
   python -m ziglang c++ -target x86_64-windows-gnu -fopenmp dev/probe_omp.cpp
   ```
   fails with:
   ```text
   fatal error: 'omp.h' file not found
   ```
   Zig does not ship the LLVM OpenMP runtime library (`libomp`) for MinGW/Windows targets.

3. **Why POSIX Threads (`pthread`) is the Robust Solution**:
   - In `moose/libmesh/include/libmesh/threads_pthread.h`, when `!LIBMESH_HAVE_OPENMP`, libMesh falls back cleanly to native POSIX thread routines: `pthread_create`, `pthread_join`, `pthread_mutex_*`, and spinlocks (`pthread_spinlock_t` or atomic spinlocks).
   - Zig's C runtime bundles a static MinGW `winpthreads` implementation mapping POSIX thread APIs directly onto Windows Win32 thread APIs (`CreateThread`, `WaitForSingleObject`, etc.).
   - PE import header analysis of binaries linked with `-pthread` confirms **zero** external runtime DLLs:
     - `KERNEL32.dll`
     - Universal CRT (`api-ms-win-crt-*`)
     - NO `libwinpthread-1.dll`, NO `libgcc_s_seh-1.dll`, NO `libstdc++-6.dll`.
   - Autoconf feature probe with `--with-thread-model=pthread --enable-pthreads --disable-openmp`:
     ```text
     <<< User requested thread model: pthread >>>
     checking whether pthreads work without any flags... yes
     checking for joinable pthread attribute... PTHREAD_CREATE_JOINABLE
     <<< Configuring library with pthread support >>>
     <<< Found thread model: pthread >>>
     ```

---

## 3. Implementation Details

### A. Dependency Build Script (`scripts/install_dependencies_windows.ps1`)
In `Stage libmesh` (line 478):
- **Old**: `--disable-openmp --disable-boost --with-thread-model=none`
- **New**: `--disable-openmp --disable-boost --with-thread-model=pthread --enable-pthreads`

Because `.github/workflows/windows_build_and_test.yml` includes `hashFiles('scripts/install_dependencies_windows.ps1')` in its `libmesh` cache key, modifying this script automatically invalidates the stale `--with-thread-model=none` cache on CI runners.

### B. Clean-Machine Wheel Smoke Test (`.github/workflows/smoke.yml`)
Updated the Windows serial wheel smoke test to verify multi-threaded execution in an isolated virtualenv:
- Executes `cube_thermomech_HEX8` with `--n-threads=2`.
- Verifies return code 0 and non-empty Exodus output.

### C. Test Suite Regression Protection (`test/test_simulations.py`)
Added regression test `test_smp_threads()`:
- Calls `run_rabbit(cube_thermomech_input_path(EElemType.HEX8), extra_args=['Executioner/end_time=1', '--n-threads=2'], cwd=isolated_dir)`.
- Asserts exit code 0 and valid Exodus file generation.
- Validates the PE import table to ensure no `libwinpthread*.dll` or compiler runtime DLLs leaked into the binary.

### D. Documentation (`README.md`)
Updated the execution documentation to state that Windows serial and MPI builds support multi-threading via `--n-threads=N`.

---

## 4. Verification

1. **Compilation & Linking**:
   - `moose/libmesh` successfully configures with pthread support and `#define LIBMESH_USING_THREADS 1`.
   - `rabbit-opt.exe` compiles and links statically against `libmesh_opt.a`.
2. **PE Import Audit**:
   - Audited import directory of `rabbit-opt.exe` via `_get_pe_imported_dlls()`.
   - Verified that `libwinpthread*.dll` does not appear.
3. **Execution**:
   - `.\rabbit-opt.exe --n-threads=2` runs without triggering the MooseApp abort.
   - Simulation completes successfully and outputs valid results.
