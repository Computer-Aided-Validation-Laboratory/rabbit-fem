# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

simName = dogbone3d_elas
!include common_dogbone_params.i

[Mesh]
    type = FileMesh
    file = 'dogbone3d.msh'
[]

!include common_3d_bcs.i

[Physics/SolidMechanics/QuasiStatic]
    [all]
        strain = FINITE
        add_variables = true
        new_system = true
        formulation = UPDATED

        volumetric_locking_correction = false
        material_output_family = MONOMIAL
        material_output_order = FIRST

        generate_output = 'vonmises_cauchy_stress cauchy_stress_xx cauchy_stress_yy cauchy_stress_zz cauchy_stress_xy cauchy_stress_yz cauchy_stress_xz strain_xx strain_yy strain_zz strain_xy strain_yz strain_xz'
    []
[]

[Materials]
    [elasticity]
        type = ComputeIsotropicElasticityTensor
        youngs_modulus = ${ss316LEMod}
        poissons_ratio = ${ss316LPRatio}
    []
    [stress]
        type = ComputeLagrangianLinearElasticStress
    []
[]

!include common_dogbone_solver.i

[Postprocessors]
    [react_y_top]
        type = SidesetReaction
        direction = '0 1 0'
        stress_tensor = cauchy_stress
        boundary = 'bc-top-disp'
    []
    [disp_y_max]
        type = NodalExtremeValue
        variable = disp_y
    []
    [stress_vm_max]
        type = ElementExtremeValue
        variable = vonmises_cauchy_stress
    []
[]

!include common_dogbone_outputs.i