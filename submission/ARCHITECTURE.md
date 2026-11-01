# Viewer lifecycle architecture

One logical agent owns a viewer's facts, one open goal, one active plan and durable history. Viewers share application code, not goals or memory. SQLite uniqueness constraints enforce ownership.

## Planning and evidence

Received events are deduplicated. Server receipt and phone-buffer duration distinguish fresh visits from old offline opens. Facts retain source, timestamp, age and conflicts. App settings determine display dialect; campaign hints cannot override them. Billing contradicts stale never-paid snapshots. Opt-outs override snapshot consent. SOURCE_RULES.md defines field-specific precedence and freshness.

Eligibility is computed locally. A valid existing goal is retained until evidence, its deadline or an authoritative correction changes it. A live model can jointly propose an eligible goal, offered intervention or no action. Pages and message copy are built locally from available dialect variants and approved templates.

Before selection, the decision records a planning trace of the evidence actually read: named facts and provenance, entry counts, coverage, eligible goals, active commitment and any unfinished-series target. A local renderer explains eligibility, recorded selection, channel/content rules, measurable deadline and vetoes. The explanation is persisted with the decision before committing an action, and its computation counts toward decision latency. CSV exports expose final_reason separately from stable reason_code. Model replies supply a reason category and evidence keys; explanations do not claim an unstated model preference or calibrated probability. Historical exports are labelled and never consult later outcome events.

## Provider boundary and validation

ModelProvider is the injected provider interface. Live mode uses the configured primary and secondary OpenAI-compatible models. Recorded mode loads prior genuine replies for identical minimized inputs, needs no credentials/network and records its source explicitly. A missing recording is a dependency failure followed by a verified local fallback, never a fabricated model success.

Every reply — live, cached or recorded — passes jsonschema.Draft202012Validator. Types, enums, required fields, evidence keys and confidence are checked; duplicate JSON keys, non-finite numbers and extra claims are rejected. The prompt/input contain only rule IDs, fact enums, freshness, offered channels and capped counts. Raw viewer IDs, titles, descriptions, searches and credentials remain local.

## Independent verification and delivery

Fresh evidence is reread independently before publication. Verification can reject eligibility, dialect, availability, consent, quiet hours, daily caps, copy/templates, shape, holdout actions, duplicates or late decisions. Model confidence is neither evidence nor approval.

A commit records the decision, state, single active plan and pending outbox request. delivery.py rechecks at dispatch, cancels invalidated plans and uses action IDs for idempotent local backend acceptance. Acceptance does not imply delivery; actual delivery events must match action, viewer and channel. The unchanged assignment simulator supplies observations during replay evaluation.

## Memory, latency and recovery

SQLite WAL persists facts, goals, decisions, actions, outcomes, learning and a time-indexed timeline. Duplicate jobs reuse saved decisions after restart. Purchases can close/invalidate conversion goals, cancel pending actions and trigger worker replanning. Deadline review and page TTL expiry end obsolete plans without inventing outcomes.

The replay CLI processes the supplied script in time order. runtime.py separately provides stable SHA-256 partitions, one sequential worker per partition, OS ownership locks and durable inboxes. Partitions run concurrently; arrivals during planning are checked before publication. Routing is pinned across restarts.

Live primary/secondary attempts share a total model budget, at most two attempts. Known whole-provider outages skip both; a circuit breaker suppresses repeated primary failure. The engine enforces the assignment ceilings of eight model calls, twenty evidence reads and sixty seconds, with a safe smaller page or no action on failure. A prior cold run violated timing during a roughly 682-second wait; the failure is retained in benchmarks/cold_failure. No local timer can guarantee execution while its host is suspended.

## Measurement and trust

Actual event IDs, committed windows, current success rules and IST dates govern outcome judging. Incomplete telemetry is inconclusive. Provisional G06/G10 definitions are labelled; G11 requires real TV telemetry. Impact compares every triggered viewer once in its assigned randomized arm using shared business outcomes and confidence intervals. Individual success is not causal proof.

Local files and the model are separate trust boundaries. Generated content cannot authorize action or establish facts. Nothing is deployed; the local backend and simulator contact no real phones. Recorded-mode timing/impact is engine evaluation, not fresh model or production performance.
