# ADR 0003: no fine-tuning in version 1

Accepted under the user's delegated architecture authority.

The initial hybrid benchmark missed two paraphrases. Separate relevance calibration and safer citation transport resolved those observed defects without training; the unchanged small regression set then passed its gates. There is no reviewed, varied training set or independent corpus-level test split to justify LoRA.

No fine-tuned checkpoint, synthetic-training score, DPO/RLHF result or GPU training claim is included. Pretrained BGE-M3/Qwen inference is distinct from training.

Revisit for a narrow recurring task, such as Turkish incident field extraction, when real reviewed examples show a defect that retrieval/prompting/validation cannot address. Compare a simple baseline, the same untuned model and a PEFT adapter on project/time-separated data. Require predeclared quality/cost benefit and no material abstention/security regression. Publish provenance, splits, configuration and failures.
