!include common_cube_solver.i

[Executioner]
    # Parallel algebraic multigrid is available in the MPI wheel.
    petsc_options_iname = '-pc_type -pc_hypre_type -ksp_type -ksp_gmres_restart'
    petsc_options_value = 'hypre boomeramg gmres 30'
[]
