[Preconditioning]
    [SMP]
        type = SMP
        full = true
    []
[]

[Executioner]
    type = Transient
    solve_type = NEWTON
    # Hypre is available in the MPI wheel.
    petsc_options_iname = '-pc_type -pc_hypre_type -ksp_type -ksp_gmres_restart'
    petsc_options_value = 'hypre boomeramg gmres 30'

    # Balance thermal and displacement Jacobian rows without changing field units.
    automatic_scaling = true
    scaling_group_variables = 'disp_x disp_y disp_z'

    l_max_its = 100
    l_tol = 1e-6
    nl_max_its = 20
    nl_rel_tol = 1e-7
    nl_abs_tol = 1e-7

    start_time = 0.0
    end_time = ${endTime}
    dt = ${timeStep}

    [Predictor]
        type = SimplePredictor
        scale = 1
    []
[]
