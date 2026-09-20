const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    _ = target;
    _ = optimize;

    const build_python = b.addSystemCommand(&[_][]const u8{
        "uv",
        "run",
        "python",
        "scripts/build_rabbit.py",
    });

    const run_build_step = b.step(
        "build_app",
        "Build rabbit MOOSE distribution using zig cc wrappers",
    );
    run_build_step.dependOn(&build_python.step);

    const default_step = b.getInstallStep();
    default_step.dependOn(&build_python.step);
}
