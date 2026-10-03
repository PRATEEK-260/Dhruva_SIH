# Risk thresholds

> **Partly cited (2026-10-03).** Wind limits and the 4.0 m sea limit are IMD's own
> criteria for warning fishermen, quoted below. The stricter wave limits for small
> boats have no published source in hand and are **provisional**: the evidence
> card says so beside every verdict they decide, and `PROVISIONAL = True` stays in
> `backend/dhruva/risk/thresholds.py` until every row is cited. Never present a
> provisional row as official.

Every advisory built on this table carries: *advisory only, follow official
INCOIS and IMD warnings.*

## Source

IMD, *Marine Weather Services: Standard Operation Procedure*, section 7.1
"Criteria for fishermen warnings",
<https://rsmcnewdelhi.imd.gov.in/uploads/report/71/71_7d2c29_MARINE%20SOP.pdf>,
read 2026-10-03; copy at `data/imd/imd_marine_weather_services_sop.pdf`
(SHA-256 `33183088…6fbf21`). Quoted exactly:

> (i) Squally weather (maximum sustained wind speed (MSW) ≥ 20 knots alongwith
> fairly widespread (51-75% area receiving rainfall) to widespread (76-100% area
> receiving rainfall) rainfall over a region
>
> (ii) Strong of-shore and on-shore (or with appropriate direction) winds, speed
> exceeding 45 kmph.
>
> (iii) Significant wave height ≥ 4.0 m i.e. state of sea is very rough and above
>
> (iv) There is a depression or above intensity cyclonic disturbance over an area

These are national values. IMD gives one set for every fisherman, so DHRUVA uses
them for every boat class and says so. Criterion (iv) is the cyclone override
below. Criterion (i)'s rainfall condition is not checked: 20 kt is used as the
caution limit on wind alone, which can only warn more, not less.

## Per boat class

| Boat class | Caution H_s | No-go H_s | Caution wind | No-go wind |
|---|---|---|---|---|
| FRP / country craft < 12 m | 2.0 m *provisional* | 3.0 m *provisional* | 20 kt — SOP 7.1(i) | 24.3 kt (45 kmph) — SOP 7.1(ii) |
| Mechanised 12–20 m | 2.5 m *provisional* | 3.5 m *provisional* | 20 kt — SOP 7.1(i) | 24.3 kt (45 kmph) — SOP 7.1(ii) |
| Deep-sea > 20 m | 3.5 m *provisional* | 4.0 m — SOP 7.1(iii) | 20 kt — SOP 7.1(i) | 24.3 kt (45 kmph) — SOP 7.1(ii) |

No class may go past IMD's 4.0 m: the smaller boats' provisional limits sit below
it, never above. Until 2026-10-03 the wind limits were placeholders (no-go 28, 33
and 40 kt); moving to IMD's 45 kmph makes every class stricter on wind.

## Absolute overrides

These ignore boat class and ignore every favourable signal. They are evaluated
**before** the per-class table, and any one of them forces NO-GO.

| Rule | Condition | Verdict |
|---|---|---|
| `CYCLONE-A1` | Active cyclone warning within 300 km | NO-GO |
| `LIGHTNING-A2` | Lightning within 50 km | NO-GO |
| `TSUNAMI-A3` | Any tsunami alert in force | NO-GO |

## Rule IDs

Each rule that fires is recorded by ID on the evidence bundle, so a verdict can
be traced to the line that produced it rather than to "the model decided".

| ID | Meaning |
|---|---|
| `WAVE-S1` / `WIND-S1` | Below the class's caution limit: safe on this variable. The evidence row shows the caution limit it was compared with |
| `WAVE-C2` / `WAVE-N3` | Wave height reached caution / no-go for the boat class |
| `WIND-C2` / `WIND-N3` | Wind reached caution / no-go for the boat class |

A Safe row quotes the caution limit and a No-go row quotes the no-go limit, so two rows
for the same boat class can show different limits. Both come from the one table above.
| `CYCLONE-A1`, `LIGHTNING-A2`, `TSUNAMI-A3` | Absolute overrides above |
| `DATA-U0` | A threshold variable was unavailable, so no verdict is possible |

## Missing data is not safety

`DATA-U0` exists because the dangerous failure here is silent. If wave height
could not be fetched, the answer is **UNKNOWN**, never SAFE. A system that
returns "safe" when it simply does not know is worse than one that returns
nothing, because a crew acts on it.
