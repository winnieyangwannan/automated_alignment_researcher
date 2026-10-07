# Run 8 implementation and test progress

## Success criterion

An unattended AAR loop must initiate AutoData workspace creation, satisfy the
delegated grounding and pipeline approval policy, execute `meta_optimize`, use
the winning frozen pipeline for production generation, fetch and verify the
resulting dataset, and prove that the AAR method consumed that exact dataset.

Passing isolated AutoData tests, calling a mock HTTP endpoint, or generating a
standalone dataset does not by itself satisfy this criterion.

## Milestones

### 2026-10-06 — Initial discovery (superseded by qualified-route milestone below)

- Confirmed the requested AAR worktree is
  `/home/winnieyangwn/aar-worktrees/autodata` on branch `autodata`.
- Confirmed the canonical framework checkout is
  `/home/winnieyangwn/autodata_pipelines`; the integration targets its `main`
  contracts rather than the historical legal/SandoQ fleet path.
- Audited the existing AAR surface: `autodata_generate`, `autodata_status`, and
  `autodata_fetch` currently target an assumed service; the checked-in contract
  smoke server is not a native AutoData execution.
- Started parallel implementation tracks for the AAR-facing adapter, AAR tool
  and enforcement changes, and a native AutoData end-to-end harness.
- Confirmed the development environment has both Model API and Llama
  passthrough credentials configured without printing either secret.
- Queried the credential-scoped Model API catalog. The exact judge route
  `gpt-5-6-luna` is available. No Kimi route appeared in the listed catalog;
  the configured `Kimi-K2.6` deployment alias still requires an exact route or
  RIFT-tier preflight before the real-provider canary.
- The branch-local `.venv` is absent and direct package installation is blocked
  by DNS. A compatible existing devserver AAR environment is available at
  `/home/winnieyangwn/aar-worktrees/uv/.venv`; focused tests will run against
  the current source through `PYTHONPATH`, without copying that environment.
- No end-to-end run has been claimed yet.

### 2026-10-06 — Native unattended lifecycle passed

- Ran `scripts/autodata_unattended_e2e.py` against the canonical AutoData
  checkout on `main` at `9e623eb25bab4c4ba50642f72ca338f887772e27`.
- The named `aar-research-agent` actor created workspace
  `ws_3c4b1c6492f949f883db6b7d2dedfcd3`.
- The named independent `aar-integrity-monitor` actor completed grounding and
  baseline approvals under the deterministic delegated test policy; no human
  action paused the state machine.
- Native `meta_optimize` execution `exe_61caebbdbdb5495cb81dd737380a35a3`
  completed with fitness `1.0` over 10 source tasks.
- The winning frozen pipeline then ran as native production execution
  `exe_21a47dd1a8df4774b9e6de8ca23b1c9a`, completed with fitness `1.0`, and
  exported 10 deterministic smoke rows.
- Evidence is under ignored run directory
  `experiments/dishonest_sycophancy_concealing/run_8/run/native-e2e-attempt-1/`.
- This passes the native zero-cost orchestration gate. It does **not** yet prove
  invocation through the AAR MCP/HTTP surface, dataset consumption by an AAR
  method, or real Kimi/Luna/SandoQ execution.

### 2026-10-07 — Initial judge/alias preflight (Kimi conclusion superseded below)

- Sent one bounded Responses API request through the configured Model API
  credential to exact served model `gpt-5-6-luna`.
- The request completed and returned the required `OK` response using 12 input
  tokens and 5 output tokens (17 total).
- This confirms judge availability only. No generated row has yet been judged,
  and the exact Kimi-K2.6 generator route remains unresolved.
- Probed both Model API and the Llama passthrough using the friendly names
  `Kimi-K2.6` and `kimi-k2.6`. Model API returned `model_not_found`; the
  passthrough reported that no model properties exist for that name. No
  substitute generator was selected. A real generator preflight requires the
  exact served Kimi model or RIFT tier identifier.

### 2026-10-07 — Canonical framework regression suite passed

- Ran the canonical AutoData `main` unittest suite with its repository root as
  the discovery top-level: 57 tests passed and 1 was skipped.
- A first discovery command used the wrong unittest package root and produced
  three relative-import collection errors; rerunning with `-t` set to the
  AutoData checkout resolved the invocation issue with no code change.

### 2026-10-07 — Final live AAR-agent integration run passed

- Launched the integrated local AAR-facing adapter and then one real bounded
  `AutonomousAgentLoop` session using `claude-opus-4-8`.
- The session was permitted only the AutoData MCP tools; no training,
  evaluation, shell, filesystem, benchmark, or web tool was exposed.
- Observed the agent call, in order:
  `autodata_generate` → `autodata_step` → `autodata_status` →
  `autodata_fetch`.
