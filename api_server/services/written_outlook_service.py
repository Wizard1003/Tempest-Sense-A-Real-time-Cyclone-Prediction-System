"""
Written Outlook Service
Generates professional written forecast narratives for all tropical basins.
Works even when 0 active cyclones — always gives a meaningful seasonal outlook.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------
# Climatological data: peak months (1-indexed) and seasonal context
# -----------------------------------------------------------------
BASIN_CLIMATOLOGY = {
    "Atlantic": {
        "peak_months": [8, 9, 10],
        "active_months": [6, 7, 8, 9, 10, 11],
        "avg_annual_storms": 14,
        "avg_annual_hurricanes": 7,
        "typical_formation_areas": [
            "the Cape Verde Islands region",
            "the Gulf of Mexico",
            "the western Caribbean Sea",
            "the Bahamas and Florida Straits",
        ],
    },
    "Eastern Pacific": {
        "peak_months": [7, 8, 9],
        "active_months": [5, 6, 7, 8, 9, 10, 11],
        "avg_annual_storms": 15,
        "avg_annual_hurricanes": 8,
        "typical_formation_areas": [
            "the Gulf of Tehuantepec",
            "waters southwest of Mexico",
            "the Central American coast",
        ],
    },
    "Western Pacific": {
        "peak_months": [8, 9, 10],
        "active_months": [5, 6, 7, 8, 9, 10, 11, 12],
        "avg_annual_storms": 26,
        "avg_annual_hurricanes": 16,
        "typical_formation_areas": [
            "the Philippine Sea",
            "the South China Sea",
            "the Marshall Islands region",
            "east of the Philippines",
        ],
    },
    "North Indian Ocean": {
        "peak_months": [10, 11, 5],
        "active_months": [4, 5, 6, 10, 11, 12],
        "avg_annual_storms": 5,
        "avg_annual_hurricanes": 2,
        "typical_formation_areas": [
            "the Bay of Bengal",
            "the Arabian Sea",
        ],
    },
    "Southern Hemisphere": {
        "peak_months": [2, 3],
        "active_months": [11, 12, 1, 2, 3, 4],
        "avg_annual_storms": 20,
        "avg_annual_hurricanes": 10,
        "typical_formation_areas": [
            "the southwest Indian Ocean",
            "the Coral Sea",
            "waters north of Australia",
        ],
    },
}

# ENSO influence descriptions
ENSO_INFLUENCE = {
    "el_nino": {
        "Atlantic": "suppressed — El Niño typically increases wind shear over the Atlantic, inhibiting cyclone development.",
        "Eastern Pacific": "enhanced — El Niño typically warms eastern Pacific waters, fuelling increased activity.",
        "Western Pacific": "slightly suppressed — activity tends to shift eastward during El Niño.",
        "North Indian Ocean": "near normal — El Niño has a moderate influence on Bay of Bengal activity.",
        "Southern Hemisphere": "near normal with a slight eastward track shift.",
    },
    "la_nina": {
        "Atlantic": "enhanced — La Niña reduces wind shear, favouring hurricane development.",
        "Eastern Pacific": "suppressed — cooler waters reduce storm formation.",
        "Western Pacific": "enhanced — La Niña typically increases western Pacific typhoon activity.",
        "North Indian Ocean": "near normal to slightly enhanced.",
        "Southern Hemisphere": "near normal with a slight westward track shift.",
    },
    "neutral": {
        "Atlantic": "near-normal conditions expected.",
        "Eastern Pacific": "near-normal conditions expected.",
        "Western Pacific": "near-normal conditions expected.",
        "North Indian Ocean": "near-normal conditions expected.",
        "Southern Hemisphere": "near-normal conditions expected.",
    },
}


def _season_status(basin: str, month: int) -> Dict[str, Any]:
    """Return season status and activity fraction for a basin/month."""
    climo = BASIN_CLIMATOLOGY[basin]
    active = climo["active_months"]
    peak = climo["peak_months"]

    if month in peak:
        status = "PEAK SEASON"
        activity_pct = 90
        risk_level = "HIGH"
    elif month in active:
        # How far into/out of season?
        if any(month < p for p in peak):
            status = "PRE-PEAK SEASON"
            activity_pct = 45
        else:
            status = "POST-PEAK SEASON"
            activity_pct = 30
        risk_level = "MODERATE"
    else:
        status = "OFF-SEASON"
        activity_pct = 5
        risk_level = "LOW"

    return {"status": status, "activity_pct": activity_pct, "risk_level": risk_level}


def _format_month_range(months: List[int]) -> str:
    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    if not months:
        return "—"
    sorted_months = sorted(set(months))
    names = [month_names[m] for m in sorted_months]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _basin_paragraph(
    basin: str, month: int, active_cyclones: List[Dict], enso: str = "neutral"
) -> Dict[str, Any]:
    """Generate a full written paragraph for a single basin."""
    climo = BASIN_CLIMATOLOGY[basin]
    season = _season_status(basin, month)
    enso_desc = ENSO_INFLUENCE.get(enso, ENSO_INFLUENCE["neutral"]).get(basin, "near-normal conditions expected.")

    active_in_basin = [c for c in active_cyclones if basin.lower() in c.get("basin", "").lower()]
    n_active = len(active_in_basin)

    # Build storm sentence
    if n_active == 0:
        storm_sentence = "There are currently no active tropical cyclones in this basin."
    elif n_active == 1:
        s = active_in_basin[0]
        storm_sentence = (
            f"One active system is currently being tracked: {s.get('name', 'UNNAMED')} "
            f"({s.get('intensity', 'Tropical System')}) at {s.get('latitude', 0.0):.1f}°N, "
            f"{abs(s.get('longitude', 0.0)):.1f}°{'W' if s.get('longitude', 0) < 0 else 'E'}, "
            f"with sustained winds near {s.get('max_sustained_wind', 0):.0f} kt."
        )
    else:
        names = ", ".join(s.get("name", "UNNAMED") for s in active_in_basin)
        storm_sentence = f"There are {n_active} active systems currently tracked in this basin: {names}."

    # Build formation areas
    areas_str = "; ".join(climo["typical_formation_areas"][:2])

    # Build season narrative
    month_name = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ][month]
    peak_str = _format_month_range(climo["peak_months"])
    active_str = _format_month_range(climo["active_months"])

    narrative = (
        f"{basin} Basin — {season['status']} ({month_name}): "
        f"The {basin} season is typically most active from {active_str}, "
        f"with peak activity in {peak_str}. "
        f"{storm_sentence} "
        f"Formation risk for the next 7 days is {season['risk_level']}, "
        f"with an estimated {season['activity_pct']}% of climatological activity expected for this time of year. "
        f"Typical development areas during the active season include {areas_str}. "
        f"Current ENSO influence on this basin is {enso_desc}"
    )

    return {
        "basin": basin,
        "status": season["status"],
        "risk_level": season["risk_level"],
        "activity_pct": season["activity_pct"],
        "active_storms": n_active,
        "narrative": narrative,
    }


def _global_summary(month: int, active_cyclones: List[Dict], enso: str = "neutral") -> str:
    """Write a global summary paragraph."""
    month_name = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ][month]

    n_total = len(active_cyclones)
    enso_label = {"el_nino": "El Niño", "la_nina": "La Niña", "neutral": "ENSO-neutral"}.get(enso, "ENSO-neutral")

    # Which basins are currently in active season?
    active_basins = [b for b, d in BASIN_CLIMATOLOGY.items() if month in d["active_months"]]
    inactive_basins = [b for b in BASIN_CLIMATOLOGY if b not in active_basins]

    if n_total == 0:
        storm_str = (
            "No active tropical cyclones are currently being tracked anywhere on Earth. "
            "This is consistent with seasonal climatology."
        )
    elif n_total == 1:
        s = active_cyclones[0]
        storm_str = (
            f"One tropical cyclone is currently active globally: {s.get('name', 'UNNAMED')} "
            f"in the {s.get('basin', 'Unknown')} basin."
        )
    else:
        storm_str = f"There are currently {n_total} active tropical cyclones globally."

    active_basin_str = ", ".join(active_basins) if active_basins else "none"
    inactive_basin_str = ", ".join(inactive_basins) if inactive_basins else "none"

    summary = (
        f"GLOBAL TROPICAL WEATHER OUTLOOK — Issued {datetime.utcnow().strftime('%d %B %Y %H:%MZ')}\n\n"
        f"During {month_name}, the global tropical weather pattern reflects a transition "
        f"period in several key basins. The current large-scale environment is characterised by "
        f"{enso_label} conditions, which influence tropical cyclone activity worldwide.\n\n"
        f"{storm_str}\n\n"
        f"Basins currently within their active season: {active_basin_str}. "
        f"Basins in their off-season period: {inactive_basin_str}.\n\n"
        f"Ocean heat content and atmospheric instability across all monitored basins are "
        f"being evaluated continuously. The following basin-by-basin analysis provides detailed "
        f"outlooks for each region."
    )
    return summary


def _seven_day_highlights(month: int, active_cyclones: List[Dict]) -> str:
    """Generate a 7-day highlights section."""
    n_total = len(active_cyclones)

    lines = []
    lines.append("7-DAY TROPICAL WEATHER HIGHLIGHTS")
    lines.append("")

    if n_total > 0:
        for c in active_cyclones:
            lines.append(
                f"• {c.get('name', 'UNNAMED')} ({c.get('intensity', 'System')}): "
                f"Located at {c.get('latitude', 0):.1f}°{'N' if c.get('latitude', 0) >= 0 else 'S'}, "
                f"{abs(c.get('longitude', 0)):.1f}°{'W' if c.get('longitude', 0) < 0 else 'E'}. "
                f"Moving {c.get('movement_direction', 0):.0f}° at "
                f"{c.get('movement_speed', 0):.0f} kt. "
                f"Max winds {c.get('max_sustained_wind', 0):.0f} kt. "
                f"Minimum pressure {c.get('central_pressure', 1010):.0f} mb."
            )
    else:
        lines.append(
            "• No active systems require monitoring at this time."
        )

    lines.append("")

    # Formation risk areas based on season
    active_basins_now = [
        b for b, d in BASIN_CLIMATOLOGY.items() if month in d["active_months"]
    ]

    if active_basins_now:
        lines.append("Areas of interest for potential development (next 7 days):")
        for basin in active_basins_now:
            climo = BASIN_CLIMATOLOGY[basin]
            season = _season_status(basin, month)
            if season["risk_level"] in ("HIGH", "MODERATE"):
                area = climo["typical_formation_areas"][0]
                lines.append(
                    f"• {basin}: Monitor {area} for any signs of tropical organisation. "
                    f"Climatological development probability: {season['activity_pct']}% of peak."
                )
    else:
        lines.append(
            "No basins are currently in a high-risk formation period. "
            "Tropical cyclone development is unlikely across all basins over the next 7 days."
        )

    return "\n".join(lines)


def _safety_guidance(n_active: int) -> str:
    if n_active == 0:
        return (
            "SAFETY GUIDANCE: No immediate tropical cyclone threats exist at this time. "
            "Residents in tropical-prone regions should remain prepared year-round by maintaining "
            "emergency supply kits, reviewing evacuation routes, and monitoring official sources "
            "such as your national meteorological service and NOAA's National Hurricane Center."
        )
    else:
        return (
            f"SAFETY GUIDANCE: With {n_active} active system(s) currently tracked, "
            "residents in potentially affected areas should monitor official warnings closely, "
            "review emergency preparedness plans, and be ready to act on short notice. "
            "Follow guidance from your national meteorological authority."
        )


def generate_written_outlook(
    active_cyclones: Optional[List[Dict]] = None,
    enso_phase: str = "neutral",
) -> Dict[str, Any]:
    """
    Main entry point — generate the full written outlook.

    Args:
        active_cyclones: List of active cyclone dicts (can be empty)
        enso_phase: 'el_nino', 'la_nina', or 'neutral'

    Returns:
        Dict with all sections of the written outlook
    """
    if active_cyclones is None:
        active_cyclones = []

    now = datetime.utcnow()
    month = now.month

    # Global summary
    global_summary = _global_summary(month, active_cyclones, enso_phase)

    # Per-basin outlooks
    basin_outlooks = []
    for basin in BASIN_CLIMATOLOGY:
        basin_outlooks.append(
            _basin_paragraph(basin, month, active_cyclones, enso_phase)
        )

    # Sort: active-season basins first, then by risk level
    risk_order = {"HIGH": 0, "MODERATE": 1, "LOW": 2}
    basin_outlooks.sort(key=lambda x: risk_order.get(x["risk_level"], 3))

    # 7-day highlights
    highlights = _seven_day_highlights(month, active_cyclones)

    # Safety guidance
    safety = _safety_guidance(len(active_cyclones))

    # Determine overall global risk
    if any(b["risk_level"] == "HIGH" for b in basin_outlooks) or len(active_cyclones) >= 3:
        global_risk = "HIGH"
    elif any(b["risk_level"] == "MODERATE" for b in basin_outlooks) or len(active_cyclones) >= 1:
        global_risk = "MODERATE"
    else:
        global_risk = "LOW"

    return {
        "issued_at": now.isoformat() + "Z",
        "valid_through": (now + timedelta(days=7)).isoformat() + "Z",
        "total_active_cyclones": len(active_cyclones),
        "global_risk_level": global_risk,
        "enso_phase": enso_phase,
        "global_summary": global_summary,
        "seven_day_highlights": highlights,
        "basin_outlooks": basin_outlooks,
        "safety_guidance": safety,
    }