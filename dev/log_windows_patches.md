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
  - `waspcore/Format.h`
  - `waspcore/CMakeLists.txt`
- **Origin**:
  - `Format.h`: **Local Windows Build** (Entry 017 of [`dev/log_windows_port.md`](file:///home/lloydf/rabbit-fem/dev/log_windows_port.md)).
  - `waspcore/CMakeLists.txt`: **Windows CI** ([Run #35955448580](https://github.com/Computer-Aided-Validation-Laboratory/rabbit-fem/actions/runs/35955448580) on commit `0d4ed03`, failure log [paste.rs/0t7wO](https://paste.rs/0t7wO)).
- **What it does**:
  1. In `Format.h`: Adds a check for `defined(_TWO_DIGIT_EXPONENT)` before calling `_set_output_format()`.
  2. In `waspcore/CMakeLists.txt`: Changes target include directory visibility from `PRIVATE` to `PUBLIC` and exports the parent WASP root directory (`$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/..>`).
- **Why it is needed**:
  1. `_set_output_format` and `_TWO_DIGIT_EXPONENT` were legacy MSVCRT functions removed from modern Universal CRT (UCRT) and MinGW-w64. Calling them caused compilation failures (`use of undeclared identifier '_TWO_DIGIT_EXPONENT'`).
  2. When building WASP out-of-tree via CMake (`build/`), internal source files (`waspcore/Definition.cpp`, `waspcore/Interpreter.cpp`, etc.) `#include "waspcore/Definition.h"` relative to the WASP root. Because `CMakeLists.txt` only added the local `waspcore` directory privately, the compiler could not resolve `waspcore/*.h`.

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
```
