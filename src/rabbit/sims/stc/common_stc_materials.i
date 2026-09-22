# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

[Functions]
    [ss_density_fun]
        type = PiecewiseLinear
        data_file = ./data/ss316L_density_K.csv
        format = columns
    []
    [ss_therm_cond_fun]
        type = PiecewiseLinear
        data_file = ./data/ss316L_therm_cond_K.csv
        format = columns
    []
    [ss_therm_spec_heat_fun]
        type = PiecewiseLinear
        data_file = ./data/ss316L_therm_spec_heat_K.csv
        format = columns
    []
[]

[Materials]
    [ss_density]
        type = ADCoupledValueFunctionMaterial
        v = temperature
        prop_name = density
        function = ss_density_fun
        block = 'stc-vol'
    []
    [ss_thermal_conductivity]
        type = ADCoupledValueFunctionMaterial
        v = temperature
        prop_name = thermal_conductivity
        function = ss_therm_cond_fun
        block = 'stc-vol'
    []
    [ss_specific_heat]
        type = ADCoupledValueFunctionMaterial
        v = temperature
        prop_name = specific_heat
        function = ss_therm_spec_heat_fun
        block = 'stc-vol'
    []

    # HTC from sieder-tate with HIVE test conditions
    [coolant_heat_transfer_coefficient]
        type = ADPiecewiseLinearInterpolationMaterial
        xy_data = '
            274 23.6e3
            323 31.9e3
            373 38.8e3
            423 44.4e3
            473 48.9e3
            523 52.4e3
            573 67.6e3
        '
        variable = temperature
        property = heat_transfer_coefficient
        boundary = 'bc-pipe-htc'
    []
[]
