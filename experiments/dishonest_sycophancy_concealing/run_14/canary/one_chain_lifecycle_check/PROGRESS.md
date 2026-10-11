# Run 14 one-chain lifecycle progress

Append-only operational record. All timestamps use Pacific Time (`PT`).

- 2026-10-10 17:02 PT — Planned; no attempt created and no jobs launched.
  Source commit: not yet committed
  Attempt: not created
  Jobs: none
  Evidence: source configuration only
  Decision: validate source before launch

- 2026-10-10 17:05 PT — Source validation passed; lifecycle remains unlaunched.
  Source commit: not yet committed
  Attempt: not created
  Jobs: none
  Evidence: 39 tests plus 5 subtests, ShellCheck, Bash syntax, Python compilation
  Decision: commit and synchronize before launching this canary

- 2026-10-10 17:19 PT — Pre-launch audit found and fixed the smoke-to-evaluator handoff.
  Source commit: pending
  Attempt: not created
  Jobs: none
  Evidence: the one-step training path deliberately did not stage its adapter;
  Run 14 now waits for the verified smoke proof, stages that exact adapter, and
  starts the evaluator on demand
  Decision: revalidate, commit, synchronize, then launch

- 2026-10-10 17:24 PT — GPU and runtime preflight passed on FAIR GB300.
  Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
  Attempt: not yet created
  Jobs: preflight `1809164` completed `0:0` in 1m01s
  Evidence: CUDA, BF16, target imports, and representative GPU execution passed
  Decision: launch the bounded one-chain lifecycle canary

- 2026-10-10 17:25 PT — One-chain canary launched with native data generation.
  Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
  Attempt: `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/canary_attempts/20261011T002500Z-c8d5bc8da647`
  Jobs: pipeline `1809175`; research chain `1809185`
  Evidence: retained submission records `research_model=Kimi-K2.6`,
  `data_generation_backend=native`, and `autodata=0`
  Decision: monitor the complete method-to-finding lifecycle

- 2026-10-10 17:43 PT — Method, proposal, native examples, and training smoke passed.
  Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
  Attempt: unchanged
  Jobs: pipeline `1809175` completed `0:0` in 17m29s; training `1809212`
  completed `0:0` in 1m53s
  Evidence: Kimi corrected two contract findings before approval; method source
  SHA-256 `37359a7e8804d811c720f572c01fe599a06270b079ff42286b4afcd12933396d`;
  approved package SHA-256
  `62813494c848efda7ed96b4b76a3e08cc2a72bac7e7a1744378167100e56d16e`;
  eight method-authored examples; one optimizer step; adapter reload validation
  and exact adapter staging passed
  Decision: evaluate the staged adapter; do not retrain

- 2026-10-10 17:52 PT — Fail-closed vLLM evaluation completed and published a score.
  Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
  Attempt: unchanged
  Jobs: evaluator `1809218` completed `0:0` in 8m15s
  Evidence: vLLM 0.25.1, language-model-only mode, atomically merged adapter,
  retained merge manifest, and removed ephemeral checkpoint; `verbalized_ece`
  scored 0.0 on two items versus baseline 0.3874, so the regression gate failed
  Decision: treat the two-item result as workflow evidence only, not a
  scientific conclusion

- 2026-10-10 17:59 PT — Research chain failed only at final finding publication.
  Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
  Attempt: unchanged
  Jobs: research chain `1809185` failed `1:0` after 30m50s
  Evidence: Kimi's first `share_finding` call omitted `results_writeup`; its
  second omitted `run_id`; it then exhausted 24 continuations. The approved
  method, adapter, evaluator proof, and authoritative score remain valid, but
  no forum finding exists and the score/result pair is incomplete
  Decision: preserve all expensive artifacts and perform a finding-only
  recovery; do not repeat method authoring, training, or evaluation

- 2026-10-10 18:04 PT — Finding-only recovery was committed and model roles confirmed.
  Source commit: `d49bef0766eee1733bd1c58c9505151680841d21`
  Attempt: unchanged
  Jobs: no recovery job launched yet
  Evidence: commit `d49bef0` adds a scored-run-only finalizer that requires the
  existing approved run ID and public score, keeps `AAR_AUTODATA=0`, forbids
  method edits/training/evaluation, and requires one durable `share_finding`
  Decision: synchronize the commit to HPC, publish the missing finding, create
  the one-chain lifecycle proof, then launch the five-chain canary

- 2026-10-10 18:06 PT — Exact source synchronization to FAIR HPC completed cleanly.
  Source commit: `fae1191f236f9aaca75a65005e402737fe391c73`
  Attempt: unchanged
  Jobs: no recovery job launched yet
  Evidence: the matching HPC execution worktree is clean at exact commit
  `fae1191f236f9aaca75a65005e402737fe391c73`
  Decision: use this synchronized revision as the recovery starting point

- 2026-10-10 18:07 PT — User explicitly confirmed the presented model-role mapping.
  Source commit: `fae1191f236f9aaca75a65005e402737fe391c73`
  Attempt: unchanged
  Jobs: no recovery job launched yet
  Evidence: research and native generation use Kimi-K2.6 deployment
  `steerability_8-kimi26`; proposal monitoring uses `claude-4-8-opus`;
  training targets the fixed Gemma 4 31B IT base; evaluator inference uses
  Gemma 4 plus the merged adapter through vLLM 0.25.1 in language-model-only
  mode; no evaluator judge, AutoData teacher, row judge, or broker is used
  Decision: the confirmed mapping authorizes finding-only recovery at this
  configuration revision

- 2026-10-10 18:08 PT — Shared Kimi final-finding hardening is in progress.
  Source commit: `fae1191f236f9aaca75a65005e402737fe391c73`
  Attempt: unchanged
  Jobs: no recovery job launched yet
  Evidence: implementation and focused validation are proceeding in a separate
  work thread so the one-chain recovery and later five-chain experiment share
  the same guarded final-finding behavior
  Decision: wait for the shared hardening to be committed and synchronized
  before finding-only recovery; no lifecycle proof has passed yet
