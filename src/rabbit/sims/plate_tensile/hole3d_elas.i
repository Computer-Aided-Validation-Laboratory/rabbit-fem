# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

!include common_load_time.i
!include common_elas_props.i
simName = hole3d_elas

[GlobalParams]
    displacements = 'disp_x disp_y disp_z'
[]

[Mesh]
    type = FileMesh
    file = 'mesh3d_holeplate.msh'
[]

[Physics/SolidMechanics/QuasiStatic]
    [all]
        strain = SMALL
        incremental = true
        add_variables = true
        material_output_family = MONOMIAL
        material_output_order = FIRST
        generate_output = 'vonmises_stress strain_xx strain_yy strain_zz strain_xy strain_yz strain_xz stress_xx stress_yy stress_zz stress_xy stress_yz stress_xz'
    []
[]

!include common_3d_bcs.i
!include common_elas_materials.i
!include common_solver.i

[Postprocessors]
    [react_y_top]
        type = SidesetReaction
        direction = '0 1 0'
        stress_tensor = stress
        boundary = 'bc-top'
    []
    [disp_y_max]
        type = NodalExtremeValue
        variable = disp_y
    []
[]

!include common_outputs.i
