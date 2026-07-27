# Structured-Output Local LLM Pilot: Admission, Labels, and Benchmark Hygiene

Use this recipe when a small local instruction model is fine-tuned to emit JSON or another strict schema.

## Audit the actual training lineage first

Before changing hyperparameters or launching another run:

1. Read the exact training report and bind its manifest hash to the on-disk manifest.
2. Count every record by `review_status`, provenance kind, task type, and assistant-target parseability.
3. Trace the promotion implementation—not just its receipt—to verify that it rejects non-approved records rather than relabeling them.
4. Dry-run the current candidate corpus through admission and require zero pending records to promote.
5. If a historical adapter used non-approved data, preserve its artifacts but issue an explicit inadmissibility receipt. It may remain negative mechanics evidence, never promotion or quality evidence.

A manifest labeled “approved” is not evidence when its producer could silently rewrite review state.

## Train on assistant targets, not the whole conversation

For chat-template causal-LM tuning:

1. Render the prompt from system+user messages with `add_generation_prompt=True`.
2. Render the complete system+user+assistant conversation without an extra generation prompt.
3. Tokenize both with identical truncation and special-token settings.
4. Set labels to `-100` for every prompt token and to the full token ID for assistant-target tokens.
5. Preserve those labels through batching; pad labels with `-100` rather than reconstructing labels from `input_ids` and `attention_mask`.
6. Abort before CUDA if truncation leaves a record with no supervised assistant token.

Unit-test both seams independently: prompt masking at tokenization and label preservation/padding in batching. A falling loss from full-conversation supervision can mostly measure prompt imitation and does not prove structured-output learning.

Record in the training receipt:

- label strategy (`assistant_only`);
- train/holdout supervised-token counts;
- examples seen and optimizer steps;
- input/config/code hashes;
- allocator ceiling and peak allocation.

## Separate development evidence from benchmark evidence

- Use an approved development holdout for quick base-versus-adapter schema checks.
- Predeclare a quantitative gate before training, such as minimum schema-valid count and adapter pass count greater than base.
- Once a benchmark has been opened or inspected, do not tune against it again or call it untouched.
- If the scorer requires fields or terms that the prompt never requests, classify this as an evaluation-contract defect. Do not silently retrofit the opened benchmark and then call the result independent. Make the output contract explicit in future benchmark prompts and author a genuinely new untouched benchmark for promotion evidence.
- Preserve development wins honestly: “development gate passed, not promoted” is a valid terminal state.

For structured output, report schema validity separately from required-term and semantic pass counts. A model can reach 100% parseability while still missing task-critical terms.

## Bounded execution

Run one trainer or evaluator at a time. Use two independent resource boundaries:

- an in-process framework allocator ceiling;
- an external host guard for total VRAM, total RAM, elapsed time, and serialized-process admission.

Do not infer success from the guard process exiting zero. Verify the durable model report, adapter files, exact hashes, state projection, and evaluation receipt. Copy guard receipts into durable run storage before deleting temporary scripts/logs.

## Promotion sequence

1. Repair and test admission.
2. Train only on currently approved records.
3. Evaluate on the frozen development holdout.
4. Complete explicit human review through immutable packet-bound decisions.
5. Atomically apply decisions and freeze a new manifest.
6. Train a successor under a new protocol.
7. Evaluate once on a genuinely untouched benchmark.
8. Promote only if every predeclared quality, resource, and governance gate passes.
