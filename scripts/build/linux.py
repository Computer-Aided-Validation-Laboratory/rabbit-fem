"""Linux-specific build, toolchain configuration, and dependency logic."""

import glob
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .common import (
    ensure_moose_repo,
    ensure_moose_submodules,
    ensure_serial_mpi_fallback,
    find_python_exe,
    is_mpi_build,
    mpi_compiler_env,
    mpi_fortran_wrapper,
)


def detect_system_include_flags(wrapper_dir: Path) -> list[str]:
    """Detect system GCC libstdc++ and OpenMP include paths with idirafter."""
    flags: list[str] = ["-nostdinc++"]

    cxx_dirs = sorted(glob.glob("/usr/include/c++/*"))
    if cxx_dirs:
        latest_cxx = cxx_dirs[-1]
        cxx_ver = Path(latest_cxx).name
        flags.append(f"-I{latest_cxx}")

        arch_cxx = f"/usr/include/x86_64-linux-gnu/c++/{cxx_ver}"
        if Path(arch_cxx).is_dir():
            flags.append(f"-I{arch_cxx}")

        backward_cxx = f"{latest_cxx}/backward"
        if Path(backward_cxx).is_dir():
            flags.append(f"-I{backward_cxx}")

    # OpenMP header isolation
    inc_dir = wrapper_dir / "include"
    inc_dir.mkdir(parents=True, exist_ok=True)
    omp_candidates = glob.glob(
        "/usr/lib/gcc/x86_64-linux-gnu/*/include/omp.h"
    )
    if omp_candidates:
        omp_target = inc_dir / "omp.h"
        if not omp_target.exists():
            shutil.copy2(omp_candidates[-1], omp_target)
        flags.append(f"-I{inc_dir}")

    flags.append("-idirafter /usr/include")
    flags.append("-idirafter /usr/include/x86_64-linux-gnu")
    return flags


def check_build_tools(*, mpi: bool = False) -> None:
    """Fail early if required build tools are missing from PATH.

    libMesh's bundled dependencies shell out to ``m4`` during configure,
    and the default make target compiles module test plugins from
    Fortran sources (without a Fortran compiler the build dies with a
    cryptic ``make: no: No such file or directory`` from libtool). The
    MPI PETSc recipe additionally needs ``flex``/``bison`` (its
    PTScotch download fails configure without them). Only tools proven
    required are gated here.
    """
    import shutil

    tools = ["m4", "gfortran"]
    if mpi:
        tools += ["flex", "bison"]
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        raise RuntimeError(
            "Required build tools not found on PATH: "
            + ", ".join(missing)
            + ". Install them (e.g. `sudo apt-get install -y "
            + " ".join(missing)
            + "` on Ubuntu) and retry."
        )


def _xdr_include_candidates() -> list[list[str]]:
    """Candidate -I flag sets for the XDR header probe.

    Mirrors libMesh's own ``CONFIGURE_XDR`` fallback order: a bare
    compile first (glibc sunrpc, conda prefix already on ``CPATH``, or
    caller-provided ``CPPFLAGS``), then the documented system tirpc
    location (``libtirpc-dev`` on Debian/Ubuntu, same ``-I`` libMesh
    tries). Env-derived prefixes (``TIRPC_DIR``, ``CONDA_PREFIX``) are
    preferred over the system path, matching MOOSE's
    ``configure_libmesh.sh`` handling. Entries whose directories do not
    exist are skipped so no bogus ``-I`` is passed.
    """
    candidates: list[list[str]] = [[]]
    seen: set[str] = set()
    extra_dirs: list[str] = []
    tirpc_dir = os.environ.get("TIRPC_DIR", "")
    if tirpc_dir:
        extra_dirs.append(tirpc_dir)
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix:
        extra_dirs.append(str(Path(conda_prefix) / "include" / "tirpc"))
    # Documented system location (what libMesh itself falls back to).
    extra_dirs.append("/usr/include/tirpc")
    for inc_dir in extra_dirs:
        if not inc_dir or inc_dir in seen:
            continue
        seen.add(inc_dir)
        if Path(inc_dir).is_dir():
            candidates.append([f"-I{inc_dir}"])
    return candidates


