# -----------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# -----------------------------------------------------------------------------

"""Build and package the rabbit MOOSE distribution.

Single entry point to build upstream MOOSE dependencies, compile RabbitApp
using the Zig compiler toolchain, stage relocatable libraries, build standalone
wheels, and run test verification.
"""

import argparse
import glob
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


def setup_zig_wrappers(repo_dir: Path) -> tuple[Path, Path]:
    """Create wrapper scripts for zig cc / clang toolchain."""
    wrapper_dir = repo_dir / ".zig_wrappers"
    wrapper_dir.mkdir(parents=True, exist_ok=True)

    zigcc_path = wrapper_dir / "zigcc"
    zigcxx_path = wrapper_dir / "zigcxx"

    if sys.platform == "darwin":
        llvm_clang = (
            sorted(glob.glob("/opt/homebrew/opt/llvm*/bin/clang"))
            + sorted(glob.glob("/usr/local/opt/llvm*/bin/clang"))
        )
        clang_candidates = (
            llvm_clang
            + ([shutil.which("clang")] if shutil.which("clang") else [])
        )
        clangxx_candidates = (
            [p.replace("clang", "clang++") for p in llvm_clang]
            + ([shutil.which("clang++")] if shutil.which("clang++") else [])
        )
    else:
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
        subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                "next",
                "https://github.com/idaholab/moose.git",
                str(moose_dir),
            ],
            check=True,
        )
        subprocess.run(
            ["git", "checkout", target_commit],
            cwd=str(moose_dir),
            check=True,
        )
    else:
        # Directory exists from cache; initialize and overlay framework
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
            check=False,
        )
        subprocess.run(
            ["git", "fetch", "--depth", "50", "origin", "next"],
            cwd=str(moose_dir),
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "-f", target_commit],
            cwd=str(moose_dir),
            check=True,
        )


