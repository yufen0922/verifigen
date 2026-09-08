# Security and data handling

v0.2 is alpha software for LLM-assisted content review and repair. It does not
authorize or execute payments, refunds, shipments or account changes.

Source adapters and contract callbacks are trusted application code. The SDK
does not evaluate model-written Python or YAML expressions. Model endpoint
configuration must be set by the application owner, never by an untrusted
request parameter. Remote endpoints require HTTPS and redirects are disabled.

An LLM Judge verdict is probabilistic and can be wrong; it is not a security or
authorization decision. Only quality-gated output or a configured fallback should reach an end user. Keep
business authorization, current-state checks, idempotency and transaction logic
in the system that performs an action. Re-query state and verify a real receipt
before reporting completed execution.

`write_quality_trace` omits candidate text, issue text and provider response bodies.
The v0.1 compatibility `write_trace` also omits fact values. Full result and
benchmark exports contain source-derived content and require appropriate access
controls in a deployment. Hashes are not a substitute for anonymization.

Do not post credentials or sensitive reproductions in a public issue. Once this
source is hosted, use the repository's private vulnerability reporting feature
if enabled. Repository maintainers should enable that feature before accepting
security reports. No personal maintainer email is invented in this template.
