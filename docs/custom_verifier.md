# Extending the SDK

> This page documents the v0.1 deterministic `Contract/Harness` compatibility
> layer. For the v0.2 primary LLM Judge/Repair API, start with
> [architecture.md](architecture.md).

## Bind a fact, derive a value, or enforce a rule

Use `FactVerifier.from_path(name, output_pointer, source_pointer)` for a direct
copy. Use `FieldVerifier(expected=..., depends_on=...)` for a uniquely defined
derived field. Use `RuleVerifier(predicate=...)` for a condition that does not
by itself determine a valid replacement.

```python
from verifigen import FactVerifier, FieldVerifier, RuleVerifier

fact = FactVerifier.from_path("fact.current", "/current", "/metrics/current")
delta = FieldVerifier(
    "derived.delta",
    "/delta",
    lambda draft, ctx: draft["current"] - draft["previous"],
    depends_on=("/current", "/previous"),
)
rule = RuleVerifier(
    "capacity_limit",
    lambda draft, ctx: draft["current"] <= ctx.source["capacity"],
    target="/current",
    message="Current count exceeds the permitted capacity",
)
```

A failing rule triggers regeneration if a generator exists, otherwise fallback.
It does not automatically clip `current` to `capacity`. If clipping is correct
for your particular application, represent that as an explicitly defined
expectation and explain its semantics in your contract.

Use JSON pointers, including `~1` for a slash in a key and `~0` for a tilde.
v0.1 can read arrays but automatic patches replace existing dictionary fields;
array edits or missing schema structure require regeneration. Keep field
targets at non-overlapping leaf paths. Declare every output-field dependency.

## Custom async checker

```python
from verifigen import CheckResult, Violation


class ApprovalFlagVerifier:
    name = "approval_flag"

    async def verify(self, candidate, context):
        flag = context.source.get("approval_flag")
        if flag is None:
            return CheckResult(
                self.name,
                "unknown",
                Violation("MISSING_APPROVAL", "/action", "Approval status is unavailable"),
            )
        if candidate["action"] == "suggest_review" or flag is True:
            return CheckResult(self.name, "pass")
        return CheckResult(
            self.name,
            "fail",
            Violation("APPROVAL_REQUIRED", "/action", "Action lacks an approval flag"),
        )
```

This is a contract checker, not an authorization service. The caller must define
the source, schema and meaning of the approval flag. Append a checker to a
contract with `dataclasses.replace(contract, verifiers=(*contract.verifiers, checker))`.
The runnable [custom rule example](../examples/custom_verifier/run.py) demonstrates
this extension with a data report.

The protocol accepts a `CheckResult` with the exact registered name. Exceptions,
invalid IDs, and missing evidence produce `unknown`. Return values of
`RuleVerifier` must be `True`, `False`, or `None`; arbitrary truthy values are not
accepted. A custom verifier's runtime falls under the run deadline.

## Integrate an existing agent

1. Query the application's read-only tools and construct one consistent snapshot.
2. Ask the agent to produce a response plan matching the contract schema.
3. Call `await harness.run(source=snapshot, initial=agent_plan)`.
4. Publish `result.text` and inspect `result.status`. Never publish an unchecked
   initial candidate or a rejected staged repair.
5. If the agent must execute an action, implement a separate business executor
   with its own authorization and current-state checks. Feed its real receipt
   into a new snapshot before reporting completion.

The existing agent can be AgentScope, LangGraph or your own loop. No framework
is imported by the runtime. These are integration boundaries, not claims of
tested framework-specific adapters.

## Integrate another model

Implement `async generate(request: GenerationRequest) -> Generation`.
Requests carry the source, user task, schema, contract instructions, previous
candidate and violations. `Generation` carries JSON-compatible content and
`Usage`. Preserve missing usage as `None`. Do not implement invisible retries;
each invocation is one budgeted attempt. Support cancellation where possible.

For an LLM judge extension, set `method="llm"` in its result, preserve uncertainty
and record its usage. In v0.1 the model-call budget counts generator invocations,
not arbitrary network calls inside custom verifiers. A judge needs its own
explicit accounting until a shared verification budget is implemented. No
semantic-judge accuracy claim is made by this release.
