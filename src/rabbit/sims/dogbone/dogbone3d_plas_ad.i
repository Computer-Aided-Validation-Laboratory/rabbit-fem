# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

simName = dogbone3d_plas_ad

endTime = 50
elasticTime = 5
timeStep = 1
topDispRate = ${fparse 0.01275e-3 / elasticTime}  # m/s

# Mechanical Properties: SS316L
ss316LEMod = 200e9       # Pa
ss316LPRatio = 0.3      # -
ss316Yield = 300e6
ss316LHardMod = 5000e6     # Pa

[GlobalParams]
    displacements = 'disp_x disp_y disp_z'
[]

[Mesh]
    type = FileMesh
    file = 'dogbone3d.msh'
[]

[Physics/SolidMechanics/QuasiStatic]
    [all]
        strain = FINITE
        incremental = true
        add_variables = true

        use_automatic_differentiation = true

        material_output_family = MONOMIAL
        material_output_order = SECOND

        generate_output = 'vonmises_stress stress_xx stress_yy stress_zz stress_xy stress_yz stress_xz strain_xx strain_yy strain_zz strain_xy strain_yz strain_xz plastic_strain_xx plastic_strain_yy plastic_strain_zz plastic_strain_xy plastic_strain_yz plastic_strain_xz'
    []
[]

[Materials]
    [elasticity]
        type = ADComputeIsotropicElasticityTensor
        youngs_modulus = ${ss316LEMod}
        poissons_ratio = ${ss316LPRatio}
    []
    [radial_return_stress]
        type = ADComputeMultipleInelasticStress
        inelastic_models = 'isoplas'
    []
    [isoplas]
        type = ADIsotropicPlasticityStressUpdate
        yield_stress = ${ss316Yield}
        hardening_constant = ${ss316LHardMod}
        relative_tolerance = 1e-9
        absolute_tolerance = 1e-9
    []
[]

[BCs]
    [bottom_x]
        type = ADDirichletBC
        variable = disp_x
        boundary = 'bc-base-disp'
        value = 0.0
    []
    [bottom_y]
        type = ADDirichletBC
        variable = disp_y
        boundary = 'bc-base-disp'
        value = 0.0
    []
    [bottom_z]
        type = ADDirichletBC
        variable = disp_z
        boundary = 'bc-base-disp'
        value = 0.0
    []

    [top_x]
        type = ADDirichletBC
        variable = disp_x
        boundary = 'bc-top-disp'
        value = 0.0
    []
    [top_y]
        type = ADFunctionDirichletBC
        variable = disp_y
        boundary = 'bc-top-disp'
        function = '${topDispRate}*t'
    []
    [top_z]
        type = ADDirichletBC
        variable = disp_z
        boundary = 'bc-top-disp'
        value = 0.0
    []
[]

[Preconditioning]
    [SMP]
        type = SMP
        full = true
    []
[]

[Executioner]
    type = Transient

    solve_type = 'NEWTON'
    petsc_options = '-snes_converged_reason'
    petsc_options_iname = '-pc_type -ksp_type -ksp_gmres_restart'
    petsc_options_value = 'lu gmres 200'

    l_max_its = 100
    l_tol = 1e-6

    nl_max_its = 50
    nl_rel_tol = 1e-6
    nl_abs_tol = 1e-6

    end_time = ${endTime}
    dt = ${timeStep}

    [Predictor]
        type = SimplePredictor
        scale = 1
    []
[]

[Postprocessors]
    [react_y_top]
        type = ADSidesetReaction
        direction = '0 1 0'
        stress_tensor = stress
        boundary = 'bc-top-disp'
    []
    [disp_y_max]
        type = NodalExtremeValue
        variable = disp_y
    []
    [strain_yy_plas_max]
        type = ElementExtremeValue
        variable = plastic_strain_yy
    []
    [strain_yy_max]
        type = ElementExtremeValue
        variable = strain_yy
    []
    [stress_yy_max]
        type = ElementExtremeValue
        variable = stress_yy
    []
    [stress_vm_max]
        type = ElementExtremeValue
        variable = vonmises_stress
    []
[]

!include common_dogbone_outputs.i