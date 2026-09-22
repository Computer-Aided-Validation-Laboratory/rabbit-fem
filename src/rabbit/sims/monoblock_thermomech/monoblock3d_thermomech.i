# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

!include common_monoblock_params.i

[Mesh]
    type = FileMesh
    file = ${mesh_file}
[]

[Variables]
    [temperature]
        family = LAGRANGE
        order = SECOND
        initial_condition = ${coolantTemp}
    []
[]

[Kernels]
    [heat_conduction]
        type = HeatConduction
        variable = temperature
    []
    [time_derivative]
        type = HeatConductionTimeDerivative
        variable = temperature
    []
[]

[Physics/SolidMechanics/QuasiStatic]
    [all]
        strain = SMALL
        incremental = true
        add_variables = true
        material_output_family = MONOMIAL
        material_output_order = FIRST
        generate_output = 'strain_xx strain_xy strain_xz strain_yx strain_yy strain_yz strain_zx strain_zy strain_zz'
    []
[]

!include common_monoblock_materials.i
!include common_monoblock_bcs.i
!include common_monoblock_solver.i
!include common_monoblock_outputs.i
