# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

simName = dogbone2d_elas
!include common_dogbone_params.i

[Mesh]
    type = FileMesh
    file = 'dogbone2d.msh'
[]

!include common_2d_bcs.i

[Physics/SolidMechanics/QuasiStatic]
    [all]
        strain = FINITE
        incremental = true
        add_variables = true

        material_output_family = MONOMIAL
        material_output_order = FIRST

        generate_output = 'vonmises_stress stress_xx stress_yy stress_xy strain_xx strain_yy strain_xy'
    []
[]

[Materials]
    [elasticity]
        type = ComputeIsotropicElasticityTensor
        youngs_modulus = ${ss316LEMod}
        poissons_ratio = ${ss316LPRatio}
    []
    [stress]
        type = ComputeFiniteStrainElasticStress
    []
[]

!include common_dogbone_solver.i

[Postprocessors]
    [react_y_top]
        type = SidesetReaction
        direction = '0 1 0'
        stress_tensor = stress
        boundary = 'bc-top-disp'
    []

    [disp_y_max]
        type = NodalExtremeValue
        variable = disp_y
    []

    [stress_vm_max]
        type = ElementExtremeValue
        variable = vonmises_stress
    []
[]

!include common_dogbone_outputs.i
