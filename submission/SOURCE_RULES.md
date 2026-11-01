# Field-specific evidence rules

| Fact | Authority / precedence | Freshness or uncertainty rule |
|---|---|---|
| Display dialect | Current app-settings feed; profile is fallback context; campaign link is never a display setting | App event must have nonnegative buffering lag at most ten minutes and receipt within the last 24 hours. The current trigger must name a catalogue-supported dialect; NA/d7/missing values cause insufficient evidence before a model call. Profile/campaign conflicts are recorded explicitly. |
| App language | Known current app language, then warehouse preference | A missing language on a later event does not erase the known language. WhatsApp additionally requires an approved template in that language. |
| Subscription | Observed purchase/renewal/lapse can override stale or contradicted warehouse status | Billing is ordered by buffer-adjusted event time and server receipt. Active/trial entitlement needs a known future plan end. Missing/expired entitlement becomes unknown rather than assumed active. |
| Ever paid | Positive paid purchase or renewal is durable evidence | A stale never-paid snapshot cannot erase a positive paid observation. First-paid eligibility still records the warehouse's explicit never-paid claim as an assumption; missing lifetime history is not proof. |
| Signup | Supplied signup fact or observed signup event | Immutable date with provenance. Absence-based first-play/completion claims require observed signup within the supplied observation period. |
| Push/WhatsApp consent | Snapshot consent can allow a channel; any observed channel opt-out vetoes it | True consent older than seven days cannot authorize sending. Explicit false remains a veto. Check again at dispatch. No consent is inferred from another channel. |
| Series progress | Actual play/completion events and supplied episode catalogue | Require an evidenced unfinished series, known observation coverage and remaining episode. Resume goal binds the series slug and episode evidence. |
| Goal success | Actual event IDs within the committed window and current authoritative success rule | Use IST dates for distinct-day rules. Generated text and provider acceptance are never success evidence. Late attributable signals can revise inconclusive judgments. |
| Delivery | message_delivered for the same action, viewer and channel | Submission/acceptance is not delivery. Wrong-viewer/channel/title receipts cannot update delivery state. |

The 24-hour app-setting and seven-day consent limits are explicit implementation freshness policies, not additional facts claimed to appear in the supplied brief. Raw evidence, timestamps, age, conflict resolutions and assumptions remain local and reviewable. Full replay decisions retain their exact known evidence; later outcome analysis does not rewrite them.
