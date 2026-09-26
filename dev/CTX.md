# CONTEXT

You are debugging and fixing this project with the goal of producing robust, maintainable, cross-system solutions.

Your job is not merely to make the current CI run pass. Fix the underlying cause in a way that should work reliably both locally and in clean CI environments.

For every failure:

1. Diagnose before patching

   * Identify the actual root cause.
   * Explain briefly why the failure occurs.
   * Distinguish the root cause from symptoms exposed by CI.
   * Do not make speculative changes simply to see whether CI becomes green.

2. Prefer general fixes over environment-specific fixes

   * Prefer standard, documented behaviour of the language, build system, package manager, compiler and operating system.
   * Avoid depending on incidental details of the current machine or CI runner.
   * Do not hard-code absolute paths, usernames, runner-specific directories, temporary directory names, drive letters, tool installation locations or similar environment details.
   * Derive paths and configuration from the repository, environment, installed tools or documented APIs wherever possible.

3. Preserve cross-platform behaviour

   * Assume this project should work on supported Linux and Windows environments, and macOS where applicable.
   * Be conscious of:

     * `/` versus `\`
     * executable suffixes
     * PATH lookup
     * quoting and whitespace
     * shell differences
     * line endings
     * filesystem case sensitivity
     * permissions
     * temporary directories
     * process invocation
     * environment variables
     * compiler/linker differences
   * Prefer language/library abstractions over manually implementing OS-specific behaviour.
   * If platform-specific code is genuinely necessary, isolate it behind a small, explicit platform boundary.

4. Treat CI as a clean machine

   * Do not assume tools, files, directories, environment variables, caches or previous build artefacts exist unless the workflow explicitly creates them.
   * Builds should succeed from a fresh checkout with the documented dependencies.
   * Do not rely on state left behind by previous workflow steps unless that dependency is deliberate and explicit.

5. Avoid brittle CI workarounds

   * Do not add arbitrary sleeps.
   * Do not hide errors with `|| true`, ignored exit codes or equivalent behaviour.
   * Do not add retries unless the operation is genuinely externally flaky, such as a network service.
   * Do not disable tests simply to get CI green.
   * Do not weaken assertions without demonstrating that the assertion itself was incorrect.
   * Do not pin an obsolete dependency merely because it happens to avoid the immediate failure.
   * Do not special-case a particular CI runner unless there is a documented reason.

6. Keep local and CI behaviour aligned

   * Prefer running the same build/test commands locally and in CI.
   * Put build logic in project scripts/build configuration rather than duplicating substantial logic inside CI YAML.
   * CI should orchestrate the project build, not contain a separate implementation of it.
   * A developer should normally be able to reproduce a CI step with a documented command.

7. Make failures deterministic and informative

   * Fail early when required dependencies or assumptions are missing.
   * Produce useful error messages explaining what is wrong.
   * Do not silently fall back to behaviour that can conceal configuration errors.

8. Minimise changes

   * Make the smallest change that fixes the root cause cleanly.
   * Do not refactor unrelated code while fixing CI.
   * Do not introduce additional abstractions unless they materially improve correctness, portability or maintainability.

9. Add regression protection

   * Where practical, add or update a test that would have caught the underlying problem.
   * Test the invariant we actually depend on, rather than reproducing one particular CI environment.

10. Verify your assumptions

    * Read the relevant existing build scripts, workflows and project configuration before modifying them.
    * Check documentation or existing project conventions when behaviour is uncertain.
    * Do not invent command-line options, environment variables or tool behaviour.

When considering a proposed fix, ask:

> Would this still be the correct solution on a clean developer machine and on a different CI runner six months from now?

If the answer is no, look for a more fundamental solution.

For each fix, report briefly and log in ./dev/log_opencode_fixes.md:

* Root cause
* Why the proposed fix addresses the root cause
* Any platform-specific considerations
* Files changed
* How the fix can be verified
* Any remaining uncertainty

Optimise for correctness, portability and maintainability first. A green CI run is evidence that the solution works, not the objective by itself.

Make sure OS fixes are compartmentalised so that changes to one OS doesn't break the build for another.

We are currently specifically debugging mac builds.

While we are working set a 5 minute timer to check the CI and on first failure on any OS go through the process above and push a robust fix. Then set recurring 5 minute timers to check the CI repeatedly until the next failure on any OS. 
