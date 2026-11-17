"""gta6-twitch-ccu-forecast-01 entry: a shape forecaster for launch-day Twitch viewers.

Model (calibrated at run time from the case's own comparables, no network, no model):

  For each comparable launch we take its release-day hourly curve (UTC hours 1..24
  of its day_start) and express every hour as a log-ratio to that launch's hour 1.
  Two pools are built from the case's comparables: the console pool (rolling-
  midnight console launches: tier "comparable", no PC in `platforms` -- a PC
  simultaneous unlock front-loads viewership into hour 1 and flattens the curve)
  and the all pool (every tier-"comparable" launch).  Both pools require hour 1
  to be at least 5% of the launch's day peak (hour 1 was already a launch hour,
  not hours before the unlock).  For each forecast hour we take the median
  log-ratio across each pool, weighted by how close the curve's hour-1 size is
  to this case's hour-1 print (Gaussian kernel, bandwidth 0.6 in log10 viewers):
  big launches whose first hour was already huge rise little through the day,
  small first hours rise a lot.  The forecast median is the mean of the two
  pools' medians in log space -- the console pool is the right mechanism for a
  console-only rolling launch like GTA VI, the all pool hedges it with the
  biggest launches ever (Elden Ring, Cyberpunk) in case the first hour turns
  out to be near the peak.  The spread is the larger of the two pools' weighted
  inter-quartile ranges (an honest, data-driven spread, floored at 0.15 and
  capped at 0.85 in log units).  Quantiles: q_tau = p1 * exp(median + z_tau *
  sigma).

  The release day of a rolling-midnight console launch has a fixed shape: a dip
  in hours 2-4 (deep night in Europe, US not yet unlocked), a step at hours 5-6
  (US East unlock), a steady rise as the US wakes, and a peak in hours 18-22
  (US afternoon/evening).  The house baseline (flat at hour 1) misses all of
  that; this model follows it.

  Fallbacks, in order: if fewer than 3 curves pass the console filter, the
  forecast uses the all pool alone; if the all pool is also too small, its 5%
  rule is dropped; if no curve survives at all, fall back to the baseline
  formula (flat median, 0.15 * sqrt(h-1) spread).

  Deterministic: sorted file order, no randomness, no time or environment
  dependence.  Standard library only.  Reads $MAKEFUN_INPUT_DIR (else /input),
  writes $MAKEFUN_OUTPUT_DIR (else /output).
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a sibling
# module would import; this entry is one file, but the line is harmless.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Gaussian kernel bandwidth (log10 viewers) for weighting comparables by
# how close their hour-1 size is to this case's hour-1 print.
BANDWIDTH = 0.6
# A comparable only counts if its hour 1 is at least this fraction of its
# release-day peak (hour 1 was a launch hour, not hours before the unlock).
MIN_FRACTION = 0.05
# At least this many curves must survive a filter level before we use it.
MIN_CURVES = 3
# Spread of the log-ratios, in log units: floor and cap.
SIGMA_MIN = 0.15
SIGMA_MAX = 0.85
# Baseline fallback spread, per square-root hour.
BASE_SIGMA = 0.15


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def tier_of(comp):
    """The research tier recorded in the comparable's unlock note."""
    u = comp.get("unlock") or ""
    if "Tier: early-access" in u:
        return "early-access"
    if "Tier: weak" in u:
        return "weak"
    if "Tier: target-history" in u:
        return "target-history"
    return "comparable"


def day_curve(comp):
    """Release-day hourly viewers, hours 1..24 of the comparable's UTC day."""
    ds = parse_ts(comp["day_start"])
    vals = [None] * 24
    for row in comp.get("hourly") or []:
        try:
            t = parse_ts(row["from"])
        except (KeyError, TypeError, ValueError):
            continue
        d = (t - ds).total_seconds() / 3600.0
        if 0 <= d < 24 and int(d) == d:
            v = row.get("viewers")
            if isinstance(v, (int, float)) and v > 0:
                vals[int(d)] = float(v)
    return vals


def usable_curve(comp, console_only, min_fraction):
    """A comparable's release-day curve, or None if it fails the filter."""
    if tier_of(comp) != "comparable":
        return None
    if console_only and "PC" in (comp.get("platforms") or ""):
        return None
    vals = day_curve(comp)
    if vals[0] is None or vals[0] <= 0:
        return None
    present = [v for v in vals if v is not None]
    if len(present) < 18:
        return None
    if vals[0] / max(present) < min_fraction:
        return None
    return vals


