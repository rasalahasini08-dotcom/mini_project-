import pytest
from app.services.pricing_service import (
    calculate_surge_multiplier,
    compute_zone_pricing,
    get_all_zones_pricing_summary,
    get_system_wide_stats,
    PRICING_TIERS
)


class TestPricingCalculations:
    """Verify dynamic surge pricing formulas, thresholds, and boundary conditions."""

    def test_occupancy_boundary_zero_percent(self):
        tier = calculate_surge_multiplier(0.0)
        assert tier["tier"] == "Standard"
        assert tier["multiplier"] == 1.0

    def test_occupancy_boundary_forty_nine_percent(self):
        tier = calculate_surge_multiplier(49.9)
        assert tier["tier"] == "Standard"
        assert tier["multiplier"] == 1.0

    def test_occupancy_boundary_fifty_percent(self):
        tier = calculate_surge_multiplier(50.0)
        assert tier["tier"] == "Moderate"
        assert tier["multiplier"] == 1.3

    def test_occupancy_boundary_seventy_four_percent(self):
        tier = calculate_surge_multiplier(74.9)
        assert tier["tier"] == "Moderate"
        assert tier["multiplier"] == 1.3

    def test_occupancy_boundary_seventy_five_percent(self):
        tier = calculate_surge_multiplier(75.0)
        assert tier["tier"] == "High"
        assert tier["multiplier"] == 1.6

    def test_occupancy_boundary_eighty_nine_percent(self):
        tier = calculate_surge_multiplier(89.9)
        assert tier["tier"] == "High"
        assert tier["multiplier"] == 1.6

    def test_occupancy_boundary_ninety_percent(self):
        tier = calculate_surge_multiplier(90.0)
        assert tier["tier"] == "Peak Surge"
        assert tier["multiplier"] == 2.0

    def test_occupancy_boundary_hundred_percent(self):
        tier = calculate_surge_multiplier(100.0)
        assert tier["tier"] == "Peak Surge"
        assert tier["multiplier"] == 2.0

    def test_compute_zone_pricing_standard_tier(self):
        pricing = compute_zone_pricing(
            zone_id=1,
            zone_name="Test Zone",
            zone_code="ZONE-T",
            base_rate=50.0,
            occupied_slots=2,
            total_slots=10
        )
        assert pricing["occupancy_percentage"] == 20.0
        assert pricing["multiplier"] == 1.0
        assert pricing["effective_rate"] == 50.0
        assert pricing["demand_level"] == "Standard"

    def test_compute_zone_pricing_peak_surge(self):
        pricing = compute_zone_pricing(
            zone_id=1,
            zone_name="Test Zone",
            zone_code="ZONE-T",
            base_rate=60.0,
            occupied_slots=11,
            total_slots=12
        )
        assert pricing["occupancy_percentage"] >= 90.0
        assert pricing["multiplier"] == 2.0
        assert pricing["effective_rate"] == 120.0
        assert pricing["demand_level"] == "Peak Surge"

    def test_pricing_api_endpoint(self, client):
        res = client.get("/api/pricing")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "tiers" in data
        assert len(data["tiers"]) == 4
        assert "zones" in data
