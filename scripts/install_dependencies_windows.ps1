# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Windows Build and Dependency Automation Script
# Compatible with PowerShell 5.1+ and PowerShell 7+
# ------------------------------------------------------------------------------

param(
    [int]$Jobs = 8,
    [string]$Method = "opt",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Rabbit-FEM Windows Native Build Toolchain" -ForegroundColor Cyan
Write-Host " Repository Root: $RepoRoot" -ForegroundColor Cyan
Write-Host " Parallel Jobs:   $Jobs" -ForegroundColor Cyan
Write-Host " Build Method:    $Method" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Check MSYS2
$MsysBash = "C:\msys64\usr\bin\bash.exe"
if (-not (Test-Path $MsysBash)) {
    throw "MSYS2 bash not found at $MsysBash. Please install MSYS2 to C:\msys64."
}
Write-Host "[OK] MSYS2 found at $MsysBash" -ForegroundColor Green

$requiredMsysTools = @("diff.exe", "make.exe", "patch.exe", "m4.exe", "git.exe", "python3.exe")
$needsInstall = $false
foreach ($tool in $requiredMsysTools) {
    if (-not (Test-Path "C:\msys64\usr\bin\$tool")) {
        $needsInstall = $true
        break
    }
}
if ($needsInstall) {
    Write-Host "[*] Synchronizing MSYS2 database and installing required packages..." -ForegroundColor Yellow
    & "C:\msys64\usr\bin\pacman.exe" -Sy --needed --noconfirm msys/diffutils msys/make msys/patch msys/m4 msys/git msys/python
}
foreach ($tool in $requiredMsysTools) {
    if (-not (Test-Path "C:\msys64\usr\bin\$tool")) {
        throw "Failed to install required MSYS2 tool C:\msys64\usr\bin\$tool."
    }
}
Write-Host "[OK] MSYS2 required tools verified (diff, make, patch, m4, git, python3)." -ForegroundColor Green

# 2. Check or create Python virtual environment with uv
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[*] Creating virtual environment with uv..." -ForegroundColor Yellow
    & uv venv (Join-Path $RepoRoot ".venv")
}
Write-Host "[OK] Python environment: $VenvPython" -ForegroundColor Green

