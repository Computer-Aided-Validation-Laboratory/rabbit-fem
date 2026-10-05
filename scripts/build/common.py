"""Common build, staging, packaging, and test routines for rabbit-fem."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def find_python_exe() -> str:
    """Return the current python executable path."""
    return sys.executable


def is_mpi_build() -> bool:
    """Whether the MPI (multi-rank) variant is being built.

    Selected by the ``RABBIT_MPI`` environment variable (``"1"`` for the
    ``rabbit-fem-mpi`` wheel) or the ``--mpi`` / ``--no-mpi`` flags of
    ``build_rabbit.py``, which set it. The default is the serial/SMP
    ``rabbit-fem`` wheel, which needs no system MPI installation.
    """
    return os.environ.get("RABBIT_MPI", "0") == "1"


def get_moose_dir(
    repo_dir: Path, custom_path: str | None = None
) -> Path:
    """Locate MOOSE directory from argument, local repo, env, or home."""
    if custom_path:
        return Path(custom_path).expanduser().resolve()

    local_moose = repo_dir / "moose"
    if local_moose.is_dir() and (local_moose / "framework").is_dir():
        return local_moose.resolve()

    env_dir = os.environ.get("MOOSE_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()

    return (repo_dir / "moose").resolve()


def get_pinned_moose_version(repo_dir: Path) -> str:
    """Read pinned MOOSE commit hash from moose_version.txt.

    The pin tracks the MOOSE master branch at a fixed commit for stability;
    see moose_deps.txt for the corresponding dependency commits.
    """
    version_file = repo_dir / "moose_version.txt"
    if version_file.is_file():
        commit = version_file.read_text(encoding="utf-8").strip()
        if commit:
            return commit
    return "975c9a1ca693c21bef850b7beba724e0fb703591"


_MOOSE_DEP_SUBMODULES = {
    "petsc": "petsc",
    "libmesh": "libmesh",
    "wasp": "framework/contrib/wasp",
    "mfem": "framework/contrib/mfem",
    "conduit": "framework/contrib/conduit",
}

# Submodules only the MPI variant (MFEM backend) needs. The serial
# `rabbit-fem` wheel never compiles against them, so serial builds must
# not fetch or verify them: a serial run should stay green when an
# MFEM/Conduit pin or submodule breaks, and vice versa. Variant
# isolation is via `is_mpi_build()` (RABBIT_MPI=1); CI additionally
# isolates via separate runners and `-serial`/`-mpi` cache keys.
_MPI_ONLY_MOOSE_DEPS = frozenset({"mfem", "conduit"})


def get_pinned_moose_deps(repo_dir: Path) -> dict[str, str]:
    """Read pinned MOOSE dependency commits from moose_deps.txt."""
    deps: dict[str, str] = {}
    deps_file = repo_dir / "moose_deps.txt"
    if not deps_file.is_file():
        return deps
    for line in deps_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 2:
            deps[parts[0]] = parts[1]
    return deps


def verify_moose_deps(moose_dir: Path, repo_dir: Path) -> None:
    """Fail early if materialized submodules differ from pinned commits.

    Submodules that are not checked out yet are skipped; materializing them
    is the responsibility of the submodule ensure steps. Submodules whose
    git metadata is unavailable (e.g. cache-restored trees with dangling
    gitlinks) cannot be verified and only produce a warning. Anything
    verifiable must match moose_deps.txt exactly so dependency drift
    surfaces here instead of as confusing downstream build failures.
    """
    deps = get_pinned_moose_deps(repo_dir)
    if not deps:
        return
    mpi = is_mpi_build()
    for name, rel_path in _MOOSE_DEP_SUBMODULES.items():
        if name in _MPI_ONLY_MOOSE_DEPS and not mpi:
            continue
        expected = deps.get(name)
        if not expected:
            continue
        sub_dir = moose_dir / rel_path
        if not (sub_dir / ".git").exists():
            continue
        res = subprocess.run(
            ["git", "-C", str(sub_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            print(
                f"WARNING: cannot verify checked-out commit of MOOSE "
                f"dependency '{name}' in {sub_dir} "
                f"(git metadata unavailable); skipping pin check."
            )
            continue
        actual = res.stdout.strip()
        if actual != expected:
            raise RuntimeError(
                f"MOOSE dependency '{name}' is at {actual} but "
                f"moose_deps.txt pins {expected}. Update the pin files "
                f"or re-materialize submodules at the pinned commits."
            )


def ensure_moose_repo(repo_dir: Path, moose_dir: Path) -> None:
    """Ensure the MOOSE repository framework files exist at pinned commit."""
    target_commit = get_pinned_moose_version(repo_dir)
    framework_mk = moose_dir / "framework" / "build.mk"
    if framework_mk.is_file():
        return

    print(
        f"Ensuring MOOSE repository at {moose_dir} "
        f"(pinned to {target_commit[:10]})..."
    )
    if not moose_dir.is_dir():
        moose_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=str(moose_dir),
            check=True,
        )
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://github.com/idaholab/moose.git",
            ],
            cwd=str(moose_dir),
            check=True,
        )
        subprocess.run(
            [
                "git",
                "fetch",
                "--depth",
                "1",
                "origin",
                target_commit,
            ],
            cwd=str(moose_dir),
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "FETCH_HEAD"],
            cwd=str(moose_dir),
            check=True,
        )
    else:
        # Directory exists from cache; fetch framework and overlay
        temp_clone = repo_dir / ".moose_framework_tmp"
        if temp_clone.exists():
            shutil.rmtree(temp_clone, ignore_errors=True)
        temp_clone.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "init"],
                cwd=str(temp_clone),
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/idaholab/moose.git",
                ],
                cwd=str(temp_clone),
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "fetch",
                    "--depth",
                    "1",
                    "origin",
                    target_commit,
                ],
                cwd=str(temp_clone),
                check=True,
            )
            subprocess.run(
                ["git", "checkout", "FETCH_HEAD"],
                cwd=str(temp_clone),
                check=True,
            )
            for item in temp_clone.iterdir():
                dest = moose_dir / item.name
                if item.is_dir():
                    if item.name in ("petsc", "libmesh") and dest.is_dir():
                        continue
                    shutil.copytree(
                        item,
                        dest,
                        symlinks=True,
                        ignore_dangling_symlinks=True,
                        dirs_exist_ok=True,
                    )
                else:
                    shutil.copy2(item, dest, follow_symlinks=False)
            # Ensure .git is also present in moose_dir
            git_src = temp_clone / ".git"
            git_dst = moose_dir / ".git"
            if git_src.exists() and not git_dst.exists():
                shutil.copytree(
                    git_src,
                    git_dst,
                    symlinks=True,
                    ignore_dangling_symlinks=True,
                    dirs_exist_ok=True,
                )
        finally:
            if temp_clone.exists():
                shutil.rmtree(temp_clone, ignore_errors=True)


def is_petsc_ready(moose_dir: Path) -> bool:
    """Check if PETSc source or build is present."""
    petsc_dir = moose_dir / "petsc"
    return (
        (petsc_dir / "include" / "petsc.h").is_file()
        or (petsc_dir / "configure").is_file()
        or (petsc_dir / "arch-linux" / "lib" / "libpetsc.so").is_file()
        or (petsc_dir / "arch-darwin-opt" / "lib" / "libpetsc.dylib").is_file()
        or (petsc_dir / "arch-windows-opt" / "lib" / "libpetsc.a").is_file()
    )


def is_libmesh_ready(moose_dir: Path) -> bool:
    """Check if libMesh source or build is present."""
    libmesh_dir = moose_dir / "libmesh"
    return (
        (
            libmesh_dir / "installed" / "include" / "libmesh" / "libmesh.h"
        ).is_file()
        or (libmesh_dir / "contrib" / "timpi" / "README").is_file()
    )


def is_wasp_ready(moose_dir: Path) -> bool:
    """Check if WASP source or build is present."""
    wasp_dir = moose_dir / "framework" / "contrib" / "wasp"
    return (
        (wasp_dir / "install" / "lib").is_dir()
        or (wasp_dir / "install" / "include").is_dir()
        or (wasp_dir / "CMakeLists.txt").is_file()
    )


def is_conduit_ready(moose_dir: Path) -> bool:
    """Check if Conduit source or build is present."""
    conduit_dir = moose_dir / "framework" / "contrib" / "conduit"
    return (
        (conduit_dir / "installed" / "lib").is_dir()
        or (conduit_dir / "installed" / "include").is_dir()
        or (conduit_dir / "src" / "CMakeLists.txt").is_file()
        or (conduit_dir / "CMakeLists.txt").is_file()
    )


def is_mfem_ready(moose_dir: Path) -> bool:
    """Check if MFEM source or build is present."""
    mfem_dir = moose_dir / "framework" / "contrib" / "mfem"
    return (
        (mfem_dir / "installed" / "lib").is_dir()
        or (mfem_dir / "installed" / "include").is_dir()
        or (mfem_dir / "CMakeLists.txt").is_file()
    )


def ensure_moose_submodules(moose_dir: Path) -> None:
    """Check and initialize missing MOOSE git submodules.

    Only the MPI variant materializes the Conduit/MFEM submodules (the
    MFEM backend is MPI-only); serial builds fetch just
    petsc/libmesh/wasp so MFEM-side breakage cannot red a serial run.
    """
    needed: list[str] = []
    if not is_petsc_ready(moose_dir):
        needed.append("petsc")
    if not is_libmesh_ready(moose_dir):
        needed.append("libmesh")
    if not is_wasp_ready(moose_dir):
        needed.append("framework/contrib/wasp")
    if is_mpi_build():
        if not is_conduit_ready(moose_dir):
            needed.append("framework/contrib/conduit")
        if not is_mfem_ready(moose_dir):
            needed.append("framework/contrib/mfem")

    if not needed:
        print("All MOOSE submodules/dependencies are present.")
        return

    print(f"Initializing missing MOOSE git submodules: {needed}...")
    subprocess.run(
        ["git", "submodule", "sync", "--recursive"] + needed,
        cwd=str(moose_dir),
        check=False,
    )
    subprocess.run(
        ["git", "submodule", "init"] + needed,
        cwd=str(moose_dir),
        check=False,
    )
    for sub in needed:
        sub_path = moose_dir / sub
        if sub_path.is_dir() and not (sub_path / ".git").exists():
            shutil.rmtree(sub_path, ignore_errors=True)

    submodule_cmd = [
        "git",
        "submodule",
        "update",
        "--init",
        "--recursive",
        # framework/contrib/mfem and framework/contrib/conduit set
        # `update = none` in .gitmodules, which makes a plain update
        # print "Skipping submodule ..." even for explicitly listed
        # paths. An explicit --checkout overrides that default, matching
        # what MOOSE's own update_and_rebuild_{mfem,conduit}.sh scripts
        # pass. For other submodules this is the default strategy.
        "--checkout",
    ] + needed
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            subprocess.run(
                submodule_cmd, cwd=str(moose_dir), check=True
            )
            break
        except subprocess.CalledProcessError:
            if attempt == max_attempts:
                raise
            print(
                f"Submodule checkout failed (attempt {attempt}/"
                f"{max_attempts}). Waiting 30s before retry "
                "(GitLab load/rate limit backoff)..."
            )
            time.sleep(30)


def mpi_impl() -> str:
    """Which MPI implementation the MPI variant builds against.

    ``openmpi`` (default) or ``mpich``, selected by ``RABBIT_MPI_IMPL``.
    Only meaningful when :func:`is_mpi_build` is true; the serial build
    never consults it. Explicit suffixed wrapper names
    (``mpicc.mpich``) keep the selection immune to the machine's
    update-alternatives state.
    """
    impl = os.environ.get("RABBIT_MPI_IMPL", "openmpi").strip().lower()
    if impl not in ("openmpi", "mpich"):
        raise RuntimeError(
            f"Unknown MPI implementation {impl!r} in RABBIT_MPI_IMPL; "
            'expected "openmpi" or "mpich".'
        )
    return impl


def mpi_compiler_env(
    zigcc_path: Path, zigcxx_path: Path
) -> dict[str, str]:
    """Compiler selection for MPI builds, by implementation.

    OpenMPI wrappers read ``OMPI_CC``/``OMPI_CXX``; MPICH wrappers read
    ``MPICH_CC``/``MPICH_CXX`` (both documented wrapper variables).
    MPICH names are explicitly suffixed so a machine with both runtimes
    still resolves deterministically.
    """
    if mpi_impl() == "mpich":
        return {
            "MPICH_CC": str(zigcc_path),
            "MPICH_CXX": str(zigcxx_path),
            "CC": "mpicc.mpich",
            "CXX": "mpicxx.mpich",
        }
    return {
        "OMPI_CC": str(zigcc_path),
        "OMPI_CXX": str(zigcxx_path),
        "CC": "mpicc",
        "CXX": "mpicxx",
    }


def mpi_fortran_wrapper() -> str:
    """MPI Fortran wrapper for the selected implementation."""
    if is_mpi_build() and mpi_impl() == "mpich":
        return "mpif90.mpich"
    return "mpif90"


def build_rabbit_binary(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> Path:
    """Compile RabbitApp and link rabbit-opt."""
    ensure_moose_repo(repo_dir, moose_dir)
    if not (moose_dir / "framework" / "build.mk").is_file():
        raise FileNotFoundError(
            f"MOOSE framework not found in {moose_dir}."
        )
    if not is_mpi_build() and sys.platform != "win32":
        # Windows patching (including serial fallbacks) is owned by
        # install_dependencies_windows.ps1, which applies unconditionally.
        apply_serial_patches(moose_dir, repo_dir)

    env = dict(os.environ)
    env["PATH"] = f"{repo_dir / '.venv' / 'bin'}:{env.get('PATH', '')}"
    env["PYTHONNOUSERSITE"] = "1"
    env["MOOSE_DIR"] = str(moose_dir)
    env["METHODS"] = "opt"
    if is_mpi_build():
        env.update(mpi_compiler_env(zigcc_path, zigcxx_path))
    else:
        env["CC"] = str(zigcc_path)
        env["CXX"] = str(zigcxx_path)

    jobs = os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4))
    cmd = ["make", f"-j{jobs}"]

    print(f"Building RabbitApp with MOOSE_DIR={moose_dir} ({jobs} jobs)...")
    subprocess.run(cmd, cwd=str(repo_dir), env=env, check=True)

    output_bin = repo_dir / "rabbit-opt"
    if not output_bin.is_file():
        raise FileNotFoundError(
            f"Expected binary {output_bin} was not built."
        )
    return output_bin


def find_needed_libraries(
    binary_path: Path,
    available_libs: dict[str, Path],
) -> tuple[dict[str, Path], set[str]]:
    """Find all needed sonames and map them to their concrete file paths."""
    resolved_libs: dict[str, Path] = {}
    unresolved_libs: set[str] = set()
    queue: list[Path] = [binary_path]
    visited_binaries: set[Path] = set()

    system_prefixes = (
        "libc.so",
        "libm.so",
        "libdl.so",
        "libpthread.so",
        "librt.so",
        "libstdc++.so",
        "libgcc_s.so",
        "ld-linux",
        "libmpi.so",
        "libmpi_",
        "libmpi_cxx.so",
        "libopen-pal.so",
        "libopen-rte.so",
        "libhwloc.so",
        "libevent",
        "libz.so",
        "libtirpc.so",
        "libgfortran.so",
        "libquadmath.so",
        "libgomp.so",
        "liblzma.so",
        "libsz.so",
        "libX11.so",
        "libXau.so",
        "libXdmcp.so",
        "libxcb.so",
        "libbsd.so",
        "libmd.so",
        "libudev.so",
        "libkrb5",
        "libk5crypto",
        "libcom_err",
        "libcap.so",
        "libkeyutils",
        "libresolv.so",
        "libgssapi_krb5",
    )

    while queue:
        current = queue.pop(0)
        if current in visited_binaries:
            continue
        visited_binaries.add(current)

        try:
            if sys.platform == "darwin":
                cmd = ["otool", "-L", str(current)]
                res = subprocess.run(
                    cmd, capture_output=True, text=True, check=True
                )
                for line in res.stdout.splitlines():
                    line = line.strip()
                    if not line or line.endswith(":"):
                        continue
                    dep = line.split()[0]
                    if dep.startswith(
                        ("/usr/lib/", "/System/Library/", "@loader_path")
                    ):
                        continue
                    soname = Path(dep).name
                    if soname not in resolved_libs:
                        if soname in available_libs:
                            real_path = available_libs[soname].resolve()
                            resolved_libs[soname] = real_path
                            queue.append(real_path)
                        else:
                            unresolved_libs.add(soname)
            else:
                cmd = ["readelf", "-d", str(current)]
                res = subprocess.run(
                    cmd, capture_output=True, text=True, check=True
                )
                for line in res.stdout.splitlines():
                    if "NEEDED" not in line:
                        continue
                    match = re.search(r"\[(.*)\]", line)
                    if not match:
                        continue
                    soname = match.group(1)
                    if soname.startswith(system_prefixes):
                        continue

                    if soname not in resolved_libs:
                        if soname in available_libs:
                            real_path = available_libs[soname].resolve()
                            resolved_libs[soname] = real_path
                            queue.append(real_path)
                        else:
                            unresolved_libs.add(soname)
        except Exception:
            pass

    return resolved_libs, unresolved_libs


def elf_library_search_dirs(binary_path: Path) -> list[Path]:
    """Return absolute directories recorded in an ELF RPATH/RUNPATH."""
    try:
        result = subprocess.run(
            ["readelf", "-d", str(binary_path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    search_dirs: list[Path] = []
    for line in result.stdout.splitlines():
        if "(RPATH)" not in line and "(RUNPATH)" not in line:
            continue
        match = re.search(r"\[(.*)\]", line)
        if not match:
            continue
        for entry in match.group(1).split(":"):
            path = Path(entry)
            if path.is_absolute() and path.is_dir() and path not in search_dirs:
                search_dirs.append(path)
    return search_dirs


_SYSTEM_OPENMP_PATTERNS = (
    "/usr/lib/x86_64-linux-gnu/libomp.so*",
    "/usr/lib/llvm-*/lib/libomp.so*",
    "/opt/rocm-*/lib/llvm/lib/libomp.so*",
    "/opt/rocm-*/lib/llvm/lib-debug/libomp.so*",
)

# Homebrew runtime libraries. The macOS linker records absolute build
# paths (e.g. /opt/homebrew/opt/llvm/lib/libomp.dylib), which do not
# exist on clean user machines, so the wheel must bundle them exactly
# like Linux bundles libomp.so.5. Each entry is an explicit allowlist
# decision: the serial build must stay fully self-contained, so every
# absolute Homebrew reference gets staged rather than left for dyld.
_DARWIN_HOMEBREW_RUNTIME_PATTERNS = (
    "/opt/homebrew/opt/llvm/lib/libomp.dylib",
    "/opt/homebrew/opt/libomp/lib/libomp.dylib",
    "/usr/local/opt/llvm/lib/libomp.dylib",
    "/usr/local/opt/libomp/lib/libomp.dylib",
    "/opt/homebrew/opt/libpng/lib/libpng16*.dylib",
    "/usr/local/opt/libpng/lib/libpng16*.dylib",
)


def index_system_openmp_libs(
    available_libs: dict[str, Path],
    patterns: tuple[str, ...] | None = None,
) -> None:
    """Index system OpenMP runtimes by filename for wheel staging.

    The OpenMP runtime (e.g. libomp.so.5 from libomp-dev, libomp.dylib
    from Homebrew llvm/libomp) lives outside the repository, so its
    NEEDED entry cannot resolve from the source trees or the binary
    RPATH. Record canonical locations keyed by exact filename so
    resolution matches the binary's SONAME. Existing repository entries
    take precedence and are never overridden. An explicit ``patterns``
    argument overrides the platform default (used by tests to avoid
    touching real system paths).
    """
    import glob

    if patterns is None:
        patterns = (
            _DARWIN_HOMEBREW_RUNTIME_PATTERNS
            if sys.platform == "darwin"
            else _SYSTEM_OPENMP_PATTERNS
        )
    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            path = Path(candidate)
            if path.is_file() and path.name not in available_libs:
                available_libs[path.name] = path


_SERIAL_MPI_FALLBACK_MARKER = "Rabbit serial/SMP build"


def ensure_serial_mpi_fallback(moose_dir: Path) -> None:
    """Provide MPI_Comm fallback types for serial MOOSE builds.

    ``Moose.h`` uses ``MPI_Comm`` without a guard while PETSc MPIUNI's
    ``mpi.h`` is not on the include path, so serial compiles fail with
    ``unknown type name 'MPI_Comm'``. Append the same fallback the
    Windows port uses to the generated ``MooseConfig.h`` (reached via
    ``MooseDefaultConfig.h``). Idempotent: skipped once applied, so
    re-running configure or builds never duplicates it. Serial builds
    only; MPI builds must never see this.
    """
    if is_mpi_build():
        return
    moose_cfg = moose_dir / "framework" / "include" / "base" / "MooseConfig.h"
    if not moose_cfg.is_file():
        raise FileNotFoundError(
            f"MOOSE is not configured in {moose_dir}; cannot apply the "
            "serial MPI fallback."
        )
    content = moose_cfg.read_text(encoding="utf-8")
    if _SERIAL_MPI_FALLBACK_MARKER in content:
        return
    moose_cfg.write_text(
        content
        + (
            "\n/* Rabbit serial/SMP build (no MPI): Moose.h uses MPI_Comm\n"
            "   without a guard while PETSc MPIUNI's mpi.h is not on the\n"
            "   include path. Same fallback as the Windows port. */\n"
            "#ifndef LIBMESH_HAVE_MPI\n"
            "typedef int MPI_Comm;\n"
            "#ifndef MPI_COMM_WORLD\n"
            "#define MPI_COMM_WORLD 0\n"
            "#endif\n"
            "#endif\n"
        ),
        encoding="utf-8",
    )
    print(f"Applied serial MPI fallback to {moose_cfg}")


def apply_serial_patches(moose_dir: Path, repo_dir: Path) -> None:
    """Apply serial-build portability patches to MOOSE sources.

    Serial (MPIUNI) builds hit upstream code paths that assume MPI is
    present (e.g. unguarded ``#include <mpi.h>``); each is guarded on
    ``LIBMESH_HAVE_MPI`` instead, mirroring the Windows port approach.
    Idempotent: already-applied patches are skipped, genuine failures
    raise. Serial builds only; shared by all OSes because the guarded
    code is MPI-conditional, not OS-conditional.
    """
    patch_file = repo_dir / "patches" / "serial" / "moose.patch"
    if not patch_file.is_file():
        return
    patch_bin = shutil.which("patch")
    if patch_bin is None:
        raise RuntimeError(
            "Cannot apply serial MOOSE patches: the 'patch' utility was "
            "not found on PATH."
        )
    proc = subprocess.run(
        [patch_bin, "-p1", "-N", "-r", "-", "-i", str(patch_file)],
        cwd=str(moose_dir),
        capture_output=True,
        text=True,
    )
    if proc.returncode in (0, 1):
        applied = "applied" if proc.returncode == 0 else "already applied"
        print(f"Serial MOOSE patch {applied}.")
    else:
        raise RuntimeError(
            f"Applying serial MOOSE patch failed:\n{proc.stdout}\n{proc.stderr}"
        )


def stage_moose_data(repo_dir: Path, moose_dir: Path) -> None:
    """Stage MOOSE runtime data files into src/rabbit/share.

    MOOSE resolves data files from ``<exe>/../share/<name>/data``,
    falling back to absolute in-tree paths baked in at compile time that
    do not exist on user machines. A wheel without these files fails at
    startup with "Failed to determine data file path".
    """
    share_target_dir = repo_dir / "src" / "rabbit" / "share"
    for app_name, data_src in (
        ("moose", moose_dir / "framework" / "data"),
        (
            "solid_mechanics",
            moose_dir / "modules" / "solid_mechanics" / "data",
        ),
    ):
        if not data_src.is_dir():
            raise FileNotFoundError(
                "Cannot create a standalone wheel; MOOSE data directory "
                f"missing: {data_src}"
            )
        data_dest = share_target_dir / app_name / "data"
        if data_dest.is_dir():
            shutil.rmtree(data_dest)
        shutil.copytree(data_src, data_dest)

    # Record which binary variant was staged so the runtime CLI can adapt
    # (preconditioner defaults, multi-rank misuse guard). Read by
    # rabbit.cli.is_mpi_binary(); wheels built before this marker fall back
    # to platform inference there.
    variant_marker = repo_dir / "src" / "rabbit" / "variant.txt"
    variant_marker.write_text(
        "mpi\n" if is_mpi_build() else "serial\n", encoding="utf-8"
    )


def stage_artifacts(
    repo_dir: Path,
    moose_dir: Path,
    binary_path: Path,
) -> None:
    """Stage executable and minimal shared libraries into src/rabbit."""
    bin_target_dir = repo_dir / "src" / "rabbit" / "bin"
    lib_target_dir = repo_dir / "src" / "rabbit" / "lib"

    if lib_target_dir.is_dir():
        shutil.rmtree(lib_target_dir)
    lib_target_dir.mkdir(parents=True, exist_ok=True)
    bin_target_dir.mkdir(parents=True, exist_ok=True)

    dest_bin = bin_target_dir / "rabbit"
    shutil.copy2(binary_path, dest_bin)
    dest_bin.chmod(0o755)

    available_libs: dict[str, Path] = {}
    lib_glob = "*.dylib*" if sys.platform == "darwin" else "*.so*"
    for search_root in [repo_dir, moose_dir]:
        for p in search_root.rglob(lib_glob):
            if p.is_file() and not p.name.endswith((".son", ".i")):
                available_libs[p.name] = p

    # PETSc and other third-party libraries may live outside the source trees.
    # Include the binary's recorded linker search paths so the staged closure
    # reflects what the linker used, rather than only what happens to be under
    # the repository checkout.
    if sys.platform != "darwin":
        for search_dir in elf_library_search_dirs(binary_path):
            for p in search_dir.glob(lib_glob):
                if p.is_file():
                    available_libs[p.name] = p

    # The OpenMP runtime is a documented system dependency that lives
    # outside the source trees. Index it before resolution so its SONAME
    # (e.g. libomp.so.5) resolves instead of aborting the wheel staging.
    index_system_openmp_libs(available_libs)

    resolved_libs, unresolved_libs = find_needed_libraries(
        binary_path, available_libs
    )
    if unresolved_libs:
        missing = ", ".join(sorted(unresolved_libs))
        raise FileNotFoundError(
            "Cannot create a standalone wheel; required shared libraries "
            f"were not found: {missing}"
        )

    for soname, real_path in resolved_libs.items():
        dest = lib_target_dir / soname
        shutil.copy2(real_path, dest)

    stage_moose_data(repo_dir, moose_dir)

    print("Stripping debug symbols from libraries and executable...")
    if sys.platform == "darwin":
        subprocess.run(["strip", "-x", str(dest_bin)], check=False)
        for f in lib_target_dir.glob("*.dylib*"):
            if f.is_file():
                subprocess.run(["strip", "-x", str(f)], check=False)

        # The linker records absolute build paths in Mach-O load
        # commands; rewrite staged IDs/references/RPATHs to @rpath form
        # so the shipped tree resolves via its @loader_path RPATHs.
        from .darwin import relink_darwin_staged_artifacts

        relink_darwin_staged_artifacts(dest_bin, lib_target_dir)
    else:
        subprocess.run(["strip", "--strip-all", str(dest_bin)], check=False)
        for f in lib_target_dir.glob("*.so*"):
            if f.is_file():
                subprocess.run(
                    ["strip", "--strip-unneeded", str(f)], check=False
                )

        patchelf_bin = "patchelf"
        for cand in (
            shutil.which("patchelf"),
            Path(sys.prefix) / "bin" / "patchelf",
            repo_dir / ".venv" / "bin" / "patchelf",
        ):
            if cand and Path(cand).is_file():
                patchelf_bin = str(cand)
                break

        rpath_app = "$ORIGIN/../lib:/usr/lib/x86_64-linux-gnu/openmpi/lib"
        rpath_lib = "$ORIGIN:/usr/lib/x86_64-linux-gnu/openmpi/lib"

        subprocess.run(
            [patchelf_bin, "--set-rpath", rpath_app, str(dest_bin)],
            check=True,
        )
        for f in lib_target_dir.glob("*.so*"):
            if f.is_file():
                subprocess.run(
                    [patchelf_bin, "--set-rpath", rpath_lib, str(f)],
                    check=True,
                )

    print(
        f"Staged rabbit binary and {len(resolved_libs)} libraries "
        f"at {dest_bin}"
    )


def build_wheel(repo_dir: Path) -> Path:
    """Build standalone Python wheel package and tag appropriately.

    MPI variants are published under their own project names
    (``rabbit-fem-mpi`` for OpenMPI, ``rabbit-fem-mpich`` for MPICH);
    the default serial/SMP build keeps ``rabbit-fem``.
    """
    print("--> Building standalone wheel package...")
    pyproject_file = repo_dir / "pyproject.toml"
    original_pyproject = pyproject_file.read_text(encoding="utf-8")
    renamed = False
    if is_mpi_build():
        dist_name = (
            "rabbit-fem-mpich" if mpi_impl() == "mpich" else "rabbit-fem-mpi"
        )
        renamed_text = original_pyproject.replace(
            'name = "rabbit-fem"', f'name = "{dist_name}"', 1
        )
        if renamed_text == original_pyproject:
            raise RuntimeError(
                "Cannot build MPI wheel: project name not found in "
                f"{pyproject_file}."
            )
        pyproject_file.write_text(renamed_text, encoding="utf-8")
        renamed = True
    try:
        return _build_wheel_inner(repo_dir)
    finally:
        if renamed:
            pyproject_file.write_text(original_pyproject, encoding="utf-8")


def _build_wheel_inner(repo_dir: Path) -> Path:
    """Run the hatch build and retag the wheel for the host platform."""
    uv_bin = shutil.which("uv")
    if uv_bin:
        cmd = ["uv", "build", "--wheel"]
    else:
        cmd = [find_python_exe(), "-m", "build", "--wheel"]

    subprocess.run(cmd, cwd=str(repo_dir), check=True)
    dist_dir = repo_dir / "dist"
    wheels = sorted(dist_dir.glob("*.whl"), key=os.path.getmtime)
    if not wheels:
        raise FileNotFoundError("No .whl package generated in dist/")
    raw_whl = wheels[-1]

    # Retag from py3-none-any to platform tag
    if "none-any" in raw_whl.name:
        if sys.platform == "win32":
            platform_tag = "win_amd64"
            wheel_bin = shutil.which("wheel") or str(
                repo_dir / ".venv" / "Scripts" / "wheel.exe"
            )
        elif sys.platform == "darwin":
            import platform
            arch = platform.machine()
            if arch == "arm64":
                platform_tag = "macosx_14_0_arm64"
            else:
                platform_tag = "macosx_13_0_x86_64"
            wheel_bin = shutil.which("wheel") or str(
                repo_dir / ".venv" / "bin" / "wheel"
            )
        else:
            # A wheel can contain compressed (dot-separated) platform tags,
            # but each one is a separate compatibility promise.  Do not add
            # the host ``linux_x86_64`` tag or a second manylinux baseline:
            # they make the filename misleading and can cause PyPI installers
            # to select the wheel on unsupported systems.
            #
            # The Linux build is produced against glibc 2.38, so publish the
            # one corresponding PEP 600 platform tag.
            platform_tag = "manylinux_2_38_x86_64"
            wheel_bin = shutil.which("wheel") or str(
                repo_dir / ".venv" / "bin" / "wheel"
            )
        wheel_cmd = (
            [wheel_bin]
            if (shutil.which(wheel_bin) or Path(wheel_bin).is_file())
            else [find_python_exe(), "-m", "wheel"]
        )
        # ``wheel tags --remove`` removes only ``raw_whl``.  Clear earlier
        # platform variants for this exact release so a subsequent upload does
        # not accidentally pick up an obsolete compatibility declaration.
        release_prefix = raw_whl.name.removesuffix("-py3-none-any.whl")
        for existing_whl in dist_dir.glob(f"{release_prefix}-*.whl"):
            if existing_whl != raw_whl:
                existing_whl.unlink()
        print(f"--> Retagging wheel for platform: {platform_tag}")
        subprocess.run(
            wheel_cmd
            + [
                "tags",
                f"--platform-tag={platform_tag}",
                "--remove",
                str(raw_whl),
            ],
            check=True,
        )
        latest_whl = raw_whl.with_name(
            raw_whl.name.replace("none-any", f"none-{platform_tag}")
        )
        if not latest_whl.is_file():
            raise FileNotFoundError(
                "Retagged wheel was not generated: " f"{latest_whl}"
            )
    else:
        latest_whl = raw_whl

    size_mb = latest_whl.stat().st_size / (1024 * 1024)
    print(f"Wheel package ready: {latest_whl.name} ({size_mb:.2f} MB)")
    return latest_whl


def run_tests(repo_dir: Path) -> None:
    """Run pytest suite against staged package."""
    print("--> Running pytest suite...")
    subprocess.run(
        [find_python_exe(), "-m", "pytest", "test/", "-v"],
        cwd=str(repo_dir),
        check=True,
    )
