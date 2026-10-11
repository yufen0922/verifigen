# Changelog

## Unreleased

- Add charged evidence-first refinement, separate Judge model configuration and corrective,
  budgeted protocol retries; retain known failed-call usage and explicit provider categories.
- Use non-thinking JSON mode in configured live examples/workbench; keep thinking opt-in and
  literal-quotation validation experimental. Isolate quotation fields from the plain Judge schema.
- Publish four 30-case development diagnostics and a source-disjoint 60-case validation (2,000
  runtime/review calls). Self-refinement still leads on useful proxy yield/cost; do not claim
  human-confirmed loop superiority. Expose failed experiments and configurations in the workbench.
- Audit release-candidate identity, call/revision accounting, anonymous packets and duplicate
  review records; test tampered artifacts and add all optimization audits to CI.

- Add paired real-model RAGTruth baselines, anonymous cross-model proxy review, development-only
  threshold diagnostics and dual-human-review/adjudication tooling; preserve unfavorable results.
- Support optional history-hidden re-judgment while preserving repair feedback and audit history.
- Bound actual chunked request bytes and allow deletion of completed private workbench history.
- Add concurrent-run isolation, cancellation, oscillation and repair-regression tests.
- Clarify criteria-only judgment and unknown-versus-false evidence handling in Judge/Repair
  prompts; publish a known-failure live recheck without changing historical benchmark results.

- Add a live, local FastAPI workbench with SSE rounds, input editing, budgets, cancellation,
  private persisted history, export and actual benchmark records.
- Publish the frozen, source-isolated RAGTruth-600 corpus with pinned hashes, license,
  downloader, builder and resumable live evaluator; keep gold labels out of model inputs.
- Add support financial-fact and report arithmetic gates independent of the LLM verdict.
- Add exact detection metrics and source-cluster bootstrap confidence intervals; audit the
  historical first-Judge accuracy from 97.22% to 96.11% without changing model outputs.
- Add safe environment configuration and a bounded `verifigen doctor --live` connectivity check.

- Add original, reproducible SVG architecture and decision diagrams in English and Chinese,
  with light/dark theme variants for GitHub documentation.
- Extract a pure `QualityPolicy` with opt-in score plateau termination.
- Enforce Draft 2020-12 output schemas and add an async `CandidateGate` extension point;
  gate failures become repair feedback, while unavailable checks fail closed.
- Add a citation whitelist/consistency gate to the live RAG example.
- Select fallback messages by termination reason and expose separate gate reports.
- Isolate task data for every adapter call and validate finite execution limits.
- Record budget/policy configuration and explicit release/repair/fallback decisions in traces.
- Add gate/policy ablation switches, dataset fingerprints and per-case gate/trace records
  to cross-scenario evaluation; handle evaluation subsets with no incorrect drafts.
- Expand architecture diagrams, scenario integration documentation and boundary/concurrency tests.
- Historical 180-case model results remain unchanged; these changes require a new live evaluation.

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
- Add English/Chinese README, architecture and learning guides.
