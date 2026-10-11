# Development Diagnostic: JSON-Compatible Non-Thinking Mode

2026-10-11. Same 30 development responses and 30 source groups. Runtime snapshot: `f155183`.
Qwen3.5-Flash uses `enable_thinking=false`, strict quotations are disabled, feedback is compact,
Judge sees no previous verdicts, and protocol retries include corrective instructions.
All five arms are re-executed; review instructions and common ceilings are unchanged.

| Arm | Released | Proxy usable / 30 | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 30 | 11 | 0 | 0 | <0.01 |
| Judge only | 11 | 9 | 31 | 78,093 | 4.60 |
| Self-refine | 30 | 25 | 60 | 104,073 | 5.72 |
| Quality loop | 27 | 24 | 70 | 180,481 | 16.54 |
| Refine then verify | 29 | 26 | 66 | 142,676 | 9.74 |

227 runtime calls plus 101 review calls. Reviewer known usage: 219,838 tokens; two unique
review errors remain unavailable. Original-label agreement: 23/30 (76.67%), including one
unavailable original. All runtime attempts have known usage in this trial.

The hybrid's 26/30 proxy yield versus self-refine's 25/30 is only a development observation,
not statistical significance or a human-confirmed accuracy gain. Several settings changed,
so the lower latency cannot be causally attributed to just one change. The provider's
[JSON support documentation](https://help.aliyun.com/en/model-studio/qwen-structured-output)
warns that thinking-mode Qwen3.5 responses can violate JSON format.

Two loop failures are traced to a non-string value in the experimental `source_quote` field
that was unnecessarily advertised even in plain mode. The final schema omits quote fields
unless enabled; strict-mode absent source quotations accept null and normalize to empty text,
without changing any pass/fail decision. Status and criterion IDs are enumerated in the prompt
schema. Two targeted development probes return valid FAIL after that correction; they are
debugging evidence, not added benchmark cases or favorable replacements.

The final profile is frozen separately at `7266ef6` and validated on 60 eval responses excluding
all source groups in the original pilot. These development records are never overwritten.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-json-dev-30
```
