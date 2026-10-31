[Solvers]
  inactive = 'jacobi'
  [boomeramg]
    type = MFEMHypreBoomerAMG
  []
  [jacobi]
    type = MFEMOperatorJacobiSmoother
  []
  [main]
    type = MFEMHypreGMRES
    preconditioner = boomeramg
    l_tol = 1e-8
    l_max_its = 1000
  []
[]


[Executioner]
  type = MFEMSteady
  device = cpu
[]

