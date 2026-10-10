# Run 12 direct model routing

## Purpose

Run 12 was blocked when the cluster-wide `ram-inference-gateway` returned HTTP
503 even though the underlying Kimi deployment was healthy. The gateway has
since recovered: its model registry returns HTTP 200 and `aar_8-kimi26` is
registered. That recovery makes the existing gateway-backed AutoData path the
lowest-risk way to launch promptly, but it does not remove the gateway as a
shared failure point.

The direct-route design remains the gateway-independent hardening path. It
gives AutoData its own Kimi serving deployment and calls Kimi and Gemma Serve
API proxies through trusted local bridges. It does **not** share Kimi capacity
with the AAR researcher.

This document records a design and rollout plan. The dedicated AutoData Kimi
deployment and Run 12 direct routes are not implemented merely by the presence
of this file.

## Decisions

### Verified current call paths

Gateway registration and request routing are different facts. A deployment can
remain registered while a caller uses its direct proxy. Run 12 currently has
these call paths:

```text
AAR researcher
  → local credential-hiding bridge
  → direct proxy for aar_8-kimi26

AutoData Kimi generator
  → ram-inference-gateway
  → deployment selected by X-Deployment-Id

AutoData Gemma target
  → ram-inference-gateway
  → chain/iteration deployment selected by X-Deployment-Id

Gemma evaluator
  → merged candidate loaded directly by vLLM inside its four-GPU Slurm job

Luna judge and approval reviewer
  → Model API
```

The researcher path is verified in `aar/research_loop/kimi_agent.py`: trusted
host code runs `serve.sh generate-opencode-config`, checks the expected model,
and places a local bridge in front of the returned deployment-specific proxy.
The live generated base URL is a Serve API CPU proxy, not the inference-gateway
ingress. `aar_8-kimi26` is also gateway-registered, but that does not make the
researcher's calls use the gateway.

The Gemma evaluator does not need an endpoint because the evaluator is the only
consumer of that candidate. Its trusted Slurm job owns four GPUs, loads the
atomic merged checkpoint locally with vLLM, runs the private held-out suite,
and writes scores. Putting these short-lived candidates behind the gateway
would add deployment, registration, HTTP, cleanup, and shared-control-plane
failure without adding GPU capacity or throughput.

### Why the deferred gateway gate existed

The deferred gate was for the existing AutoData routes, not the AAR researcher.
AutoData's Local Bubblewrap tasks cannot read the protected Serve API ledger or
proxy credentials. Their signed campaign policy instead supplied a stable
gateway URL, an exact model name, and an exact deployment ID. During the HTTP
503 outage, the researcher could still reach Kimi directly, but AutoData could
reach neither its Kimi generator nor its Gemma target.

The launcher held the entire experiment before research began so researchers
would not spend time and bounded attempts producing approved proposals whose
data-generation stage was guaranteed to fail. The old gate checked
`aar_8-kimi26` because that deployment served both researcher and generator
roles. A gateway-backed relaunch with dedicated capacity must instead check an
exact `autodata_8-kimi26` registry entry and a real completion through that
route. Researcher readiness remains a separate direct-proxy preflight.

### Separate the researcher and AutoData Kimi deployments

The AAR researcher continues using its existing deployment:

```text
AAR researcher
  → serve_api_v2 deployment aar_8-kimi26
  → researcher proxy
  → researcher Kimi-K2.6 replicas
```

AutoData receives a new deployment with independent capacity and lifecycle:

```text
AutoData generation
  → dedicated Run 12 AutoData Kimi deployment
  → AutoData-only proxy
  → AutoData-only Kimi-K2.6 replicas
```

The requested deployment ID is `autodata_8-kimi26`. It is not considered ready
until preflight verifies its model identity, replica health, and a real
completion through the selected route. A direct launch additionally verifies
its protected proxy contract; a gateway-backed launch verifies its exact
gateway registration. Start with two replicas, subject to a measured capacity
canary. With the current Kimi model card, each replica uses four GPUs, so two
replicas cost eight GPUs.

### Dedicated AutoData Kimi endpoint

