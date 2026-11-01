# How to test the agent and prepare the repository

This guide is for Windows PowerShell. Copy one command at a time.

## 1. What does CLI mean?

CLI means **Command-Line Interface**. It lets you run the agent by typing a command in PowerShell.

The assessor asked for a **CLI or an API**. Our project provides a CLI, so a website or a hosted server is not needed for this submission.

Our CLI reads the supplied viewer events, makes and records decisions, runs the supplied simulator, and saves the results for review.

"Replay" means running the supplied list of past events through the agent again. The "holdout" is the group of viewers assigned to receive no agent changes, so we have a fair comparison.

## 2. Open the right folder

On your current computer, open PowerShell and run:

```powershell
Set-Location "C:\Users\ADMIN\Documents\ott_agent\one_user_one_agent_pack\submission"
```

All the remaining commands in this guide start from this `submission` folder.

If you are testing an extracted ZIP on another computer, open the `submission` folder inside the extracted `one_user_one_agent_pack` instead. Change only the folder path above; keep the rest of the commands the same.

## 3. Check Python

Your current working folder already has a Python environment. Check it with:

```powershell
..\.venv\Scripts\python.exe --version
```

You should see Python 3.12 or newer. If that works, go to step 4.

### Only for a new copy or another computer

The ZIP does not contain an installed Python environment. That is expected. With Python 3.12 or newer installed, create the environment and install the project requirements:

```powershell
python -m venv ..\.venv
```

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The installation may need internet access. The default agent test below needs no API key or internet access. You do not need to activate the environment; the commands already use it directly.

## 4. Check that the CLI opens

```powershell
..\.venv\Scripts\python.exe replay.py --help
```

You should see help text with choices such as `--out`, `--provider` and `--resume`. This checks that the command opens; it does not run the complete agent yet.

## 5. Run the complete supplied replay

Run this one command:

```powershell
..\.venv\Scripts\python.exe replay.py --out runs/my_cli_test
```

This is the **one-command replay** the assessor asked for. It:

1. Reads the supplied history and trigger files.
2. Handles the supplied changes, late events, duplicates and failures.
3. Records each viewer's decision and explanation.
4. Runs `simulator/simulate_outcomes.py` to generate follow-up viewer events.
5. Saves goal outcomes and the comparison with the holdout group.

You will see messages such as `Loading local history...` and `Processed .../2769 trigger deliveries`. Some supplied failure cases deliberately slow the run, so allow several minutes. Wait for the final line:

```text
Run saved to ...\submission\runs\my_cli_test
```

Immediately afterwards, check:

```powershell
$LASTEXITCODE
```

`0` means the command finished successfully. Also run the checks in step 7; finishing the command alone does not prove every requirement passed.

### Does this use live AI?

The default replay uses saved, validated replies from earlier real AI calls when the inputs match. This lets the assessor run the full program without your personal API key. Missing replies use a clearly recorded safe fallback.

This checks the agent's full workflow. It does not measure the quality or speed of fresh AI requests. Optional live mode is explained in step 9.

## 6. Open the saved results

Open the result folder:

```powershell
Invoke-Item .\runs\my_cli_test
```

Start with these files:

| File or folder | What to look for |
|---|---|
| `responses.csv` | Open it in a spreadsheet. Read `final_reason` to understand why the agent acted or did nothing. Use Wrap Text if a cell is long. |
| `decisions.jsonl` | Full decision records, including the goal, evidence, source times, model proposal and checks. |
| `actions.jsonl` | The changes the agent actually published. |
| `no_action_decisions.jsonl` | Decisions where the agent deliberately did nothing, with reasons. |
| `state.sqlite` and `viewer_state/` | Saved viewer memory. The program keeps this after it stops. |
| `outcomes.jsonl` | Whether each goal succeeded, failed or had too little evidence to judge. Some goals may remain open beyond the observation period. |
| `sim/simulator_report.json` | Proof that the supplied simulator ran, plus its policy checks. |
| `impact_report.md` | The comparison between viewers assigned to the agent and viewers assigned to the holdout. |
| `final_report.md` | A short summary of the completed replay. |

