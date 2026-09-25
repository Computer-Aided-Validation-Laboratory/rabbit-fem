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
    """Read pinned MOOSE commit hash from moose_version.txt."""
    version_file = repo_dir / "moose_version.txt"
    if version_file.is_file():
        commit = version_file.read_text(encoding="utf-8").strip()
        if commit:
            return commit
    return "73c6aa53af67b8046f7ace5fd1c96846d5d6641d"


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


def ensure_moose_submodules(moose_dir: Path) -> None:
    """Check and initialize missing MOOSE git submodules."""
    needed: list[str] = []
    if not is_petsc_ready(moose_dir):
        needed.append("petsc")
    if not is_libmesh_ready(moose_dir):
        needed.append("libmesh")
    if not is_wasp_ready(moose_dir):
        needed.append("framework/contrib/wasp")

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

    env = dict(os.environ)
    env["PATH"] = f"{repo_dir / '.venv' / 'bin'}:{env.get('PATH', '')}"
    env["PYTHONNOUSERSITE"] = "1"
    env["MOOSE_DIR"] = str(moose_dir)
    env["METHODS"] = "opt"
    env["OMPI_CC"] = str(zigcc_path)
    env["OMPI_CXX"] = str(zigcxx_path)
    env["CC"] = "mpicc"
    env["CXX"] = "mpicxx"

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

    resolved_libs, unresolved_libs = find_needed_libraries(
        binary_path, available_libs
    )
    if unresolved_libs:
        missing = ", ".join(sorted(unresolved_libs))
        raise FileNotFoundError(
            "Cannot create a standalone wheel; required shared libraries "
            f"were not found: {missing}"
        )

    if sys.platform != "darwin":
        import glob
        omp_candidates = (
            glob.glob("/opt/rocm-*/lib/llvm/lib-debug/libomp.so")
            + glob.glob("/opt/rocm-*/lib/llvm/lib/libomp.so")
            + glob.glob("/usr/lib/llvm-*/lib/libomp.so")
            + glob.glob("/usr/lib/x86_64-linux-gnu/libomp.so*")
        )
        if omp_candidates and "libomp.so" not in resolved_libs:
            resolved_libs["libomp.so"] = Path(omp_candidates[-1]).resolve()

    for soname, real_path in resolved_libs.items():
        dest = lib_target_dir / soname
        shutil.copy2(real_path, dest)

    print("Stripping debug symbols from libraries and executable...")
    if sys.platform == "darwin":
        subprocess.run(["strip", "-x", str(dest_bin)], check=False)
        for f in lib_target_dir.glob("*.dylib*"):
            if f.is_file():
                subprocess.run(["strip", "-x", str(f)], check=False)

        subprocess.run(
            [
                "install_name_tool",
                "-add_rpath",
                "@loader_path/../lib",
                str(dest_bin),
            ],
            check=False,
        )
        for f in lib_target_dir.glob("*.dylib*"):
            if f.is_file():
                subprocess.run(
                    [
                        "install_name_tool",
                        "-add_rpath",
                        "@loader_path",
                        str(f),
                    ],
                    check=False,
                )
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
    """Build standalone Python wheel package and tag appropriately."""
    print("--> Building standalone wheel package...")
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
        [find_python_exe(), "-m", "pytest", "test/test_simulations.py", "-v"],
        cwd=str(repo_dir),
        check=True,
    )
