# One viewer, one lifecycle agent

A local lifecycle agent with one durable owner, measurable goal and active plan per viewer. Live OpenAI proposes goals/interventions; independent code checks evidence and policy before publishing. The supplied simulator produces outcomes. Nothing is deployed and no real phones are contacted.

For a plain-English walkthrough with copyable PowerShell commands and expected results, start with [CLI_TEST_GUIDE.md](CLI_TEST_GUIDE.md).

## Setup

Requires Python 3.12 or newer. From this submission directory in PowerShell:

    python -m venv ..\.venv
    ..\.venv\Scripts\python.exe -m pip install -r requirements.txt

For the existing workspace, the environment is already created. On macOS/Linux use ../.venv/bin/python for the commands below.

## One-command evaluator replay — no API key required

    ..\.venv\Scripts\python.exe replay.py

This processes the complete supplied trigger script and runs the unchanged simulator. It writes durable SQLite state, per-viewer exports, decisions, actions, no-action reasons, goal outcomes, response validation, timing, independent policy audit and randomized impact into runs/evaluator.

Open responses.csv for readable explanations: goal eligibility and its evidence, how the goal was selected or retained, the channel/content rule, the success signal and deadline, and any verifier veto. explanations.jsonl and decisions.jsonl retain the structured explanation and decision-time planning facts. reason_code is a stable machine label; final_reason is the human explanation. No additional model request is needed to produce it.

The evaluator provider reuses 687 validated replies from earlier real-model runs for identical minimized inputs. It makes no network calls, reads no .env and fabricates no LLM responses. Missing recordings or injected failures use a labelled safe local fallback. Recorded runs measure engine behavior, not fresh model quality. The output explicitly says provider_mode=recorded and model_source=recorded_llm or verified_fallback.

To choose another output or resume:

    ..\.venv\Scripts\python.exe replay.py --out runs/another_replay
    ..\.venv\Scripts\python.exe replay.py --resume

The equivalent explicit CLI is:

    ..\.venv\Scripts\python.exe -m ott_agent replay --provider recorded --pack .. --out runs/evaluator

## Live mode with your own credentials

Create .env from .env.example and fill your own key locally. The primary model is gpt-5.4-mini and the secondary is gpt-4.1-mini; both are configurable. The secondary reuses the primary key unless set separately.

    ..\.venv\Scripts\python.exe replay.py --provider live --out runs/my_live_run

Live mode validates HTTPS hosts and the explicit data-handling authorization flags. The bundled evaluator mode needs neither credentials nor those flags. Never include .env or .venv in the submission.

Optional installable console CLI:

    ..\.venv\Scripts\python.exe -m pip install -e .
    ..\.venv\Scripts\ott-agent.exe replay --provider recorded --pack .. --out runs/console_replay

## Validate and test

    ..\.venv\Scripts\python.exe -m ott_agent validate-responses --decisions sample_replay/decisions.jsonl
    ..\.venv\Scripts\python.exe -m tools.run_tests
    ..\.venv\Scripts\python.exe -m tools.check_submission

To update readable explanations for an older saved replay without rewriting its original decisions or LLM replies:

    ..\.venv\Scripts\python.exe -m tools.export_responses --run runs/full_user_check_20261101

Those explanations are labelled historical_record_rendering. Missing original entry counts are stated explicitly; later outcomes are never used to explain an earlier choice.

Responses are validated locally with jsonschema.Draft202012Validator, including types, required fields, permitted goal/channel IDs, evidence references and finite confidence. Duplicate keys, extra claims and malformed JSON are rejected. Fresh factual and policy checks remain independent of schema validation. Unit tests require no key or network.

## Submission evidence

- [Technical checklist](SUBMISSION_CHECKLIST.md): every requested deliverable and its file.
- [What to submit and how](../SUBMISSION.md): repository contents, exclusions, evaluator commands and packaging.
- [Sample replay manifest](sample_replay/manifest.json): 21 viewers, 46 historical decisions, actions, no-action reasons, state exports and judged outcomes.
- [Full replay report](benchmarks/live_full/completion_report.md) and the benchmark guide below: full-cohort reports and preserved cold-run timing failures.
- [Architecture](ARCHITECTURE.md), [exact prompt](PROMPTS.md), [source rules](SOURCE_RULES.md), [collaboration log](AI_COLLABORATION.md), [limitations](KNOWN_LIMITATIONS.md) and [security](SECURITY.md).

The sample is a behavior-selected excerpt of the historical real-model-backed replay, including all decisions, actions and goals for the selected viewers, their state exports, trigger deliveries and simulator observations. Its impact files describe the full randomized cohort of 1,746 viewers; do not estimate causal impact from the selected sample. Use the evaluator command above to regenerate a complete replay with durable SQLite state; its outputs are labelled recorded. Generated runs are ignored; sample_replay and benchmarks are part of the submission.

All twelve goal paths exist. G06/G10 use visible provisional definitions in ott_agent/assets/goal_interpretations.json. G11 needs an actual TV event; missing simulator TV telemetry remains inconclusive.

## Benchmark guide

These compact reports preserve evidence from earlier runs. Counts and timings describe those runs, rather than promising identical results on every replay. Paths below are relative to benchmarks/.

| Directory/file | Evidence |
|---|---|
| live_full/ | Historical full replay: 2,679 decisions, 1,746 viewers, 886 homepages, 12 push plans and one WhatsApp plan. It mixed 69 fresh network requests with 836 cached replies. |
| cold_failure/ | Separate cold replay: 706 actual requests and 58 deadline misses around a roughly 682-second request anomaly. Full failing decisions remain in deadline_failures.jsonl. |
| explanation_latency_failure/ | Recorded replay with a roughly 642-second elapsed-time anomaly during a degraded-store read and 20 deadline misses. All late decisions abstained; failing records and timing are retained. |
| explanations_verified/ | Clean extracted-archive replay: all 2,679 decisions carry evidence-backed explanations; 103 extracted-copy tests passed; zero deadline misses and policy problems. Includes current decision examples. |
| early_cold/, early_warm/ | Earlier timing records, kept separate from the latest results. |
| messages_complete/ | Authored live engine/simulator check covering push, WhatsApp and in-app, including a real secondary-model response. |
| messages_abstention/ | Later run where the model abstained on in-app. The historical channel-coverage failure flag is preserved; it does not indicate a policy violation. |
| runtime_stress.json | Three-times-peak local actor burst with zero network calls. |
| response_validation.json | Formal validation of all 903 accepted historical full-run proposals. |
| live_validator_check.json | Five fresh uncached API checks through the formal validator, including fallback. |
| evaluator_replay/ | Complete key-free recorded-provider replay reports. |
| test_report.json | Automated regression results. |
| cleanup_manifest.json | Removed generated paths, bytes reclaimed and preserved evidence references. |

Old full-run folder names in copied reports are provenance labels; their retained reports now live under benchmarks/.
