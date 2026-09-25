# Windows Porting Patches Log

This document details all unified patch files stored in [`patches/windows/`](file:///home/lloydf/rabbit-fem/patches/windows), what each patch accomplishes, why it is needed, and where the issue was first encountered (local Windows build vs GitHub Actions CI).

---

## 1. NetCDF-C (`patches/windows/netcdf.patch`)

- **Target Component**: `moose/libmesh/contrib/netcdf/netcdf-c-4.6.2`
- **Files Modified**:
  - `libdispatch/dwinpath.c`
  - `libsrc/memio.c`
- **Origin**: **Local Windows Build** (Documented in Entry 011 of [`dev/log_windows_port.md`](file:///home/lloydf/rabbit-fem/dev/log_windows_port.md)).
- **What it does**:
  1. In `dwinpath.c`: Adds `#include <errno.h>` so error constants like `ENOENT` are defined.
  2. In `dwinpath.c`: Uses `_fullpath(NULL, relpath, 8192)` and `_access()` on `_WIN32` rather than POSIX `realpath()` and `access()`, which are unavailable in the MinGW/UCRT runtime.
  3. In `memio.c`: Broadens `#ifdef _MSC_VER` to `#if defined(_MSC_VER) || defined(_WIN32)` so `<windows.h>` is included and file streams are opened in binary mode (`"rb"`/`"wb"`).
- **Why it is needed**:
  NetCDF's Windows path and memory IO implementations were historically guarded strictly for Microsoft Visual C++ (`_MSC_VER`). When building with Clang/Zig under MSYS2 targeting `x86_64-windows-gnu`, these code paths were skipped, falling back to POSIX functions that do not exist in the Windows CRT.

---

## 2. METIS GKlib (`patches/windows/metis.patch`)

- **Target Component**: `moose/libmesh/contrib/metis/GKlib`
- **Files Modified**:
  - `gk_arch.h`
  - `GKlib.h`
  - `gk_getopt.h`
- **Origin**: **Local Windows Build** (Documented in Entry 012 of [`dev/log_windows_port.md`](file:///home/lloydf/rabbit-fem/dev/log_windows_port.md)).
- **What it does**:
  1. In `gk_arch.h`: Guards `#include <sys/resource.h>` with `#if !defined(_WIN32) && !defined(__MINGW32__)`.
  2. In `GKlib.h`: Selects METIS's bundled `"gkregex.h"` whenever `_WIN32` or `__MINGW32__` is defined instead of attempting to include `<regex.h>`.
  3. In `gk_getopt.h`: Renames function prototype parameters `__argc`, `__argv`, `__shortopts`, `__longopts`, and `__longind` to `argc`, `argv`, `shortopts`, `longopts`, and `longind`.
- **Why it is needed**:
  1. Windows CRT does not supply POSIX `<sys/resource.h>` (e.g. `getrusage`).
  2. Windows lacks native POSIX regular expressions (`<regex.h>`).
  3. In the Windows CRT (`<stdlib.h>`), `__argc` and `__argv` are predefined global argument access macros. Using them as argument names in header prototypes causes macro substitution errors during compilation.

---

## 3. WASP (`patches/windows/wasp.patch`)

- **Target Component**: `moose/framework/contrib/wasp`
- **Files Modified**:
  - `CMakeLists.txt`
  - `waspcore/Format.h`
  - `waspcore/CMakeLists.txt`
- **Origin**:
  - `Format.h`: **Local Windows Build** (Entry 017 of [`dev/log_windows_port.md`](file:///home/lloydf/rabbit-fem/dev/log_windows_port.md)).
  - `waspcore/CMakeLists.txt`: **Windows CI** ([Run #35955448580](https://github.com/Computer-Aided-Validation-Laboratory/rabbit-fem/actions/runs/35955448580) on commit `0d4ed03`, failure log [paste.rs/0t7wO](https://paste.rs/0t7wO)).
  - `CMakeLists.txt`: **Windows CI** ([Run #35969401750](https://github.com/Computer-Aided-Validation-Laboratory/rabbit-fem/actions/runs/35969401750) on commit `88530bb`, failure log [paste.rs/NF6GF](https://paste.rs/NF6GF)).
- **What it does**:
  1. In `CMakeLists.txt`: Sets `CMAKE_DEPENDS_USE_COMPILER FALSE` when `CMAKE_SYSTEM_NAME` is Windows.
  2. In `Format.h`: Adds a check for `defined(_TWO_DIGIT_EXPONENT)` before calling `_set_output_format()`.
  3. In `waspcore/CMakeLists.txt`: Changes target include directory visibility from `PRIVATE` to `PUBLIC` and exports the parent WASP root directory (`$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/..>`).
- **Why it is needed**:
  1. In CMake 3.20+, source dependencies for Makefiles are generated directly by the compiler. Under MSYS2, `zig cc` outputs Windows drive paths (e.g. `D:/a/...`) into `compiler_depend.make`. When GNU Make parses the file, it interprets the drive colon as a rule delimiter and aborts with `*** multiple target patterns. Stop.`. Setting `CMAKE_DEPENDS_USE_COMPILER FALSE` forces CMake to use its internal dependency scanner, preventing raw drive-letter dependencies.
  2. `_set_output_format` and `_TWO_DIGIT_EXPONENT` were legacy MSVCRT functions removed from modern Universal CRT (UCRT) and MinGW-w64. Calling them caused compilation failures (`use of undeclared identifier '_TWO_DIGIT_EXPONENT'`).
  3. When building WASP out-of-tree via CMake (`build/`), internal source files (`waspcore/Definition.cpp`, `waspcore/Interpreter.cpp`, etc.) `#include "waspcore/Definition.h"` relative to the WASP root. Because `CMakeLists.txt` only added the local `waspcore` directory privately, the compiler could not resolve `waspcore/*.h`.

---

## 4. MOOSE Framework (`patches/windows/moose.patch`)

- **Target Component**: `moose`
- **Files Modified**:
  - `framework/moose.mk`
  - `framework/scripts/get_repo_revision.py`
- **Origin**:
  - `moose.mk`: **Windows CI** ([Run #35980313025](https://github.com/Computer-Aided-Validation-Laboratory/rabbit-fem/actions/runs/35980313025) on commit `f1e3357`).
  - `get_repo_revision.py`: **Windows CI** ([Run #35996839352](https://github.com/Computer-Aided-Validation-Laboratory/rabbit-fem/actions/runs/35996839352) on commit `bafabb7`).
- **What it does**:
  1. In `moose.mk` on Windows (`$(findstring NT,$(shell uname))`):
     - Stubs the build rule for `pycapabilities` (`_pycapabilities.so`/`.pyd`) by creating the destination directory and touching the target file.
     - Skips rebuilding HIT via `cd $(HIT_DIR) && $(MAKE)`; instead verifies the WASP-stage `hit.exe`/`hit` exists (failing early with a clear message otherwise) and touches `$(pyhit_LIB)`.
     - Ensures `unity_file_rule` and `UNAME10` match all Windows NT variants (including MSYS2 `MSYS_NT-*`), invoking `cygpath -m` to output standard Windows drive paths (`D:/...`) into `#include` statements within generated `_Unity.C` files.
  2. In `get_repo_revision.py`:
     - Adds a fallback version comparison mechanism so `MooseRevision.h` generation succeeds even if the host/MSYS2 Python environment lacks the third-party `packaging` module.
- **Why it is needed**:
  1. In MSYS2, `python3-config` resolves to MSYS2 POSIX Python (`/usr/bin/python3-config`), which pulls in `/usr/include/python3.12/Python.h` and `<sys/select.h>`. When compiling with Zig targeting Windows GNU (`x86_64-windows-gnu`), `<sys/select.h>` is unavailable in the Windows C runtime, causing `_pycapabilities.so` compilation to fail with `fatal error: 'sys/select.h' file not found`.
  2. `_pycapabilities` and `pyhit_LIB` are Python C extensions intended for MOOSE internal test harness scripts and are neither linked into `rabbit-opt.exe` nor packaged into Rabbit distribution wheels. Stubbing them on Windows allows the core simulation engine and application binary to build and link cleanly without POSIX Python runtime conflicts.
  3. Rebuilding HIT from `moose.mk` via a bare `cd $(HIT_DIR) && $(MAKE)` (no `CXX` override, unlike the WASP stage which passes `CXX=zig-cxx`) links with a MinGW `g++` found on the runner `PATH` (`C:/mingw64/.../ld.exe` via `collect2.exe` in CI logs), whose GNU `libstdc++` cannot link the Zig-built WASP static libs (libc++ `std::__1` symbols such as `ios_base::clear`, `cin`/`cout`), failing with `undefined reference to 'std::__1::...'` and `make[1]: *** [Makefile:61: hit] Error 1`. The WASP stage already builds a correct Zig `hit.exe`; the Rabbit-stage rebuild is redundant, so it is skipped after verifying the executable exists.
  3. `get_repo_revision.py` unconditionally imported `from packaging import version` on Python $\ge 3.7$. In clean MSYS2 Python installations, `packaging` is not present by default, causing `MooseRevision.h` header generation to fail during `make`. Providing a lightweight standard library fallback ensures header generation always succeeds.
  4. In MSYS2 bash, `uname` outputs `MSYS_NT-10.0-...`, causing the upstream `ifeq ($(UNAME10), MINGW64_NT)` check to evaluate to false. This resulted in generating raw MSYS POSIX paths (e.g. `"/d/a/..."`) inside unity source `#include` directives. Windows-native Clang cannot resolve POSIX mount paths, triggering `'file not found'` compilation errors. Using `cygpath -m` produces Windows paths (`"D:/a/..."`) that Clang resolves directly.

---

## 5. Toolchain Wrapper POSIX Path Conversion (`scripts/windows_wrappers/wrapper_utils.py`)

- **Target Component**: `scripts/windows_wrappers/wrapper_utils.py`
- **Origin**:
  - `posix_to_win()` include/macro flags: **Windows CI** ([Run #36009350409](https://github.com/Computer-Aided-Validation-Laboratory/rabbit-fem/actions/runs/36009350409) on commit `c9962f7`).
  - `posix_to_win()` MSYS system mounts (`/tmp`, `/usr`): **Windows CI** ([Run #36024094553](https://github.com/Computer-Aided-Validation-Laboratory/rabbit-fem/actions/runs/36024094553) on commit `f19b9e7`).
- **What it does**:
  Transforms MSYS2 POSIX drive paths (`/d/...`, `/c/...` -> `D:/...`, `C:/...`) and MSYS system mount paths (`/tmp/...`, `/usr/...` -> `C:/msys64/tmp/...`, `C:/msys64/usr/...`) to native Windows paths across all compiler/archiver/linker invocations (`-include /d/...`, `-isystem /d/...`, `-MF /d/...`, `-Wl,-rpath,/d/...`, `zig-ar cr lib.a /tmp/obj.o`, and composite `-I` and `-L` arguments).
- **Why it is needed**:
  1. During MOOSE and module compilation, GNU Make and `libmesh-config` emit flags with embedded MSYS POSIX paths (such as `libmesh_CPPFLAGS += -include $(moose_config)` or `-I/d/a/rabbit-fem/moose/libmesh/installed/include`). Because `zig cc` / `zig c++` are native Windows Clang binaries, unresolved POSIX paths cause Clang to miss `libmesh_config.h` and PETSc headers, triggering `PETSc has not been detected` and `'petscsys.h' file not found`.
  2. During PETSc build steps (like `f2cblaslapack`), objects are created in `/tmp/...`. When `zig-ar` runs to package archives, passing raw `/tmp/...` causes the Windows archiver to search the workspace root drive (`D:/tmp/...`) where the files do not exist. Resolving `/tmp/...` to `C:/msys64/tmp/...` ensures `zig-ar` finds all temporary object files.

---

## Patch Management

All patches are applied automatically in [`scripts/install_dependencies_windows.ps1`](file:///home/lloydf/rabbit-fem/scripts/install_dependencies_windows.ps1) using MSYS2 `patch`:

```powershell
# NetCDF
cd moose/libmesh/contrib/netcdf/netcdf-c-4.6.2 && patch -p1 -N -r - < "$RepoRootPosix/patches/windows/netcdf.patch"

# METIS
cd moose/libmesh/contrib/metis/GKlib && patch -p1 -N -r - < "$RepoRootPosix/patches/windows/metis.patch"

# WASP
cd moose/framework/contrib/wasp && patch -p1 -N -r - < "$RepoRootPosix/patches/windows/wasp.patch"

# MOOSE Framework
cd moose && patch -p1 -N -r - < "$RepoRootPosix/patches/windows/moose.patch"
```

