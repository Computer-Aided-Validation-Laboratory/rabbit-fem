# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

simName = stc_therm_unifhf_wrad_std_ad

endTime = 1
timeStep = 1

# Thermal Loads/BCs
toK = 273.15
ambTemp = ${fparse 20.0 + toK}
coolantTemp = ${fparse 160.0 + toK}      # degK

# Induction power
inductionkW = 1.0
surfHeatPower = ${fparse inductionkW * 85}      # W

surfArea = ${fparse 50e-3 * 37e-3}   # m^2
surfHeatFlux = ${fparse surfHeatPower / surfArea} # W.m^-2

# Mesh settings
mesh_file = 'stc_astested.msh'
elem_order = 'SECOND'
