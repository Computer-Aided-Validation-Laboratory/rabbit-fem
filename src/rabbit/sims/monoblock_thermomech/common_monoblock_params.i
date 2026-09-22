# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

simName = monoblock3d_thermomech

endTime = 23
timeStep = 1

coolantTemp = 150.0      # degC
heatTransCoeff = 125.0e3 # W.m^-2.K^-1
surfHeatFlux = 4.67e6    # W.m^-2
timeConst = 1            # s

# Material Properties:
# Thermal Properties: Copper-Chromium-Zirconium
cucrzrDensity = 8816.0  # kg.m^-3
cucrzrThermCond = 343.0 # W.m^-1.K^-1
cucrzrSpecHeat = 407.0  # J.kg^-1.K^-1

# Thermal Properties: Pure (OFHC) Copper
cuDensity = 8829.0  # kg.m^-3
cuThermCond = 384.0 # W.m^-1.K^-1
cuSpecHeat = 406.0  # J.kg^-1.K^-1

# Thermal Properties: Tungsten
wDensity = 19150.0  # kg.m^-3
wThermCond = 127.0  # W.m^-1.K^-1
wSpecHeat = 147.0   # J.kg^-1.K^-1

# Mechanical Properties: Copper-Chromium-Zirconium
cucrzrEMod = 123e9       # Pa
cucrzrPRatio = 0.33      # -

# Mechanical Properties: OFHC Copper
cuEMod = 108e9       # Pa
cuPRatio = 0.33      # -

# Mechanical Properties: Tungsten
wEMod = 387e9       # Pa
wPRatio = 0.29      # -

# Thermo-mechanical coupling
stressFreeTemp = ${coolantTemp} # degC
cucrzrThermExp = 17.7e-6 # 1/degC
cuThermExp = 17.8e-6     # 1/degC
wThermExp = 4.72e-6      # 1/degC

# Mesh file string
mesh_file = 'monoblock3d.msh'
