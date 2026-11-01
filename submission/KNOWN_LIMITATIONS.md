# Known limitations

- No production deployment or real push/WhatsApp provider integration was performed. Published actions, durable local backend acceptance and simulator delivery are validated; no real phone was contacted.
- G06's fourteen-day lapse recency and G10's episode-completion proxy are explicit implementation assumptions, not supplied definitions. They are labelled and can be replaced by authoritative corrections.
- G11 accepts tv_app_open events, but the supplied simulator emits none. Missing TV evidence is inconclusive.
- Recorded mode is a key-free evaluator path using historical genuine replies. Unseen inputs can fall back to local rules. It does not test current model quality, API access or fresh-network latency.
- Historical cold timing failures remain in benchmarks/cold_failure and benchmarks/early_cold. A passing cached/recorded run does not erase them or guarantee host/network availability.
- A subsequent recorded replay encountered a roughly 642-second elapsed-time anomaly during a scheduled 8-second degraded-store read. It caused 20 deadline misses, all recorded as no action. The cause is unconfirmed; full failure records and the failed budget check remain in benchmarks/explanation_latency_failure/.
- Local worker ownership and a three-times-peak burst were tested without network calls. Distributed leases, resharding, cross-region recovery and hosted capacity are not established.
- Source history is incomplete. Clock jumps, missing lifetime history, expired entitlements and stale consent can require abstention.
- Confidence is not calibrated. Randomized simulator comparisons do not establish positive real-world business uplift.
- The LLM returns a reason category and evidence keys. The application supplies a factual decision explanation, but cannot establish why a model preferred one eligible alternative over every other alternative. Historical decisions lack some entry counts; their derived explanations label those gaps.
- Local SQLite/JSON files are not application-encrypted. Provider retention settings remain unverified; live transmission requires explicit scoped authorization. The evaluator path transmits nothing.
- The compact sample is behavior-selected. Its impact report intentionally uses the full randomized cohort; the subset is not a representative causal sample.
