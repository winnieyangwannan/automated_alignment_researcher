# Replication v0 progress

Date: 2026-09-30

## GPT judge decision

- Use `gpt-5.6-sol` for every GPT-backed role unless the user explicitly
  specifies another GPT model.
- FAIR Model API exposes it under the canonical identifier `gpt-5-6-sol`.
- Use `https://api.meta.ai/v1/responses` with `MODEL_API_KEY`; do not route
  replication-v0 judge calls to public `api.openai.com`.

## Model API smoke result

- Slurm job: `1658751`
- Environment: CPU-only job submitted with account `ram`, partition `g3`, and
  QoS `g3_ram_high`
- Discovery: `GET /v1/models` contained `gpt-5-6-sol`
- Request: one bounded Responses call asking for exactly `SMOKE_OK`
- Result: `status=completed`, returned model `gpt-5-6-sol`, output `SMOKE_OK`
- Usage: 16 input tokens, 7 output tokens, 23 total tokens
- Security: the key was loaded from the HPC-local `.env`; its value was neither
  printed nor written to the progress record

The GPT judge route is therefore available from the intended Slurm environment.
Before rerunning the full baseline, the evaluator still needs to be configured
to use this backend and Gemma-4-31B evaluation must be reduced from batch size 32
to batch size 4 (falling back to 2 if allocator warnings remain).
