# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Python floor regression tests.

Colleague report: a system Python 3.9 venv installed the wheel and died
at import with ``TypeError: unsupported operand type(s) for |`` from
``rabbit/sims/simulations.py``. The package uses PEP 604 ``X | Y``
annotations, which evaluate at ``def`` time and require 3.10+. These
tests pin the declared floor and the fail-fast guard so the failure
mode is a clear message, not a deep TypeError.
"""

from pathlib import Path
import re
import sys


def _repo_root() -> Path:
    """Repository root derived from this file's location."""
    return Path(__file__).resolve().parent.parent


def test_requires_python_floor_is_3_10() -> None:
    """Declared floor must match the syntax the code actually uses."""
    # NOTE: parsed with a regex, not tomllib, so this test itself runs
    # on 3.10 where tomllib does not exist yet.
    pyproject = (_repo_root() / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    match = re.search(r'requires-python\s*=\s*"([^"]+)"', pyproject)
    assert match is not None, "requires-python missing from pyproject.toml"
    requires = match.group(1)
    assert "3.10" in requires, (
        f"requires-python must declare the 3.10 floor "
        f"(PEP 604 unions need 3.10+), got: {requires!r}"
    )
    assert "3.9" not in requires, (
        f"requires-python must not admit 3.9, got: {requires!r}"
    )


def test_package_imports_on_supported_interpreter() -> None:
    """The modules that use PEP 604 unions import cleanly here."""
    assert sys.version_info >= (3, 10), (
        f"This test itself needs 3.10+ (running {sys.version.split()[0]})"
    )
    import rabbit  # noqa: F401
    import rabbit.exodus  # noqa: F401
    import rabbit.sims.simulations  # noqa: F401


def test_version_guard_runs_before_submodule_imports() -> None:
    """The fail-fast guard must precede any submodule import."""
    init_src = (_repo_root() / "src" / "rabbit" / "__init__.py").read_text(
        encoding="utf-8"
    )
    guard_pos = init_src.find("sys.version_info")
    assert guard_pos != -1, "version guard missing from __init__.py"
    sims_pos = init_src.find("from rabbit import sims")
    assert sims_pos != -1, "expected submodule import in __init__.py"
    assert guard_pos < sims_pos, (
        "version guard must run before submodule imports, otherwise "
        "Python 3.9 dies with TypeError before reaching the message"
    )
