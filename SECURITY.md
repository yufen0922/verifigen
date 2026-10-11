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

The optional workbench is loopback-only, not an authenticated public service. Never expose it
through a tunnel. Browser configuration contains only a model name and a configured boolean;
provider secrets stay on the server. Local full run records contain business context and are
written under ignored `runs/web` with owner-only permissions. Metadata-only SDK traces and full
operator observations are different privacy surfaces. Gold benchmark annotations stay outside
Judge/Repair prompts; dataset text remains untrusted data, not executable instructions.

Do not post credentials or sensitive reproductions in a public issue. Use the
repository's private vulnerability reporting form for security reports. No
personal maintainer email is published or invented by this project.