def check_xdr_headers(zigcc_path: Path) -> None:
    """Fail early if no XDR (rpc) headers are visible to the toolchain.

    MOOSE's ``configure_libmesh.sh`` hardcodes ``--enable-xdr-required``,
    so a libMesh configure without XDR headers dies deep in the build
    with ``configure: error: *** XDR was not found``. Probe with the
    actual wrapper compiler instead of checking fixed paths: headers may
    legitimately come from the system (``libtirpc-dev``), a conda prefix,
    or ``CPATH``. Anything the probe cannot compile, libMesh cannot use.

    The probe mirrors libMesh's fallback: a bare ``#include <rpc/rpc.h>``
    first, then the same ``-I/usr/include/tirpc`` libMesh tries (plus any
    ``TIRPC_DIR``/conda prefix from the environment).
    """
    import tempfile

    candidates = _xdr_include_candidates()
    with tempfile.TemporaryDirectory(prefix="rabbit-xdr-probe-") as tmp:
        src = Path(tmp) / "xdr_probe.c"
        src.write_text(
            '#include <rpc/rpc.h>\nint main(void) { return 0; }\n',
            encoding="utf-8",
        )
        for extra_flags in candidates:
            res = subprocess.run(
                [
                    str(zigcc_path),
                    "-c",
                    str(src),
                    "-o",
                    str(Path(tmp) / "x.o"),
                    *extra_flags,
                ],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                return
    raise RuntimeError(
        "XDR (rpc) headers not found by the build compiler. "
        "libMesh requires them (MOOSE passes --enable-xdr-required). "
        "Install the system package (e.g. "
        "`sudo apt-get install -y libtirpc-dev` on Ubuntu) and retry."
    )


def setup_linux_toolchain(repo_dir: Path) -> tuple[Path, Path]:
    """Create wrapper scripts for zig cc / clang toolchain on Linux."""
    wrapper_dir = repo_dir / ".zig_wrappers"
    wrapper_dir.mkdir(parents=True, exist_ok=True)

    zigcc_path = wrapper_dir / "zigcc"
    zigcxx_path = wrapper_dir / "zigcxx"

    clang_candidates = (
        [shutil.which("clang")] if shutil.which("clang") else []
    ) + sorted(glob.glob("/opt/rocm-*/lib/llvm/bin/clang"))
    clangxx_candidates = (
        [shutil.which("clang++")] if shutil.which("clang++") else []
    ) + sorted(glob.glob("/opt/rocm-*/lib/llvm/bin/clang++"))

    if clang_candidates and clangxx_candidates:
        c_compiler = clang_candidates[0]
        cxx_compiler = clangxx_candidates[0]
        cc_template = (
            "#!/bin/bash\n"
            f"exec {c_compiler} \"$@\"\n"
        )
        cxx_template = (
            "#!/bin/bash\n"
            f"exec {cxx_compiler} \"$@\"\n"
        )
    else:
        py_exe = find_python_exe()
        inc_flags = " ".join(detect_system_include_flags(wrapper_dir))
        warn_flags = (
            "-Wno-date-time -Wno-error=date-time "
            "-Wno-ignored-attributes -Wno-unused-command-line-argument "
            "-fno-sanitize=all"
        )
        omp_candidates = (
            glob.glob("/opt/rocm-*/lib/llvm/lib/libomp.so")
            + glob.glob("/opt/rocm-*/lib/llvm/lib-debug/libomp.so")
            + glob.glob("/usr/lib/llvm-*/lib/libomp.so")
        )
        omp_link_flag = (
            f"-x none {omp_candidates[0]}" if omp_candidates else ""
        )

        cc_template = (
            "#!/bin/bash\n"
            "is_compile=0\n"
            "extra_link=\"\"\n"
            "filtered_args=()\n"
            "for arg in \"$@\"; do\n"
            "    if [ \"$arg\" = \"-c\" ] || [ \"$arg\" = \"-E\" ] || "
            "[ \"$arg\" = \"-S\" ]; then\n"
            "        is_compile=1\n"
            "    fi\n"
            "    if [ \"$arg\" = \"-shared\" ]; then\n"
            "        extra_link=\"-nostartfiles\"\n"
            "    fi\n"
            "    if [ \"$arg\" != \"-lstdc++\" ] && "
            "[ \"$arg\" != \"-lstdc++fs\" ]; then\n"
            "        filtered_args+=(\"$arg\")\n"
            "    fi\n"
            "done\n"
            "if [ \"$is_compile\" -eq 1 ]; then\n"
            f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ "
            f"{inc_flags} "
            "\"${filtered_args[@]}\" "
            f"{warn_flags}\n"
            "else\n"
            f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ "
            f"{inc_flags} "
            + '"${filtered_args[@]}" $extra_link '
            + f"{omp_link_flag} "
            "-Wl,--allow-shlib-undefined "
            f"{warn_flags}\n"
            "fi\n"
        )

        cxx_template = (
            "#!/bin/bash\n"
            "is_compile=0\n"
            "extra_link=\"\"\n"
            "filtered_args=()\n"
            "for arg in \"$@\"; do\n"
            "    if [ \"$arg\" = \"-c\" ] || [ \"$arg\" = \"-E\" ] || "
            "[ \"$arg\" = \"-S\" ]; then\n"
            "        is_compile=1\n"
            "    fi\n"
            "    if [ \"$arg\" = \"-shared\" ]; then\n"
            "        extra_link=\"-nostartfiles\"\n"
            "    fi\n"
            "    if [ \"$arg\" != \"-lstdc++\" ] && "
            "[ \"$arg\" != \"-lstdc++fs\" ]; then\n"
            "        filtered_args+=(\"$arg\")\n"
            "    fi\n"
            "done\n"
            "if [ \"$is_compile\" -eq 1 ]; then\n"
            f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ "
            f"{inc_flags} "
            "\"${filtered_args[@]}\" "
            f"{warn_flags}\n"
            "else\n"
            f"    exec {py_exe} -m ziglang cc -stdlib=libstdc++ "
            f"{inc_flags} "
            + '"${filtered_args[@]}" $extra_link -x none '
            + "/usr/lib/x86_64-linux-gnu/libstdc++.so.6 "
            "/usr/lib/x86_64-linux-gnu/libgcc_s.so.1 "
            f"{omp_link_flag} "
            f"-Wl,--allow-shlib-undefined {warn_flags}\n"
            "fi\n"
        )

    zigcc_path.write_text(cc_template)
    zigcxx_path.write_text(cxx_template)

    zigcc_path.chmod(0o755)
    zigcxx_path.chmod(0o755)

    return zigcc_path, zigcxx_path


def get_linux_tool_env(
    zigcc_path: Path,
    zigcxx_path: Path,
) -> dict[str, str]:
    """Prepare environment variables for building Linux dependencies."""
    tool_env = dict(os.environ)
    if is_mpi_build():
        tool_env.update(mpi_compiler_env(zigcc_path, zigcxx_path))
    else:
        # Serial/SMP variant: no MPI compiler wrappers anywhere. PETSc
        # falls back to its MPIUNI stubs and libMesh builds serial with
        # threading intact, so --n-threads keeps working.
        tool_env["CC"] = str(zigcc_path)
        tool_env["CXX"] = str(zigcxx_path)
    tool_env["CMAKE_LIBRARY_PATH"] = "/usr/lib/x86_64-linux-gnu"
    tool_env["CMAKE_PREFIX_PATH"] = (
        "/usr/lib/x86_64-linux-gnu:"
        + os.environ.get("CMAKE_PREFIX_PATH", "")
    )
    tool_env["LIBRARY_PATH"] = (
        "/usr/lib/x86_64-linux-gnu:"
        + os.environ.get("LIBRARY_PATH", "")
    )
    return tool_env


def build_petsc(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build PETSc dependency on Linux."""
    ensure_moose_repo(repo_dir, moose_dir)
    ensure_moose_submodules(moose_dir)
    check_build_tools(mpi=is_mpi_build())
    petsc_built = (
        (moose_dir / "petsc" / "arch-moose" / "lib" / "libpetsc.so").is_file()
        or (
            moose_dir / "petsc" / "arch-linux" / "lib" / "libpetsc.so"
        ).is_file()
        or (moose_dir / "petsc" / "lib" / "libpetsc.so").is_file()
    )
    if not petsc_built:
        print("--> Building PETSc...")
        petsc_env = get_linux_tool_env(zigcc_path, zigcxx_path)
        petsc_env.pop("PETSC_DIR", None)
        petsc_env.pop("PETSC_ARCH", None)
        if is_mpi_build():
            # PETSc's configure ignores CC/CXX/FX env (it warns and
            # auto-detects bare `mpicc` instead), so on multi-MPI
            # machines it silently configures the wrong MPI. Pin the
            # wrappers as configure args instead, which
            # update_and_rebuild_petsc.sh forwards to ./configure.
            mpi_compiler_args = [
                f"--with-cc={petsc_env['CC']}",
                f"--with-cxx={petsc_env['CXX']}",
                f"--with-fc={mpi_fortran_wrapper()}",
            ]
            subprocess.run(
                [
                    "./scripts/update_and_rebuild_petsc.sh",
                    "--skip-submodule-update",
                    "--CXXOPTFLAGS=-O3",
                    "--COPTFLAGS=-O3",
                    "--FOPTFLAGS=-O3",
                    *mpi_compiler_args,
                ],
                cwd=str(moose_dir),
                env=petsc_env,
                check=True,
            )
        else:
            _build_petsc_serial(
                moose_dir, zigcc_path, zigcxx_path, petsc_env
            )
    else:
        print("[OK] PETSc already built.")


def _build_petsc_serial(
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
    petsc_env: dict[str, str],
) -> None:
    """Configure and build serial (MPIUNI) PETSc directly.

    MOOSE's update_and_rebuild_petsc.sh hardcodes --with-mpi=1 plus
    MPI-only package downloads, so the serial stack configures PETSc
    directly instead (same approach as the Windows build): no Fortran,
    no MPI, shared libraries, minimal BLAS via f2cblaslapack.
    """
    print("--> Building serial PETSc (no MPI)...")
    petsc_dir = moose_dir / "petsc"
    env = dict(petsc_env)
    env["PETSC_DIR"] = str(petsc_dir)
    env["PETSC_ARCH"] = "arch-moose"
    jobs = os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4))
    subprocess.run(
        [
            "./configure",
            "PETSC_ARCH=arch-moose",
            f"--with-cc={zigcc_path}",
            f"--with-cxx={zigcxx_path}",
            "--with-fc=0",
            "--with-fortran-bindings=0",
            "--with-mpi=0",
            "--with-shared-libraries=1",
            "--with-debugging=no",
            # No X11 viewers in headless Rabbit solves; without this,
            # PETSc records an unresolvable -lX11 in its link line that
            # breaks every downstream libMesh/app link.
            "--with-x=0",
            "--download-f2cblaslapack=1",
        ],
        cwd=str(petsc_dir),
        env=env,
        check=True,
    )
    subprocess.run(
        [
            "make",
            f"PETSC_DIR={petsc_dir}",
            "PETSC_ARCH=arch-moose",
            "all",
            f"-j{jobs}",
        ],
        cwd=str(petsc_dir),
        env=env,
        check=True,
    )


def build_libmesh(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build libMesh dependency on Linux."""
    ensure_moose_repo(repo_dir, moose_dir)
    ensure_moose_submodules(moose_dir)
    check_build_tools()
    check_xdr_headers(zigcc_path)
    libmesh_lib = (
        moose_dir / "libmesh" / "installed" / "lib" / "libmesh_opt.so"
    )
    libmesh_a = (
        moose_dir / "libmesh" / "installed" / "lib" / "libmesh_opt.a"
    )
    if not (libmesh_lib.is_file() or libmesh_a.is_file()):
        print("--> Building libMesh with Zig toolchain...")
        libmesh_env = get_linux_tool_env(zigcc_path, zigcxx_path)
        libmesh_env["METHODS"] = "opt"
        # Serial PETSc has no Hypre, so the hard-coded
        # --enable-petsc-hypre-required in MOOSE's configure_libmesh.sh
        # must be overridden (later autoconf flags win). No --disable-mpi:
        # libMesh unconditionally drops PETSc under that flag, while
        # omitting it lets PETSc's MPIUNI stubs be detected and used
        # (same approach as the Windows serial build).
        mpi_args = (
            ["--with-mpi"]
            if is_mpi_build()
            else ["--disable-petsc-hypre-required"]
        )
        subprocess.run(
            ["./scripts/update_and_rebuild_libmesh.sh", *mpi_args],
            cwd=str(moose_dir),
            env=libmesh_env,
            check=True,
        )
    else:
        print("[OK] libMesh already built.")


def build_wasp(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build WASP and HIT parser on Linux."""
    ensure_moose_repo(repo_dir, moose_dir)
    ensure_moose_submodules(moose_dir)
    wasp_install = moose_dir / "framework" / "contrib" / "wasp" / "install"
    if not (wasp_install / "lib").is_dir():
        print("--> Building WASP parser...")
        tool_env = get_linux_tool_env(zigcc_path, zigcxx_path)
        subprocess.run(
            ["./scripts/update_and_rebuild_wasp.sh"],
            cwd=str(moose_dir),
            env=tool_env,
            check=True,
        )
    else:
        print("[OK] WASP parser already built.")


def build_conduit(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build Conduit I/O library on Linux (required by MFEM)."""
    ensure_moose_repo(repo_dir, moose_dir)
    ensure_moose_submodules(moose_dir)
    conduit_install = (
        moose_dir / "framework" / "contrib" / "conduit" / "installed"
    )
    if not (conduit_install / "lib").is_dir():
        print("--> Building Conduit...")
        tool_env = get_linux_tool_env(zigcc_path, zigcxx_path)
        subprocess.run(
            ["./scripts/update_and_rebuild_conduit.sh"],
            cwd=str(moose_dir),
            env=tool_env,
            check=True,
        )
    else:
        print("[OK] Conduit already built.")


def build_mfem(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build MFEM backend on Linux via MOOSE's installer script.

    Only the MPI variant is supported: upstream MOOSE's MFEM layer is
    written exclusively against parallel MFEM (``ParMesh`` and friends),
    so a serial MFEM cannot satisfy the framework compile.
    """
    ensure_moose_repo(repo_dir, moose_dir)
    ensure_moose_submodules(moose_dir)
    if not is_mpi_build():
        raise RuntimeError(
            "MFEM backend builds require the MPI variant (RABBIT_MPI=1); "
            "MOOSE has no serial-MFEM path."
        )
    mfem_lib_dir = (
        moose_dir / "framework" / "contrib" / "mfem" / "installed" / "lib"
    )
    # moose.mk links both -lmfem-opt and -lmfem-common-opt; both must
    # exist or the framework build fails, so both gate the short-circuit.
    if (mfem_lib_dir / "libmfem-opt.so").is_file() and (
        mfem_lib_dir / "libmfem-common-opt.so"
    ).is_file():
        print("[OK] MFEM already built.")
        return
    print("--> Building MFEM backend...")
    tool_env = get_linux_tool_env(zigcc_path, zigcxx_path)
    tool_env["METHODS"] = "opt"
    # MFEM's CMake runs find_package(MPI), whose Fortran leg needs an
    # MPI Fortran compiler (plain gfortran leaves MPI_Fortran_* empty
    # and the configure fails). CC/CXX already select the MPI C/C++
    # wrappers via get_linux_tool_env.
    tool_env["FC"] = mpi_fortran_wrapper()
    subprocess.run(
        ["./scripts/update_and_rebuild_mfem.sh"],
        cwd=str(moose_dir),
        env=tool_env,
        check=True,
    )


def check_cached_moose_config(moose_dir: Path) -> None:
    """Remove a stale cached MOOSE config whose MFEM flags disagree.

    Only MooseConfig.h is cached, never the generated conf_vars.mk that
    carries ENABLE_MFEM/MFEM_DIR (moose.mk includes MFEM via
    $(MFEM_DIR)/share/mfem/config.mk). If the cached header enables the
    MFEM backend but the flags file is missing or its MFEM_DIR holds no
    mfem.hpp, delete both so configure below re-runs fresh instead of
    failing deep in the framework build with 'mfem.hpp file not found'.
    Serial headers never define MOOSE_MFEM_ENABLED, so serial runs pass
    through untouched.
    """
    cfg = moose_dir / "framework" / "include" / "base" / "MooseConfig.h"
    if not cfg.is_file():
        return
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if "MOOSE_MFEM_ENABLED" not in text:
        return
    vars_mk = moose_dir / "conf_vars.mk"
    usable = False
    if vars_mk.is_file():
        try:
            vars_text = vars_mk.read_text(encoding="utf-8", errors="replace")
        except OSError:
            vars_text = ""
        for line in vars_text.splitlines():
            if line.startswith("MFEM_DIR"):
                _, _, value = line.partition(":=")
                mfem_dir = value.strip()
                usable = bool(mfem_dir) and (
                    Path(mfem_dir) / "include" / "mfem.hpp"
                ).is_file()
                break
    if not usable:
        print(
            "Cached MOOSE config enables MFEM without usable flags; "
            "removing to force a fresh configure..."
        )
        cfg.unlink()
        if vars_mk.is_file():
            vars_mk.unlink()


def configure_moose(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Configure MOOSE framework on Linux."""
    ensure_moose_repo(repo_dir, moose_dir)
    check_cached_moose_config(moose_dir)
    moose_cfg = (
        moose_dir / "framework" / "include" / "base" / "MooseConfig.h"
    )
    if not moose_cfg.is_file():
        print("--> Configuring MOOSE...")
        tool_env = get_linux_tool_env(zigcc_path, zigcxx_path)
        # The MFEM backend is MPI-only (upstream MOOSE has no serial
        # path); serial configures exactly as before.
        mfem_args = ["--with-mfem"] if is_mpi_build() else []
        subprocess.run(
            ["./configure", "--with-derivative-size=89", *mfem_args],
            cwd=str(moose_dir),
            env=tool_env,
            check=True,
        )
    else:
        print("[OK] MOOSE framework already configured.")
    ensure_serial_mpi_fallback(moose_dir)


def build_linux_dependencies(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Build all MOOSE dependencies sequentially on Linux."""
    jobs = os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4))
    print("=" * 60)
    print(f" Setting up MOOSE and dependencies (Linux) at: {moose_dir}")
    print(f" Parallel jobs: {jobs}")
    print("=" * 60)

    build_petsc(repo_dir, moose_dir, zigcc_path, zigcxx_path)
    build_libmesh(repo_dir, moose_dir, zigcc_path, zigcxx_path)
    # Conduit/MFEM serve the MPI-only MFEM backend; the serial order is
    # unchanged.
    if is_mpi_build():
        build_conduit(repo_dir, moose_dir, zigcc_path, zigcxx_path)
    build_wasp(repo_dir, moose_dir, zigcc_path, zigcxx_path)
    if is_mpi_build():
        build_mfem(repo_dir, moose_dir, zigcc_path, zigcxx_path)
    configure_moose(repo_dir, moose_dir, zigcc_path, zigcxx_path)

    print("=" * 60)
    print(" MOOSE Linux dependencies built and configured successfully!")
    print("=" * 60)