For this supplied pack, expect **2,679 unique decisions across 1,746 triggered viewers**, from **2,769 deliveries**. The **90 repeated deliveries** should not create repeated decisions. The pack has 5,000 viewers overall; the other 3,254 have no supplied trigger in this replay.

Do not expect every decision to take an action or every goal to succeed. A valid result can be "do nothing", "not enough evidence", or a failed goal recorded honestly.

## 7. Check the assessor's requirements

### A. Check the completed replay

```powershell
..\.venv\Scripts\python.exe -m tools.assess_run runs/my_cli_test
```

Look for:

```text
"all_checks_passed": true
```

This also creates `requirements_report.md` in the result folder. Read it if any check is false. In particular, do not ignore a failed time-budget check.

The printed result matters: this particular report command can finish with exit code 0 even when one of its checks is false.

### B. Check saved model replies

```powershell
..\.venv\Scripts\python.exe -m ott_agent validate-responses --decisions runs/my_cli_test/decisions.jsonl
```

Look for `"passed": true` and `"rejected_count": 0`. This checks the reply format and allowed values. The separate action checks establish whether an action was allowed.

### C. Run the automated tests

```powershell
..\.venv\Scripts\python.exe -m tools.run_tests
```

At the time this guide was written, the result was **103 tests, OK**. These include the required tests for a late or repeated trigger, conflicting sources, a tool failure and a corrected goal rule.

### D. Check the submission files

```powershell
..\.venv\Scripts\python.exe -m tools.check_submission
```

Look for `"passed": true` and `"missing_files": []`. This checks the required files, sample records, saved-reply collection and possible API-key leaks in the files it scans. The ZIP packager also checks the files selected for the archive.

### A quick result checklist

| Result file | Good result |
|---|---|
| `verification_report.json` | `violation_count` is `0`. |
| `sim/simulator_report.json` | `policy_problem_count` is `0`. |
| `latency_report.json` | `over_60s` is `0`; maximum model calls are no more than `8`, and maximum tool calls are no more than `20`. |
| `requirements_report.md` | All listed checks say `PASS`. |
| `responses.csv` | Decisions have understandable reasons, including reasons for no action. |

An earlier run had a long timing failure. It is preserved in `benchmarks/explanation_latency_failure/`; a later clean archive replay passed. If your run fails, keep its results and investigate the failed check. A passing replay also does not mean the agent has proved positive business improvement; read the uncertainty shown in the impact report.

## 8. Run again without overwriting the first result

Choose a new result folder:

```powershell
..\.venv\Scripts\python.exe replay.py --out runs/my_cli_test_2
```

Use `--resume` only when you want to continue the same saved run, for example after an interruption:

```powershell
..\.venv\Scripts\python.exe replay.py --out runs/my_cli_test --resume
```

An "output already contains a run" message protects your earlier results. Use a new folder name for a separate test.

## 9. Optional: test with your API key

Your own configured key must stay in the local `submission/.env` file. Do not copy the key into this guide, the repository or a message to the assessor.

```powershell
..\.venv\Scripts\python.exe replay.py --provider live --out runs/my_live_cli_test
```

This uses the configured provider and may reuse matching cached replies. Check `model_source` in the output to distinguish fresh replies, cached replies and fallbacks. Run the step 7 checks again, using `runs/my_live_cli_test` as the result folder.

The assessor can use the default mode without your key. If they choose live mode, they should use their own key and settings.

## 10. What should go in the repository?

A repository is the project folder you share with the assessor. Use **`one_user_one_agent_pack` as its root**, rather than the whole `ott_agent` working folder.

The assessor wants enough files to run, test and review the project. They have not asked for every file on your computer. The ZIP is a selected package of project files and supporting evidence; it excludes your private configuration and large generated working folders.

Keep this structure:

