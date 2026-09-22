# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

simName = cube_thermomech_HEX8

# Mesh Properties
nElemX = 2
nElemY = 2
nElemZ = 2
eType = HEX8

!include common_cube_params.i
!include common_cube_physics.i