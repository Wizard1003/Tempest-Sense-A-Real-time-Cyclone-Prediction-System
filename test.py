"""
Pytest Test Suite for MLCycloneForecast
Run: pytest test_ml_cyclone_forecast.py -v
Place this file in the same folder as ml_cyclone_forecast.py
"""

import sys
import importlib
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

# ── Locate ml_cyclone_forecast.py next to this test file ─────────────────────
_HERE = Path(__file__).parent
_MODULE_PATH = _HERE / "ml_cyclone_forecast.py"

if not _MODULE_PATH.exists():
    pytest.exit(
        f"\n\nCannot find ml_cyclone_forecast.py in:\n  {_HERE}\n"
        "Place this test file in the same directory as the source file.\n",
        returncode=1,
    )

# Load the module once for the whole session
_spec   = importlib.util.spec_from_file_location("ml_cyclone_forecast", _MODULE_PATH)
_ml_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("ml_cyclone_forecast", _ml_mod)
_spec.loader.exec_module(_ml_mod)
MLCycloneForecast = _ml_mod.MLCycloneForecast


# ── Shared helpers ────────────────────────────────────────────────────────────

def make_track(n: int = 10, base_lat: float = 15.0, base_lon: float = 85.0) -> list:
    """Return a synthetic cyclone track with n 6-hourly points."""
    base_time = datetime(2024, 10, 1, 0, 0, 0)
    return [
        {
            "id":                 "CYCLONE_TEST_01",
            "name":               "TEST",
            "timestamp":          (base_time + timedelta(hours=i * 6)).isoformat(),
            "latitude":           round(base_lat + i * 0.3, 4),
            "longitude":          round(base_lon - i * 0.5, 4),
            "max_sustained_wind": round(50 + i * 3, 1),
            "central_pressure":   round(1000 - i * 2, 1),
        }
        for i in range(n)
    ]


@pytest.fixture(scope="module")
def fc():
    return MLCycloneForecast()


@pytest.fixture(scope="module")
def track10():
    return make_track(10)


# ══════════════════════════════════════════════════════════════════════════════
#  1. predict_formation  (pure Python – no Prophet / sklearn needed)
# ══════════════════════════════════════════════════════════════════════════════

