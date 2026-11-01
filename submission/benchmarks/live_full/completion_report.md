# Requirement-focused completion report



Full supplied replay: 2679 unique decisions across 1746 viewers. Decision kinds: {'ACT': 899, 'ABSTAIN': 1607, 'INSUFFICIENT_EVIDENCE': 173}. Actions: {'home_page': 886, 'push': 12, 'whatsapp': 1}.



Actual fresh network requests: 69; logical attempts including injected faults/cache checks: 917. Sources: {'live_llm_cache': 836, 'not_called': 1766, 'live_llm': 67, 'verified_fallback': 10}. Accepted secondary-model responses: 4.

Measured p95 43.584 ms; maximum 20449.158 ms; decisions over 60s: 0. Maximum logical model calls 2; evidence calls 3.



83 unit tests pass. Independent violations: 0. Unchanged simulator: 31604 events, 0 policy problems.

Separate uncached actual-engine checks exercised in_app_message, push, whatsapp; all had zero safety violations. One later in-app case legitimately abstained. Backend acceptance is distinct from the simulator's confirmed deliveries.



Worker burst: 726 jobs (3x supplied ten-minute peak), 726 duplicate submissions suppressed, 21.89 seconds, p95 219.235 ms, zero network calls. This tests local workers/safe decisions, not OpenAI capacity.



All twelve entry/success paths are implemented and tested. G06 uses provisional fourteen-day lapse recency. G10 uses a provisional episode-completion proxy. Neither is falsely represented as an original supplied definition. G11 accepts actual TV events; absent simulator TV telemetry remains inconclusive. Definition groups: {'original': {'goals': 1200, 'succeeded': 126}, 'provisional': {'goals': 226, 'succeeded': 87}}



See REQUIREMENTS.md and PROMPTS.md in the parent submission folder for exact behavior, surprise-event evidence and instructions. See impact_report.md for randomized differences and intervals; workflow completion is not proof of positive uplift. Real external delivery and deployment were not performed.



The separate cold run made 706 actual requests and had 58 decisions over 60 seconds, including a roughly 682-second primary-request anomaly. Its failure record remains under agent_run_requirements_v3; this hardened pass must not be advertised as an all-fresh network benchmark.



Raw replay decisions/actions are unchanged. Current offline analysis finalizes memory and signal-backed delivery state. Historical failed, interrupted and warm-cache runs are preserved separately.