# 3. Install required Python packages
Write-Host "[*] Installing Python build and test dependencies..." -ForegroundColor Yellow
& uv pip install --python $VenvPython ziglang packaging pyyaml jinja2 pytest gmsh
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
    @{ Name = "zig-ranlib"; Script = "ranlib_wrapper.py" }
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
    $setupCmd = "export PATH=`"/usr/bin:$RepoRootPosix/.venv/Scripts:`$PATH`" && cd `"$RepoRootPosix`" && "
    $combined = $setupCmd + $BashCommand
    & $MsysBash -lc $combined
    if ($LASTEXITCODE -ne 0) {
        throw "$StepTitle failed with exit code $LASTEXITCODE."
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
    if (-not (Test-Path $MooseDir)) {
        Invoke-MsysBash "git clone --branch next https://github.com/idaholab/moose.git moose" "Cloning upstream MOOSE repository (next branch)"
    } else {
        Invoke-MsysBash "cd moose && git init && git remote add origin https://github.com/idaholab/moose.git 2>/dev/null || true && git fetch --depth 50 origin next" "Fetching MOOSE repository"
    }
    Invoke-MsysBash "cd moose && git checkout -f $MooseCommit" "Checking out MOOSE at commit $MooseCommit"
}

if (-not $AllDepsBuilt -and (-not (Test-Path $MoosePetscCfg) -or -not (Test-Path $MooseLibmeshCfg))) {
    foreach ($sub in @("libmesh", "framework\contrib\wasp", "petsc")) {
        $target = Join-Path $MooseDir $sub
        if ((Test-Path $target) -and (-not (Test-Path (Join-Path $target ".git")))) {
            Write-Host "[!] Cleaning non-git submodule directory: $target" -ForegroundColor Yellow
            Remove-Item -Recurse -Force $target
        }
    }

    $submoduleCmd = "cd moose && git config core.autocrlf false && git submodule update --init --recursive petsc libmesh framework/contrib/wasp"
    $maxAttempts = 5
    $attempt = 1
    $success = $false
    while (-not $success -and $attempt -le $maxAttempts) {
        try {
            Invoke-MsysBash $submoduleCmd "Initializing MOOSE submodules at commit $MooseCommit (Attempt $attempt/$maxAttempts)"
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

    $fixSymlinks = Join-Path $RepoRoot "moose\libmesh\contrib\bin\fix_windows_symlinks.sh"
    if (Test-Path $fixSymlinks) {
        $symlinkScript = [System.IO.File]::ReadAllText($fixSymlinks)
        $fixedScript = $symlinkScript.Replace('shell git rev-parse', 'git rev-parse')
        [System.IO.File]::WriteAllText($fixSymlinks, $fixedScript)
        Invoke-MsysBash "cd moose/libmesh/contrib && ./bin/fix_windows_symlinks.sh" "Fixing libMesh Windows symlinks"
    }
}

# 6. Build PETSc
$PetscLib = Join-Path $RepoRoot "moose\petsc\arch-windows-opt\lib\libpetsc.a"
if (-not (Test-Path $PetscLib)) {
    $petscConfig = "cd moose/petsc && python3 ./configure PETSC_ARCH=arch-windows-opt --with-cc=$RepoRootPosix/.zig_wrappers/zig-cc --with-cxx=$RepoRootPosix/.zig_wrappers/zig-cxx --with-ar=$RepoRootPosix/.zig_wrappers/zig-ar --with-ranlib=$RepoRootPosix/.zig_wrappers/zig-ranlib --with-fc=0 --with-mpi=0 --with-shared-libraries=0 --with-debugging=0 --download-f2cblaslapack=1 --with-make-np=$Jobs && make PETSC_DIR=$RepoRootPosix/moose/petsc PETSC_ARCH=arch-windows-opt all"
    Invoke-MsysBash $petscConfig "Configuring and building PETSc (arch-windows-opt)"
} else {
    Write-Host "[OK] PETSc already built at $PetscLib" -ForegroundColor Green
}

# 7. Build libMesh
$LibMeshLib = Join-Path $RepoRoot "moose\libmesh\installed\lib\libmesh_opt.a"
if (-not (Test-Path $LibMeshLib)) {
    $libmeshBuild = "cd moose/libmesh && ./configure --prefix=$RepoRootPosix/moose/libmesh/installed --host=x86_64-w64-mingw32 CC=$RepoRootPosix/.zig_wrappers/zig-cc CXX=$RepoRootPosix/.zig_wrappers/zig-cxx AR=$RepoRootPosix/.zig_wrappers/zig-ar RANLIB=$RepoRootPosix/.zig_wrappers/zig-ranlib --disable-shared --enable-static --with-methods=opt --enable-unique-id --disable-warnings --enable-silent-rules --disable-openmp --disable-boost --with-thread-model=none --disable-maintainer-mode --disable-petsc-hypre-required --without-gdb-command --with-petsc=$RepoRootPosix/moose/petsc PETSC_ARCH=arch-windows-opt && make -j$Jobs && make install"
    Invoke-MsysBash $libmeshBuild "Configuring and building libMesh"
} else {
    Write-Host "[OK] libMesh already built at $LibMeshLib" -ForegroundColor Green
}

# 8. Build WASP and HIT
$HitExe = Join-Path $RepoRoot "moose\framework\contrib\hit\hit.exe"
if (-not (Test-Path $HitExe)) {
    $waspBuild = "cd moose/framework/contrib/wasp && mkdir -p build && cd build && cmake -G `"MinGW Makefiles`" -DCMAKE_C_COMPILER=`"$RepoRootPosix/.zig_wrappers/zig-cc`" -DCMAKE_CXX_COMPILER=`"$RepoRootPosix/.zig_wrappers/zig-cxx`" -DCMAKE_AR=`"$RepoRootPosix/.zig_wrappers/zig-ar`" -DCMAKE_RANLIB=`"$RepoRootPosix/.zig_wrappers/zig-ranlib`" -DCMAKE_INSTALL_PREFIX=`"$RepoRootPosix/moose/framework/contrib/wasp/install`" -DBUILD_SHARED_LIBS=OFF .. && make -j$Jobs && make install && cd $RepoRootPosix/moose/framework/contrib/hit && make -j$Jobs"
    Invoke-MsysBash $waspBuild "Building WASP and HIT parser"
} else {
    Write-Host "[OK] HIT parser already built at $HitExe" -ForegroundColor Green
}

# 9. Configure MOOSE
$MooseConfig = Join-Path $RepoRoot "moose\framework\include\base\MooseConfig.h"
if (-not (Test-Path $MooseConfig)) {
    $mooseConf = "cd moose/framework && ./configure --with-derivative-size=89"
    Invoke-MsysBash $mooseConf "Configuring MOOSE framework"
} else {
    Write-Host "[OK] MOOSE framework already configured." -ForegroundColor Green
}

# 10. Build Rabbit
$RabbitExe = Join-Path $RepoRoot "rabbit-$Method.exe"
Write-Host "`n[*] Building Rabbit application (rabbit-$Method.exe)..." -ForegroundColor Yellow
$rabbitBuild = "cd $RepoRootPosix && make -j$Jobs METHOD=$Method LIBMESH_DIR=$RepoRootPosix/moose/libmesh/installed WASP_DIR=$RepoRootPosix/moose/framework/contrib/wasp/install"
Invoke-MsysBash $rabbitBuild "Compiling and linking Rabbit"

if (-not (Test-Path $RabbitExe)) {
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

# 12. Run Verification Tests
if (-not $SkipTests) {
    Write-Host "`n[*] Running simulation regression test suite..." -ForegroundColor Yellow
    $env:PYTHONPATH = "src"
    & $VenvPython -m pytest (Join-Path $RepoRoot "test") -v
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[OK] ALL TESTS PASSED SUCCESSFULLY!" -ForegroundColor Green
    } else {
        Write-Host "`n[!] Some tests failed. Check output above." -ForegroundColor Red
    }
}
