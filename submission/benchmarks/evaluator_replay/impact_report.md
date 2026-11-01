# Impact report

Fixed 7-day outcomes, using every unique triggered user once in their assigned arm. No filtering by whether the agent served them.

| Metric | Agent | Holdout | Difference (pp) | Approx. 95% CI (pp) |
|---|---:|---:|---:|---:|
| play_started | 580/863 (67.21%) | 560/883 (63.42%) | 3.79 | -0.67 to 8.25 |
| episode_completed | 385/863 (44.61%) | 370/883 (41.90%) | 2.71 | -1.94 to 7.36 |
| purchase_completed | 24/863 (2.78%) | 31/883 (3.51%) | -0.73 | -2.37 to 0.91 |

Intervals are approximate and unadjusted for multiple metrics. Goal attainment is descriptive because goals differ across viewers. Observed success after a page is not individual causal attribution.

Pilot randomized treatment success: 18.25%; holdout: 19.56%. The served-versus-everyone headline is selection-biased.

These are simulator results, not evidence of production uplift. A second seed and unseen replay can change results.