# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

simName = cube_thermomech_TET10

# Mesh Properties
nElemX = 1
nElemY = 1
nElemZ = 1
eType = TET10

!include common_cube_params.i
!include common_cube_physics.i