def build_moose_dependencies(
    repo_dir: Path,
    moose_dir: Path,
    zigcc_path: Path,
    zigcxx_path: Path,
) -> None:
    """Clone upstream MOOSE (if missing) and compile PETSc, libMesh, WASP."""
    jobs = os.environ.get("MOOSE_JOBS", str(os.cpu_count() or 4))
    print("=" * 60)
    print(f" Setting up MOOSE and dependencies at: {moose_dir}")
    print(f" Parallel jobs: {jobs}")
    print("=" * 60)

    ensure_moose_repo(repo_dir, moose_dir)

    # Check and initialize submodules if not checked out
    petsc_cfg = moose_dir / "petsc" / "configure"
    timpi_readme = (
        moose_dir / "libmesh" / "contrib" / "timpi" / "README"
    )
    if not (petsc_cfg.is_file() and timpi_readme.is_file()):
        for sub_name in [
            "petsc",
            "libmesh",
            "framework/contrib/wasp",
        ]:
            target_sub = moose_dir / sub_name
            if (
                target_sub.is_dir()
                and not (target_sub / ".git").exists()
            ):
                print(
                    f"Removing non-git directory before checkout: "
                    f"{target_sub}"
                )
                shutil.rmtree(target_sub)

        print(
            "Initializing MOOSE git submodules "
            "(petsc, libmesh, wasp)..."
        )
        submodule_cmd = [
            "git",
            "submodule",
            "update",
            "--init",
            "--recursive",
            "petsc",
            "libmesh",
            "framework/contrib/wasp",
        ]
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

    tool_env = dict(os.environ)
    tool_env["OMPI_CC"] = str(zigcc_path)
    tool_env["OMPI_CXX"] = str(zigcxx_path)
    tool_env["CC"] = "mpicc"
    tool_env["CXX"] = "mpicxx"
    if sys.platform == "darwin":
        brew_prefix = (
            "/opt/homebrew"
            if Path("/opt/homebrew").is_dir()
            else "/usr/local"
        )
        llvm_prefix = f"{brew_prefix}/opt/llvm"
        omp_prefix = f"{brew_prefix}/opt/libomp"
        tool_env["PATH"] = (
            f"{llvm_prefix}/bin:{brew_prefix}/bin:"
            + os.environ.get("PATH", "")
        )
        tool_env["CMAKE_LIBRARY_PATH"] = (
            f"{llvm_prefix}/lib:{omp_prefix}/lib:{brew_prefix}/lib"
        )
        tool_env["CMAKE_PREFIX_PATH"] = (
            f"{llvm_prefix}:{omp_prefix}:{brew_prefix}:"
            + os.environ.get("CMAKE_PREFIX_PATH", "")
        )
        tool_env["LIBRARY_PATH"] = (
            f"{llvm_prefix}/lib:{omp_prefix}/lib:{brew_prefix}/lib:"
            + os.environ.get("LIBRARY_PATH", "")
        )
        tool_env["DYLD_LIBRARY_PATH"] = (
            f"{llvm_prefix}/lib:{omp_prefix}/lib:{brew_prefix}/lib:"
            + os.environ.get("DYLD_LIBRARY_PATH", "")
        )
        tool_env["CPATH"] = (
            f"{llvm_prefix}/include:{omp_prefix}/include:"
            f"{brew_prefix}/include:"
            + os.environ.get("CPATH", "")
        )
        ldflags = (
            f"-L{llvm_prefix}/lib -Wl,-rpath,{llvm_prefix}/lib "
            f"-L{omp_prefix}/lib -Wl,-rpath,{omp_prefix}/lib "
            f"-L{brew_prefix}/lib "
            + os.environ.get("LDFLAGS", "")
        ).strip()
        tool_env["LDFLAGS"] = ldflags
        cppflags = (
            f"-I{llvm_prefix}/include -I{omp_prefix}/include "
            f"-I{brew_prefix}/include "
            + os.environ.get("CPPFLAGS", "")
        ).strip()
        tool_env["CPPFLAGS"] = cppflags
    else:
        tool_env["CMAKE_LIBRARY_PATH"] = "/usr/lib/x86_64-linux-gnu"
        tool_env["CMAKE_PREFIX_PATH"] = (
            "/usr/lib/x86_64-linux-gnu:"
            + os.environ.get("CMAKE_PREFIX_PATH", "")
        )
        tool_env["LIBRARY_PATH"] = (
            "/usr/lib/x86_64-linux-gnu:"
            + os.environ.get("LIBRARY_PATH", "")
        )

    # 1. Build PETSc
    print("--> Building PETSc...")
    petsc_env = dict(tool_env)
    petsc_env.pop("PETSC_DIR", None)
    petsc_env.pop("PETSC_ARCH", None)
    subprocess.run(
        [
            "./scripts/update_and_rebuild_petsc.sh",
            "--skip-submodule-update",
            "--CXXOPTFLAGS=-O3",
            "--COPTFLAGS=-O3",
            "--FOPTFLAGS=-O3",
        ],
        cwd=str(moose_dir),
        env=petsc_env,
        check=True,
    )

    # 2. Build libMesh
    print("--> Building libMesh with Zig toolchain...")
    libmesh_env = dict(tool_env)
    libmesh_env["METHODS"] = "opt"
    subprocess.run(
        [
            "./scripts/update_and_rebuild_libmesh.sh",
            "--with-mpi",
        ],
        cwd=str(moose_dir),
        env=libmesh_env,
        check=True,
    )

    # 3. Build WASP
    print("--> Building WASP parser...")
    subprocess.run(
        ["./scripts/update_and_rebuild_wasp.sh"],
        cwd=str(moose_dir),
        env=tool_env,
        check=True,
    )

    # 4. Configure MOOSE
    print("--> Configuring MOOSE...")
    subprocess.run(
        ["./configure", "--with-derivative-size=89"],
        cwd=str(moose_dir),
        env=tool_env,
        check=True,
    )

    print("=" * 60)
    print(" MOOSE dependencies built and configured successfully!")
    print("=" * 60)



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
) -> dict[str, Path]:
    """Find all needed sonames and map them to their concrete file paths."""
    resolved_libs: dict[str, Path] = {}
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
        "libmpi.so",
        "libmpi_cxx.so",
        "libopen-pal.so",
        "libopen-rte.so",
        "libhwloc.so",
        "libevent",
        "libz.so",
        "libtirpc.so",
        "libgfortran.so",
        "libgomp.so",
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
        except Exception:
            pass

    return resolved_libs


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

    resolved_libs = find_needed_libraries(binary_path, available_libs)

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
    """Build standalone Python wheel package and tag as manylinux."""
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
            platform_tag = (
                "manylinux_2_35_x86_64.manylinux_2_38_x86_64.linux_x86_64"
            )
            wheel_bin = shutil.which("wheel") or str(
                repo_dir / ".venv" / "bin" / "wheel"
            )
        wheel_cmd = (
            [wheel_bin]
            if (shutil.which(wheel_bin) or Path(wheel_bin).is_file())
            else [find_python_exe(), "-m", "wheel"]
        )
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
        wheels = sorted(dist_dir.glob("*.whl"), key=os.path.getmtime)
        latest_whl = wheels[-1]
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


