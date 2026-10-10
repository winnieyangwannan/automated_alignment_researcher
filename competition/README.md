# AAR competition export

`export_aar_spipes.py` is the end-to-end bridge from an AAR team run to one or more verified competition `.spipe` bundles.

It performs four fail-closed stages:

1. Joins authoritative scores, approved proposals, exact evaluated model artifacts, result findings, and approved method source by `run_id`.
2. Ranks valid candidates by `headline_pct`, breaking ties by proposal time and then `run_id`, and selects the champion or top K. It does not re-score candidates.
3. Submits one GPU Slurm job per selected adapter. Each job rechecks the source checksums, loads the matching base model, attaches the exact evaluated adapter, writes a frozen self-contained bundle with `artifacts="fat"`, runs `SPipe.verify()`, and runs the starter-kit checker.
4. When `--upload` is enabled, waits for all jobs, preflights the Hugging Face destination, uploads only the verified `.spipe`, and verifies its path, size, and immutable Hub commit.

The original adapters are never modified or copied into Git. Selection, source checksums, method source, scores, generated job scripts, logs, bundle reports, and optional upload reports remain under the chosen output directory.

## Requirements

Run the launcher from the FAIR HPC login node containing the AAR results. The packaging itself runs through Slurm on one GPU per candidate.

You must provide:

- the validated Apptainer base image;
- the competition starter-kit checkout with its ARM64 `.venv`;
- the read-only Hugging Face model cache containing the base model.

For the environment used to export run 7, those are:

```text
/engshare/aira/shared/sif/super.sif
/storage/home/winnieyangwn/steerability-challenge-starter-kit
/checkpoint/aira/shared/data/steerability/hf-overlay/upper/root/.cache/huggingface
```

## Export the champion

Wait until all research and evaluator jobs are terminal and their final score/result pairs have landed.

```bash
cd /storage/home/winnieyangwn/aar-worktrees/multi_vllm
source .venv/bin/activate
export PYTHONPATH="$PWD"

python competition/export_aar_spipes.py \
  --team-dir "$TEAM_DIR" \
  --output-dir "$ATTEMPT_DIR/competition_export" \
  --top-k 1 \
  --suite honesty_sycophancy_concealing_uncertainty \
  --inference-backend vllm \
  --base-model google/gemma-4-31B-it \
  --base-sif /engshare/aira/shared/sif/super.sif \
  --starter-kit /storage/home/winnieyangwn/steerability-challenge-starter-kit \
  --hf-cache /checkpoint/aira/shared/data/steerability/hf-overlay/upper/root/.cache/huggingface \
  --wait
```

Use `--attempt-dir` instead of `--team-dir` when the attempt contains exactly one directory under `aar_teams/`. Run 7 contains reconstructed history alongside the active team, so it requires `--team-dir`.

Use `--top-k 5` to export the top five valid adapters. They are packaged in parallel as separate Slurm jobs and retained under `rank-01_*` through `rank-05_*`.

Use `--dry-run` to perform selection, provenance capture, checksum generation, and job-script generation without submitting Slurm jobs. The output directory must be new unless `--force` is explicitly supplied.

## Optional Hugging Face upload

Authenticate beforehand using the normal Hugging Face credential store or `HF_TOKEN`. Never put a token in the command.

Add these options to the export command:

```bash
  --upload \
  --hf-repo owner/repository
```

`--upload=true` is also accepted. Upload implies `--wait`. For one champion, the bundle is uploaded at the repository root. For top K, the default paths are `<rank>-<run_id>/<model-slug>.spipe`; customize them with `--hf-path-template`.

The repository must already exist. To create it deliberately, add `--hf-create-repo` and exactly one of `--hf-private` or `--hf-public`. Existing remote files are never replaced unless `--hf-overwrite` is supplied.

Only the `.spipe` is uploaded. The method card, scores, source code, logs, adapters, and local provenance remain local.

## Outputs

The root contains `selection.json`, `jobs.json`, terminal `job_states.json` when waiting, and `run_report.json` after successful completion. Each selected candidate contains:

```text
rank-01_<run-id>/
├── package.sbatch
├── logs/
├── provenance/
│   ├── candidate.json
│   ├── source_model_checksums.json
│   ├── score.json
│   ├── proposal.json
│   ├── finding.json
│   └── method/
└── work/
    ├── pipeline.py
    └── submission/
        ├── <model-slug>.spipe
        ├── method_card.md
        ├── check_report.json
        └── bundle_report.json
```

An upload additionally writes `upload.json` beside the candidate directory. Success means the bundle passed model-free SPipe verification and the starter-kit single-model partial check. A complete competition submission still requires the same method packaged for every required base model.
