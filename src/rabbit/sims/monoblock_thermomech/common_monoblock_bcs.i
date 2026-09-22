# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

[GlobalParams]
    displacements = 'disp_x disp_y disp_z'
[]

[BCs]
    [heat_flux_in]
        type = FunctionNeumannBC
        variable = temperature
        boundary = 'bc-top-heatflux'
        function = '${fparse surfHeatFlux}*(1-exp(-(1/${timeConst})*t))'
    []
    [heat_flux_out]
        type = ConvectiveHeatFluxBC
        variable = temperature
        boundary = 'bc-pipe-heattransf'
        T_infinity = ${coolantTemp}
        heat_transfer_coefficient = ${heatTransCoeff}
    []

    [mech_bc_c_dispy]
        type = DirichletBC
        variable = disp_y
        boundary = 'bc-base-disp'
        value = 0.0
    []
    [mech_bc_c_dispx]
        type = DirichletBC
        variable = disp_x
        boundary = 'bc-c-point-xyz-mech'
        value = 0.0
    []
    [mech_bc_c_dispz]
        type = DirichletBC
        variable = disp_z
        boundary = 'bc-c-point-xyz-mech'
        value = 0.0
    []

    [mech_bc_l_dispz]
        type = DirichletBC
        variable = disp_z
        boundary = 'bc-l-point-yz-mech'
        value = 0.0
    []
    [mech_bc_r_dispz]
        type = DirichletBC
        variable = disp_z
        boundary = 'bc-r-point-yz-mech'
        value = 0.0
    []

    [mech_bc_f_dispx]
        type = DirichletBC
        variable = disp_x
        boundary = 'bc-f-point-xy-mech'
        value = 0.0
    []
    [mech_bc_b_dispx]
        type = DirichletBC
        variable = disp_x
        boundary = 'bc-b-point-xy-mech'
        value = 0.0
    []
[]
