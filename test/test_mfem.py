# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

"""MFEM backend simulation tests (scaffold).

The packaged ``sims/mfem/`` cases need a binary with the MFEM backend
compiled in, which upstream MOOSE only supports with parallel
(MPI) MFEM. Serial wheels skip loudly here; the tests activate
automatically once an MFEM-enabled binary runs them. A gold regression
file (``test_mfem_gold.py``, following ``test_em_gold.py``) still needs
a capable binary to generate its baseline snapshot.
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

    Probes behaviourally (portable across Linux/macOS/Windows): a tiny
    MFEM input is rejected with "not a registered object" when the
    backend is absent. Anything else (including a converged solve)
    means the backend is present.
    """
    try:
        bin_path = get_binary_path()
    except FileNotFoundError:
        return False
    probe = subprocess.run(
        [str(bin_path), "-i", str(mfem_input_path("diffusion"))],
        capture_output=True,
        text=True,
    )
    combined = probe.stdout + probe.stderr
    return "is not a registered object" not in combined


@pytest.mark.parametrize("case_name", MFEM_CASES)
def test_mfem_execution(case_name: str, tmp_path: Path) -> None:
    """Each packaged MFEM case converges and produces Exodus output."""
    if not _mfem_backend_available():
        pytest.skip(
            "MFEM backend not compiled into this binary "
            "(serial builds exclude it; tracked for the MPI variant)."
        )
    input_file = mfem_input_path(case_name)
    mesh_file = mfem_mesh_path(case_name)
    result = run_rabbit(
        input_file,
        extra_args=[f"Mesh/file={mesh_file}"],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    outputs = sorted(tmp_path.glob("*.e"))
    assert outputs, f"No Exodus output produced for MFEM case {case_name}"
