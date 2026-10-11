# Qwen3.5-Flash multi-scenario results

Run date: **2026-09-08**. Model: **qwen3.5-flash**. Thinking budget: **1024**.
Concurrency: **8**. Cases: **180**.

This is a real-model run over template-generated evaluation data. Final correctness is scored by
scenario-specific deterministic oracles rather than by the LLM Judge itself.

| Scenario | Cases | First-judge accuracy | Bad-case repair success | Final oracle success | Fallback | Published precision |
|---|---:|---:|---:|---:|---:|---:|
| RAG | 60 | 96.67% | 98.15% | 98.33% | 0.00% | 98.33% |
| Customer support | 60 | 91.67% | 61.11% | 65.00% | 21.67% | 82.98% |
| Data-to-text report | 60 | 100.00% | 61.11% | 65.00% | 5.00% | 68.42% |
| **Overall** | **180** | **96.11%** | **73.46%** | **76.11%** | **8.89%** | **83.54%** |

Metric correction (2026-10-11): the previous 97.22% counted two failed Judge calls as correct
detections. Exact `pass`/`fail` judgments now determine correctness; `unknown` and `error` never
count as correct. No model output, repair outcome or call count changed. The original value and
affected IDs are preserved in `summary.json.metric_revision`.

The run made 513 model calls and used 866,953 input tokens plus 641,459 output tokens. The Judge
published 164 outputs; 137 passed the independent oracle and 27 were incorrect releases.

The strong RAG result does not generalize to every scenario. Customer-support failures concentrate
around incorrect order facts, stale wording and unauthorized promises. Report failures concentrate
around omitted original values, periods, direction and zero-baseline explanations.

See `summary.json` for machine-readable aggregates and `records.jsonl` for all per-case candidates,
verdicts, outputs, token counts and trace outcomes. The dataset is synthetic, so these numbers are
evaluation evidence rather than a production accuracy claim.