def weighted_median(pairs):
    """Median of (value, weight) pairs, deterministic on ties."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if acc >= total / 2.0:
            return value
    return pairs[-1][0]


def weighted_quantile(pairs, q):
    """q-quantile of (value, weight) pairs, deterministic on ties."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if acc >= q * total:
            return value
    return pairs[-1][0]


def pool_shape(curves, log_p1, hours):
    """Per forecast hour (median log-ratio, sigma) for one pool of curves."""
    weights = []
    for vals in curves:
        d = (math.log10(vals[0]) - log_p1) / BANDWIDTH
        weights.append(math.exp(-d * d))
    shape = {}
    for h in hours:
        idx = h - 1
        pairs = []
        for vals, w in zip(curves, weights):
            v = vals[idx]
            if v is not None:
                pairs.append((math.log(v / vals[0]), w))
        if not pairs:
            shape[h] = None
            continue
        med = weighted_median(pairs)
        iqr = weighted_quantile(pairs, 0.75) - weighted_quantile(pairs, 0.25)
        sigma = min(SIGMA_MAX, max(SIGMA_MIN, iqr / 1.349))
        shape[h] = (med, sigma)
    return shape


def collect_curves(case, console_only, min_fraction):
    """All comparable curves passing one filter level, or [] if too few."""
    found = []
    for comp in case.get("comparables") or []:
        vals = usable_curve(comp, console_only, min_fraction)
        if vals is not None:
            found.append(vals)
    return found if len(found) >= MIN_CURVES else []


def shape_for_case(case, p1):
    """Per forecast hour: (median log-ratio to hour 1, log spread).

    Returns a dict hour -> (median, sigma), for every hour in case["forecast"].
    """
    log_p1 = math.log10(max(p1, 1.0))
    hours = [row["hour"] for row in case["forecast"]]
    # The all pool: tier-comparable launches, hour 1 >= 5% of day peak.
    all_curves = collect_curves(case, False, MIN_FRACTION)
    if not all_curves:
        all_curves = collect_curves(case, False, 0.0)
    if not all_curves:
        return None
    all_shape = pool_shape(all_curves, log_p1, hours)
    # The console pool: the same, but console-only (no PC).
    console_curves = collect_curves(case, True, MIN_FRACTION)
    if console_curves:
        console_shape = pool_shape(console_curves, log_p1, hours)
    else:
        console_shape = None
    shape = {}
    prev = (0.0, SIGMA_MIN)
    for h in hours:
        a = all_shape.get(h)
        c = console_shape.get(h) if console_shape else None
        if a is None and c is None:
            # No comparable has this hour: carry the previous hour's shape.
            shape[h] = prev
            continue
        if c is None:
            med, sigma = a
        elif a is None:
            med, sigma = c
        else:
            # Blend the two pools in log space; take the wider spread.
            med = 0.5 * (a[0] + c[0])
            sigma = max(a[1], c[1])
        shape[h] = (med, sigma)
        prev = shape[h]
    return shape


def round2(x):
    """x rounded to 2 decimals, half up (like the starter)."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100.0
    return int(value) if float(value).is_integer() else value


def clamp_quantiles(qs):
    """Keep quantiles finite, > 0, <= 1e9 and non-decreasing."""
    out = []
    prev = 0.0
    for q in qs:
        if not math.isfinite(q):
            q = prev if prev > 0 else 1.0
        q = min(max(q, 0.01), 1e9)
        if q < prev:
            q = prev
        out.append(round2(q))
        prev = out[-1]
    return out


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    shape = shape_for_case(case, p1)
    hours = []
    for row in case["forecast"]:
        h = row["hour"]
        if shape is not None and h in shape:
            med, sigma = shape[h]
            qs = [p1 * math.exp(med + z * sigma) for z in Z]
        else:
            # Baseline fallback: flat median, widening spread.
            qs = [p1 * math.exp(z * BASE_SIGMA * math.sqrt(h - 1)) for z in Z]
        hours.append({"hour": h, "q": clamp_quantiles(qs)})
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
