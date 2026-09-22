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
# pyvale: gmsh,mechanical,transient
#-------------------------------------------------------------------------

#-------------------------------------------------------------------------
#_* MOOSEHERDER VARIABLES - START
!include common_load_time.i
!include common_het_geometry.i
simName = notch2d_elas_het
PRatio = 0.3      # -
EModInf = 200e3         # MPa, modulus far from the bump
PeakEMod = 240e3        # MPa, modulus at the bump centre
#** MOOSEHERDER VARIABLES - END
#-------------------------------------------------------------------------

[Variables]
    [scalar_strain_zz]
    []
[]

[GlobalParams]
    displacements = 'disp_x disp_y'
    out_of_plane_strain = scalar_strain_zz
[]

[Mesh]
    type = FileMesh
    file = 'mesh2d_notchplate.msh'
[]

[Physics/SolidMechanics/QuasiStatic]
    [all]
        strain = SMALL
        planar_formulation = WEAK_PLANE_STRESS
        incremental = true
        add_variables = true
        material_output_family = MONOMIAL
        material_output_order = CONSTANT
        generate_output = 'vonmises_stress strain_xx strain_yy strain_zz strain_xy stress_xx stress_yy stress_zz stress_xy'
    [] 
[]

[BCs]
    [bottom_x]
        type = DirichletBC
        variable = disp_x
        boundary = 'bc-bot-mid'
        value = 0.0
    []
    [bottom_y]
        type = DirichletBC
        variable = disp_y
        boundary = 'bc-bot'
        value = 0.0
    []

    [top_y]
        type = FunctionDirichletBC
        variable = disp_y
        boundary = 'bc-top'
        function = '${topDispRate}*t'
    []
[]

[Functions]
    [youngs_modulus_fn]
        type = ParsedFunction
        expression = '${EModInf} + (${PeakEMod} - ${EModInf}) * exp(-0.5 * (((x - ${centX})/${stdX})^2 + ((y - ${centY})/${stdY})^2))'
    []
[]

[Materials]
    [youngs_modulus_material]
        type = GenericFunctionMaterial
        prop_names = 'youngs_modulus'
        prop_values = 'youngs_modulus_fn'
    []

    [poissons_ratio_material]
        type = GenericConstantMaterial
        prop_names = 'poissons_ratio'
        prop_values = '${PRatio}'
    []

    [elasticity]
        type = ComputeVariableIsotropicElasticityTensor
        args = ''
        youngs_modulus = youngs_modulus
        poissons_ratio = poissons_ratio
    []

    [stress]
        type = ComputeFiniteStrainElasticStress
    []
[]

[AuxVariables]
    [youngs_modulus_out]
        family = MONOMIAL
        order = CONSTANT
    []
[]

[AuxKernels]
    [youngs_modulus_out]
        type = MaterialRealAux
        variable = youngs_modulus_out
        property = youngs_modulus
        execute_on = 'INITIAL TIMESTEP_END'
    []
[]

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
