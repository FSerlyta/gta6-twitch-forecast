# GTA VI Twitch CCU Forecaster — make.fun `gta6-twitch-ccu-forecast-01`

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/FSerlyta/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/FSerlyta/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each
hour (2–24) of its release day, 2026-11-19 UTC, after seeing only hour 1.

Entry: `main.py` (Python 3.13, standard library only, no network, no model
calls, deterministic). It reads every `*.in` in `$MAKEFUN_INPUT_DIR`
(or `/input`) and writes one `<id>.out` per case to `$MAKEFUN_OUTPUT_DIR`
(or `/output`).

## How it works

A shape forecaster calibrated at run time from the case's own comparables
(past big launches' hourly Twitch counts, supplied inside each case file):

1. Each comparable's release-day curve (UTC hours 1–24 of its release day)
   is expressed as log-ratios to its own hour 1.
2. Two pools are built: a **console pool** (rolling-midnight console launches
   only — tier "comparable", no PC in `platforms`, hour 1 at least 5% of the
   day peak) and an **all pool** (every tier-"comparable" launch with the same
   5% rule). A PC simultaneous unlock front-loads viewership into hour 1 and
   flattens the curve, so it is the wrong mechanism for a console-only
   rolling launch like GTA VI — but it hedges the case where hour 1 turns out
   to be near the peak.
3. For each forecast hour, the median log-ratio of each pool is taken,
   weighted by how close the curve's hour-1 size is to this case's hour-1
   print (Gaussian kernel, bandwidth 0.6 in log10 viewers). The forecast
   median is the mean of the two pools' medians in log space; the spread is
   the wider of the two pools' weighted inter-quartile ranges (floored 0.15,
   capped 0.85 in log units). Quantiles: `q_tau = p1 * exp(median + z_tau *
   sigma)`.
4. Fallbacks: console pool too small → all pool alone; all pool too small →
   drop the 5% rule; no curves at all → the house baseline formula (flat
   median, 0.15·√(h−1) spread).

The release day of a rolling-midnight console launch has a fixed shape: a dip
in hours 2–4 (deep night in Europe, US not yet unlocked), a step at hours
5–6 (US East unlock at 05:00Z), a midday sag, then a steady rise to a peak in
hours 18–22 (US afternoon/evening). The house baseline (flat at hour 1)
misses all of that.

## Local evaluation (practice answers from SullyGnome)

Practice answers (hours 2–24 of the four launch days) were fetched from
SullyGnome's public chart API and verified: each extracted hour-1 value
matches the case file's `known` print exactly. Mean pinball loss on the log
scale (lower is better):

| case | model | house baseline |
| ---- | ----- | -------------- |
| p00 Marvel's Wolverine | 0.3437 | 0.7437 |
| p01 Red Dead Redemption 2 | 0.1292 | 0.2868 |
| p02 God of War Ragnarök | 0.1555 | 0.2146 |
| p03 Marvel's Spider-Man 2 | 0.1777 | 0.3033 |
| **mean** | **0.2015** | **0.3871** |

90% coverage on practice: 0.87 / 1.00 / 1.00 / 0.78 (honest target ≈ 0.9).
Typical miss: 84% / 25% / 23% / 28% (baseline: 83% overall).

Simulated final case (42 comparables, incl. the four practice launches):
median peak ratio 1.93× at p1 = 300k, 1.51× at 500k, 1.33× at 800k —
the forecast adapts to how big hour 1 turns out to be.

## Run it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Checks: output valid on all four practice cases (23 rows, hours 2–24,
non-decreasing quantiles, ≤ 64 KB), byte-identical across two runs,
~0.07 s per case (limit 8 s). Robustness tested: tiny/huge/zero hour-1
prints, no comparables, and sparse comparables all produce valid output
(falling back to the baseline formula where the data is absent).

## Research notes (sources)

- GTA VI Trailer 1: 90.4M YouTube views in 24 h (Guinness record);
  Trailer 2: 475M views across platforms in 24 h (biggest video launch
  ever, Rockstar via The Hollywood Reporter).
- Launch-day Twitch peaks (SullyGnome / press): Elden Ring 875k,
  Cyberpunk 2077 ~1.07M, The Last of Us Part II 508k, God of War
  Ragnarök 478–481k, God of War (2018) 292k, Marvel's Spider-Man 234k.
- GTA VI category itself peaked at 1,418,094 viewers during the 27 Aug
  2026 extended-look premiere (SullyGnome hourly data in the case file).

## License

MIT — see `LICENSE`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=t64s0rz7&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
