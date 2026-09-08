# VerifiBench results

Mode: **synthetic_replay**. Cases: 60.

Synthetic replay is a mechanics check, not evidence of model superiority.

| Strategy | Valid answer | Released error | Abstention | Repair success | Calls/case |
|---|---:|---:|---:|---:|---:|
| generator_only | 11.1% | 90.0% | 0.0% | 0.0% | 0.00 |
| template | 100.0% | 0.0% | 10.0% | 100.0% | 0.00 |
| field_only_ablation | 24.1% | 75.9% | 10.0% | 14.6% | 0.00 |
| full_regenerate | 100.0% | 0.0% | 10.0% | 100.0% | 0.80 |
| dependency_repair | 100.0% | 0.0% | 10.0% | 100.0% | 0.10 |

See summary.json for definitions and token availability; records.jsonl contains paired candidates, outputs and trace metadata. These files can contain source-derived data.
