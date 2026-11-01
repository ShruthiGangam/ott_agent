# Current submission status

The application includes live planning and a key-free recorded-response evaluator provider. Local JSON Schema validation gates responses from both. Durable viewer state, independent action verification, messaging, replay controls, outcome judging and randomized impact reporting are implemented.

Use README.md for setup and the one-command evaluator replay. SUBMISSION_CHECKLIST.md maps each technical deliverable to code and evidence. sample_replay is a compact historical excerpt; benchmarks retains full-cohort summaries and timing failures. New runs write durable SQLite and exports under ignored runs/.

The latest historical full live-backed run had 2,679 decisions across 1,746 viewers, with 886 homepages, 12 push plans and one WhatsApp plan, zero policy violations and zero deadline misses. It reused replies and is not an all-fresh benchmark. The separate cold run had 58 deadline misses and remains visible in benchmarks/cold_failure.

G06/G10 have explicit provisional definitions. Missing G11 TV telemetry remains inconclusive. Real external delivery and deployment are intentionally excluded. See benchmarks/test_report.json and benchmarks/evaluator_replay for the current verification results.
