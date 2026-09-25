<!--
--------------------------------------------------------------------------------
Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation

Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
Licensed under the GNU Lesser General Public License v2.1
See LICENSE for details.

Authors: scepticalrabbit (Lloyd Fletcher)
--------------------------------------------------------------------------------
-->

# Building, Verifying, Testing, and Publishing Wheels to PyPI

This guide provides step-by-step instructions for building standalone `manylinux` wheels for `rabbit-fem`, validating binary relocatability, smoke-testing in isolated environments, and uploading to TestPyPI and production PyPI.

---

## 1. Prerequisites

### Environment Setup
Ensure development tools (`twine`, `wheel`, `pytest`) are installed in your virtual environment:

```bash
uv pip install -e ".[dev]"
```

### PyPI API Credentials
Set up API tokens for PyPI and TestPyPI:
- **PyPI**: [https://pypi.org/manage/account/token/](https://pypi.org/manage/account/token/)
- **TestPyPI**: [https://test.pypi.org/manage/account/token/](https://test.pypi.org/manage/account/token/)

Configure credentials in `~/.pypirc` (recommended) or pass tokens interactively:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-<your-production-token>

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-<your-testpypi-token>
```

---

## 2. Clean Build & Manylinux Packaging

1. **Clean prior build artifacts**:
   ```bash
   rm -rf dist/ build/ *.egg-info
   ```

2. **Build the wheel and execute full test suite**:
   ```bash
   uv run python build_rabbit.py --wheel --test
   ```

   *What this step does:*
   - Compiles `RabbitApp` against MOOSE using the Zig toolchain.
   - Strips debug symbols from the binary and `.so` libraries.
   - Rewrites RPATHs with `patchelf` to `$ORIGIN/../lib` and `$ORIGIN`.
   - Stages files into `src/rabbit/bin` and `src/rabbit/lib`.
   - Packages the wheel and retags it to the single PEP 600 platform tag
     `manylinux_2_38_x86_64`.
   - Runs the test suite in `test/test_simulations.py` (which audits relocatability with `readelf` and runs all benchmark simulations).

---

## 3. Package Verification

1. **Check package integrity with Twine**:
   ```bash
   uv run twine check dist/*
   ```
   *Expected output: `PASSED` for all files in `dist/`.*

2. **Verify wheel filename and file size**:
   ```bash
   ls -lh dist/*.whl
   ```
   *The wheel size should be ~60–65 MB (well below PyPI's 100 MB compressed limit).*

---

## 4. Local Smoke-Testing in an Isolated Environment

Before uploading to any index, install the newly built wheel in a fresh virtual environment in `/tmp` and test simulation execution with `MOOSE_DIR` unset:

```bash
# 1. Create a clean virtual environment outside the repository
python3 -m venv /tmp/rabbit_smoke_test
source /tmp/rabbit_smoke_test/bin/activate

# 2. Install the newly built local wheel
pip install dist/rabbit_fem-*.whl

# 3. Test CLI version with MOOSE_DIR stripped
env -u MOOSE_DIR rabbit --version

# 4. Run a packaged simulation from Python
python3 -c "from rabbit.sims import cube_thermomech_input_path, EElemType, run_rabbit; res = run_rabbit(cube_thermomech_input_path(EElemType.HEX8)); assert res.returncode == 0; print('Smoke test successful!')"

# 5. Clean up temporary test environment
deactivate
rm -rf /tmp/rabbit_smoke_test
```

---

## 5. Dry-Run on TestPyPI

Upload to TestPyPI first to test distribution index integration and remote installation:

1. **Upload to TestPyPI**:
   ```bash
   uv run twine upload --repository testpypi dist/*
   ```

2. **Verify installation from TestPyPI**:
   ```bash
   python3 -m venv /tmp/testpypi_verify
   source /tmp/testpypi_verify/bin/activate
   pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple rabbit-fem
   rabbit --help
   deactivate
   rm -rf /tmp/testpypi_verify
   ```

---

## 6. Publish to Production PyPI

Once verified on TestPyPI:

1. **Upload to Production PyPI**:
   ```bash
   uv run twine upload dist/*
   ```

2. **Final Verification from PyPI**:
   ```bash
   python3 -m venv /tmp/pypi_verify
   source /tmp/pypi_verify/bin/activate
   pip install rabbit-fem
   rabbit --version
   deactivate
   rm -rf /tmp/pypi_verify
   ```