- `autodata_generate` plus `autodata_step` initiated native workspace creation
  without a human action. Workspace ID:
  `ws_ba518abb101e491a873d735d9737940f`.
- Native meta-optimization execution
  `exe_06c59e617bf846bc826736c9cabb3ad0` completed before production execution
  `exe_532260aa64f34b72bd814b6b3c30f154`.
- The agent fetched 10 verified SFT smoke rows. The fixture method loaded those
  rows through `load_autodata_dataset`, creating and then verifying the required
  consumption receipt for dataset digest
  `f9b4fa7784f591777fbb49aad02139b343ee6b3ff6e8e6666e1f4e2c15f6a2ac`.
- The AAR loop completed one successful session with zero failed sessions. The
  adapter was stopped after evidence collection.
- Retained report:
  `experiments/dishonest_sycophancy_concealing/run_8/run/final-live-agent/agent_smoke_report.json`.
- This completes the unattended AAR → AutoData orchestration and consumption
  test using the deterministic provider. It is not evidence of Kimi generation,
  Luna row judging, SandoQ/Firecracker execution, or model training.

### 2026-10-07 — Shared campaign-budget enforcement added

- Operator controls are sent separately from the agent-authored scientific
  `AUTODATA_SPEC`; unknown spec fields and agent attempts to set models, paths,
  credentials, concurrency, retained rows, or budgets are rejected.
- Jobs with the same `budget_scope_id` now use one persisted service-side
  balance. Provider execution is conservatively serialized per scope, receives
  only the remaining authorization, and cannot report spend above that amount.
- Added a focused test showing that a first job spending `0.6` of a `1.0` cap
  completes and a second `0.6` job in the same scope fails without increasing
  persisted spend past `0.6`.

### 2026-10-07 — Final validation pass

- The focused AAR/AutoData suite passed: 25 tests passed in 5.44 seconds.
- Python compilation passed for every changed Python implementation and test
  file. Shell syntax validation passed for all three changed launch scripts,
  and `git diff --check` found no whitespace errors.
- Ruff was not available in either the current shell or the compatible existing
  AAR virtual environment, so no Ruff result is claimed.
- The requested unattended integration criterion is complete: a real AAR agent
  initiated workspace creation and used AutoData through meta-optimization,
  production, verified fetch, and dataset consumption without a human pause.

## Production gaps after deterministic smoke (superseded by implementation below)

- Configure and preflight the exact served Kimi generator or RIFT tier. The
  friendly aliases `Kimi-K2.6` and `kimi-k2.6` are not accepted by the available
  gateways.
- Implement and approve the AAR-owned scientific recipe and live
  SandoQ/Firecracker backend, then run the two-row Kimi/Luna canary.
- Run the real 16-row provider integration smoke and one complete training and
  isolated-evaluation iteration. None of these production results are claimed
  by the deterministic orchestration test.

### 2026-10-07 — Real production-path preflight and native broker canary

- Re-resolved the configured generator through the supported
  `serve_api_v2` path. Deployment `winnieyangwn-kimi26` is serving with one of
  one workers ready; its exact served model is `Kimi-K2.6` and it is a
  non-default route.
- A qualified host-side probe using
  `X-Deployment-Id: winnieyangwn-kimi26` completed successfully through the
  `fair-cw-use2-1` inference gateway. The prior Model API alias failure was a
  registry mismatch, not a missing Kimi endpoint.
- Launched native AutoData broker job `1743844` for a real
  `oci-runner-firecracker-small` canary. Broker job
  `job_73767df...` successfully obtained a SandoQ Firecracker lease and reached
  the environment's execsidecar, then failed closed with HTTP 401 because the
  configured value was only a placeholder rather than the environment's
  Firecracker Runner auth key. The broker service was stopped after preserving
  the canary evidence.
- Internal SandoQ documentation confirms this execsidecar bearer is a
  per-environment Kubernetes secret protected by the restricted Firecracker
  Runner Auth Key/RAM access path. It cannot be inferred from the model route,
  Model API credential, or SandoQ session identity. No credential value was
  printed or persisted in the repository.
- Production launch therefore requires the authorized operator to install that
  bearer in a user-owned mode-0600 file on HPC. AutoData already accepts this
  file through `--execsidecar-token-file`; the AAR agent never receives or
  approves the secret.
- Added an AAR-owned scientific recipe and live lifecycle driver. The recipe
  creates original honesty/sycophancy-resistance/uncertainty-disclosure SFT
  examples with qualified Kimi generation and GPT-5.6 Luna judging, uses an
  explicit 64-task tuning split plus 32 validation tasks, and drives native
  meta-optimization followed by production through
  `SandoQFirecrackerExecutor`.