`autodata_8-kimi26` is reserved for AutoData generation. It must not carry AAR
researcher traffic; the researchers continue to use `aar_8-kimi26`. The two
deployments therefore have independent capacity, health, and lifecycle:

```text
AAR researcher traffic → aar_8-kimi26
AutoData generation     → autodata_8-kimi26
```

The production target is two independent four-GPU replicas, preferably one
replica per node, behind the `autodata_8-kimi26` deployment proxy. This is
replication for throughput and failure tolerance, not model sharding across
two nodes. Five chains at concurrency eight can offer up to forty simultaneous
generation requests, so production concurrency must be selected from measured
queue time, tail latency, error rate, and accepted-row throughput.

The deployment has been requested but must remain marked **pending** until the
operator provides readiness and trusted orchestration independently confirms:

- deployment ID `autodata_8-kimi26` and model `Kimi-K2.6`;
- both requested replicas are in the serving phase;
- the selected route passes a deterministic completion from the Run 12
  cluster;
- gateway mode names exactly `autodata_8-kimi26`, while direct mode validates
  the current protected proxy contract; and
- no AutoData request is routed through `aar_8-kimi26`.

### Use direct Serve API proxies, not `ram-inference-gateway`

Trusted host orchestration will:

1. query `serve_api_v2 status <deployment-id> --json`;
2. require the exact deployment and served-model identities;
3. require every requested replica to be ready;
4. resolve the current protected `proxy_info.json` contract;
5. verify a real completion through the direct proxy; and
6. pass only a local bridge URL and non-secret provenance into AutoData.

The direct proxy address is intentionally not treated as permanent. Trusted
orchestration must re-resolve it at every AAR session boundary and after any
Serve API recovery.

### Resolve and manage endpoint lifecycles

We resolve endpoints before the AAR run, but we do not permanently hard-code
their physical addresses.

```text
serve_api_v2 deployment ID
→ trusted controller discovers current proxy address
→ controller verifies model identity and health
→ controller starts local authenticated bridge
→ AutoData receives only the bridge’s localhost address
```

At initial launch:

- Researcher Kimi must be ready and verified.
- Dedicated AutoData Kimi must be ready and verified.
- Each chain’s initial Gemma target must serve the fixed base.
- Evaluator endpoints are managed independently as evaluations occur.

For a planned Gemma update after promotion, we do not let it restart
arbitrarily:

1. Select the accepted adapter.
2. Merge it with the fixed base.
3. Launch a new chain-specific Gemma serving process.
4. Wait until it is healthy.
5. Verify checkpoint hash, chain, iteration, adapter, and model identity.
6. Run a real test completion.
7. Switch the chain’s local Gemma bridge for the next AutoData iteration.
8. Retire the previous target after the switch succeeds.

For an unexpected endpoint failure, Serve API may automatically restart the
underlying server. However, AutoData must pause. The route supervisor
rediscovers the address, revalidates the exact model, tests it, and only then
resumes work.

Thus, restarting the server can be automated, but selecting and accepting its
route is always controlled and verified by our chain controller. We never
simply assume that a restarted endpoint is the correct Gemma model.

### Route both Kimi and Gemma directly

Changing only the Kimi route does not remove Run 12's gateway dependency. One
AutoData task calls three providers:

```text
generated scenario
  → dedicated Kimi generator
  → chain-specific Gemma target probe
  → Luna judge through Model API
```

Kimi and Gemma therefore both need direct routes. Luna remains on the existing
Model API route.

Each active chain session will run two fixed-upstream loopback bridges:

```text
local-bwrap task
  ├─ localhost Kimi bridge
  │    → dedicated AutoData Kimi proxy
  └─ localhost Gemma bridge
       → this chain's current Gemma proxy
```

The Kimi deployment remains stable across the full experiment. Each chain's
Gemma deployment is immutable within one AAR iteration and changes only after
trusted promotion logic has verified and served `base + accepted adapter` for
the next iteration.

### Keep endpoint selection outside the AutoData sandbox

The task must not read the Serve API deployment ledger, choose arbitrary
upstreams, or receive proxy credentials. Endpoint discovery and credential use
belong to trusted AAR orchestration.

AutoData's signed campaign policy will contain:

