# Autodata tool integration and smoke plan

## Decision

- Expose Autodata through an opt-in in-process SDK MCP server; keep Autodata, SandoQ,
  gateway, and provider credentials outside the AAR sandbox.
- The operator pins one immutable pipeline revision with `AAR_AUTODATA_SHA`; tool calls
  cannot select or override a branch/ref.
- The agent declares one literal `AUTODATA_SPEC` inside the proposed method code. The
  integrity monitor hashes that code before approval. Generation is allowed only after
  approval and is bound to the proposal-issued `run_id`.
- Store fetched artifacts under `$TEAM_DIR/autodata/<run_id>/`. Training loads them using
  `AAR_CURRENT_RUN_ID` and verifies schema, run binding, pipeline SHA, row count, and
  dataset SHA-256.
- Strong generators, including Kimi, are allowed when their exact roles, generation
  procedure, sampling, filtering, and retained size are disclosed.

## HTTP service contract

- `POST /v1/jobs`: `{run_id, pipeline_sha, spec}` -> `{job_id, state, ...}`.
- `GET /v1/runs/<run_id>` -> durable state/progress/provenance summary.
- `GET /v1/runs/<run_id>/artifacts` -> `{rows, manifest}` after completion.
- Artifact manifests use schema `aar.autodata.dataset/v1` and contain `run_id`,
  `pipeline_sha`, `row_count`, and `dataset_sha256`.

## Validation

- `env PYTHONPATH=$PWD /home/winnieyangwn/aar-worktrees/uv/.venv/bin/python -m pytest tests -q`
  passed: 204 tests and 35 subtests.
- The first FAIR launch is an integration smoke. The currently available legal v0
  Autodata recipe produces question/rubric records and is not a production AAR safety
  recipe; production use requires a safety-domain recipe plus a verified SFT/DPO export.
