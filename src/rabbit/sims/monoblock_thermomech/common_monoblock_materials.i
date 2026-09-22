# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

[Materials]
    [cucrzr_thermal]
        type = HeatConductionMaterial
        thermal_conductivity = ${cucrzrThermCond}
        specific_heat = ${cucrzrSpecHeat}
        block = 'pipe-cucrzr'
    []
    [cucrzr_density]
        type = GenericConstantMaterial
        prop_names = 'density'
        prop_values = ${cucrzrDensity}
        block = 'pipe-cucrzr'
    []
    [cucrzr_elasticity]
        type = ComputeIsotropicElasticityTensor
        youngs_modulus = ${cucrzrEMod}
        poissons_ratio = ${cucrzrPRatio}
        block = 'pipe-cucrzr'
    []
    [cucrzr_expansion]
        type = ComputeThermalExpansionEigenstrain
        temperature = temperature
        stress_free_temperature = ${stressFreeTemp}
        thermal_expansion_coeff = ${cucrzrThermExp}
        eigenstrain_name = thermal_expansion_eigenstrain
        block = 'pipe-cucrzr'
    []

    [copper_thermal]
        type = HeatConductionMaterial
        thermal_conductivity = ${cuThermCond}
        specific_heat = ${cuSpecHeat}
        block = 'interlayer-cu'
    []
    [copper_density]
        type = GenericConstantMaterial
        prop_names = 'density'
        prop_values = ${cuDensity}
        block = 'interlayer-cu'
    []
    [copper_elasticity]
        type = ComputeIsotropicElasticityTensor
        youngs_modulus = ${cuEMod}
        poissons_ratio = ${cuPRatio}
        block = 'interlayer-cu'
    []
    [copper_expansion]
        type = ComputeThermalExpansionEigenstrain
        temperature = temperature
        stress_free_temperature = ${stressFreeTemp}
        thermal_expansion_coeff = ${cuThermExp}
        eigenstrain_name = thermal_expansion_eigenstrain
        block = 'interlayer-cu'
    []

    [tungsten_thermal]
        type = HeatConductionMaterial
        thermal_conductivity = ${wThermCond}
        specific_heat = ${wSpecHeat}
        block = 'armour-w'
    []
    [tungsten_density]
        type = GenericConstantMaterial
        prop_names = 'density'
        prop_values = ${wDensity}
        block = 'armour-w'
    []
    [tungsten_elasticity]
        type = ComputeIsotropicElasticityTensor
        youngs_modulus = ${wEMod}
        poissons_ratio = ${wPRatio}
        block = 'armour-w'
    []
    [tungsten_expansion]
        type = ComputeThermalExpansionEigenstrain
        temperature = temperature
        stress_free_temperature = ${stressFreeTemp}
        thermal_expansion_coeff = ${wThermExp}
        eigenstrain_name = thermal_expansion_eigenstrain
        block = 'armour-w'
    []

    [stress]
        type = ComputeFiniteStrainElasticStress
    []
[]
