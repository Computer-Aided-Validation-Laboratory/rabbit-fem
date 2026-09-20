//* This file is part of the Rabbit MOOSE distribution.
//* Licensed under LGPL 2.1, please see LICENSE for details.

#pragma once

#include "MooseApp.h"

class RabbitApp : public MooseApp {
public:
    static InputParameters validParams();

    RabbitApp(InputParameters parameters);
    virtual ~RabbitApp();

    static void registerApps();
    static void registerAll(Factory &f, ActionFactory &af, Syntax &s);
};
