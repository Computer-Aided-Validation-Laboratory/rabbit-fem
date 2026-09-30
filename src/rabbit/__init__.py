# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Rabbit FEM: Lightweight MOOSE distribution."""

import sys

# Fail fast on unsupported interpreters. The package uses PEP 604
# ``X | Y`` annotations (e.g. in rabbit.sims.simulations and
# rabbit.exodus), which evaluate at ``def`` time and require Python
# 3.10+. pip enforces ``requires-python`` for wheel installs, but
# conda copies, system pythons, or direct checkouts can bypass it and
# would otherwise die deep inside with
# ``TypeError: unsupported operand type(s) for |``. This guard runs
# before any submodule import (importing rabbit.sims executes this
# parent __init__ first) so every entry point gets the same message.
if sys.version_info < (3, 10):
    raise RuntimeError(
        f"rabbit-fem requires Python 3.10 or newer "
        f"(running {sys.version.split()[0]}). "
        "Please create a Python 3.10+ environment; "
        "Python 3.9 reached end-of-life in October 2025."
    )

from rabbit import sims
from rabbit.cli import get_binary_path, get_library_dir
from rabbit.sims import (
    DataSetError,
    EDims,
    EElemType,
    SimDataError,
    run_gmsh,
    run_rabbit,
)

__version__ = "2026.9.0"

__all__ = [
    "DataSetError",
    "EDims",
    "EElemType",
    "SimDataError",
    "__version__",
    "get_binary_path",
    "get_library_dir",
    "run_gmsh",
    "run_rabbit",
    "sims",
]
