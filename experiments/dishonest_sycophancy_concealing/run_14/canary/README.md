# Run 14 recipe comparison canary

## Goal

Exercise the same one-chain training-smoke lifecycle as Run 13 Trial 14 with
the selected v3 recipe.

## Context

See [the experiment specification](../README.md) and
[the runnable gate](v3_recipe_comparison/README.md).

## Launch

Use `v3_recipe_comparison/launch/launch.sh` after the prerequisites and
model-role confirmation documented in the gate. This overview is not an
independent launch entrypoint.

## Pass criteria

Meet the gate's configuration, production-export and training-receipt checks.

## Stop criteria

Stop on recipe/host incompatibility, configuration drift, isolation or
provenance failures, or an evaluator launch.
