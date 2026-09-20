//* This file is part of the Rabbit MOOSE distribution.
//* Licensed under LGPL 2.1, please see LICENSE for details.

#include "MooseMain.h"
#include "RabbitApp.h"

int main(int argc, char *argv[]) {
    Moose::main<RabbitApp>(argc, argv);
    return 0;
}
