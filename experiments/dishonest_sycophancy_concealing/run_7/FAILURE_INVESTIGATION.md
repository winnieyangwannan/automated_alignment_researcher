# Run 7 failure investigation

Snapshot date: 2026-10-07 UTC

This report distinguishes a completed evaluation (an atomic public score and
finding pair) from a started session. A candidate rejected by a fail-closed
health gate is a real method failure, but it is not a completed evaluation.

## Original attempt

The checkpoint-backed attempt started 30 sessions. Fourteen produced durable
score/finding pairs, eleven ended without a score, and the final five in-flight
sessions were interrupted when the experiment's checkpoint NFS namespace
became unresolvable.

| Chain   | Started | Scored | Failed before score | NFS-interrupted |
| ------- | ------: | -----: | ------------------: | --------------: |
| alpha   |       7 |      2 |                   4 |               1 |
| beta    |       6 |      4 |                   1 |               1 |
| gamma   |       5 |      4 |                   0 |               1 |
| delta   |       6 |      3 |                   2 |               1 |
| epsilon |       6 |      1 |                   4 |               1 |
| Total   |      30 |     14 |                  11 |               5 |

The eleven pre-score failures did not share one cause:

| Failure class                         | Count | Affected sessions                         | Evidence and disposition |
| ------------------------------------- | ----: | ----------------------------------------- | ------------------------ |
| Removed vLLM launcher snapshot        |     2 | alpha iterations 1 and 6                  | Training and adapter merge succeeded, then the named deployment's `worker_vllm.sh` disappeared. Infrastructure failure. |
| Candidate output-health rejection     |     4 | alpha iteration 4; epsilon iterations 2–4 | Full evaluation ran, but excessive non-termination/truncation crossed the fail-closed gate. These are method failures; do not relax the gate. |
| Externally recycled evaluator cohort  |     1 | epsilon iteration 1                       | All evaluator workers received the same external termination signal. Infrastructure failure. |
| Non-finite adapter weights            |     1 | beta iteration 2                          | Submission validation found NaN/Inf weights before evaluation. Candidate/training instability; fail-fast behavior was correct. |
| Agent/API connection refusal          |     2 | delta pre-score sessions                  | Claude Agent SDK ended with `ConnectionRefused` before a candidate score existed. Control-plane failure. |
| Deliberate operator containment       |     1 | alpha iteration 5                         | Two unchanged retrain attempts were canceled after the agent ignored an operator correction that the previous candidate had failed a health gate. This was not a hidden deduplication guard. |

The five NFS-interrupted sessions are a separate storage incident, not five
independent method failures.

## Storage continuation

The continuation keeps durable state under `/storage/home`, reconstructs the
14 retained findings, and uses node-local temporary 62.5 GB merged checkpoints.
Its first candidate round produced three scores and two failures. The two
failures shared one cause: Slurm spread each four-GPU evaluator across two
nodes, while the evaluator launches four local GPU replicas. The replicas for
non-local GPU indices failed with NVML invalid-argument errors.

The evaluator launcher now requires `--nodes=1 --ntasks=1`. The malformed jobs
were canceled and replaced by jobs 1751149 and 1751150; both replacements have
one node, one task, and four GPUs. The other three evaluators were already
single-node and remain healthy.

## Fix status

| Failure mode                         | Status | Action |
| ------------------------------------ | ------ | ------ |
| Experiment checkpoint NFS loss       | Fixed  | Durable state moved to `/storage/home`; temporary merged checkpoints use node-local storage and retain manifests. |
| Multi-node four-GPU evaluator        | Fixed  | Evaluator submissions explicitly request one node and one task; replacements are active. |
| Deployment launcher path removal     | Fixed for new/replacement workers | Each attempt atomically copies and tree-hash-verifies the validated `serve_api_v2` launcher runtime under its durable `/storage` root. |
| Candidate truncation/non-termination | Working as designed | Keep the 10% health gate. Agents must change the training objective/data/terminator behavior; rejected checkpoints must not be rescored unchanged. |
| Non-finite adapter                   | Working as designed | Submission validation rejects NaN/Inf weights before publishing `.submitted`. Earlier training-loss checks would improve efficiency but are not required for correctness. |
| Agent/API connection refusal         | Open   | A blind whole-session retry is unsafe after tools may have caused training/submission side effects. Implement only a pre-tool retry or true SDK session resume after validating SDK support. |
| Ignored operator correction          | Open   | Do not infer a scheduler bug. A future prompt/memory change may make operator corrections higher priority, but the currently modified prompt files were intentionally left untouched. |

## Remaining semantic risk

`max_iterations` counts sessions that begin, including failures. The recovery
budgets preserve a combined cap of 50 started sessions per chain. If the desired
endpoint is instead 50 completed score/finding pairs per chain, deficits must be
measured at termination and filled with explicit top-up sessions.