- loopback generator and target URLs;
- expected served-model and deployment IDs;
- the exact Gemma checkpoint identity;
- token, timeout, cost, and retry ceilings; and
- no proxy key or other credential value.

The operator-only bridge receives the protected `proxy_info.json` path. The
path and deployment identity may be inherited by a trusted Slurm process, but
the file contents must never enter a campaign policy, workspace, task archive,
agent prompt, result, or log.

### Use Local Bubblewrap only

Run 12 is physically configured with:

```text
AAR_AUTODATA_BROKER_RUNNER=local-bwrap
```

The `oci-runner-firecracker-large` string is retained recipe/environment
metadata; it is not the physical Run 12 executor.

This direct-loopback design works because AutoData's Local Bubblewrap executor
uses host networking (`--share-net`). The same design must fail closed if the
physical runner changes. A Firecracker guest's `127.0.0.1` would refer to the
guest rather than the broker host.

## What a model bridge does

The bridge is a small trusted CPU process, not another model and not another
GPU allocation. It:

1. securely reads one deployment's `proxy_info.json`;
2. obtains the current proxy URL and private proxy key;
3. listens only on a loopback address;
4. accepts only the required OpenAI-compatible path;
5. validates the intended local caller when local authentication is enabled;
6. discards caller-supplied routing and authentication headers;
7. injects the proxy's `Authorization` and `X-User-Id` headers;
8. forwards the bounded request to its fixed upstream; and
9. returns the bounded response without logging model content or credentials.

`scripts/loopback_model_auth_bridge.py` already implements the core
upstream-authentication pattern and was exercised by Run 9. Its current
`/healthz` proves only that the bridge process is alive, and it reads the proxy
contract once at startup. Run 12 needs the hardening described below before a
full production launch.

## AutoData compatibility findings

The `autodata_pipelines` documentation and Run 12's pinned AutoData revision
`34f0a22c89a2a40e605afd43f3a7b11c25003ab7` establish the following:

- AutoData has no contract-level dependency on `ram-inference-gateway`.
- Local Bubblewrap shares host networking while retaining its user, PID, IPC,
  UTS, mount, and cgroup isolation.
- Local Bubblewrap rejects a network mode other than host networking.
- Model proxy credentials cannot be placed in non-secret environment settings.
- The broker's daemon workload file currently allowlists only
  `MODEL_API_KEY`.
- AutoData expects external services and credentials to be provisioned out of
  band by trusted operator code.
- AutoData does not natively resolve `serve_api_v2` deployments or
  `proxy_info.json`; that integration belongs to AAR orchestration.

These rules permit the direct route but make a host-side credential bridge
necessary.

## Risks and required mitigations

> Direct routing’s main operational risk is safely tracking changing proxy
> contracts while preserving authentication and exact model identity. Network
> reachability is a required preflight, but Local Bubblewrap on the same
> cluster makes it manageable.

This risk is addressable. Trusted orchestration must rediscover and verify the
route before admitting work, pause admission whenever the route becomes stale
or unhealthy, and resume only after a newly authenticated route passes model-
identity and completion checks. It must never silently fall back to the shared
gateway or a different deployment.

### Proxy relocation

A Serve API proxy hostname can change after restart or redeployment. The
cluster gateway normally hides this movement.

The bridge must securely reload `proxy_info.json` when its file identity or
contents change, or trusted orchestration must restart the bridge before new
tasks are admitted. Existing requests may finish on the old proxy, but new
requests must use only the newly verified contract. A stale proxy must fail
closed rather than silently falling back to the gateway or a different model.

### Local caller isolation

The existing Run 9 bridge authenticates itself to the upstream proxy but does
not authenticate a local caller. Loopback alone may be insufficient if multiple
Slurm jobs share a node.

Before production, select and validate one of these controls:

1. add an attempt-scoped bridge capability injected through AutoData's secret
   path and require it on every local request; or
2. run each bridge and broker on an allocation with a verified exclusive
   network trust boundary.

The first option is the durable design. It requires a small, reviewed extension
to the broker workload-secret allowlist and recipe client so the capability is
injected anonymously and never stored in the campaign policy. Until that is
implemented, an unauthenticated loopback bridge must not be treated as safe on
an untrusted shared node.

