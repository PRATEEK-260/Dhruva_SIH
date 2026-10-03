"""The threshold table, as data, with the source of each limit.

Values mirror docs/THRESHOLDS.md. Since 2026-10-03 the wind limits and the
4.0 m sea limit are cited to IMD's own criteria for warning fishermen (Marine
Weather Services SOP, section 7.1), national values used for every boat class.
The stricter wave limits for small boats have no published source in hand and
stay PROVISIONAL: each limit says which it is (source_for), the evidence card
shows it, and PROVISIONAL stays True while any row is uncited.
"""

from __future__ import annotations

from dataclasses import dataclass

from dhruva.graph.state import BoatClass

PROVISIONAL = True
PROVISIONAL_NOTE = (
    "Thresholds are engineering placeholders, not INCOIS Ocean State Forecast "
    "criteria. See docs/THRESHOLDS.md."
)

ADVISORY_NOTICE = "Advisory only. Follow official INCOIS and IMD warnings."

# Absolute overrides, evaluated before the per-class table.
CYCLONE_RADIUS_KM = 300.0
LIGHTNING_RADIUS_KM = 50.0


@dataclass(frozen=True, slots=True)
class Citation:
    title: str
    section: str
    quote: str
    url: str
    local_copy: str
    sha256: str
    read_on: str

    @property
    def short(self) -> str:
        return f"IMD Marine Weather Services SOP, {self.section}"


_SOP = dict(
    title="IMD, Marine Weather Services: Standard Operation Procedure",
    url="https://rsmcnewdelhi.imd.gov.in/uploads/report/71/71_7d2c29_MARINE%20SOP.pdf",
    local_copy="data/imd/imd_marine_weather_services_sop.pdf",
    sha256="33183088890585d19116a010828c26947a1222c8e7ab9a9f344cfe5b946fbf21",
    read_on="2026-10-03",
)
# Section 7.1, "Criteria for fishermen warnings", quoted exactly.
SOP_SQUALL = Citation(
    section="7.1(i)",
    quote=(
        "Squally weather (maximum sustained wind speed (MSW) >= 20 knots alongwith fairly "
        "widespread (51-75% area receiving rainfall) to widespread (76-100% area receiving "
        "rainfall) rainfall over a region"
    ),
    **_SOP,
)
SOP_WIND = Citation(
    section="7.1(ii)",
    quote=(
        "Strong of-shore and on-shore (or with appropriate direction) winds, speed exceeding "
        "45 kmph."
    ),
    **_SOP,
)
SOP_SEA = Citation(
    section="7.1(iii)",
    quote="Significant wave height >= 4.0 m i.e. state of sea is very rough and above",
    **_SOP,
)
KMPH_PER_KT = 1.852
# 45 kmph is 24.298 kt; 24.3 kt is the first tenth above it ("exceeding 45 kmph").
IMD_WIND_NO_GO_KT = 24.3
IMD_WIND_CAUTION_KT = 20.0  # 7.1(i); its rainfall condition is not checked
IMD_SEA_NO_GO_M = 4.0


@dataclass(frozen=True, slots=True)
class ClassThresholds:
    caution_wave_m: float
    no_go_wave_m: float
    caution_wind_kt: float
    no_go_wind_kt: float


# Wind: IMD's national fishermen-warning criteria for every class. Waves: IMD's
# 4.0 m for the largest boats; smaller boats keep stricter provisional limits,
# always below IMD's 4.0 m, never above it.
THRESHOLDS: dict[BoatClass, ClassThresholds] = {
    BoatClass.FRP_UNDER_12M: ClassThresholds(2.0, 3.0, IMD_WIND_CAUTION_KT, IMD_WIND_NO_GO_KT),
    BoatClass.MECHANISED_12_20M: ClassThresholds(2.5, 3.5, IMD_WIND_CAUTION_KT, IMD_WIND_NO_GO_KT),
    BoatClass.DEEP_SEA_OVER_20M: ClassThresholds(
        3.5, IMD_SEA_NO_GO_M, IMD_WIND_CAUTION_KT, IMD_WIND_NO_GO_KT
    ),
}


def thresholds_for(boat_class: BoatClass) -> ClassThresholds:
    return THRESHOLDS[boat_class]


def source_for(field: str, value: float) -> Citation | None:
    """The citation behind a limit, or None for a provisional one. Matched on
    the value, so a class that keeps a stricter provisional limit is never
    credited with IMD's."""
    if field.endswith("_wind_kt"):
        if value == IMD_WIND_NO_GO_KT:
            return SOP_WIND
        if value == IMD_WIND_CAUTION_KT:
            return SOP_SQUALL
    if field == "no_go_wave_m" and value == IMD_SEA_NO_GO_M:
        return SOP_SEA
    return None
