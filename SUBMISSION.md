# Candidate submission

The implementation and setup instructions are in [submission/README.md](submission/README.md).

For simple step-by-step testing and an explanation of which files belong in the repository, use [submission/CLI_TEST_GUIDE.md](submission/CLI_TEST_GUIDE.md).

After installing submission/requirements.txt into a Python 3.12+ environment,
run the complete trigger stream from this pack directory with one command:

    python submission/replay.py

This evaluator path requires no personal API key and no runtime network access.
It writes durable state, decisions, actions, outcomes, validation and randomized
impact reports under submission/runs/evaluator. Pass --out for another folder or
--resume to reuse durable progress. Live mode is available with the evaluator's
own credentials: add --provider live.

Review [submission/SUBMISSION_CHECKLIST.md](submission/SUBMISSION_CHECKLIST.md)
for all requested deliverables. Original supplied data, configuration, replay
scripts and simulator remain unchanged.

## What to submit

Use one_user_one_agent_pack as the repository root. Include the supplied data/, config/, replay/, pilot/ and simulator/ so the evaluator can reproduce the run, together with submission/ and the brief. Keep the original pack README.md, this submission guide and submission/README.md.

| Assessment deliverable | Repository location |
|---|---|
| Runnable CLI, setup and one replay command | submission/replay.py, submission/README.md, submission/requirements.txt and submission/pyproject.toml |
| Durable viewer state, evidence and decisions | submission/ott_agent/store.py; sample_replay/viewer_state.jsonl and decisions.jsonl under submission/; each replay creates state.sqlite and viewer_state/ |
| Provider abstraction without your personal key | submission/ott_agent/recorded_provider.py and its bundled validated real-response assets; recorded mode needs no key or runtime network |
| Late/duplicate, conflict, tool-failure and corrected-rule tests | submission/tests/test_agent.py, test_more.py and test_requirements_v2.py; further regressions in the same directory |
| Sample decisions, actions, no-action reasons, judgments and impact | submission/sample_replay/; readable responses.csv and explanations.jsonl accompany the original historical decisions |
| Architecture: ownership, planning, memory, verification, latency, recovery and trust | submission/ARCHITECTURE.md, with SOURCE_RULES.md and SECURITY.md for detail |
| Short AI collaboration log | submission/AI_COLLABORATION.md |
| Known limitations | submission/KNOWN_LIMITATIONS.md |

Do not submit .env, .venv/, .llm_response_cache files, __pycache__/, installed egg-info/, or submission/runs/. The compact sample, benchmark evidence, requirements, tests and recorded-provider assets must remain included. A source repository need not include an installed environment or a generated SQLite database: the evaluator creates them, and portable sample viewer-state exports are already included.

## Evaluator setup and run

From the repository root in Windows PowerShell, with Python 3.12 or newer:

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r submission\requirements.txt
    .\.venv\Scripts\python.exe submission\replay.py

The third line is the single replay command. It processes the entire supplied trigger script, applies its disturbances, invokes the original simulator and writes submission/runs/evaluator/. Open responses.csv for explanations, decisions.jsonl for full evidence, outcomes.jsonl for goal judgments and impact_report.md for the randomized comparison. On a second run choose --out submission/runs/another_replay or use --resume deliberately.

For tests and the deliverable checker, from submission/:

    ..\.venv\Scripts\python.exe -m tools.run_tests
    ..\.venv\Scripts\python.exe -m tools.check_submission

The dependency installation may need internet access; recorded replay and tests run without an API key or network. Live mode is optional and requires the evaluator's own configuration.

## Preparing the repository for handoff

The included packager selects the source, supplied inputs and preserved review evidence explicitly, checks for possible API keys, and creates a ZIP with SHA-256 manifest. From submission/:

    ..\.venv\Scripts\python.exe -m tools.package_submission --out ..\..\ott_agent_submission_20261101.zip

Use the extracted one_user_one_agent_pack folder as the source for the repository you share. If the assessment portal asks for a repository URL, provide that URL and ensure the evaluator has access. If it accepts a ZIP, the generated source archive contains the same files. The supplied brief does not establish a submission portal, repository visibility or invitation address; follow the evaluator's delivery instructions for those details. Nothing has been uploaded or published automatically.

The eight requested submission categories are present. This is a local agent and simulator submission. The limitations note explicitly retains provisional G06/G10 definitions, absent TV telemetry, historical timing failures and unvalidated production/real-phone delivery. A passing replay does not prove positive business uplift.
