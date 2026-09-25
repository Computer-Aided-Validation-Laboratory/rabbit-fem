# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Windows Build and Dependency Automation Script
# Compatible with PowerShell 5.1+ and PowerShell 7+
# ------------------------------------------------------------------------------

param(
    [string]$Stage = "all",
    [int]$Jobs = 4,
    [string]$Method = "opt",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$env:MSYS2_PATH_TYPE = "inherit"
$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Rabbit-FEM Windows Native Build Toolchain" -ForegroundColor Cyan
Write-Host " Repository Root: $RepoRoot" -ForegroundColor Cyan
Write-Host " Parallel Jobs:   $Jobs" -ForegroundColor Cyan
Write-Host " Build Method:    $Method" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Detect MSYS2 installation dynamically
$MsysRoot = $null
if ($env:MSYS2_ROOT -and (Test-Path (Join-Path $env:MSYS2_ROOT "usr\bin\bash.exe"))) {
    $MsysRoot = $env:MSYS2_ROOT
} elseif ($env:MSYS_ROOT -and (Test-Path (Join-Path $env:MSYS_ROOT "usr\bin\bash.exe"))) {
    $MsysRoot = $env:MSYS_ROOT
} else {
    $candidates = @("C:\msys64", "D:\msys64", "C:\tools\msys64", "D:\tools\msys64", (Join-Path $env:LOCALAPPDATA "msys64"))
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path (Join-Path $cand "usr\bin\bash.exe"))) {
            $MsysRoot = $cand
            break
        }
    }
}
if (-not $MsysRoot) {
    $bashCmd = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($bashCmd -and $bashCmd.Source -like "*msys*") {
        $MsysRoot = (Get-Item $bashCmd.Source).Directory.Parent.Parent.FullName
    }
}
if (-not $MsysRoot) {
    throw "MSYS2 not found. Please install MSYS2 to C:\msys64 or set `$env:MSYS2_ROOT."
}
$MsysBash = Join-Path $MsysRoot "usr\bin\bash.exe"
$env:MSYS2_ROOT = $MsysRoot
Write-Host "[OK] MSYS2 found at $MsysBash" -ForegroundColor Green

$requiredMsysTools = @("diff.exe", "make.exe", "patch.exe", "m4.exe", "git.exe", "python3.exe", "cmake.exe")
$needsInstall = $false
foreach ($tool in $requiredMsysTools) {
    if (-not (Test-Path (Join-Path $MsysRoot "usr\bin\$tool"))) {
        $needsInstall = $true
        break
    }
}
if ($needsInstall) {
    Write-Host "[*] Synchronizing MSYS2 database and installing required packages..." -ForegroundColor Yellow
    & (Join-Path $MsysRoot "usr\bin\pacman.exe") -Sy --needed --noconfirm msys/diffutils msys/make msys/patch msys/m4 msys/git msys/python msys/python-pip msys/cmake
    & (Join-Path $MsysRoot "usr\bin\python3.exe") -m pip install --break-system-packages --quiet packaging pyyaml
}
foreach ($tool in $requiredMsysTools) {
    if (-not (Test-Path (Join-Path $MsysRoot "usr\bin\$tool"))) {
        throw "Failed to install required MSYS2 tool $tool in $MsysRoot\usr\bin."
    }
}
Write-Host "[OK] MSYS2 required tools verified (diff, make, patch, m4, git, python3, cmake)." -ForegroundColor Green

# 2. Check or create Python virtual environment with uv
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[*] Creating virtual environment with uv..." -ForegroundColor Yellow
    & uv venv (Join-Path $RepoRoot ".venv")
}
Write-Host "[OK] Python environment: $VenvPython" -ForegroundColor Green

# 3. Install required Python packages
Write-Host "[*] Installing Python build and test dependencies..." -ForegroundColor Yellow
& uv pip install --python $VenvPython ziglang packaging pyyaml jinja2 pytest gmsh wheel
Write-Host "[OK] Python dependencies installed." -ForegroundColor Green

