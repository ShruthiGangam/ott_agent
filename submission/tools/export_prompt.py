"""Export exactly the active prompt for human review; no API call."""
from pathlib import Path
from ott_agent.prompts import PLANNING_PROMPT,PROMPT_VERSION,PROMPT_SHA256

text=f'''# Model prompt and call contract

Version: {PROMPT_VERSION}. SHA-256: `{PROMPT_SHA256}`.

The runtime makes one joint planning call when a new plan reduces uncertainty.
This call proposes a goal AND one intervention, or explicit no action. There are
no separate LLM calls for the homepage, copy, verification, outcome judging or
measurement. Those use the supplied data and deterministic checks. Unchanged
live plans, holdout viewers, old triggers and missing dialects skip the model.

Primary: `LLM_MODEL` (currently gpt-5.4-mini). Secondary:
`LLM_FALLBACK_MODEL` (currently gpt-4.1-mini), using the same key/endpoint unless
separately configured. At most two logical attempts fit one total time budget;
the assignment ceiling remains eight. A 30-second circuit breaker skips a
repeatedly failing primary. A known whole-provider outage skips both. Final
fallback is a locally evidenced homepage or recorded no action.

Every decision records exact minimized `model_input`, `model_proposal`,
`model_attempts`, actual model name, token usage and prompt version/hash. Cached
responses are labelled separately and never counted as fresh network calls.

Inputs contain only whitelisted goal/rule identifiers, success event/window,
fact enums, freshness categories, offered channels and capped activity counts.
Viewer IDs, raw events, search text, catalogue descriptions, titles, API keys
and URLs are excluded. Fact keys refer to local provenance; generated text
does not supply evidence. Catalogue/pricing data is used only by local code.

G06's 14-day recency and G10's episode-completion proxy are explicit provisional
definitions in ott_agent/assets/goal_interpretations.json. G11 needs an actual TV event; the
supplied simulator does not emit it, so missing TV evidence stays inconclusive.

## Exact system prompt

The evaluator's --provider recorded path reuses bundled genuine replies for
identical minimized contexts. It reads no key and makes no network requests.
Recordings pass the same local jsonschema validator. Missing recordings use a
labelled safe fallback; recorded outputs are not presented as fresh inference.

```text
{PLANNING_PROMPT}
```

## Output example

```json
{{"goal_id":"G12","intervention":"push","reason_code":"reminder","evidence_keys":["F0","F1"],"confidence":0.65}}
```

The response must match a closed JSON schema. The parser rejects extra fields,
duplicate JSON keys, unsupported goal/channel IDs, invented evidence keys,
missing evidence on an action and invalid confidence. Independent local checks
can reject even a syntactically valid, confident response. Message copy comes
from catalogue-derived text or approved templates, never from generated claims.
'''
Path('PROMPTS.md').write_text(text,encoding='utf-8')
