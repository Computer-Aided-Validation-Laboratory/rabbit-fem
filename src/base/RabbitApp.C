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

#include "RabbitApp.h"
#include "AppFactory.h"
#include "ModulesApp.h"
#include "Moose.h"
#include "MooseSyntax.h"

InputParameters RabbitApp::validParams() {
    InputParameters params = MooseApp::validParams();
    params.set<bool>("use_legacy_material_output") = false;
    params.set<bool>("use_legacy_initial_residual_evaluation_behavior") = false;
    return params;
}

RabbitApp::RabbitApp(InputParameters parameters) : MooseApp(parameters) {
    RabbitApp::registerAll(_factory, _action_factory, _syntax);
}

RabbitApp::~RabbitApp() {}

void RabbitApp::registerAll(Factory &f, ActionFactory &af, Syntax &syntax) {
    ModulesApp::registerAllObjects<RabbitApp>(f, af, syntax);
    Registry::registerObjectsTo(f, {"RabbitApp"});
    Registry::registerActionsTo(af, {"RabbitApp"});
}

void RabbitApp::registerApps() {
    registerApp(RabbitApp);
}

/***************************************************************************************************
 *********************** Dynamic Library Entry Points - DO NOT MODIFY ******************************
 **************************************************************************************************/
extern "C" void RabbitApp__registerAll(Factory &f, ActionFactory &af,
                                       Syntax &s) {
    RabbitApp::registerAll(f, af, s);
}

extern "C" void RabbitApp__registerApps() {
    RabbitApp::registerApps();
}
