# Performance and measurement evidence

Historical real-model-backed full replay (benchmarks/live_full): 2,679 unique decisions across 1,746 viewers; 899 actions; 69 actual new network requests and 836 genuine cached replies. Its p95 was 43.584 ms and maximum 20.449 s, with zero 60-second misses. Those are mixed cached/fresh timings.

The separate cold run (benchmarks/cold_failure) made 706 actual requests and had 58 deadline misses after a roughly 682-second request anomaly. No cached or recorded result is presented as proof that this cold-network failure disappeared.

The actor burst (benchmarks/runtime_stress.json) processed 726 jobs, three times the supplied ten-minute peak, plus 726 suppressed duplicates, with zero network calls. It tests local worker/safe-decision capacity, not API quota.

The current evaluator run is in benchmarks/evaluator_replay and explicitly uses recorded replies with zero network calls. It checks the engine, not fresh LLM targeting quality.

Randomized measurement counts all triggered viewers once in assigned arms, including no-action viewers: 863 agent and 883 holdout. Historical full-cohort differences were play +3.79 percentage points, completion +2.71 points and paid purchase -0.73 points. Every approximate 95% interval included zero; positive uplift was not established. Full figures remain in benchmarks/live_full/impact_report.md. Selected per-viewer goal rates and the behavior-selected sample are not causal uplift estimates.
