# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

#-------------------------------------------------------------------------
# 3Dstc,1mat,thermal,steady
#-------------------------------------------------------------------------

#-------------------------------------------------------------------------
#_* MOOSEHERDER VARIABLES - START

# NOTE: only used for transient solves
endTime = 1
timeStep = 1

# Thermal Loads/BCs
toK = 273.15
ambTemp = ${fparse 20.0 + toK}
coolantTemp = ${fparse 160.0 + toK}      # degK

# NOTE (13 March): Below is completely wrong after talking with JHJ, nominal
# power to the coil is very different to what is simulated due to losses, sim
# actually uses rogowski coil!

# NOTE: 5.9kw is the nominal induction coil power, 85W goes into the sample per
# kw applied to the coil based on a full EM-thermal simulation
# inductionkW = 6.4 # From Adel for exp 2 = 6.4kW, exp 1 = 5.9 kW
# surfHeatPower =${fparse inductionkW*85}      # W
# surfArea = ${fparse 50e-3*37e-3}   # m^2
# surfHeatFlux = ${fparse surfHeatPower/surfArea} # W.m^-2

# Mesh file string
mesh_file = 'stc_astested.msh'
elem_order = 'SECOND'

#** MOOSEHERDER VARIABLES - END
#-------------------------------------------------------------------------

[Mesh]
    type = FileMesh
    file = ${mesh_file}
[]

[Variables]
    [temperature]
        family = LAGRANGE
        order = ${elem_order}
        initial_condition = ${coolantTemp}
    []
[]

[Kernels]
    [heat_conduction]
        type = ADHeatConduction
        variable = temperature
    []
[]

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

    [surf_hf_spat_fun]
        type = PiecewiseBilinear
        data_file = ./data/surf_hf.csv
        xaxis = 0 # x in csv is x geometry for the top surface
        yaxis = 2 # y in csv is z geometry for the top surface
    []
    [surf_hf_scale_fun]
        type = ParsedFunction
        expression = '1.0'
    []
    [surf_hf_fun]
        type = CompositeFunction
        functions = 'surf_hf_scale_fun surf_hf_spat_fun'
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

[BCs]
    [heat_flux_out]
        type = ADConvectiveHeatFluxBC
        variable = temperature
        boundary = 'bc-pipe-htc'
        T_infinity = ${coolantTemp}
        heat_transfer_coefficient = heat_transfer_coefficient
    []
    # [heat_flux_in]
    #     type = ADNeumannBC
    #     variable = temperature
    #     boundary = 'bc-top-heatflux'
    #     value = ${surfHeatFlux}
    # []
    [heat_flux_in]
        type = ADFunctionNeumannBC
        variable = temperature
        boundary = 'bc-top-heatflux'
        function = surf_hf_fun
    []
    [radiation_flux]
        type = ADFunctionRadiativeBC
        variable = temperature
        boundary = 'bc-top-heatflux bc-base-surf bc-left-surf bc-right-surf bc-front-surf bc-back-surf'
        emissivity_function = '1'
        Tinfinity = ${ambTemp}
        stefan_boltzmann_constant = 5.67e-8
        use_displaced_mesh = true
    []
[]

[Executioner]
    type = Transient

    # Best options for thermal solve
    solve_type = 'NEWTON'
    petsc_options = '-snes_converged_reason'
    petsc_options_iname = '-pc_type -pc_hypre_type -ksp_type -ksp_gmres_restart'
    petsc_options_value = ' hypre    boomeramg      gmres     200'

    l_max_its = 200
    l_tol = 1e-6

    nl_max_its = 50
    nl_rel_tol = 1e-6
    nl_abs_tol = 1e-6

    end_time= ${endTime}
    dt = ${timeStep}

    # [Predictor]
    #     type = SimplePredictor
    #     scale = 1
    # []

[]

[Postprocessors]
    [temp_max]
        type = NodalExtremeValue
        variable = temperature
    []
    [temp_avg]
        type = AverageNodalVariableValue
        variable = temperature
    []
[]

[Outputs]
    exodus = true
[]