# 4. Check Zig compiler
$ZigExe = Join-Path $RepoRoot ".venv\Lib\site-packages\ziglang\zig.exe"
if (-not (Test-Path $ZigExe)) {
    throw "Zig compiler executable not found in site-packages at $ZigExe."
}
Write-Host "[OK] Zig compiler found: $ZigExe" -ForegroundColor Green

# Convert RepoRoot to MSYS2 POSIX path
$driveLetter = $RepoRoot.Substring(0, 1).ToLower()
$pathRest = $RepoRoot.Substring(2).Replace('\', '/')
$RepoRootPosix = "/$driveLetter$pathRest"

# 5. Set up compiler wrappers
$WrappersDir = Join-Path $RepoRoot ".zig_wrappers"
if (-not (Test-Path $WrappersDir)) {
    New-Item -ItemType Directory -Force -Path $WrappersDir | Out-Null
}
$srcWrappersDir = Join-Path $RepoRoot "scripts\windows_wrappers"
if (Test-Path $srcWrappersDir) {
    Copy-Item (Join-Path $srcWrappersDir "*.py") $WrappersDir -Force
}
$pyWinPath = $VenvPython.Replace('\', '/')
$wrappers = @(
    @{ Name = "zig-cc"; Script = "cc_wrapper.py" },
    @{ Name = "zig-cxx"; Script = "cxx_wrapper.py" },
    @{ Name = "zig-ar"; Script = "ar_wrapper.py" },
    @{ Name = "zig-ranlib"; Script = "ranlib_wrapper.py" },
    @{ Name = "lib"; Script = "ar_wrapper.py" }
)
foreach ($w in $wrappers) {
    $shPath = Join-Path $WrappersDir $w.Name
    $cmdPath = Join-Path $WrappersDir ($w.Name + ".cmd")
    $pyScriptWin = (Join-Path $WrappersDir $w.Script).Replace('\', '/')
    $shContent = "#!/usr/bin/env bash`nexec `"$pyWinPath`" `"$pyScriptWin`" `"`$@`"`n"
    $cmdContent = "@`"$VenvPython`" `"" + (Join-Path $WrappersDir $w.Script) + "`" %*`n"
    [System.IO.File]::WriteAllText($shPath, $shContent)
    [System.IO.File]::WriteAllText($cmdPath, $cmdContent)
}
Write-Host "[OK] Compiler wrappers configured in $WrappersDir" -ForegroundColor Green

# Helper function to run bash commands
function Invoke-MsysBash([string]$BashCommand, [string]$StepTitle) {
    Write-Host "`n>>> $StepTitle..." -ForegroundColor Cyan
    $localLog = Join-Path $RepoRoot "current_step.log"
    $lastLog = Join-Path $RepoRoot "last_step.log"
    if (Test-Path $localLog) { Remove-Item -Force $localLog }

    $stepScript = Join-Path $RepoRoot "run_step.sh"
    $stepScriptPosix = "$RepoRootPosix/run_step.sh"

    $lines = @(
        "set -euo pipefail",
        "export PATH=`"$RepoRootPosix/.zig_wrappers:/usr/bin:$RepoRootPosix/.venv/Scripts:`$PATH`"",
        "cd `"$RepoRootPosix`"",
        $BashCommand
    )
    $content = ($lines -join "`n") + "`n"
    [System.IO.File]::WriteAllText($stepScript, $content, (New-Object System.Text.UTF8Encoding($false)))

    $cmd = "set -o pipefail && ( source `"$stepScriptPosix`" ) 2>&1 | tee `"$RepoRootPosix/current_step.log`""
    & $MsysBash -lc $cmd
    $code = $LASTEXITCODE

    if (Test-Path $localLog) {
        Copy-Item $localLog $lastLog -Force
    }

    if ($code -ne 0) {
        Write-Host "`n[!] $StepTitle FAILED with exit code $code" -ForegroundColor Red
        $possibleLogs = @(
            (Join-Path $RepoRoot "moose\petsc\configure.log"),
            (Join-Path $RepoRoot "moose\petsc\arch-windows-opt\lib\petsc\conf\configure.log")
        )
        foreach ($petscLog in $possibleLogs) {
            if (Test-Path $petscLog) {
                "`n--- PETSC CONFIGURE.LOG TAIL ---`n" | Out-File -FilePath $localLog -Append -Encoding utf8
                Get-Content $petscLog -Tail 150 | Out-File -FilePath $localLog -Append -Encoding utf8
                break
            }
        }
        if (Test-Path $localLog) {
            $tail = Get-Content $localLog -Tail 100
            Write-Host "`n--- LAST 100 LINES OF $StepTitle LOG ---" -ForegroundColor Red
            $tail | ForEach-Object { Write-Host $_ }
            Write-Host "--- END OF LOG ---`n" -ForegroundColor Red
            try {
                $pasteUrl = (Invoke-RestMethod -Uri "https://paste.rs" -Method Post -InFile $localLog -TimeoutSec 10).Trim()
                Write-Host "[*] Build failure log uploaded to: $pasteUrl" -ForegroundColor Yellow
                $pasteUrl | Set-Content (Join-Path $RepoRoot "paste_url.txt")
            } catch {}
        }
        throw "$StepTitle failed with exit code $code."
    }
    Write-Host "[OK] $StepTitle completed successfully." -ForegroundColor Green
}

# 5.5. Ensure MOOSE repository and submodules
$MooseDir = Join-Path $RepoRoot "moose"
$MooseVersionFile = Join-Path $RepoRoot "moose_version.txt"
$MooseCommit = "73c6aa53af67b8046f7ace5fd1c96846d5d6641d"
if (Test-Path $MooseVersionFile) {
    $MooseCommit = (Get-Content $MooseVersionFile).Trim()
}
$MooseFrameworkMk = Join-Path $MooseDir "framework\build.mk"
$MoosePetscCfg = Join-Path $RepoRoot "moose\petsc\configure"
$MooseLibmeshCfg = Join-Path $RepoRoot "moose\libmesh\configure"
$PetscLib = Join-Path $RepoRoot "moose\petsc\arch-windows-opt\lib\libpetsc.a"
$LibMeshLib = Join-Path $RepoRoot "moose\libmesh\installed\lib\libmesh_opt.a"
$HitExe = Join-Path $RepoRoot "moose\framework\contrib\hit\hit.exe"
$MooseConfig = Join-Path $RepoRoot "moose\framework\include\base\MooseConfig.h"

$AllDepsBuilt = (Test-Path $PetscLib) -and (Test-Path $LibMeshLib) -and (Test-Path $HitExe) -and (Test-Path $MooseConfig)

if (-not (Test-Path $MooseFrameworkMk)) {
    Write-Host "[*] Ensuring MOOSE framework files exist (commit $MooseCommit)..." -ForegroundColor Yellow
    & $VenvPython -c "from scripts.build.common import ensure_moose_repo, get_moose_dir; from pathlib import Path; ensure_moose_repo(Path('.'), get_moose_dir(Path('.')))"
}

$needPetsc = ($Stage -in @("all", "petsc")) -and -not (Test-Path $PetscLib) -and -not (Test-Path $MoosePetscCfg)
$needLibmesh = ($Stage -in @("all", "libmesh")) -and -not (Test-Path $LibMeshLib) -and -not (Test-Path (Join-Path $MooseDir "libmesh\installed\include\libmesh\libmesh.h"))
$needWasp = ($Stage -in @("all", "wasp")) -and -not (Test-Path $HitExe) -and -not (Test-Path (Join-Path $MooseDir "framework\contrib\wasp\CMakeLists.txt"))

$subsNeeded = @()
if ($needPetsc) { $subsNeeded += "petsc" }
if ($needLibmesh) { $subsNeeded += "libmesh" }
if ($needWasp) { $subsNeeded += "framework/contrib/wasp" }

if ($subsNeeded.Count -gt 0) {
    $subsList = $subsNeeded -join " "
    $submoduleCmd = "cd moose && git config core.autocrlf false && git submodule sync --recursive $subsList && git submodule update --init --recursive $subsList"
    $maxAttempts = 5
    $attempt = 1
    $success = $false
    while (-not $success -and $attempt -le $maxAttempts) {
        try {
            Invoke-MsysBash $submoduleCmd "Initializing MOOSE submodules: $subsList (Attempt $attempt/$maxAttempts)"
            $success = $true
        } catch {
            if ($attempt -ge $maxAttempts) {
                throw $_
            }
            Write-Host "[!] Submodule update failed (transient remote/load error). Waiting 30s before retry..." -ForegroundColor Yellow
            Start-Sleep -Seconds 30
            $attempt++
        }
    }
}

# 6. Build PETSc
if ($Stage -in @("all", "petsc")) {
    $PetscLib = Join-Path $RepoRoot "moose\petsc\arch-windows-opt\lib\libpetsc.a"
    if (-not (Test-Path $PetscLib)) {
        $applyPetsc = "cd moose/petsc && patch -p1 -N -r - < `"$RepoRootPosix/patches/windows/petsc.patch`" || true"
        Invoke-MsysBash $applyPetsc "Applying PETSc Windows patch"

        $petscConfig = "cd moose/petsc && python3 ./configure PETSC_ARCH=arch-windows-opt --with-cc=$RepoRootPosix/.zig_wrappers/zig-cc --with-cxx=$RepoRootPosix/.zig_wrappers/zig-cxx --with-ar=$RepoRootPosix/.zig_wrappers/zig-ar --with-ranlib=$RepoRootPosix/.zig_wrappers/zig-ranlib --with-fc=0 --with-mpi=0 --with-shared-libraries=0 --with-debugging=0 --download-f2cblaslapack=1 --with-windows-graphics=0 --with-x=0 --with-make-np=$Jobs && make PETSC_DIR=$RepoRootPosix/moose/petsc PETSC_ARCH=arch-windows-opt all"
        Invoke-MsysBash $petscConfig "Configuring and building PETSc (arch-windows-opt)"
    } else {
        Write-Host "[OK] PETSc already built at $PetscLib" -ForegroundColor Green
    }
}

# 7. Build libMesh
if ($Stage -in @("all", "libmesh")) {
    $LibMeshLib = Join-Path $RepoRoot "moose\libmesh\installed\lib\libmesh_opt.a"
    if (-not (Test-Path $LibMeshLib)) {
        $fixSymlinks = Join-Path $RepoRoot "moose\libmesh\contrib\bin\fix_windows_symlinks.sh"
        $robustSymlinkScript = @"
#!/bin/sh
set -e

LIBMESH_ROOT=`$(git rev-parse --show-toplevel)
cd "`$LIBMESH_ROOT"

SYMLINKS=`$(git ls-files -s | grep '^120000' | cut -f2)

for sl in `$SYMLINKS
do
    TARGET_REL=`$(git cat-file blob ":`$sl" 2>/dev/null | tr -d '\r\n')
    if [ -z "`$TARGET_REL" ]; then
        continue
    fi
    TARGET=`$(dirname "`$sl")/"`$TARGET_REL"
    if [ ! -e "`$TARGET" ]; then
        echo "Warning: target `$TARGET does not exist for `$sl"
        continue
    fi
    echo "Replacing symlink `$sl by copy of `$TARGET..."
    rm -rf "`$sl"
    cp -r "`$TARGET" "`$sl"
    git update-index --assume-unchanged "`$sl" 2>/dev/null || true
done
"@
        [System.IO.File]::WriteAllText($fixSymlinks, $robustSymlinkScript)
        Invoke-MsysBash "cd moose/libmesh && ./contrib/bin/fix_windows_symlinks.sh" "Fixing libMesh Windows symlinks"

        # Ensure nested eigen symlink (eigen/eigen -> eigen/gitshim -> ../git/Eigen) is properly resolved
        $fixEigen = "cd moose/libmesh/contrib && if [ -d eigen/git/Eigen ]; then rm -rf eigen/gitshim/Eigen eigen/gitshim/unsupported eigen/gitshim/root && cp -r eigen/git/Eigen eigen/gitshim/Eigen && cp -r eigen/git/unsupported eigen/gitshim/unsupported && cp -r eigen/git eigen/gitshim/root && rm -rf eigen/eigen && cp -r eigen/gitshim eigen/eigen; fi && test -f eigen/eigen/Eigen/Householder"
        Invoke-MsysBash $fixEigen "Resolving and verifying Eigen headers for Windows"

        # Apply Windows patches for NetCDF and METIS
        $applyNetcdf = "cd moose/libmesh/contrib/netcdf/netcdf-c-4.6.2 && patch -p1 -N -r - < `"$RepoRootPosix/patches/windows/netcdf.patch`" || true"
        Invoke-MsysBash $applyNetcdf "Applying NetCDF Windows patch"

        $applyMetis = "cd moose/libmesh/contrib/metis/GKlib && patch -p1 -N -r - < `"$RepoRootPosix/patches/windows/metis.patch`" || true"
        Invoke-MsysBash $applyMetis "Applying METIS Windows patch"

        $libmeshBuild = "cd moose/libmesh && export PETSC_DIR=$RepoRootPosix/moose/petsc && export PETSC_ARCH=arch-windows-opt && ./configure --prefix=$RepoRootPosix/moose/libmesh/installed --host=x86_64-w64-mingw32 CC=$RepoRootPosix/.zig_wrappers/zig-cc CXX=$RepoRootPosix/.zig_wrappers/zig-cxx AR=$RepoRootPosix/.zig_wrappers/zig-ar RANLIB=$RepoRootPosix/.zig_wrappers/zig-ranlib --disable-shared --enable-static --with-methods=opt --enable-unique-id --disable-warnings --enable-silent-rules --disable-openmp --disable-boost --with-thread-model=none --disable-maintainer-mode --disable-petsc-hypre-required --without-gdb-command --disable-fortran --disable-exodus-fortran PETSC_DIR=$RepoRootPosix/moose/petsc PETSC_ARCH=arch-windows-opt && make -j$Jobs && make install"
        Invoke-MsysBash $libmeshBuild "Configuring and building libMesh"
    } else {
        Write-Host "[OK] libMesh already built at $LibMeshLib" -ForegroundColor Green
    }
}

# 8. Build WASP and HIT
if ($Stage -in @("all", "wasp")) {
    $HitExe = Join-Path $RepoRoot "moose\framework\contrib\hit\hit.exe"
    if (-not (Test-Path $HitExe)) {
        # Apply Windows patch for WASP
        $applyWasp = "cd moose/framework/contrib/wasp && patch -p1 -N -r - < `"$RepoRootPosix/patches/windows/wasp.patch`" || true"
        Invoke-MsysBash $applyWasp "Applying WASP Windows patch"

        $waspBuild = "cd moose/framework/contrib/wasp && mkdir -p build && cd build && cmake -G `"Unix Makefiles`" -DCMAKE_SYSTEM_NAME=Windows -DCMAKE_DEPENDS_USE_COMPILER=FALSE -DCMAKE_C_COMPILER=`"$RepoRootPosix/.zig_wrappers/zig-cc`" -DCMAKE_CXX_COMPILER=`"$RepoRootPosix/.zig_wrappers/zig-cxx`" -DCMAKE_AR=`"$RepoRootPosix/.zig_wrappers/zig-ar`" -DCMAKE_RANLIB=`"$RepoRootPosix/.zig_wrappers/zig-ranlib`" -DCMAKE_INSTALL_PREFIX=`"$RepoRootPosix/moose/framework/contrib/wasp/install`" -DCMAKE_BUILD_TYPE=RELEASE -DCMAKE_CXX_FLAGS=`"-I$RepoRootPosix/moose/framework/contrib/wasp -I$RepoRootPosix/moose/framework/contrib/wasp/build`" -DCMAKE_C_FLAGS=`"-I$RepoRootPosix/moose/framework/contrib/wasp -I$RepoRootPosix/moose/framework/contrib/wasp/build`" -Dwasp_ENABLE_ALL_PACKAGES=OFF -Dwasp_ENABLE_wasphit=ON -Dwasp_ENABLE_wasplsp=ON -Dwasp_ENABLE_waspsiren=ON -Dwasp_ENABLE_waspplot=ON -Dwasp_ENABLE_testframework=OFF -Dwasp_ENABLE_TESTS=OFF -DBUILD_SHARED_LIBS=OFF -DDISABLE_HIT_TYPE_PROMOTION=ON .. && make -j$Jobs && make install && cd $RepoRootPosix/moose/framework/contrib/hit && make -j$Jobs hit CXX=`"$RepoRootPosix/.zig_wrappers/zig-cxx`" WASP_DIR=`"$RepoRootPosix/moose/framework/contrib/wasp/install`" lib_suffix=a && if [ -f hit ] && [ ! -f hit.exe ]; then cp hit hit.exe; fi"
        Invoke-MsysBash $waspBuild "Building WASP and HIT parser"
    } else {
        Write-Host "[OK] HIT parser already built at $HitExe" -ForegroundColor Green
    }
}

# 9. Configure MOOSE
if ($Stage -in @("all", "moose")) {
    & $PythonExe "$RepoRoot\scripts\fix_symlinks.py" "$RepoRoot\moose"
    $applyMoose = "cd moose && patch -p1 -N -r - < `"$RepoRootPosix/patches/windows/moose.patch`" || true"
    Invoke-MsysBash $applyMoose "Applying MOOSE Windows patch"

    if (-not (Test-Path $MooseConfig)) {
        $mooseConf = "cd moose && ./configure --with-derivative-size=89"
        Invoke-MsysBash $mooseConf "Configuring MOOSE framework"
    } else {
        Write-Host "[OK] MOOSE framework already configured." -ForegroundColor Green
    }
}

# 10. Build Rabbit
if ($Stage -in @("all", "rabbit")) {
    $RabbitExe = Join-Path $RepoRoot "rabbit-$Method.exe"
    Write-Host "`n[*] Building Rabbit application (rabbit-$Method.exe)..." -ForegroundColor Yellow
    $rabbitBuild = "make -j$Jobs METHOD=$Method LIBMESH_DIR=$RepoRootPosix/moose/libmesh/installed WASP_DIR=$RepoRootPosix/moose/framework/contrib/wasp/install lib_suffix=a && if [ -f .libs/rabbit-$Method.exe ]; then cp .libs/rabbit-$Method.exe rabbit-$Method.exe; elif [ -f .libs/rabbit-$Method ]; then cp .libs/rabbit-$Method rabbit-$Method.exe; elif [ -f rabbit-$Method ] && [ ! -f rabbit-$Method.exe ]; then cp rabbit-$Method rabbit-$Method.exe; fi"
    Invoke-MsysBash $rabbitBuild "Compiling and linking Rabbit"

    if (-not (Test-Path $RabbitExe)) {
        Write-Host "`n[!] $RabbitExe not found. Searching for rabbit binaries..." -ForegroundColor Red
        Get-ChildItem -Path $RepoRoot -Filter "rabbit*" | ForEach-Object { Write-Host "  $($_.FullName)" }
        $libsDir = Join-Path $RepoRoot ".libs"
        if (Test-Path $libsDir) {
            Get-ChildItem -Path $libsDir -Filter "rabbit*" | ForEach-Object { Write-Host "  $($_.FullName)" }
        }
        throw "Expected binary $RabbitExe was not generated."
    }
    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Host " Rabbit-FEM Windows build SUCCEEDED!" -ForegroundColor Green
    Write-Host " Executable: $RabbitExe" -ForegroundColor Green

    # 11. Stage executable into package
    $BinTarget = Join-Path $RepoRoot "src\rabbit\bin"
    if (-not (Test-Path $BinTarget)) {
        New-Item -ItemType Directory -Force -Path $BinTarget | Out-Null
    }
    Copy-Item $RabbitExe (Join-Path $BinTarget "rabbit.exe") -Force
    Write-Host "[OK] Staged executable to $BinTarget\rabbit.exe" -ForegroundColor Green
}

# 12. Run Verification Tests
if (($Stage -eq "test" -or $Stage -eq "all") -and -not $SkipTests) {
    Write-Host "`n[*] Running simulation regression test suite..." -ForegroundColor Yellow
    $env:PYTHONPATH = "src"
    & $VenvPython -m pytest (Join-Path $RepoRoot "test") -v
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[OK] ALL TESTS PASSED SUCCESSFULLY!" -ForegroundColor Green
    } else {
        Write-Host "`n[!] Some tests failed. Check output above." -ForegroundColor Red
    }
}
