# Frozen Plus Follow-Up: Paired Quality, Coverage and Cost

2026-10-11. Runtime and runner frozen at `34cc0cb`, following the complete 30-case development
rerun. The cohort contains 60 responses from 55 source groups, with QA/Summary/Data2txt 20 each
and 10 clean/10 hallucinated originals per task. It excludes the union of 113 source groups from
both earlier 60-case pilots and all development sources. It is still drawn from the historically
evaluated 420-response pool, not a globally untouched or necessarily model-unseen holdout.
No prompt/configuration changes were made in response to this follow-up's outcomes.

All runtime roles and baselines use Qwen3.5-Plus, non-thinking JSON and the same 8,192-token
completion ceiling. The claim-level Judge assesses grounding and explicit fulfillment, with
previous judgments hidden; the hybrid starts with one source-first revision. Qwen-Plus anonymous
review uses the unchanged review prompt and a 4,096-token ceiling. Every arm has five calls,
two revisions, 120 seconds and 24,000 observed tokens as common ceilings; actual consumption
differs. Full source material is retained. Original generation is excluded for every arm.

## Results

Usable proxy means grounding PASS **and** fulfillment PASS divided by all 60 cases. Fallback,
unknown and unavailable review never count as success. Grounded/released uses all releases as
the denominator, including unavailable reviews. These are automatic proxies, not human truth.

| Arm | Released | Usable proxy / 60 | Grounded / released | Runtime calls | Known tokens | P95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct | 60 | 24 | 29/60 | 0 | 0 | <0.01 |
| Judge only | 22 | 19 | 20/22 | 60 | 195,540 | 22.74 |
| Self-refine | 60 | 53 | 54/60 | 120 | 206,064 | 11.39 |
| Quality loop | 58 | 48 | 52/58 | 152 | 492,017 | 70.78 |
| Refine then verify | 58 | 55 | 55/58 | 126 | 331,074 | 31.69 |

The hybrid has the highest observed usable proxy yield in this paired run: 55/60 (91.67%) versus
self-refinement's 53/60 (88.33%), a descriptive 3.33-percentage-point difference. It has three
released grounding FAILs versus six for self-refinement, and two repair-budget fallbacks. The
original loop still trails, with one repair-budget and one token-threshold fallback; one released
loop output has unavailable review. No failed cases have been removed or selectively rerun.

The improvement is not free: hybrid runtime consumes 6 more calls and 125,010 more known tokens
(about 60.67% more), with P95 31.69 versus 11.39 seconds. This is not an equal-consumption comparison
or evidence that the framework alone outperforms every alternative. Against self-refinement,
50 cases are usable in both arms, five only in the hybrid, three only in self-refinement and two
in neither. Eight discordant outcomes in a small cohort do not establish general superiority.

| Task | Self-refine usable / 20 | Loop usable / 20 | Hybrid usable / 20 |
| --- | ---: | ---: | ---: |
| QA | 19 | 18 | 18 |
| Summary | 20 | 17 | 20 |
| Data2txt | 14 | 13 | 17 |

The aggregate gain is concentrated in Data2txt; QA is one case worse and Summary ties. This does
not justify claiming improvement in every scenario or changing the generic default. Originally
hallucinated, changed-and-usable rescue is 27/30 for both self-refinement and hybrid, still a proxy,
not a human-confirmed repair success rate. Original clean/changed grounding regressions are three
for self-refinement and one for hybrid, assessed automatically on different changed-output subsets.

## Review and Reproduction

458 runtime plus 216 anonymous review attempts = 674 calls. All runtime usage is known. Reviews
consume 454,205 known tokens, with one unknown-usage attempt and four unavailable reviews. The
reviewer agrees with original human grounding labels on 47/60 (78.33%), counting four unavailable
original reviews as non-matches. Model aliases differ but both are Qwen-family models; correlated
errors and possible public-data exposure remain unmeasured. Human post-repair review is pending.
Two availability probes consume 223 known tokens, recorded separately from arm/review metrics.

The supported conclusion is a small paired proxy advantage for the opt-in source-first hybrid,
with fewer observed bad releases but higher token cost and latency. It is not SOTA, a guarantee,
statistically established dominance or a human-confirmed accuracy claim. Model/capacity changes
and different source cohorts prevent attributing differences against old Flash trials to the loop.
Do not continue tuning on this cohort until a favorable headline appears.

```bash
python scripts/audit_comparison.py --results benchmarks/results/ragtruth-evidence-plus-eval-60
DASHSCOPE_MODEL=qwen3.5-plus python examples/ragtruth/compare.py \
  --per-task 20 --optimized --judge-history none --judge-strategy claims \
  --refinement-mode source_first --check-fulfillment --max-output-tokens 8192 \
  --exclude-records benchmarks/results/ragtruth-comparison-60/records.jsonl \
    benchmarks/results/ragtruth-optimized-eval-60/records.jsonl \
  --output runs/plus-eval-60
```

The audit checks recorded cohort, accounting, criterion coverage, final candidate identity,
anonymous packets/mappings and summary arithmetic without making model calls. It does not prove
semantic reviewer correctness. Use a new directory for reproduction; aliases/provider execution
do not guarantee identical text. A tiny preflight precedes pending work, and account failures stop
queued requests without dropping already-started attempts.
