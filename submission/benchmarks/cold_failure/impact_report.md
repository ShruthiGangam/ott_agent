# Impact report

Fixed 7-day outcomes, using every unique triggered user once in their assigned arm. No filtering by whether the agent served them.

| Metric | Agent | Holdout | Difference (pp) | Approx. 95% CI (pp) |
|---|---:|---:|---:|---:|
| play_started | 579/863 (67.09%) | 560/883 (63.42%) | 3.67 | -0.79 to 8.13 |
| episode_completed | 384/863 (44.50%) | 370/883 (41.90%) | 2.59 | -2.05 to 7.24 |
| purchase_completed | 24/863 (2.78%) | 31/883 (3.51%) | -0.73 | -2.37 to 0.91 |

Intervals are approximate and unadjusted for multiple metrics. Goal attainment is descriptive because goals differ across viewers. Observed success after a page is not individual causal attribution.

Pilot randomized treatment success: 18.25%; holdout: 19.56%. The served-versus-everyone headline is selection-biased.

These are simulator results, not evidence of production uplift. A second seed and unseen replay can change results.