- The driver derives a source corpus of 342 tasks for a 256-row target. This is
  aligned with the frozen 75% minimum acceptance constraint: any native corpus
  that passes that constraint necessarily contains at least 256 Luna-accepted
  rows. The driver now explicitly fails unless both the meta-optimization and
  production final full-corpus datasets report `aggregate.metrics.valid >=
  0.75`; counting accepted rows alone cannot bypass the frozen constraint. It
  reserves the exact worst-case task ceiling for one meta iteration
  plus one production iteration, including AutoData's one permitted final
  full-corpus retry in each mode: `7*S + 2*T + 3*V`, plus the two workspace
  dry-run model tasks.
- Provider accounting now uses an executor-side usage-only tee. It observes
  every collected task result before AutoData routes hidden validation into its
  in-memory `_EphemeralArtifacts`, and writes only request ID, model role and
  identity, token counts, cost estimate, and cost basis to an owner-only
  ledger. Hidden task IDs, prompts, responses, metrics, and artifacts are never
  persisted in that ledger. This includes all three 32-task hidden validation
  passes that a visible-artifact scan would miss.
- The live service records the qualified Kimi deployment ID in dataset model
  provenance and takes its wall-clock timeout only from operator configuration,
  not the agent-authored scientific specification. Per-call retry timeouts are
  validated against the recipe's 600-second task envelope.
- Focused recipe/driver and existing integration tests currently pass (28
  tests); Python compilation and whitespace validation also pass.

### 2026-10-07 — Production launcher and pre-chain gates completed

- Added a committed-source launcher for exactly one sequential AAR chain with
  two iterations and one four-GPU vLLM 0.25.1 merged-checkpoint evaluator.
- Frozen operator controls are one $100 campaign cap across both iterations,
  64 accepted SFT rows per iteration, concurrency 4, a 64-task tuning split,
  and 32 hidden validation tasks. The service independently rejects direct HTTP
  attempts to expand the cap, reduce the row target, replace the budget scope,
  change the resource profile, change the safety axis, or request a non-SFT
  view.
- The services job starts the canonical authenticated AutoData broker and live
  adapter separately from the research chain. Before exposing the adapter it
  requires both a native Firecracker lease/image canary and a model-backed
  Firecracker canary that performs one qualified `Kimi-K2.6` generation and one
  `gpt-5-6-luna` judgment. The retained canary report contains usage and
  provenance but no generated prompt or response.
- Secrets remain in owner-only files. Adapter and broker tokens are minted in
  the retained attempt directory; provider credentials are broker/service-side
  and do not enter job manifests. The services job monitors the research-chain
  job and stops the broker and adapter when that chain ends.
- The focused combined AAR/AutoData/launcher suite passed 44 tests. The complete
  repository `tests/` suite passed 244 tests plus 35 subtests. Canonical
  AutoData `main` passed 57 tests with one skip. Full root pytest collection is
  not claimed because the compatible CPU environment intentionally lacks
  PyTorch required by `scripts/hf_bos_gen_test.py`.
- The production submission remains intentionally unstarted because
  `/storage/home/winnieyangwn/aar-worktrees/autodata/.sandoq-firecracker-token`
  does not yet exist. This is the restricted per-environment Firecracker Runner
  bearer that the earlier real lease canary proved is required at execsidecar;
  no code or model-route issue remains in front of submission.

### 2026-10-07 — Run artifacts moved to user HPC storage

- The production submitter now places every new attempt below
  `/storage/home/$USER/aar-runs/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run8_attempts/`.
- The storage root is resolved before use and the launcher fails unless it is
  contained by `/storage/home/$USER/aar-runs`; it also explicitly refuses
  `/checkpoint/ram` as a Run 8 output root.
- The attempt-local AutoData state, fetched datasets, AAR methods and findings,
  training/evaluation logs, merged candidates, score/result pairs, and metadata
  therefore remain in the user's storage space. Existing shared model,
  baseline, and evaluator-program paths may be read as immutable inputs but are
  not Run 8 output destinations.
- `/storage/home` reported approximately 11 TiB available at the time of this
  change. Seven focused launcher tests, shell syntax, and whitespace validation
  passed after the migration.

### 2026-10-07 — Storage-boundary audit hardened the launch

- The submitter now validates the requested root before creating it, confines
  overrides to `/storage/home/$USER/aar-runs`, and rejects symlinked artifact
  parents so an apparently safe path cannot redirect an attempt elsewhere.
- The pipeline and AutoData service jobs independently resolve and validate the
  attempt directory. Their host temporary files use `$ATTEMPT_DIR/tmp`.
