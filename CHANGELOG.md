# Changelog

## Unreleased

No unreleased changes.

## 0.2.0 — 2026-09-08

- Move customer-support and data-to-text examples onto the v0.2 `QualityTask`
  and `QualityLoop` interface with scenario-specific criteria and renderers.
- Add 120 labeled evaluation cases across six refund states and six metric
  patterns, plus one offline/live evaluator for all 180 cross-scenario cases.
- Add independent support/report oracles and fail-closed output rendering.
- Pass the target candidate schema to both LLM roles, distinguish repairable
  schema failures from unknown context, and ignore malformed proxy environment
  settings for explicitly configured model endpoints.
- Record a full 180-case `qwen3.5-flash` run with 513 real model calls and
  conservative oracle-scored per-scenario results.
- Rebuild the primary architecture around Generator -> LLM Judge -> LLM Repair
  -> re-Judge instead of deterministic field repair.
- Add structured criteria, verdicts, issues, scores, task context, budgets,
  quality results and metadata-only traces.
- Ensure Judge and Repair receive the original prompt, full business context,
  candidate, criteria and prior verdicts on every round.
- Add separate Qwen3-8B generation, judge and repair adapters for Bailian with
  thinking enabled and a configurable thinking budget.
- Convert the RAG example to raw policy text without `fact/value` answer labels.
- Add a BM25 -> Qwen3-8B end-to-end demo, forced-error repair demo and live
  evaluation harness over a generated 60-case RAG corpus with an independent
  claim-level scorer; the original six cases remain as a smoke set.
- Add tests for pass/fail/unknown behavior, malformed agent responses, context
  propagation, call/repair/deadline budgets and no-progress termination.
- Keep v0.1 `Contract/Harness` as an explicit deterministic compatibility layer.

## 0.1.0 — 2026-09-07

- Add Python SDK with explicit evidence contracts, strict schema validation,
  fact/rule checks, structured violations and three-state verification.
- Add dependency-closed deterministic repair, full regeneration fallback,
  regression rollback, bounded async runtime and metadata-only JSONL traces.
- Add compatible Chat Completions adapter, replay and function generators.
- Add receipt-aware customer support, data-to-text and custom-rule examples.
- Add 114 independent synthetic fixtures, paired replay/live evaluation and
  a source-driven template baseline with explicit limits on result claims.
- Add tests, developer dependency lock, CI matrix, package builds and draft
  GitHub Release automation.
- Add English/Chinese README, architecture, learning and interview guides.
