// --------------------------------------------------------------------------------------
// Rabbit: A lightweight MOOSE distribution for thermo-mechanical simulation
//
// Copyright (c) 2026 scepticalrabbit (Lloyd Fletcher)
// Licensed under the GNU Lesser General Public License v2.1
// See LICENSE for details.
//
// Authors: scepticalrabbit (Lloyd Fletcher)
// --------------------------------------------------------------------------------------

const std = @import("std");

pub fn build(builder: *std.Build) void {
    const target_options = builder.standardTargetOptions(.{});
    const optimize_options = builder.standardOptimizeOption(.{});
    _ = target_options;
    _ = optimize_options;

    const build_python_command = builder.addSystemCommand(&[_][]const u8{
        "uv",
        "run",
        "python",
        "build_rabbit.py",
    });


    const run_build_step = builder.step(
        "build_app",
        "Build rabbit MOOSE distribution using zig cc wrappers",
    );
    run_build_step.dependOn(&build_python_command.step);

    const default_step = builder.getInstallStep();
    default_step.dependOn(&build_python_command.step);
}
