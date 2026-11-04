# Evaluation

`evals/dataset.json` was frozen before the first real-model experiment: 6 hand-authored documents, 11 supported questions and 4 unrelated questions. No training data is used. `evals/calibration.json` has 10 different questions; the source corpus is shared, so independence is question-level, not corpus-level.

The fixed hybrid gates are Recall@3 >=0.85, MRR >=0.6 and no evidence retrieved for all four unrelated questions. The lexical baseline is measured separately and is not expected to pass those hybrid gates.

## Recorded local experiment, 4 November 2026

| Method | Supported Recall@3 | MRR | Unrelated without evidence |
| --- | --- | --- | --- |
| Turkish BM25 | 8/11 (0.7273) | 0.7273 | 4/4 |
| Initial hybrid, cutoff 0.5 | 9/11 (0.8182) | 0.8182 | 4/4 |
| Calibrated hybrid, cutoff 0.4 | 11/11 (1.0000) | 0.9545 | 4/4 |

The initial failure is retained. Calibration's lowest relevant maximum cosine was 0.48095; highest irrelevant was 0.30741. A rounded midpoint cutoff of 0.4 was selected from that development split, then unchanged regression questions were rerun. No label/gate changes or fine-tuning were used.

Real Qwen3.5:9b generation ran for two supported Turkish questions and one unrelated question. Both supported answers used LLM mode and valid citations; their claims matched the fixtures on inspection. The unrelated question abstained before generation. These three smoke cases are not a statistical hallucination-rate estimate. Citation identity does not prove entailment; arbitrary private corpora require broader human review.

The initial UUID citation transport caused one invalid model citation and explicit fallback. Short model-facing source IDs fixed that fragility while retaining stored chunk IDs. The failed run remains in [evidence](evidence/).

## Reproduce

```sh
uv run python scripts/evaluate.py --output test-results/lexical.json
uv run python scripts/calibrate.py
uv run python scripts/evaluate.py --models --generate --gate --output test-results/ollama.json
```

Runtime: Windows, CPython3.12, real local Ollama, BGE-M3 and Qwen3.5:9b, RTX5070 12GB. CI exercises model HTTP contracts and lexical evaluation, not GPU generation. The small benchmark is regression evidence rather than production accuracy.
