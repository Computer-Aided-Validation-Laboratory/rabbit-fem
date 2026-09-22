# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

endTime = 10
timeStep = 1

# Mechanical Loads/BCs
topDispRate = ${fparse 0.12e-3 / endTime}  # m/s

# Mechanical Properties: SS316L
ss316LEMod = 200e9       # Pa
ss316LPRatio = 0.3      # -
