"""
Outlook Routes — Written Forecast Narratives
GET /api/v1/cyclones/outlook/written
GET /api/v1/cyclones/outlook/summary
Always returns meaningful content even when 0 active cyclones.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Dict, Any

from services.redis_service import RedisService
from services.clickhouse_service import ClickHouseService
from services.written_outlook_service import generate_written_outlook

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response models ────────────────────────────────────────────────────────────

class BasinOutlookItem(BaseModel):
    basin: str
    status: str
    risk_level: str
    activity_pct: int
    active_storms: int
    narrative: str


class WrittenOutlookResponse(BaseModel):
    issued_at: str
    valid_through: str
    total_active_cyclones: int
    global_risk_level: str
    enso_phase: str
    global_summary: str
    seven_day_highlights: str
    basin_outlooks: List[BasinOutlookItem]
    safety_guidance: str


# ── Helper ─────────────────────────────────────────────────────────────────────

def _fetch_active_cyclones() -> List[Dict[str, Any]]:
    """Pull currently active cyclones from Redis (fast) or ClickHouse (fallback)."""
    cyclones = []

    # Try Redis first
    try:
        redis_service = RedisService()
        # FIX: was get_all_live_cyclones() — correct method is get_all_active_cyclones()
        live = redis_service.get_all_active_cyclones()
        if live:
            return live
    except Exception as e:
        logger.warning(f"Redis unavailable for outlook: {e}")

    # Fallback to ClickHouse
    try:
        ch_service = ClickHouseService()
        # FIX: was get_latest_positions(limit=50) — correct method is get_active_cyclones(limit=50)
        rows = ch_service.get_active_cyclones(limit=50)
        for row in rows:
            cyclones.append({
                "id": row.get("id", ""),
                "name": row.get("name", "UNNAMED"),
                "basin": row.get("basin", "Unknown"),
                "intensity": row.get("intensity", "Unknown"),
                "latitude": row.get("latitude", 0.0),
                "longitude": row.get("longitude", 0.0),
                "max_sustained_wind": row.get("max_sustained_wind", 0.0),
                "central_pressure": row.get("central_pressure", 1010.0),
                "movement_speed": row.get("movement_speed", 0.0),
                "movement_direction": row.get("movement_direction", 0.0),
            })
    except Exception as e:
        logger.warning(f"ClickHouse unavailable for outlook: {e}")

    return cyclones


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/outlook/written", response_model=WrittenOutlookResponse)
async def get_written_outlook(
    enso: Optional[str] = Query(
        "neutral",
        description="ENSO phase: 'el_nino', 'la_nina', or 'neutral'",
    )
):
    """
    Full written tropical weather outlook.

    Always returns a detailed narrative for all major basins regardless of
    whether active cyclones exist. Includes global summary, per-basin analysis,
    7-day highlights and safety guidance.
    """
    active_cyclones = _fetch_active_cyclones()

    # Normalise enso value
    enso_phase = enso if enso in ("el_nino", "la_nina") else "neutral"

    outlook = generate_written_outlook(
        active_cyclones=active_cyclones,
        enso_phase=enso_phase,
    )

    return WrittenOutlookResponse(**{
        **outlook,
        "basin_outlooks": [BasinOutlookItem(**b) for b in outlook["basin_outlooks"]],
    })


@router.get("/outlook/summary")
async def get_outlook_summary():
    """
    Lightweight one-paragraph global summary. Suitable for push notifications
    and home-screen snippets.
    """
    active_cyclones = _fetch_active_cyclones()
    outlook = generate_written_outlook(active_cyclones=active_cyclones)

    return {
        "issued_at": outlook["issued_at"],
        "total_active_cyclones": outlook["total_active_cyclones"],
        "global_risk_level": outlook["global_risk_level"],
        "summary_snippet": outlook["global_summary"].split("\n\n")[1]
        if "\n\n" in outlook["global_summary"]
        else outlook["global_summary"][:300],
        "safety_guidance": outlook["safety_guidance"],
    }