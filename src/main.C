// --------------------------------------------------------------------------------------
// Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
//
// Derived from the MOOSE framework:
//   https://mooseframework.inl.gov
//
// Original MOOSE source is licensed under the GNU Lesser General Public License v2.1.
// Original MOOSE copyright and licensing terms are retained.
// See LICENSE and COPYRIGHT for details.
//
// Rabbit modifications:
//   Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
//
// Modified and redistributed as part of Rabbit.
// --------------------------------------------------------------------------------------

#include "MooseMain.h"
#include "RabbitApp.h"

int main(int argc, char *argv[]) {
    Moose::main<RabbitApp>(argc, argv);
    return 0;
}
