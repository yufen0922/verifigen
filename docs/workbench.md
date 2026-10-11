# Local Workbench

The workbench is a local FastAPI service over the same `QualityLoop` used by the SDK and
evaluators. Its browser has no provider key and no direct connection to Bailian.

```bash
uv sync --locked --extra web
# Put DASHSCOPE_API_KEY and optional DASHSCOPE_MODEL in ignored .env.local,
# or export them in the current shell. Defaults to qwen3.5-flash.
uv run --locked --extra web verifigen doctor --live
uv run --locked --extra web verifigen-web --port 8765
```

Open http://127.0.0.1:8765. The service binds to loopback only. It is not an authenticated
multi-user deployment; do not expose it through a tunnel or on a public host.

## Workflow

Choose a RAG, support, report or RAGTruth development sample. Edit task, evidence, initial
candidate, rules, JSON Schema and budgets. With generation enabled, the initial candidate is
ignored and the Generator runs first. Otherwise Judge evaluates the supplied draft. Every
repair must be judged again. Only the final release surface contains approved output or fallback.
Drafts and intermediate verdicts are visible to the operator, not intended for end users.

The browser consumes SSE observations with sequence IDs; reconnecting replays missing events.
`round_complete` contains both the model verdict and the effective verdict after hard gates.
Core metadata traces still exclude task text. Observer exceptions cannot change loop decisions.
Support presets additionally verify order ID, paid amount, fulfillment, refund evidence priority
and next action with `SupportFactsGate`; report presets verify source fields, delta, direction and
percentage with `ReportFactsGate`. These gates do not claim to prove arbitrary sentence meaning.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /api/config` | Model and configured boolean; never the key |
| `GET /api/presets` | Six task inputs; public presets use development sources only |
| `POST /api/runs` | Validate inputs, allocate isolated run and return SSE URL |
| `GET /api/runs/{id}/events` | Event stream, `Last-Event-ID` or `after` reconnect cursor |
| `POST /api/runs/{id}/cancel` | Cancel execution without publishing the current candidate |
| `GET /api/runs/{id}` | Full operator record with inputs, candidates, verdicts and result |
| `DELETE /api/runs/{id}` | Delete a completed record from local disk and memory; active runs return 409 |
| `GET /api/history` | Latest 100 records across service restarts |
| `GET /api/evaluations` | Published actual evaluations; never a replay score |
| `GET /api/comparison` | Four-arm paired pilot with explicitly labeled external-model proxies |
| `GET /openapi.json` | Request/response schemas |

Three concurrent runs, at most seven calls and two repair rounds per run, a 180-second deadline,
512-KB request cap, local Host/Origin checks, static Content Security Policy and no browser CDN.
The byte cap is enforced on actual bodies, including chunked requests, before JSON parsing.
Numeric controls map to server validation rather than only UI restrictions. Token thresholds are
post-call observations: a single in-flight call can overshoot; they are not hard provider quotas.
Cancellation closes the local task and prevents publication; it cannot guarantee that the provider
stops an already accepted request or refunds its token charge. Timeout usage may remain unknown.

Full local records may contain sensitive business evidence. `runs/web` is ignored by Git and
records are atomically written with owner-only permissions. Delete them when no longer needed;
only sanitized public benchmark data is packaged with the application. This service persists
completed runs, not mid-call recovery or distributed job state.
History rows have a deletion control. Deletion is not secure physical erasure or automatic retention.
The budget panel also exposes `judge_history=none` for confirmation-bias ablations; repair feedback
and audit records are retained. No accuracy improvement is claimed from that switch alone.

## Browser Acceptance

```bash
npm install --no-save playwright
npx playwright install chromium
node scripts/workbench_smoke.cjs
node scripts/workbench_smoke.cjs --live  # Consumes actual model quota
```

Screenshots are written under ignored `runs/screenshots`. The test checks desktop/tablet/mobile
overflow, icons, input errors, history and evaluation records. `--live` also executes an actual run.
