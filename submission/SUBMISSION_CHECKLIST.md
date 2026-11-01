# Technical and submission checklist

| Requested item | Included implementation / evidence |
|---|---|
| Runnable CLI/API and one replay command | replay.py; python replay.py runs the complete supplied stream without a key. README.md covers virtual environment, dependency installation, recorded/live modes and resume. pyproject.toml also exposes ott-agent. |
| Durable per-viewer state, evidence and decisions | ott_agent/store.py: SQLite WAL, unique goals/decisions/actions, viewer state, outbox and time-indexed history. A replay writes state.sqlite, viewer_state/, decisions.jsonl and actions.jsonl. sample_replay/viewer_state.jsonl preserves example state. |
| Evaluator does not need a personal key | ModelProvider protocol and RecordedProvider in ott_agent/recorded_provider.py; bundled genuine replies in ott_agent/assets. --provider recorded performs zero network requests and bypasses .env. --provider live accepts an evaluator's own credentials. |
| Late/duplicate trigger test | tests/test_agent.py: test_duplicate_is_idempotent and test_late_trigger_no_action. |
| Conflicting-source test | tests/test_agent.py: test_current_dialect_wins_and_content_matches and test_purchase_overrides_stale_never; tests/test_requirements_v2.py covers three conflicting dialects. |
| Tool-failure test | tests/test_agent.py: test_model_outage_falls_back and test_slow_store_abstains_if_budget_small; provider timeout and fallback-budget regressions are also covered. |
| Corrected-goal test | tests/test_agent.py: test_corrected_rule_updates_open_goal; tests/test_more.py checks idempotent correction. |
| Sample decisions/actions/no-action/outcomes/impact | sample_replay/ contains all five, plus trigger deliveries, state exports, observation events and provenance manifest. Its impact report uses the complete randomized cohort, not the selected excerpt. |
| Readable explanations | Each new replay writes responses.csv and explanations.jsonl. decisions.jsonl records final_reason, reason_code and the planning trace. Historical sample explanations are labelled and preserve the original decision records. |
| Architecture note | ARCHITECTURE.md covers ownership, planning, memory, verification, latency, failure recovery and trust boundaries; SOURCE_RULES.md and SECURITY.md expand evidence/privacy rules. |
| Short AI collaboration log | AI_COLLABORATION.md states what Codex built and how it was checked. |
| Intentional limitations | KNOWN_LIMITATIONS.md records provisional goals, missing TV telemetry, preserved latency failures and absence of deployment/real-phone delivery. |
| LLM response validator | ott_agent/validation.py uses pinned jsonschema, strict JSON loading and semantic response checks. It gates live, cached and recorded replies. Independent action checks follow it. |

Run tools.check_submission to inspect the checked-in files and formal response validation. Run tools.run_tests for behavioral regression tests. All generated evaluator/live artifacts belong under ignored runs/; no personal key is part of the deliverables.

See ../SUBMISSION.md for the repository root, exact setup/replay commands and how to create an archive without private files. The CLI and complete local replay are supplied; a hosted API is optional under the brief's "CLI or API" wording. Real-phone delivery and production deployment are not claimed as completed.