class TestPredictFormation:

    def test_outside_zone_low_probability(self, fc):
        """Far outside all formation zones → probability ≤ 0.10."""
        res = fc.predict_formation(latitude=60.0, longitude=0.0)
        assert res["probability"] <= 0.10, f"Got {res['probability']}"
        assert res["risk_level"] == "low"
        assert res["confidence"] == "low"

    def test_indian_ocean_peak_season(self, fc):
        """Indian Ocean in October (peak) → elevated probability + favorable season."""
        with patch.object(_ml_mod, "datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 10, 15)
            res = fc.predict_formation(latitude=12.0, longitude=70.0)
        assert res["probability"] > 0.30, f"Got {res['probability']}"
        assert res["location"]["zone"] == "Indian Ocean"
        assert res["factors"]["current_season"] == "favorable"

    def test_required_keys_present(self, fc):
        """Response must contain all documented keys."""
        res = fc.predict_formation(12.0, 70.0)
        required = {
            "probability", "risk_level", "location",
            "estimated_time_hours", "confidence", "factors",
        }
        missing = required - set(res.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_probability_in_unit_interval(self, fc):
        """Probability is always in [0.0, 1.0] for various coordinates."""
        for lat, lon in [(12.0, 70.0), (60.0, 0.0), (15.0, -60.0), (10.0, 150.0)]:
            res = fc.predict_formation(lat, lon)
            assert 0.0 <= res["probability"] <= 1.0, \
                f"Probability {res['probability']} out of range for ({lat}, {lon})"

    def test_probability_capped_at_095(self, fc):
        """Probability must never exceed 0.95."""
        with patch.object(_ml_mod, "datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 9, 15)   # peak Atlantic
            res = fc.predict_formation(latitude=15.0, longitude=-60.0)
        assert res["probability"] <= 0.95, f"Cap exceeded: {res['probability']}"

    def test_off_season_lower_than_peak(self, fc):
        """Off-season probability should be lower than peak-season probability."""
        with patch.object(_ml_mod, "datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 10, 15)
            peak = fc.predict_formation(12.0, 70.0)

        with patch.object(_ml_mod, "datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 2, 15)   # off-season
            off = fc.predict_formation(12.0, 70.0)

        assert peak["probability"] > off["probability"], \
            "Peak season should yield higher probability than off-season"


# ══════════════════════════════════════════════════════════════════════════════
#  2. hybrid_forecast – validation
# ══════════════════════════════════════════════════════════════════════════════

class TestHybridForecastValidation:

    def test_raises_on_too_few_points(self, fc):
        """hybrid_forecast must raise ValueError when track has < 5 points."""
        with pytest.raises(ValueError, match="5"):
            fc.hybrid_forecast(make_track(3), hours_ahead=24)

    def test_exactly_min_points_succeeds(self, fc):
        """Exactly 5 points (boundary value) must not raise."""
        out = fc.hybrid_forecast(make_track(5), hours_ahead=12, interval_hours=6)
        assert len(out) == 2


# ══════════════════════════════════════════════════════════════════════════════
#  3. hybrid_forecast – integration (Prophet + sklearn)
# ══════════════════════════════════════════════════════════════════════════════

class TestHybridForecast:

    def test_point_count_24h(self, fc, track10):
        """24 h / 6 h interval → 4 forecast points."""
        assert len(fc.hybrid_forecast(track10, hours_ahead=24, interval_hours=6)) == 4

    def test_point_count_48h(self, fc, track10):
        """48 h / 6 h interval → 8 forecast points."""
        assert len(fc.hybrid_forecast(track10, hours_ahead=48, interval_hours=6)) == 8

    def test_required_keys_in_each_point(self, fc, track10):
        """Every forecast point must contain all required top-level keys."""
        required = {
            "id", "name", "forecast_hour", "forecast_timestamp",
            "latitude", "longitude", "max_wind", "min_pressure",
            "forecast_type", "confidence", "uncertainty_bounds",
        }
        for i, pt in enumerate(fc.hybrid_forecast(track10, hours_ahead=24, interval_hours=6)):
            assert not (required - set(pt.keys())), \
                f"Point {i} missing: {required - set(pt.keys())}"

    def test_uncertainty_bounds_sub_keys(self, fc, track10):
        """uncertainty_bounds must contain all five expected sub-keys."""
        ub_keys = {"lat_lower", "lat_upper", "lon_lower", "lon_upper", "radius_km"}
        for i, pt in enumerate(fc.hybrid_forecast(track10, hours_ahead=24, interval_hours=6)):
            assert not (ub_keys - set(pt["uncertainty_bounds"].keys())), \
                f"Point {i} uncertainty_bounds missing: {ub_keys - set(pt['uncertainty_bounds'].keys())}"

    def test_forecast_type_is_hybrid(self, fc, track10):
        out = fc.hybrid_forecast(track10, hours_ahead=24, interval_hours=6)
        for pt in out:
            assert pt["forecast_type"] == "prophet_statistical_hybrid"

    def test_forecast_hour_progression(self, fc, track10):
        """forecast_hour increments by interval_hours each step."""
        out   = fc.hybrid_forecast(track10, hours_ahead=48, interval_hours=6)
        hours = [pt["forecast_hour"] for pt in out]
        assert hours == list(range(6, 54, 6)), f"Got: {hours}"

    def test_wind_within_bounds(self, fc, track10):
        """max_wind must stay in [25, 200] kt."""
        for pt in fc.hybrid_forecast(track10, hours_ahead=48, interval_hours=6):
            assert 25 <= pt["max_wind"] <= 200, f"Wind {pt['max_wind']} out of bounds"

    def test_pressure_within_bounds(self, fc, track10):
        """min_pressure must stay in [900, 1013] mb."""
        for pt in fc.hybrid_forecast(track10, hours_ahead=48, interval_hours=6):
            assert 900 <= pt["min_pressure"] <= 1013, \
                f"Pressure {pt['min_pressure']} out of bounds"

    def test_storm_id_and_name_preserved(self, fc, track10):
        for pt in fc.hybrid_forecast(track10, hours_ahead=24, interval_hours=6):
            assert pt["id"]   == "CYCLONE_TEST_01"
            assert pt["name"] == "TEST"


# ══════════════════════════════════════════════════════════════════════════════
#  4. lstm_intensity_forecast – integration
# ══════════════════════════════════════════════════════════════════════════════

class TestIntensityForecast:

    def test_correct_point_count(self, fc, track10):
        assert len(fc.lstm_intensity_forecast(track10, hours_ahead=24, interval_hours=6)) == 4

    def test_forecast_type_and_confidence(self, fc, track10):
        for pt in fc.lstm_intensity_forecast(track10, hours_ahead=24, interval_hours=6):
            assert pt["forecast_type"] == "statistical_intensity"
            assert pt["confidence"]    == "high"

    def test_position_pinned_to_last_point(self, fc, track10):
        """Intensity-only forecast should not move lat/lon from last known position."""
        last = track10[-1]
        for pt in fc.lstm_intensity_forecast(track10, hours_ahead=24, interval_hours=6):
            assert pt["latitude"]  == last["latitude"]
            assert pt["longitude"] == last["longitude"]

    def test_wind_and_pressure_within_bounds(self, fc, track10):
        for pt in fc.lstm_intensity_forecast(track10, hours_ahead=48, interval_hours=6):
            assert 25  <= pt["max_wind"]     <= 200
            assert 900 <= pt["min_pressure"] <= 1013


# ══════════════════════════════════════════════════════════════════════════════
#  5. Edge Cases
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_large_track_50_points(self, fc):
        """50-point track must complete and return 8 points for 48 h."""
        out = fc.hybrid_forecast(make_track(50), hours_ahead=48, interval_hours=6)
        assert len(out) == 8

    def test_all_zero_wind_fallback(self, fc):
        """All-zero wind data must not crash; fallback wind must be positive."""
        track = make_track(10)
        for p in track:
            p["max_sustained_wind"] = 0
        out = fc.lstm_intensity_forecast(track, hours_ahead=12, interval_hours=6)
        assert len(out) > 0
        for pt in out:
            assert pt["max_wind"] > 0, "Fallback wind should be positive"

    def test_nan_pressure_fallback(self, fc):
        """NaN pressure values must be handled without crashing."""
        track = make_track(10)
        for p in track:
            p["central_pressure"] = float("nan")
        out = fc.lstm_intensity_forecast(track, hours_ahead=12, interval_hours=6)
        assert len(out) > 0

    def test_12h_interval(self, fc):
        """12-hour intervals over 48 h should yield 4 points."""
        out = fc.hybrid_forecast(make_track(10), hours_ahead=48, interval_hours=12)
        assert len(out) == 4