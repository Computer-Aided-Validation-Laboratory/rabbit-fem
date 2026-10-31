[Solvers]
  active = 'gmres ams'
  [ams]
    type = MFEMHypreAMS
    fespace = HCurlFESpace
  []
  [matrix_free_ams]
    type = MFEMMatrixFreeAMS
  []
  [gmres]
    type = MFEMHypreGMRES
    preconditioner = ams
    l_tol = 1e-8
  []
  [cg]
    type = MFEMCGSolver
    preconditioner = matrix_free_ams
    l_tol = 1e-8
  []
[]


[Executioner]
  type = MFEMSteady
  device = cpu
[]

