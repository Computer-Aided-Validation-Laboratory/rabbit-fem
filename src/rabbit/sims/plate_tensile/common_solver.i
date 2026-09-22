# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

[Preconditioning]
    [SMP]
        type = SMP
        full = true
    []
[]

[Executioner]
    type = Transient

    # Best solver options for low element count large deformation plasticity
    solve_type = 'NEWTON'
    petsc_options = '-snes_converged_reason'
    petsc_options_iname = '-pc_type -ksp_type -ksp_gmres_restart'
    petsc_options_value = ' lu       gmres     200'

    l_max_its = 100
    l_tol = 1e-6

    nl_max_its = 50
    nl_rel_tol = 1e-6
    nl_abs_tol = 1e-6

    end_time = ${endTime}
    dt = ${timeStep}
    dtmin = 1e-5
    dtmax = ${timeStep}

    [TimeStepper]
        type = IterationAdaptiveDT
        dt = ${timeStep}
        optimal_iterations = 8
        iteration_window = 2
        growth_factor = 1.2
        cutback_factor = 0.5
    []

    [Predictor]
        type = SimplePredictor
        scale = 1
    []
[]
