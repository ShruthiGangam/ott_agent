# Response, data and action guardrails

All live, cached and recorded proposals pass the local jsonschema.Draft202012Validator. Malformed JSON, duplicate keys, non-finite confidence, wrong types, extra fields, unsupported goal/channel IDs, invented evidence keys and action-without-evidence responses are rejected categorically. Error messages do not echo untrusted content. Schema validation does not establish factual truth; independent fresh evidence and policy checks can still veto a well-formed proposal.

Live input uses a closed vocabulary of eligible rules/signals, fact enums, freshness categories, offered channels, anonymous evidence keys and capped counts. Raw viewer IDs/events, catalogue titles/descriptions, searches, URLs and API keys are excluded. The model has no tools, filesystem access or authority to approve consent or publish actions.

Transport uses certificate-validated HTTPS, exact hostname allowlists, blocked redirects/proxies, a response-size ceiling and bounded waiting. The secondary endpoint/key is validated independently. OpenAI requests set store=false and strict structured output. Neither this flag nor no-training defaults prove Zero Data Retention.

Recorded mode loads only bundled validated genuine replies. It reads no .env and performs no network calls. A miss is a labelled safe fallback; it is never reported as successful fresh inference. The recording bank contains minimized contexts and response provenance, with no API credentials.

Before publication and dispatch, independent code checks eligibility, holdout, dialect, availability, consent, quiet hours, shared frequency caps and approved copy/templates. Purchases/opt-outs can cancel pending actions. Delivery observations must match the action, viewer and channel.

The user's synthetic-pack transmission exception is recorded separately from retention verification. Original policy files remain unchanged. .env, .venv, caches, databases and generated runs are excluded from submission; .env.example contains blank credentials. Local state is not application-encrypted.

References: [JSON Schema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/), [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
