# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""MFEM backend simulation tests.

Runs each packaged ``sims/mfem/`` case. These need a binary with the
MFEM backend compiled in (MPI variant only — upstream MOOSE has no
serial-MFEM path), so they skip loudly otherwise. The mesh file is
passed as an absolute ``Mesh/file=...`` override so the solve never
depends on the input's directory layout.
"""

from pathlib import Path
import subprocess

import pytest

from rabbit.cli import get_binary_path
from rabbit.sims import (
    MFEM_CASES,
    mfem_input_path,
    mfem_mesh_path,
    run_rabbit,
)


def _mfem_backend_available() -> bool:
    """Whether the packaged binary links the MFEM backend.

    Probes behaviourally (portable across platforms): an MFEM input is
    rejected with "not a registered object" when the backend is absent.
    Anything else (including a converged solve) means it is present.
    """
    bin_path = get_binary_path()
    probe = subprocess.run(
        [str(bin_path), "-i", str(mfem_input_path("diffusion"))],
        capture_output=True,
        text=True,
    )
    combined = probe.stdout + probe.stderr
    return "is not a registered object" not in combined


@pytest.mark.parametrize("case_name", MFEM_CASES)
def test_mfem_execution(case_name: str, tmp_path: Path) -> None:
    """Each packaged MFEM case converges and produces output."""
    if not _mfem_backend_available():
        pytest.skip(
            "MFEM backend not compiled into this binary "
            "(serial builds exclude it; see dev/log_mfem_mpi.md)."
        )
    input_file = mfem_input_path(case_name)
    mesh_file = mfem_mesh_path(case_name)
    result = run_rabbit(
        input_file,
        extra_args=[f"Mesh/file={mesh_file}"],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    outputs = sorted(tmp_path.rglob("*.csv")) + sorted(tmp_path.glob("*.e"))
    assert outputs, f"No output produced for MFEM case {case_name}"
