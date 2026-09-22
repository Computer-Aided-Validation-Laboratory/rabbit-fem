# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

endTime = 20
timeStep = 1

# Geometric Properties
lengX = 10e-3   # m
lengY = 10e-3   # m
lengZ = 10e-3   # m

# Thermal BCs
coolantTemp = 100.0      # degC
heatTransCoeff = 125.0e3 # W.m^-2.K^-1
surfHeatFlux = 4.67e6    # W.m^-2
timeConst = 1            # s

# Mechanical Loads/BCs
topDispRate = ${fparse 1e-3 / endTime}  # m/s

# Thermal Properties
Density = 8829.0   # kg.m^-3
ThermCond = 384.0  # W.m^-1.K^-1
SpecHeat = 406.0   # J.kg^-1.K^-1

# Mechanical Properties
EMod = 100e9      # Pa
PRatio = 0.33     # -

# Thermo-mechanical coupling
stressFreeTemp = 20   # degC
ThermExp = 17.8e-6    # 1/degC
