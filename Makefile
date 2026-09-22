# --------------------------------------------------------------------------------------
# Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
#
# Derived from the MOOSE framework:
#   https://mooseframework.inl.gov
#
# Original MOOSE source is licensed under the GNU Lesser General Public License v2.1.
# Original MOOSE copyright and licensing terms are retained.
# See LICENSE and COPYRIGHT for details.
#
# Rabbit modifications:
#   Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
#
# Modified and redistributed as part of Rabbit.
# --------------------------------------------------------------------------------------

# Optional Environment variables
# MOOSE_DIR        - Root directory of the MOOSE project

# Use the MOOSE submodule if it exists and MOOSE_DIR is not set
MOOSE_SUBMODULE    := $(CURDIR)/moose
ifneq ($(wildcard $(MOOSE_SUBMODULE)/framework/Makefile),)
  MOOSE_DIR        ?= $(MOOSE_SUBMODULE)
else
  MOOSE_DIR        ?= $(shell dirname `pwd`)/moose
endif

# framework
FRAMEWORK_DIR      := $(MOOSE_DIR)/framework
include $(FRAMEWORK_DIR)/build.mk
include $(FRAMEWORK_DIR)/moose.mk

################################## MODULES ####################################
ALL_MODULES                 := no

CHEMICAL_REACTIONS          := no
CONTACT                     := yes
ELECTROMAGNETICS            := no
EXTERNAL_PETSC_SOLVER       := no
FLUID_PROPERTIES            := no
FSI                         := no
FUNCTIONAL_EXPANSION_TOOLS  := no
GEOCHEMISTRY                := no
HEAT_TRANSFER               := yes
LEVEL_SET                   := no
MISC                        := no
NAVIER_STOKES               := no
OPTIMIZATION                := no
PERIDYNAMICS                := no
PHASE_FIELD                 := no
POROUS_FLOW                 := no
RAY_TRACING                 := no
RDG                         := no
REACTOR                     := no
RICHARDS                    := no
SOLID_MECHANICS             := yes
STOCHASTIC_TOOLS            := no
THERMAL_HYDRAULICS          := no
XFEM                        := no

include $(MOOSE_DIR)/modules/modules.mk
###############################################################################

# dep apps
APPLICATION_DIR    := $(CURDIR)
APPLICATION_NAME   := rabbit
BUILD_EXEC         := yes
GEN_REVISION       := no
include            $(FRAMEWORK_DIR)/app.mk

###############################################################################