### Port collisions

Five chains may be scheduled on the same host. Hard-coding a bridge port such
as `30611` can collide.

Each bridge should bind an operating-system-assigned port, write a mode-0600
readiness contract for its parent process, and be passed to the campaign-policy
builder only after health and identity checks succeed. The trusted parent owns
bridge cleanup.

### Partial gateway removal

Both the Kimi generator URL and Gemma target URL must be direct. The launcher
must reject a mixed configuration in which either still names
`fair-cw-use2-1-ingress-slurm-ingress` or carries the gateway Host header.

### Cross-cluster reachability

Direct proxy hostnames are cluster-local. The broker, bridges, and model
deployments must remain on `fair-cw-use2-1` unless a same-cluster deployment and
network canary are created elsewhere. A URL discovered on `fair-cw-use2-1`
must not be reused from `fair-cw-use2-3`.

### Capacity and fairness

Five chains at AutoData concurrency eight can offer forty simultaneous Kimi
requests. A separate deployment prevents researcher contention but does not
guarantee adequate throughput. Increase replicas only from measured queue,
latency, error-rate, and accepted-row throughput evidence.

### Failure and retry semantics

AutoData, rather than its broker, owns attempt budgets and comparison policy.
A direct-proxy restart can therefore consume useful task-attempt budget if it
is not detected before fan-out. The lifecycle supervisor must pause admission
when either bridge is unready. Infrastructure failures must remain distinct
from legitimate example rejection.

## Recommended immediate Run 12 plan

Now that the gateway is healthy, the fastest plan with the least new
infrastructure risk is:

```text
AAR researcher Kimi → existing direct aar_8-kimi26 route
AutoData Kimi       → gateway → exact autodata_8-kimi26 deployment
AutoData Gemma      → gateway → exact chain/iteration deployment
Gemma evaluation    → local vLLM evaluator job
Luna                → Model API
```

This retains a shared gateway dependency for AutoData, but it reuses the
already-implemented and previously exercised campaign-policy path. The gateway
provides a stable URL, centralized authentication and deployment selection,
and hides proxy relocation. It does not add GPU capacity or increase model
throughput.

Proceed in this order:

1. Wait for `autodata_8-kimi26` to appear in the `fair-cw-use2-1` Serve API
   ledger and verify two serving Kimi-K2.6 replicas.
2. Determine whether its immutable deployment specification enabled gateway
   registration. If not, choose explicitly between redeploying it with
   registration or continuing with the direct-route canary below; do not infer
   registration from deployment health.
3. In gateway mode, require `/v1/models` to list the exact deployment and run a
   real completion with `X-Deployment-Id: autodata_8-kimi26`.
4. Change the AutoData generator binding from `aar_8-kimi26` to
   `autodata_8-kimi26`; keep AAR researchers on their existing direct
   `aar_8-kimi26` route.
5. Keep AutoData's chain-specific Gemma targets on the exact-ID gateway route.
   A promotion launches and validates a new immutable endpoint only when the
   selected incumbent changes; it is not an arbitrary restart every iteration.
6. Update the deferred gate to verify gateway leader health, the dedicated
   AutoData Kimi route, and a real completion before any bounded researcher
   attempt starts.
7. Run the existing one-chain native AutoData canary and require generator,
   target, and judge calls in order with exact deployment provenance.
8. Launch the five chains only after the canary passes. If the gateway fails,
   pause AutoData admission rather than consuming task or AAR attempt budgets.

Direct-routing only Kimi would not remove the shared dependency while AutoData
Gemma still uses the gateway. A genuinely gateway-independent mode therefore
must move both AutoData Kimi and AutoData Gemma behind validated direct bridges.

## Direct-route implementation plan

### Stage 1: dedicated Kimi serving lane

1. Verify the requested `autodata_8-kimi26` Serve API v2 Kimi-K2.6 deployment
   with two replicas, its own coordinator, proxy, and protected
   `proxy_info.json`.
2. Do not claim the shared gateway default. Gateway registration is unnecessary
   for the direct path.
3. Require the expected model card, image/runtime identity, replica count, and
   serving phase.
