[GlobalParams]
  displacements = 'disp_x disp_y disp_z'
[]

[Mesh]
  type = GeneratedMesh
  dim = 3
  nx = 5
  ny = 2
  nz = 2
  xmin = 0.0
  xmax = 10.0
  ymin = 0.0
  ymax = 2.0
  zmin = 0.0
  zmax = 2.0
[]

[Physics/SolidMechanics/QuasiStatic]
  [./all]
    add_variables = true
    strain = SMALL
    incremental = false
  [../]
[]

[BCs]
  [./fix_x]
    type = DirichletBC
    variable = disp_x
    boundary = 'left'
    value = 0.0
  [../]
  [./fix_y]
    type = DirichletBC
    variable = disp_y
    boundary = 'left'
    value = 0.0
  [../]
  [./fix_z]
    type = DirichletBC
    variable = disp_z
    boundary = 'left'
    value = 0.0
  [../]
  [./pull_x]
    type = FunctionDirichletBC
    variable = disp_x
    boundary = 'right'
    function = '0.1 * t'
  [../]
[]

[Materials]
  [./elasticity]
    type = ComputeIsotropicElasticityTensor
    youngs_modulus = 2.1e5
    poissons_ratio = 0.3
  [../]
  [./stress]
    type = ComputeLinearElasticStress
  [../]
[]

[Executioner]
  type = Transient
  solve_type = 'PJFNK'
  start_time = 0.0
  end_time = 1.0
  dt = 0.5
[]

[Outputs]
  exodus = true
  console = true
[]