def parse_args() -> argparse.Namespace:
    """Parse command-line flags for build_rabbit."""
    parser = argparse.ArgumentParser(
        description="Unified build orchestrator for rabbit-fem."
    )
    parser.add_argument(
        "--moose",
        nargs="?",
        const="default",
        default=None,
        metavar="PATH",
        help=(
            "Clone and build upstream MOOSE dependencies "
            "(PETSc, libMesh, WASP). Optionally provide path to MOOSE."
        ),
    )
    parser.add_argument(
        "--setup-wrappers",
        action="store_true",
        help="Generate only the zig cc wrapper toolchain scripts.",
    )
    parser.add_argument(
        "--wheel",
        action="store_true",
        help=(
            "Build the standalone Python wheel package in dist/ "
            "after staging."
        ),
    )
    parser.add_argument(
        "--wheel-only",
        action="store_true",
        help=(
            "Package existing staged artifacts into dist/*.whl "
            "without recompiling."
        ),
    )
    parser.add_argument(
        "--test",
        "--tests",
        dest="test",
        action="store_true",
        help="Run pytest simulation and relocatability test suite.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Execute full pipeline: MOOSE setup, rabbit build, "
            "staging, wheel, and tests."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Main build orchestration entry point."""
    args = parse_args()
    repo_dir = Path(__file__).resolve().parent


    # If only wheel packaging of existing staged artifacts was requested
    if args.wheel_only:
        build_wheel(repo_dir)
        if args.test:
            run_tests(repo_dir)
        return

    # If only tests requested
    if args.test and not (args.moose or args.wheel or args.all):
        run_tests(repo_dir)
        return

    # 1. Generate toolchain wrappers
    zigcc_path, zigcxx_path = setup_zig_wrappers(repo_dir)
    if args.setup_wrappers:
        print(f"Generated Zig CC wrappers at {zigcc_path.parent}")
        return

    # Determine custom MOOSE path if passed
    custom_moose = None
    if args.moose and args.moose != "default":
        custom_moose = args.moose
    moose_dir = get_moose_dir(repo_dir, custom_moose)

    # 2. If --moose or --all requested, build MOOSE dependencies
    if args.moose is not None or args.all:
        build_moose_dependencies(
            repo_dir, moose_dir, zigcc_path, zigcxx_path
        )
        if args.moose is not None and not args.all and not args.wheel:
            return


    # 3. Build and Stage Rabbit
    binary_path = build_rabbit_binary(
        repo_dir, moose_dir, zigcc_path, zigcxx_path
    )
    stage_artifacts(repo_dir, moose_dir, binary_path)

    # 4. Build wheel package if requested
    if args.wheel or args.all:
        build_wheel(repo_dir)

    # 5. Run test suite if requested
    if args.test or args.all:
        run_tests(repo_dir)

    print("Rabbit build pipeline completed successfully.")



if __name__ == "__main__":
    main()
