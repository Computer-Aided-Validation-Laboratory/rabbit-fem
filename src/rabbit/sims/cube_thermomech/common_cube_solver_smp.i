!include common_cube_solver.i

[Executioner]
    # The serial wheel has no Hypre. ILU keeps the small coupled solve cheap.
    petsc_options_iname = '-pc_type -ksp_type -ksp_gmres_restart'
    petsc_options_value = 'ilu gmres 30'
[]
