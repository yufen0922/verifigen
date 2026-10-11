# Operational Boundaries

VerifiGen is an Alpha SDK with a loopback-only operator workbench, not a production multi-tenant
service. A verified execution path does not establish model correctness or business safety.

## Responsibilities

| Boundary | Current behavior | Application responsibility |
| --- | --- | --- |
| Source truth | Check output against the supplied snapshot | Authoritative source selection, freshness, conflicting versions and retrieval quality |
| Authorization | Business gates may inspect fields | Identity, tenant boundaries, policy enforcement and transaction permissions |
| Release | Model PASS, score threshold and deterministic gates must allow release | Risk-specific thresholds calibrated on development data |
| Unknown | No speculative repair; reason-specific fallback | Collect missing evidence, re-retrieve or send to an actual human queue |
| Human handoff | Returns configured text only | Create and track the human work item; do not equate fallback with successful handoff |
| Side effects | Core loop changes candidate data, not external transactions | Idempotency and commit-time version checks if an application acts on the result |

The source snapshot is internally stable during one run, but the real order, policy or account
may change while the loop is running. Recheck authorization and business versions immediately
before an external action. A well-grounded text is not permission to refund money.

## Availability and Cost

The adapter makes one HTTP request per invocation, without hidden retries. Provider failures
fail closed. Adding retry requires a classified 429/5xx policy, jitter, a deadline and accounting
for every potentially billable attempt; do not retry all semantic failures.
The Token threshold is post-response observation and can overshoot by an in-flight response.
Provider usage can be missing, particularly during timeout; known tokens are a lower bound.
Local cancellation prevents release but cannot cancel provider-side billing.

The public 420-case run has a P95 near 69 seconds **excluding queueing**. This is not a live-chat
SLA. Initial applications should evaluate asynchronous report review or operator-assisted work,
then choose repair rounds and routing by risk and latency budget. Capacity, queueing, connection
pooling and provider rate limits need measured production-like load before deployment claims.

## Local Data and Security

The browser never gets the provider credential. The local service checks Host and mutation Origin,
applies a CSP, and bounds actual request bytes before JSON parsing, including chunked uploads.
Full records contain evidence and drafts; owner-only local file permissions are not encryption.
The history deletion endpoint removes completed records from disk and process memory. Active runs
must first be cancelled. There is no automatic retention schedule or secure physical erasure.

The source/candidate separation and instructions are defense in depth against prompt injection,
not a proof that arbitrary malicious documents are harmless. Test realistic injected documents,
keep tools/transactions outside model authority and never expose the unauthenticated local service
through a public tunnel. Do not send confidential or personal data to a model without the owning
application's data-processing policy. Rotate credentials exposed in chats or logs.

## Verification Versus Deployment

`tests/test_runtime_resilience.py` injects faults and interleaves 64 runs of one loop to verify
context/history isolation and cancellation boundaries. These are deterministic engineering
tests, not 64 real model calls, capacity measurements or accuracy evidence. Unit tests also cover
protocol failures, gate failures, newly introduced errors and A/B candidate oscillation.

Distributed queues, durable in-flight recovery, multi-user authentication, tenant quotas, periodic
retention, production alerts and a rollback-capable deployment are intentionally not claimed.
Deploy first in shadow mode without blocking user output; review disagreement, fallback reasons,
error releases, coverage, P95, queueing and cost before canary enforcement. Pin prompt, rule and
model configuration with each rollout so regressions can be compared and the previous policy restored.