- The retained checkpoint literature survey is now an explicitly read-only
  input: Run 8 fails if it is incomplete instead of recovering or surveying
  into `/checkpoint/ram`.
- Agent run/job bookkeeping moved from `/tmp` to `$TEAM_DIR/logs`, and the
  research sandbox exposes the source checkout read-only while leaving only the
  attempt runtime writable.

### 2026-10-07 — Interactive production contract and final verification completed

- Replaced the hardcoded live lifecycle with a persistent prepare/execute
  protocol. The AAR agent now visibly completes native design, grounding,
  pipeline, result-analysis, and candidate-mutation actions. The independent
  integrity monitor alone completes evidence-backed approvals.
- Every native operation reserves campaign budget before model work and settles
  metered Kimi/Luna usage afterward. Unknown failed-call usage consumes the
  conservative reservation rather than silently returning it.
- The completion proof now requires exactly two sequential successful AAR
  sessions and verifies each dataset's native workspace, 64/32 meta split,
  meta-to-production order, Kimi/Luna and SandoQ provenance, action audit,
  exact approval-policy digest, 64 canonical rows, training consumption link,
  submitted-model link, score, and result finding.
- `autodata_fetch` now rejects a symlinked artifact parent as well as symlinked
  leaf files, closing the final storage-boundary issue found by the audit.
- Final validation passed: 63 focused production tests; 269 complete AAR tests
  plus 35 subtests; canonical AutoData `main` 57 tests with one skip; shell
  syntax, ShellCheck, Python compilation, and whitespace validation.
- HPC still has approximately 11 TiB free at `/storage/home`. The production
  Firecracker token file remains absent, so no production submission has been
  launched yet. No output has been written to `/checkpoint/ram` by Run 8.
- The HPC login node installs Bubblewrap but denies its user namespace, so the
  optional login-node unit probe is skipped there. Slurm diagnostic job
  `1744114` ran on the real `g3` compute environment and passed the Bubblewrap
  namespace probe. The production chain retains its mandatory compute-side
  sandbox canary and still fails closed before an agent call if that boundary
  cannot be constructed.
- Obsolete pre-Run-8 broker job `1743168` was explicitly cancelled after
  confirming that no Run 8 attempt had been created and the production token
  gate was still closed. It was not part of the production chain. No Run 8 job
  remains active.

### 2026-10-07 — Production credential gate opened and first launch preflight

- The user installed the Firecracker Runner bearer in the expected HPC file.
  Its owner, mode `0600`, nonempty one-line shape, and Git exclusion were
  verified without reading the secret into logs or source control.
- Regenerated the pinned LLM-Uncertainty-Bench source on HPC with the committed
  preparation script. Both 10,000-row inputs passed their frozen revision,
  byte-size, and SHA-256 checks.
- Production launcher job `1749477` started and failed safely before creating
  any child jobs because the old `aar-gemma-4-31b-it` shared deployment
  snapshot had been removed. The failed attempt is retained at
  `/storage/home/winnieyangwn/aar-runs/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run8_attempts/20261007T193446Z-b6125ac0dc0e`.
- Two existing Gemma deployments were verified healthy on the validated vLLM
  0.25.1 image. Run 8 now resolves its candidate-evaluation worker from the
  live user-owned, no-timeout `winnieyangwn-gemma-4-31B-it` deployment snapshot
  and validates that deployment before an attempt is created. This snapshot is
  a read-only execution input; new Run 8 outputs remain under user storage.

### 2026-10-07 — Real production services and AAR chain launched

- The first model-backed canary reached Kimi but exhausted its 1,536-token
  allowance in reasoning before emitting parseable JSON. The deployed
  Kimi-K2.6 checkpoint's own README and chat template document instant mode as
  `chat_template_kwargs: {"thinking": false}`. A live gateway probe confirmed
  normal completion in 91 output tokens, and the production recipe now pins
  that documented setting for structured generation.
- Fresh attempt
  `/storage/home/winnieyangwn/aar-runs/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run8_attempts/20261007T195117Z-aa76e1f43e1c`
  passed both mandatory production canaries. The native broker canary leased a
  real `oci-runner-firecracker-small` session and executed the pinned image;
  the model-backed canary then retained proof of one Kimi-K2.6 call and one
  `gpt-5-6-luna` call with an accepted schema-valid item.
- Launcher `1749668` emitted distinct production children only after those
  gates passed: AutoData services `1749738`, the four-GPU merged-checkpoint
  vLLM evaluator `1749774`, and one sequential two-iteration AAR chain
  `1749775`. The child manifest is retained in the attempt metadata.
- At this milestone the AutoData service is live; evaluator and research chain
  are submitted and waiting for Slurm placement. Completion still requires two
  atomic score/result pairs and the Run 8 linkage verifier.
