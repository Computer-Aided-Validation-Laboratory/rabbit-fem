# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""Electromagnetics module simulation tests.

Runs each packaged ``sims/em/`` case (libMesh Nedelec physics,
self-contained generated meshes). Passing proves the electromagnetics
module is compiled into the binary: the run fails with unknown-object
errors if it is ever disabled in the Makefile.
"""

from pathlib import Path

import pytest

from rabbit.sims import EM_CASES, em_input_path, run_rabbit


@pytest.mark.parametrize("case_name", EM_CASES)
def test_em_execution(case_name: str, tmp_path: Path) -> None:
    """Each packaged EM case converges and produces Exodus output."""
    input_file = em_input_path(case_name)
    result = run_rabbit(input_file, cwd=tmp_path)
    assert result.returncode == 0
    outputs = sorted(tmp_path.glob("*.e"))
    assert outputs, f"No Exodus output produced for EM case {case_name}"
