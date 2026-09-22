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
