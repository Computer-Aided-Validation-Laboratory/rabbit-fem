# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

[Postprocessors]
    [temp_max]
        type = NodalExtremeValue
        variable = temperature
    []
    [temp_avg]
        type = AverageNodalVariableValue
        variable = temperature
    []

    [disp_x_max]
        type = NodalExtremeValue
        variable = disp_x
    []
    [disp_y_max]
        type = NodalExtremeValue
        variable = disp_y
    []
    [disp_z_max]
        type = NodalExtremeValue
        variable = disp_z
    []

    [strain_xx_max]
        type = ElementExtremeValue
        variable = strain_xx
    []
    [strain_yy_max]
        type = ElementExtremeValue
        variable = strain_yy
    []
    [strain_zz_max]
        type = ElementExtremeValue
        variable = strain_zz
    []
[]

[Outputs]
    exodus = true
    file_base = ${simName}
[]
