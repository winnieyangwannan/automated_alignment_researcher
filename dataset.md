# Alignment-failure dataset and paper index

This document indexes the active scored and held-out datasets for the ten alignment-failure axes in this repository. Shared sources are deduplicated where several benchmarks use the same dataset.

The authoritative suite composition is in `scripts/publish_suite.py`. Exact splits, sampling, filtering, and transformations live in the corresponding benchmark `_publish.py` files. Some benchmark items are transformed, vendored, or generated locally rather than loaded directly from Hugging Face.

## Sycophancy

- `sycophancy_eval`, `sycophancy_feedback`
  - [Paper: Towards Understanding Sycophancy in Language Models](https://arxiv.org/abs/2310.13548)
  - [Hugging Face: meg-tong/sycophancy-eval](https://huggingface.co/datasets/meg-tong/sycophancy-eval)

- `sycon_fp`
  - [Paper: Measuring Sycophancy of Language Models in Multi-turn Dialogues](https://aclanthology.org/2025.findings-emnlp.121/)
  - [Data and code: JiseungHong/SYCON-Bench](https://github.com/JiseungHong/SYCON-Bench)
  - No Hugging Face dataset is used by this repository.

- `elephant_aita`
  - [Paper: ELEPHANT](https://arxiv.org/abs/2505.13995)
  - [Data used by AAR: myracheng/elephant](https://github.com/myracheng/elephant)
  - No Hugging Face dataset is used by this repository.

## Jailbreaks and refusal

- `strongreject`
  - [Paper: A StrongREJECT for Empty Jailbreaks](https://arxiv.org/abs/2402.10260)
  - [Hugging Face: AlignmentResearch/StrongREJECT](https://huggingface.co/datasets/AlignmentResearch/StrongREJECT)

- `harmbench`
  - [Paper: HarmBench](https://arxiv.org/abs/2402.04249)
  - [Hugging Face source used by AAR: walledai/HarmBench](https://huggingface.co/datasets/walledai/HarmBench)

- `jbb`
  - [Paper: JailbreakBench](https://arxiv.org/abs/2404.01318)
  - [Hugging Face: JailbreakBench/JBB-Behaviors](https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors)

- `jbb_artifacts`
  - [JailbreakBench artifacts](https://github.com/JailbreakBench/artifacts)
  - The PAIR attacks originate from [Jailbreaking Black Box Large Language Models in Twenty Queries](https://arxiv.org/abs/2310.08419).

## Prompt injection

- `open_prompt_injection`
  - [Paper: Formalizing and Benchmarking Prompt Injection Attacks and Defenses](https://arxiv.org/abs/2310.12815)
  - [Official repository](https://github.com/liu00222/Open-Prompt-Injection)
  - AAR reconstructs its tasks from:
    - [stanfordnlp/sst2](https://huggingface.co/datasets/stanfordnlp/sst2)
    - [ucirvine/sms_spam](https://huggingface.co/datasets/ucirvine/sms_spam)
    - [tdavidson/hate_speech_offensive](https://huggingface.co/datasets/tdavidson/hate_speech_offensive)

- `tensor_trust_hijack`, `tensor_trust_extract`
  - [Paper: Tensor Trust](https://arxiv.org/abs/2311.01011)
  - [Released benchmark data](https://github.com/HumanCompatibleAI/tensor-trust-data)
  - No Hugging Face dataset is used by this repository.

- `injecagent`
  - [Paper: InjecAgent](https://aclanthology.org/2024.findings-acl.624/)
  - [Official data and code](https://github.com/uiuc-kang-lab/InjecAgent)
  - No Hugging Face dataset is used by this repository.

## Power seeking

- `machiavelli_power`, `machiavelli_harm`, `machiavelli_heldout`
  - [Paper: Do the Rewards Justify the Means?](https://arxiv.org/abs/2304.03279)
  - [Official repository](https://github.com/aypan17/machiavelli)
  - [Hugging Face reformat used by AAR: wassname/machiavelli](https://huggingface.co/datasets/wassname/machiavelli)

- `instrumental_eval`
  - [Paper: Evaluating the Paperclip Maximizer](https://arxiv.org/abs/2502.12206)
  - [Data and code: yf-he/InstrumentalEval](https://github.com/yf-he/InstrumentalEval)
  - AAR vendors 65 parsed scenarios; no Hugging Face dataset is used.

## Deception and honesty

- `mask_factual`, `mask_continuation`, `mask_disinformation`
  - [Paper: The MASK Benchmark](https://arxiv.org/abs/2503.03750)
  - [Official repository](https://github.com/centerforaisafety/mask)
  - [Hugging Face: cais/mask](https://huggingface.co/datasets/cais/mask)

- `deceptionbench_reward`
  - [Paper: DeceptionBench](https://arxiv.org/abs/2510.15501)
  - [Official repository](https://github.com/Aries-iai/DeceptionBench)
  - [Hugging Face: skyai798/DeceptionBench](https://huggingface.co/datasets/skyai798/DeceptionBench)

## Hallucination and faithfulness

- `ragtruth`, `faith_mt_grounded`
  - [Paper: RAGTruth](https://arxiv.org/abs/2401.00396)
  - [Data and code: ParticleMedia/RAGTruth](https://github.com/ParticleMedia/RAGTruth)
  - AAR loads `dataset/source_info.jsonl` from GitHub rather than Hugging Face.

- `llm_aggrefact_A`, `llm_aggrefact_B`, `faith_mt_claimcheck`
  - [Paper: MiniCheck](https://arxiv.org/abs/2404.10774)
  - [Hugging Face: lytang/LLM-AggreFact](https://huggingface.co/datasets/lytang/LLM-AggreFact)
  - [Ungated fallback mirror](https://huggingface.co/datasets/NinaCalvi/llm_aggrefact_pre_aug9)
  - The current repository vendors its selected 300-row subset.

- `summedits`
  - [Paper: SummEdits](https://aclanthology.org/2023.emnlp-main.600/)
  - [Hugging Face: Salesforce/summedits](https://huggingface.co/datasets/Salesforce/summedits)

## Social bias

- `bias_refletter`, `bias_refbio`
  - [Paper: “Kelly is a Warm Person, Joseph is a Role Model”](https://aclanthology.org/2023.findings-emnlp.243/)
  - [Source repository](https://github.com/uclanlp/biases-llm-reference-letters)
  - AAR generates prompts from the published name, occupation, and age lists; it does not load a standalone Hugging Face dataset.

- `bias_race_content`
  - Race-cued names: [Bertrand and Mullainathan, 2004](https://doi.org/10.1257/0002828042002561)
  - Stereotype categories: [BOLD paper](https://arxiv.org/abs/2101.11718)
  - [Hugging Face: AmazonScience/BOLD](https://huggingface.co/datasets/AmazonScience/bold)
  - AAR derives prompts from these sources rather than copying BOLD rows.

- `bias_scene_heldout`
  - [Paper: WinoBias](https://arxiv.org/abs/1804.06876)
  - [Hugging Face: uclanlp/wino_bias](https://huggingface.co/datasets/uclanlp/wino_bias)
  - AAR uses WinoBias occupations plus the Wan et al. gender-name lists.

## Privacy

- `confaide`
  - [Paper: Can LLMs Keep a Secret?](https://arxiv.org/abs/2310.17884)
  - [Data and code: skywalker023/confAIde](https://github.com/skywalker023/confAIde)

- `privaci_bench`, `privaci_gdpr_heldout`
  - [Paper: PrivaCI-Bench](https://arxiv.org/abs/2502.17041)
  - [Data and code: HKUST-KnowComp/PrivaCI-Bench](https://github.com/HKUST-KnowComp/PrivaCI-Bench)
  - Data is packaged inside that repository as `HF_cache/cases`; it is not a separately published Hugging Face dataset.

- `privacylens`
  - [Paper: PrivacyLens](https://arxiv.org/abs/2409.00138)
  - [Data and code: SALT-NLP/PrivacyLens](https://github.com/SALT-NLP/PrivacyLens)

## Reward hacking

- `rh_mt_reward`, `reward_hacking_freeform`, and half of `world_affecting_reward`
  - [Paper: School of Reward Hacks](https://arxiv.org/abs/2508.17511)
  - [Data and code: keing1/reward-hack-generalization](https://github.com/keing1/reward-hack-generalization)

- Remaining `world_affecting_reward` items and all `reward_harm_freeform` items
  - Generated locally by AAR's 19-domain procedural generator.
  - There is no external paper or Hugging Face dataset specifically for these generated items.

- `rh_rubric_tamper`
  - [Paper: Sycophancy to Subterfuge](https://arxiv.org/abs/2406.10162)
  - [Source environment](https://github.com/anthropics/sycophancy-to-subterfuge-paper)

- `machiavelli_reward`
  - Uses the same [MACHIAVELLI paper](https://arxiv.org/abs/2304.03279) and [Hugging Face dataset](https://huggingface.co/datasets/wassname/machiavelli) listed above.

## Concealing uncertainty

- `llm_uncertainty_bench`
  - [Paper: Benchmarking LLMs via Uncertainty Quantification](https://arxiv.org/abs/2401.12794)
  - [Source data and code](https://github.com/smartyfh/LLM-Uncertainty-Bench)
  - Its AAR subset uses CosmosQA and HellaSwag data packaged by that repository.
  - [CosmosQA paper](https://aclanthology.org/D19-1243/)
  - [HellaSwag Hugging Face dataset](https://huggingface.co/datasets/Rowan/hellaswag)

- `verbalized_ece`
  - [Paper: Can LLMs Express Their Uncertainty?](https://arxiv.org/abs/2306.13063)
  - [Source code](https://github.com/MiaoXiong2320/llm-uncertainty)
  - Actual datasets loaded by AAR:
    - [ChilleD/SVAMP](https://huggingface.co/datasets/ChilleD/SVAMP)
    - [ChilleD/StrategyQA](https://huggingface.co/datasets/ChilleD/StrategyQA)
    - [mandarjoshi/trivia_qa](https://huggingface.co/datasets/mandarjoshi/trivia_qa)

- `abstentionbench`
  - [Paper: AbstentionBench](https://arxiv.org/abs/2506.09038)
  - [Original Hugging Face release: facebook/AbstentionBench](https://huggingface.co/datasets/facebook/AbstentionBench)
  - AAR does not use the full release. Its implemented subset directly loads:
    - [rajpurkar/squad_v2](https://huggingface.co/datasets/rajpurkar/squad_v2)
    - [JesusCrist/selfaware](https://huggingface.co/datasets/JesusCrist/selfaware)
    - [amayuelas/KUQ](https://huggingface.co/datasets/amayuelas/KUQ)

- `sciq_uncertainty`
  - [Paper: Crowdsourcing Multiple Choice Science Questions](https://arxiv.org/abs/1707.06209)
  - [Hugging Face: allenai/sciq](https://huggingface.co/datasets/allenai/sciq)

## Shared capability datasets

Every alignment-failure suite also uses the following capability gates:

- [MMLU paper](https://arxiv.org/abs/2009.03300) and [cais/mmlu](https://huggingface.co/datasets/cais/mmlu)
- [GSM8K paper](https://arxiv.org/abs/2110.14168) and [openai/gsm8k](https://huggingface.co/datasets/openai/gsm8k)
- [IFEval paper](https://arxiv.org/abs/2311.07911) and [google/IFEval](https://huggingface.co/datasets/google/IFEval)

## Repository coverage notes

The repository contains provenance for nearly every active benchmark, but it does not have a single centralized source manifest. Paper references and source descriptions are primarily under `benchmark_docs/<axis>/bench_explanation.md`; exact Hugging Face IDs, GitHub URLs, splits, and transformations are primarily in `scripts/publish_suite.py` and benchmark `_publish.py` files.

The generated evaluator JSONL suites and evaluator-only held-out items are intentionally not committed. Consequently, an upstream link alone may not exactly reproduce the evaluated data without also applying the repository's filtering, sampling, transformation, and seed logic.
