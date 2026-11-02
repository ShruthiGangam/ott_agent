# Technical and submission requirements: assessor guide

This guide maps each of the eight requested deliverables to its files and explains how to run and inspect the submission.

**Starting folder:** open a terminal in `submission/`. All links and file paths below are relative to that folder. Paths beginning with `../` point to the supplied pack beside it. No personal API key is needed for the default evaluation.

## 1. Runnable CLI, setup and one-command replay

The submission provides a CLI: a program run from the terminal. A hosted API is not required under the brief's "CLI or API" wording.

| File | Purpose |
|---|---|
| [replay.py](replay.py) | Entry point; defaults to the key-free recorded provider. |
| [requirements.txt](requirements.txt) | Dependencies needed to run the project. |
| [pyproject.toml](pyproject.toml) | Package details and optional `ott-agent` command. |
| [README.md](README.md) | Additional setup, live-provider and replay options. |

### First-time setup

Requires Python 3.12 or newer. Keep the supplied [data](../data/), [config](../config/), [replay](../replay/), [pilot](../pilot/) and [simulator](../simulator/) folders beside `submission/`; the program reads them.

**Windows PowerShell, from `submission/`:**

```powershell
python -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS/Linux, from `submission/`:**

```bash
python3 -m venv ../.venv
../.venv/bin/python -m pip install -r requirements.txt
```

Dependency installation may need internet access. The default replay and automated tests need no API key or runtime network access. Environment activation is unnecessary when using these commands.

### One command to replay the complete supplied trigger script

**Windows:**

```powershell
..\.venv\Scripts\python.exe replay.py
```

**macOS/Linux:**

```bash
../.venv/bin/python replay.py
```

This reads [the trigger script](../replay/triggers.jsonl), processes the accompanying event changes and faults, records decisions, runs [the original outcome simulator](../simulator/simulate_outcomes.py), and writes results to `runs/evaluator/`.

The final message is `Run saved to ...`. Confirm `runs/evaluator/progress.json` says `"stage": "complete"`. Progress messages are periodic, so the last intermediate message can show 2,750 even though all 2,769 deliveries were handled.

The supplied stream contains 2,769 deliveries, representing 2,679 unique triggers across 1,746 viewers. The 90 duplicates should not produce additional decisions. The remaining viewers in the 5,000-viewer pack have no supplied trigger in this replay.

For a separate second run, choose another output folder:

```powershell
..\.venv\Scripts\python.exe replay.py --out runs/evaluator_second
```

To continue an interrupted run without republishing saved decisions:

```powershell
..\.venv\Scripts\python.exe replay.py --out runs/evaluator --resume
```

For command help:

```powershell
..\.venv\Scripts\python.exe replay.py --help
```

For the remaining Windows examples, use `../.venv/bin/python` instead of the Windows Python path on macOS/Linux.

## 2. Durable per-viewer state, evidence references and decision outputs

| What to inspect | Included example or implementation | Created by a full replay |
|---|---|---|
| Persistent viewer memory | [Storage implementation](ott_agent/store.py); [sample viewer states](sample_replay/viewer_state.jsonl) | `runs/evaluator/state.sqlite` and `runs/evaluator/viewer_state/` |
| Decisions and evidence references | [Sample decisions](sample_replay/decisions.jsonl) | `runs/evaluator/decisions.jsonl` |
| Readable reasons | [Sample CSV](sample_replay/responses.csv); [explanation code](ott_agent/explanations.py) | `runs/evaluator/responses.csv` and `runs/evaluator/explanations.jsonl` |
| Actions actually published | [Sample actions](sample_replay/actions.jsonl) | `runs/evaluator/actions.jsonl` |
| Rule and control changes | [Sample control log](sample_replay/control_audit.jsonl) | `runs/evaluator/control_audit.jsonl` |

SQLite preserves state across process restarts. Unique trigger, action and open-goal constraints help prevent duplicate decisions and competing goals for one viewer. The source repository includes portable state examples; the full working database is created when the evaluator runs the replay.

In `decisions.jsonl`, inspect `user_id`, `goal`, `evidence`, `conflicts`, `checks` and model-source fields. Evidence records retain their source, time and age. New decisions also record `planning`, `reason_code`, `final_reason` and `explanation`.

`responses.csv` is the easiest starting point. Its `final_reason` explains the recorded eligibility facts, selection or fallback, channel, success signal, deadline and any reason for blocking action. Historical example explanations are labelled `historical_record_rendering`; missing historical details are stated rather than inferred from later outcomes.

## 3. Evaluation without a personal API key

| File | Purpose |
|---|---|
| [Provider interface and recorded provider](ott_agent/recorded_provider.py) | `ModelProvider` defines the model boundary; `RecordedProvider` supplies saved genuine replies. |
| [Recorded replies](ott_agent/assets/recorded_responses.jsonl) | Bundled real-model responses for matching, minimized inputs. |
| [Reply collection metadata](ott_agent/assets/recorded_responses.meta.json) | Entry count, checksum and provenance information. |
| [Response validator](ott_agent/validation.py) | Checks replies before the engine accepts them. |
| [Live provider](ott_agent/provider.py) | Optional live API calls and secondary-provider recovery. |
| [Settings template](.env.example) | Setting names without the submitter's real key. |

The replay command in section 1 automatically selects recorded mode. It does not read a personal `.env`, contact the model service or require the submitter's credentials.

Saved replies supply model proposals only. The engine still reads events, manages viewer memory, verifies actions, runs the simulator and evaluates outcomes. An unmatched input or injected failure uses a labelled safe fallback; it is not reported as a successful model response.

Outputs identify `provider_mode` and `model_source`. Recorded results measure the engine's workflow, not fresh model quality or network response time.

Live mode is optional. An evaluator can configure their own local `.env` using the template and the README, then run:

```powershell
..\.venv\Scripts\python.exe replay.py --provider live --out runs/evaluator_live
```

Live mode may reuse matching cached replies. Inspect `model_source` and network-attempt fields to distinguish fresh calls, cached replies and fallbacks. Real credentials must stay outside the submitted repository.

## 4. Automated tests for the required cases

Run the complete test suite from `submission/`:

```powershell
..\.venv\Scripts\python.exe -m tools.run_tests
```

Look for `OK`, with no failures or errors. The command writes a current result to `benchmarks/test_report.json`. The included [test report](benchmarks/test_report.json) records 103 passing tests; this is saved evidence, not a substitute for rerunning them.

| Required case | Test file | Tests to locate |
|---|---|---|
| Late or duplicate trigger | [tests/test_agent.py](tests/test_agent.py) | `test_late_trigger_no_action`; `test_duplicate_is_idempotent` |
| Conflicting sources | [tests/test_agent.py](tests/test_agent.py) | `test_current_dialect_wins_and_content_matches`; `test_purchase_overrides_stale_never` |
| Tool failure | [tests/test_agent.py](tests/test_agent.py) | `test_model_outage_falls_back`; `test_slow_store_abstains_if_budget_small` |
| Corrected goal rule | [tests/test_agent.py](tests/test_agent.py) | `test_corrected_rule_updates_open_goal` |

Additional coverage includes [correction idempotency](tests/test_more.py), [messaging and lifecycle requirements](tests/test_requirements_v2.py), [response validation](tests/test_validation.py), [recorded-provider behavior](tests/test_recorded_provider.py) and [decision explanations](tests/test_explanations.py).

## 5. Sample replay: decisions, actions, no-action reasons, outcomes and impact

The included [sample manifest](sample_replay/manifest.json) identifies 21 selected viewers and 46 historical decisions. It records the sample's origin and the original simulator checksum.

| Requested evidence | Included file |
|---|---|
| Decisions | [sample_replay/decisions.jsonl](sample_replay/decisions.jsonl) |
| Actions taken | [sample_replay/actions.jsonl](sample_replay/actions.jsonl) |
| Reasons for no action | [sample_replay/no_action_decisions.jsonl](sample_replay/no_action_decisions.jsonl) |
| Readable explanations | [sample_replay/responses.csv](sample_replay/responses.csv) and [explanations.jsonl](sample_replay/explanations.jsonl) |
| Goal outcome judgments and supporting signals | [sample_replay/outcomes.jsonl](sample_replay/outcomes.jsonl) |
| Impact report | [sample_replay/impact_report.md](sample_replay/impact_report.md) and [machine-readable report](sample_replay/impact_report.json) |
| Viewer memory | [sample_replay/viewer_state.jsonl](sample_replay/viewer_state.jsonl) |
| Simulator observations | [sample_replay/sim/outcome_events.jsonl](sample_replay/sim/outcome_events.jsonl) |

The sample is selected to demonstrate behavior. Its impact files deliberately describe the **full randomized cohort of 1,746 viewers**, not just the selected sample. Do not estimate causal impact from the selected viewers alone.

A full replay creates the same types of outputs for the complete supplied trigger stream under `runs/evaluator/`. Goal judgments use observed events within the committed goal window. Missing evidence or an incomplete observation window remains inconclusive. A goal may still be open when its deadline is beyond the available observation period.

The supplied simulator is used by default. It generates follow-up behavior and delivery observations; no real viewer or phone is contacted. The impact report compares assigned agent and holdout groups and reports uncertainty. Individual goal success is not proof that the agent caused it.

## 6. Architecture note

Read [ARCHITECTURE.md](ARCHITECTURE.md). It covers every requested architecture topic:

| Topic | Design and implementation to inspect |
|---|---|
| Ownership | One logical owner, one open goal and one active plan per viewer; [store.py](ott_agent/store.py) and [runtime.py](ott_agent/runtime.py). |
| Planning | Goals and plans change with evidence, purchases, expiry or corrected rules; [engine.py](ott_agent/engine.py) and [prompts.py](ott_agent/prompts.py). |
| Memory | Persistent facts, provenance, decisions, outcomes and learning; [store.py](ott_agent/store.py) and [SOURCE_RULES.md](SOURCE_RULES.md). |
| Verification | Independent eligibility, dialect, content, consent, timing, frequency and duplicate checks; [engine.py](ott_agent/engine.py), [messaging.py](ott_agent/messaging.py) and [audit.py](ott_agent/audit.py). |
| Latency | Decision and call budgets, queue delay and measured timings; [engine.py](ott_agent/engine.py), [provider.py](ott_agent/provider.py) and each run's `latency_report.json`. |
| Failure recovery | Durable decisions, restart handling, provider fallback, safe abstention and delivery rechecks; [runtime.py](ott_agent/runtime.py), [provider.py](ott_agent/provider.py) and [delivery.py](ott_agent/delivery.py). |
| Trust boundaries | Minimized model inputs, strict reply validation and locally enforced action approval; [validation.py](ott_agent/validation.py), [SECURITY.md](SECURITY.md) and [PROMPTS.md](PROMPTS.md). |

The replay CLI runs the ordered supplied stream. Worker ownership and local concurrency have separate tests; production deployment and distributed capacity are not claimed as validated.

## 7. AI collaboration log

Read [AI_COLLABORATION.md](AI_COLLABORATION.md).

It describes Codex's contribution to the implementation, prompts, checks, documentation and packaging. It also explains how outputs were checked against the supplied pack, automated tests, real API responses, independent action audits and the unchanged simulator. Failures found during testing were retained and documented.

## 8. Known limitations

Read [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). The submission explicitly records:

- No production deployment or real push/WhatsApp provider delivery.
- Provisional definitions for G06 lapse recency and G10 meaningful engagement, stored in [goal_interpretations.json](ott_agent/assets/goal_interpretations.json).
- Missing TV-event coverage in the simulator; G11 needs actual TV evidence and absence remains inconclusive.
- Recorded mode does not measure fresh model quality; unseen inputs may require fallback.
- Historical timing failures, incomplete source history and unverified distributed scale.
- Uncalibrated confidence, limited model-selection explanations and no established positive real-world impact.
- Unverified provider retention settings and local files without application-level encryption.

The preserved [cold-run timing report](benchmarks/cold_failure/latency_report.json) and [later recorded timing failure](benchmarks/explanation_latency_failure/latency_report.json) remain available. The [clean extracted-archive verification](benchmarks/explanations_verified/archive_verification.json) records a passing retry. A later passing run does not erase earlier failures or guarantee every future timing condition.

## Final evaluator checks

After the default replay completes, run:

```powershell
..\.venv\Scripts\python.exe -m tools.assess_run runs/evaluator
..\.venv\Scripts\python.exe -m ott_agent validate-responses --decisions runs/evaluator/decisions.jsonl
..\.venv\Scripts\python.exe -m tools.check_submission
```

| Check | What to look for |
|---|---|
| Completed-run assessment | Printed `"all_checks_passed": true`; details in `runs/evaluator/requirements_report.md`. Inspect this boolean: the report command can exit normally even when a check is false. |
| Reply validation | `"passed": true` and `"rejected_count": 0`. This checks the reply contract; action safety has separate checks. |
| Submission inventory | `"passed": true` and `"missing_files": []`. |
| Independent action audit | `runs/evaluator/verification_report.json`: `violation_count` is `0`. |
| Simulator safety | `runs/evaluator/sim/simulator_report.json`: `policy_problem_count` is `0`. |
| Time budget | `runs/evaluator/latency_report.json`: inspect `over_60s`, percentiles, maximum time and model/tool-call counts. |

The repository contains the eight requested deliverables. These checks assess their implementation within the documented local replay scope; they do not establish production readiness or positive business uplift.
