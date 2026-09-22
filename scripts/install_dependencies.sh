#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

set -euo pipefail

MOOSE_DIR="${MOOSE_DIR:-$HOME/moose}"
MOOSE_JOBS="${MOOSE_JOBS:-$(nproc 2>/dev/null || echo 4)}"
METHODS="opt"

echo "============================================================"
echo " Setting up MOOSE and dependencies at: ${MOOSE_DIR}"
echo " Parallel jobs: ${MOOSE_JOBS}"
echo "============================================================"

# 1. Clone or verify MOOSE repository
if [ ! -d "${MOOSE_DIR}" ]; then
    echo "Cloning MOOSE repository..."
    git clone https://github.com/idaholab/moose.git "${MOOSE_DIR}"
else
    echo "MOOSE directory already exists at ${MOOSE_DIR}."
fi

# 2. Build PETSc
echo "Building PETSc..."
cd "${MOOSE_DIR}"
unset PETSC_DIR PETSC_ARCH
./scripts/update_and_rebuild_petsc.sh \
    --skip-submodule-update \
    --CXXOPTFLAGS="-O3" \
    --COPTFLAGS="-O3" \
    --FOPTFLAGS="-O3"

# 3. Build libMesh
echo "Building libMesh..."
cd "${MOOSE_DIR}"
METHODS="${METHODS}" ./scripts/update_and_rebuild_libmesh.sh --with-mpi

# 4. Build WASP
echo "Building WASP..."
cd "${MOOSE_DIR}"
./scripts/update_and_rebuild_wasp.sh

# 5. Configure MOOSE
echo "Configuring MOOSE..."
cd "${MOOSE_DIR}"
./configure --with-derivative-size=89

echo "============================================================"
echo " MOOSE dependencies installed and configured successfully!"
echo " Export MOOSE_DIR in your environment:"
echo "   export MOOSE_DIR=${MOOSE_DIR}"
echo "============================================================"
