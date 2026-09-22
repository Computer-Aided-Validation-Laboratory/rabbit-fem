# ------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
# Licensed under the GNU Lesser General Public License v2.1
# See LICENSE for details.
#
# Authors: scepticalrabbit (Lloyd Fletcher)
# ------------------------------------------------------------------------------

from pathlib import Path
import numpy as np

def main() -> None:
    ss316L_temp = np.array(
        [[20,],
         [50,],
         [100,],
         [150,],
         [200,],
         [250,],
         [300,],
         [350,],
         [400,],
         [450,],
         [500,],
         [550,],
         [600,],
         [650,],
         [700,],
         [750,],
         [800,],
         [850,],
         [900,],
         [950,],
         [1000,],
         ]
    )

    ss316L_therm_exp = np.array(
        [[20,15.3e-6],
         [50,15.5e-6],
         [100,15.9e-6],
         [150,16.2e-6],
         [200,16.6e-6],
         [250,16.9e-6],
         [300,17.2e-6],
         [350,17.5e-6],
         [400,17.8e-6],
         [450,18.0e-6],
         [500,18.3e-6],
         [550,18.5e-6],
         [600,18.7e-6],
         [650,18.9e-6],
         [700,19.0e-6],
         [750,19.2e-6],
         [800,19.3e-6],
         [850,19.5e-6],
         [900,19.6e-6],
         [950,19.7e-6],
         [1000,19.7e-6],
         ]
    )

    ss316L_mech_elas_mod = np.array(
        [[20,200e9],
         [100,193e9],
         [150,189e9],
         [200,185e9],
         [250,180e9],
         [300,176e9],
         [350,172e9],
         [400,168e9],
         [450,164e9],
         [500,159e9],
         [550,155e9],
         [600,151e9],
         [650,147e9],
         [700,142e9],
         ]
    )

    ss316L_density = np.array(
        [[20,7930],
         [50,7919],
         [100,7899],
         [150,7879],
         [200,7858],
         [250,7837],
         [300,7815],
         [350,7793],
         [400,7770],
         [450,7747],
         [500,7724],
         [550,7701],
         [600,7677],
         [650,7654],
         [700,7630],
         [750,7606],
         [800,7582],
         ]
    )

    ss316L_therm_cond = np.array(
        [[20,14.28],
         [50,14.73],
         [100,15.48],
         [150,16.23],
         [200,16.98],
         [250,17.73],
         [300,18.49],
         [350,19.24],
         [400,19.99],
         [450,20.74],
         [500,21.49],
         [550,22.24],
         [600,22.99],
         [650,23.74],
         [700,24.49],
         [750,25.25],
         [800,26.00],
         ]
    )

    ss316L_therm_spec_heat = np.array(
        [[20,472],
         [50,485],
         [100,501],
         [150,512],
         [200,522],
         [250,530],
         [300,538],
         [350,546],
         [400,556],
         [450,567],
         [500,578],
         [550,590],
         [600,601],
         [650,610],
         [700,615],
         [750,615],
         [800,607],
         ]
    )

    ss316L_mech_yield_stress = np.array(
        [[20,190e6],
         [100,165e6],
         [150,150e6],
         [200,137e6],
         [250,127e6],
         [300,119e6],
         [350,113e6],
         [400,108e6],
         [450,103e6],
         [500,100e6],
         [550,98e6],
         ]
    )
    # Convert minimum to average
    ss316L_mech_yield_stress[:,1] = 1.28*ss316L_mech_yield_stress[:,1]

    ss316L_mech_uts = np.array(
        [[20,490e6],
         [100,430e6],
         [150,410e6],
         [200,390e6],
         [250,385e6],
         [300,380e6],
         [350,380e6],
         [400,380e6],
         [450,380e6],
         [500,360e6],
         [550,3506],
         ]
    )
    # Convert minimum to average
    ss316L_mech_uts[:,1] = 1.28*ss316L_mech_uts[:,1]

    ss316L_temp = np.array(
        [[20,],
         [50,],
         [100,],
         [150,],
         [200,],
         [250,],
         [300,],
         [350,],
         [400,],
         ]
    )
    ss316L_mech_unif_elong_func_pc = (
        lambda t: -4.72e-07 * t**3
        + 5.14e-04 * t**2
        - 1.79e-01 * t
        + 5.10e01
    )
    ss316L_mech_unif_elong = ss316L_mech_unif_elong_func_pc(ss316L_temp)
    ss316L_mech_unif_elong = np.hstack((ss316L_temp,ss316L_mech_unif_elong))

    print(ss316L_mech_unif_elong)

    # Save all material data files
    save_path = Path("simulations/data")
    fmt_str = "%10.5e"
    np.savetxt(save_path/"ss316L_density.csv",
               ss316L_density,fmt=fmt_str,
               delimiter = ",")
    np.savetxt(save_path/"ss316L_therm_cond.csv",
               ss316L_therm_cond,fmt=fmt_str,
               delimiter = ",")
    np.savetxt(save_path/"ss316L_therm_spec_heat.csv",
               ss316L_therm_spec_heat,fmt=fmt_str,
               delimiter = ",")
    np.savetxt(save_path/"ss316L_therm_exp.csv",
               ss316L_therm_exp,fmt=fmt_str,
               delimiter = ",")
    np.savetxt(save_path/"ss316L_mech_elas_mod.csv",
               ss316L_mech_elas_mod,fmt=fmt_str,
               delimiter = ",")
    np.savetxt(save_path/"ss316L_mech_yield_stress.csv",
               ss316L_mech_yield_stress,fmt=fmt_str,
              delimiter = ",")

if __name__ == "__main__":
    main()
