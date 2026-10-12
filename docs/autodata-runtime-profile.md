# AutoData runtime profiles for AAR

New AAR experiments should use the shared runtime profile instead of copying
concurrency, broker, SQLite, retry, and routing settings from an older run.

## Target-aware default

Set these variables before creating campaign policies or launching research
chains:

```bash
export AAR_AUTODATA=1
export AAR_AUTODATA_PROFILE=target-aware-local-v1
export AAR_AUTODATA_GENERATOR_PROTOCOL=openai_chat_completions
export AAR_AUTODATA_GENERATOR_DEPLOYMENT=<serve_api_v2-deployment-id>
export AAR_KIMI_PROXY_INFO=/checkpoint/ram/shared/vllm_deployments_v2/${AAR_AUTODATA_GENERATOR_DEPLOYMENT}/proxy_info.json
source "${REPO}/scripts/autodata_runtime_profile.sh"
aar_set_autodata_runtime_profile
```

Create every initial and rotated campaign policy with the same profile:

```bash
python -m aar.autodata_campaign_policy create-policy \
  --runtime-profile "${AAR_AUTODATA_PROFILE}" \
  --generator-deployment-id "${AAR_AUTODATA_GENERATOR_DEPLOYMENT}" \
  ...
```

Every campaign policy must declare one supported generator protocol. For
`openai_chat_completions`, the runtime requires and validates the selected
Serve API `proxy_info.json`, then starts the authenticated loopback bridge. For
`model_api_responses`, the runtime removes any stale Kimi proxy variable and
calls the pinned Model API Responses route directly. Missing and unknown
protocols fail closed.

Runtime validation consumes `AAR_AUTODATA_PROFILE_CONFIG` and requires its
strict checked-in profile name to match `AAR_AUTODATA_PROFILE`. Runner,
environment, concurrency, request attempts, lifecycle supervision, digest
reuse, target gates, and provider protocol come from that validated config;
unknown names are not maintained in a second runtime-only registry.

The profile fixes the measured target-aware settings:

- trusted local Bubblewrap broker;
- profile-selected per-chain concurrency (8 by default, or 32 for the explicit
  load-canary profile);
- profile-selected transient request attempts (three by default, or one for the
  explicit load-canary profile);
- orchestration-owned lifecycle supervisor;
- node-local native SQLite and broker ledger with retained snapshots;
- authenticated loopback routing to the selected Kimi deployment; and
- digest-verified reuse policy.

The research-chain entrypoint validates the campaign policy, proxy contract,
and required AutoData features before starting the broker. It rejects a policy
whose target mode, runner, environment, or request-attempt count differs from
the selected profile. Supervised execution creation separately rejects meta or
production manifests whose concurrency differs from the operator profile.

Production manifests must retain the training contract's accepted-row and task
coverage thresholds. The pinned AutoData checkout must support selective
finalization, so production stops after those requirements are satisfied rather
than retrying every failed source task.

## Dataset reuse

The profile sets `AAR_AUTODATA_REUSE_POLICY=digest-verified`, but it does not
search for or trust prior datasets automatically. To reuse a compatible prior
dataset, the operator must explicitly provide its retained state:

```bash
export AAR_AUTODATA_REUSE_STATE=/trusted/prior/run/state.db
```

The research agent can then create a reuse handoff. The training boundary still
verifies native lineage, state/manifest/dataset digests, objective and schema,
rubric version, provider provenance, row count, and consumption receipt.

## Question-only exception

An intentional target-disabled smoke or legacy comparison may select
`question-only-local-v1`, which uses concurrency 64 and one model-request
attempt. It must not be used for a normal target-aware run.

## Multi-chain capacity

Concurrency is per research chain. Five simultaneous chains can therefore
create up to 160 target-aware tasks in flight. Run 12 and Run 13 now use the
measured per-chain profile, but a new provider deployment or a larger chain
count should run an aggregate capacity canary before launch. Do not silently
change the shared profile based on an unmeasured endpoint.

## AutoData revision

Run 12 and Run 13 currently require AutoData
`823c5948854df14664f3168bc5e6c49a2cecb975`. A future upstream revision may
replace that exact pin only after the profile validator confirms it retains
local Bubblewrap, node-local broker-ledger selection, ensurepip-free bootstrap,
and selective production finalization.

On FAIR HPC, new Run 9/12/13 launches default to the dedicated detached
worktree `/storage/home/$USER/autodata-worktrees/aar-optimized-823c594`. This
avoids advancing an AutoData checkout that an existing run may still be using.
