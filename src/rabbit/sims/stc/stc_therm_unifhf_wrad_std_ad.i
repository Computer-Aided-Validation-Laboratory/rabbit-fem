# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

!include common_stc_params.i

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

!include common_stc_materials.i

[BCs]
    [heat_flux_out]
        type = ADConvectiveHeatFluxBC
        variable = temperature
        boundary = 'bc-pipe-htc'
        T_infinity = ${coolantTemp}
        heat_transfer_coefficient = heat_transfer_coefficient
    []
    [heat_flux_in]
        type = ADNeumannBC
        variable = temperature
        boundary = 'bc-top-heatflux'
        value = ${surfHeatFlux}
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

!include common_stc_solver.i
!include common_stc_outputs.i