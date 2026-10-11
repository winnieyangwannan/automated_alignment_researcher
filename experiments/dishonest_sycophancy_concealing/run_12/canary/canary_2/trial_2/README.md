# Canary 2 Trial 2

Trial 2 is the next production data-to-training canary. It starts from the
reviewed minimal v1 recipe:

```yaml
recipe_root: aar/autodata_recipes/dishonest_sycophancy_concealing_v1
training_contract:
  objective: sft
  judge_rubric: recipe/judge_rubric.json
```

The rubric path is relative to the selected recipe root. At launch, the strict
Run 12 compiler validates the repository-relative recipe directory and exports
`AAR_AUTODATA_RECIPE_ROOT`; workspace bootstrap then copies that reviewed recipe
into the proposal-bound writable workspace. Native AutoData may modify only the
pipeline's allowlisted mutable paths.

Trial 1 evidence remains under [`../trial_1/`](../trial_1/PROGRESS.md). Trial 2
has not been launched yet. Live status will be recorded in
[`PROGRESS.md`](PROGRESS.md).

## Launch

From the Run 12 directory on FAIR HPC:

```bash
canary/canary_2/trial_2/submit_canary.sh
```

This invokes the shared Run 12 production launcher with Trial 2's local YAML. It
does not launch the five-chain full experiment.