```text
one_user_one_agent_pack/
  README.md
  SUBMISSION.md
  .gitignore
  data/
  config/
  replay/
  pilot/
  simulator/
  submission/
    README.md
    CLI_TEST_GUIDE.md
    replay.py
    requirements.txt
    pyproject.toml
    .env.example
    ott_agent/             # Agent code and saved-reply assets
    tests/                 # Automated tests
    tools/                 # Run checks and packaging commands
    sample_replay/         # Small example with decisions and outcomes
    benchmarks/            # Saved test evidence, including failures
    ARCHITECTURE.md
    AI_COLLABORATION.md
    KNOWN_LIMITATIONS.md
    ...                    # Supporting project notes already in the ZIP
```

Keep `data/`, `config/`, `replay/`, `pilot/` and `simulator/` because **the current program reads them**. The assessor may already own the original pack, but including it makes this copy runnable without guessing where their copy is stored. Follow different delivery instructions if the assessor explicitly provides them.

The assignment PDF is useful reference material, but it is not needed to execute the CLI. Some extra reports and notes are included to help review. The brief does not require every historical report, but the current tests read parts of `benchmarks/`, so keep the supplied selection when using this submission as it is.

### How this matches the eight requested items

| What the assessor requested | What we provide |
|---|---|
| A CLI or API, setup instructions and one replay command | `replay.py`, `README.md` and this guide. |
| Saved viewer state, evidence and decisions | The storage code, sample state exports, and files produced by a replay. |
| A way to evaluate without your personal key | The recorded provider and its saved, validated real AI replies. |
| Tests for late/duplicate triggers, conflicts, failures and a corrected rule | Tests in `tests/`, checked by `tools.run_tests`. |
| A sample with decisions, actions, no-action reasons, outcomes and impact | `sample_replay/`. |
| An architecture note | `ARCHITECTURE.md`. |
| A short AI collaboration log | `AI_COLLABORATION.md`. |
| A known-limitations note | `KNOWN_LIMITATIONS.md`. |

These are the required submission categories. Their presence does not mean production delivery, unseen cases or every timing condition has been proved; the limitations and saved failures remain part of the submission.

### What must stay out?

Do not upload these:

- `.env` or any real API key.
- `.venv/`, the installed Python environment.
- Private `.llm_response_cache...` files.
- `submission/runs/`, which holds your large local test runs and temporary review copies.
- `__pycache__/`, `.pyc` files or installed `.egg-info/` folders.
- The submission ZIP inside the repository itself, unless the assessor specifically asks for an archive there.

Keep `.env.example`: it shows the setting names without supplying a real key. Keep `sample_replay/`: it is the small review example the assessor requested, rather than your entire generated run history.

## 11. How to hand it over

1. Extract the prepared ZIP into a separate folder.
2. Use the contents of its `one_user_one_agent_pack` folder for the repository. Preserve the folder structure and `.gitignore`.
3. Follow steps 2 to 7 in the extracted copy to check what the assessor will receive.
4. If they ask for a repository link, share the repository containing those extracted files and give them access. Do not put only the ZIP into an otherwise empty repository.
5. If their submission page accepts a ZIP instead, upload the prepared ZIP.

Use the assessor's instructions for the submission website and whether the repository should be private or public; that information has not been provided here. [SUBMISSION.md](../SUBMISSION.md) has the full handoff checklist.

## 12. Common problems

| What you see | What to do |
|---|---|
| Python path cannot be found | Make sure PowerShell is in `submission/`. For a new copy, run the setup commands in step 3. |
| `No module named jsonschema` | Run the requirements installation command in step 3. |
| The result folder already contains a run | Choose a new `--out` folder, or deliberately resume the interrupted run. |
| A check prints `false` | Open the named report and keep the failed results. Do not call that run a pass. |
| A live request fails | Check your local settings and the recorded fallback reason. You can still test the full default replay without a key. |
| PowerShell shows a red line saying `wrote ... events` | The simulator writes its completion notice to a channel PowerShell can colour red. Check the final `Run saved to` line, `$LASTEXITCODE`, and the reports before deciding the run failed. Other error messages still need investigation. |