4. Test the direct proxy with deterministic requests and retain only request
   IDs, latency, token counts, and deployment provenance—not response content.
5. Leave the AAR researcher's `aar_8-kimi26` deployment unchanged.

### Stage 2: harden the loopback bridge

1. Generalize `scripts/loopback_model_auth_bridge.py` so separate instances can
   serve Kimi and Gemma.
2. Add dynamic port selection and a mode-0600 readiness contract.
3. Add local caller authentication or prove exclusive-node isolation.
4. Securely reload a replaced proxy contract without exposing either key.
5. Add a readiness probe that verifies the exact served model and upstream
   deployment, not merely the local HTTP process.
6. Bound paths, request size, response size, timeouts, and forwarded headers.
7. Ensure every error and cleanup path redacts credentials.

### Stage 3: integrate bridge lifecycle with AAR chains

1. Trusted `slurm_aar_chain.sh` setup starts the Kimi and Gemma bridges before
   starting the AutoData broker.
2. It verifies both bridges from the actual chain allocation.
3. It creates the campaign policy only after those checks succeed.
4. It starts the broker and lifecycle supervisor only after the policy is
   frozen.
5. Its exit trap stops both bridges and snapshots broker/native state.
6. The chain controller starts a newly bound Gemma bridge after each promotion
   and switches the next iteration only after a real target completion passes.
7. A failed new Gemma route leaves the chain on its previous verified target.

### Stage 4: update policy and provenance contracts

1. Allow the campaign-policy builder to accept trusted generator and target
   URLs instead of hard-coding the gateway.
2. Require empty gateway Host headers for direct routes.
3. Bind the Kimi deployment ID and direct-proxy contract identity.
4. Continue binding Gemma iteration, incumbent run ID, base checkpoint,
   adapter, merged checkpoint, deployment ID, and checkpoint hash.
5. Fail closed on a direct URL from the wrong cluster, an unexpected model, a
   stale proxy contract, or a mixed gateway/direct configuration.

### Stage 5: test in increasing scope

1. Unit-test proxy-contract validation, secret redaction, caller
   authentication, dynamic ports, reload behavior, and cleanup.
2. Run direct Kimi and direct Gemma completion preflights from the same Slurm
   partition used by a research chain.
3. Run one native AutoData task through Local Bubblewrap. Require exactly three
   provider records in order: generator, target, judge.
4. Confirm the Kimi call used the dedicated AutoData deployment and the target
   call used the exact chain/iteration Gemma deployment and checkpoint hash.
5. Confirm that no proxy key appears in policy, SQLite, artifacts, stdout,
   stderr, or retained results.
6. Run a one-chain, one-meta-iteration, one-production-row canary.
7. Run bounded load canaries at aggregate concurrency 8, 16, and 32. Select
   production concurrency from completed-task and accepted-row throughput, not
   from submitted-task count.

### Stage 6: launch gateway-independent Run 12

1. Preserve the existing gateway-blocked attempt and logs as failure evidence.
2. Stop the deferred gateway-dependent launcher only after the direct-route
   canary succeeds.
3. Launch a fresh checkpoint-backed Run 12 attempt from a pinned, clean source
   commit.
4. Do not report the experiment as running until all five evaluator and chain
   job pairs are recorded.
5. Confirm fail-closed vLLM markers before counting any candidate evaluation.
6. Count progress only through atomic score/result pairs; the target remains
   five durable pairs for each of five chains.

## Direct-route success criteria

The direct-route implementation is ready for the full experiment only when:

- AAR researcher traffic remains on the direct proxy for its original Kimi
  deployment;
- AutoData generator traffic reaches only the dedicated AutoData Kimi
  deployment;
- each chain's target traffic reaches only its current verified Gemma
  deployment;
- no AutoData call depends on `ram-inference-gateway`;
- both routes survive a controlled proxy-contract refresh;
- bridge credentials remain absent from every persistent artifact;
- Local Bubblewrap is the asserted physical runner;
- the one-task native canary records successful Kimi, Gemma, and Luna calls;
- bounded concurrency produces no authentication, routing, or port-collision
  failures; and
- the five-chain launcher emits distinct evaluator, chain, and controller job
  IDs under `/checkpoint/ram/$USER`.
