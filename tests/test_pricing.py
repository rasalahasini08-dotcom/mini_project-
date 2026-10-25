"""
test_pricing.py - Comprehensive Unit Tests for Dynamic Surge Pricing Logic.

Tests all occupancy thresholds and boundaries:
- 0%, 49%, 50%, 79%, 80%, and 100%
- Pricing tiers (Standard ₹50, Moderate ₹75, Peak ₹100)
- Edge cases (0 total capacity, negative numbers, overflow)
"""

import pytest
from pricing import (
    calculate_occupancy_percentage,
    get_surge_pricing,
    PRICE_TIER_STANDARD,
    PRICE_TIER_MODERATE,
    PRICE_TIER_PEAK
)


class TestPricingCalculations:
    """Test occupancy formula and surge tier assignments."""

    def test_occupancy_boundary_zero_percent(self):
        """0% occupancy (0/12 occupied) -> Standard rate ₹50."""
        res = get_surge_pricing(occupied_slots=0, total_slots=12)
        assert res["occupancy_percentage"] == 0.0
        assert res["hourly_rate"] == PRICE_TIER_STANDARD
        assert res["tier_key"] == "STANDARD"
        assert res["badge_variant"] == "success"

    def test_occupancy_boundary_forty_nine_percent(self):
        """49% occupancy (49/100 occupied) -> Standard rate ₹50."""
        res = get_surge_pricing(occupied_slots=49, total_slots=100)
        assert res["occupancy_percentage"] == 49.0
        assert res["hourly_rate"] == PRICE_TIER_STANDARD
        assert res["tier_key"] == "STANDARD"

    def test_occupancy_boundary_fifty_percent(self):
        """50% occupancy (6/12 occupied) -> Moderate surge ₹75."""
        res = get_surge_pricing(occupied_slots=6, total_slots=12)
        assert res["occupancy_percentage"] == 50.0
        assert res["hourly_rate"] == PRICE_TIER_MODERATE
        assert res["tier_key"] == "MODERATE"
        assert res["badge_variant"] == "warning"

    def test_occupancy_boundary_seventy_nine_percent(self):
        """79% occupancy (79/100 occupied) -> Moderate surge ₹75."""
        res = get_surge_pricing(occupied_slots=79, total_slots=100)
        assert res["occupancy_percentage"] == 79.0
        assert res["hourly_rate"] == PRICE_TIER_MODERATE
        assert res["tier_key"] == "MODERATE"

    def test_occupancy_boundary_eighty_percent(self):
        """80% occupancy (80/100 occupied) -> Peak surge ₹100."""
        res = get_surge_pricing(occupied_slots=80, total_slots=100)
        assert res["occupancy_percentage"] == 80.0
        assert res["hourly_rate"] == PRICE_TIER_PEAK
        assert res["tier_key"] == "PEAK"
        assert res["badge_variant"] == "danger"

    def test_occupancy_boundary_hundred_percent(self):
        """100% occupancy (12/12 occupied) -> Peak surge ₹100."""
        res = get_surge_pricing(occupied_slots=12, total_slots=12)
        assert res["occupancy_percentage"] == 100.0
        assert res["hourly_rate"] == PRICE_TIER_PEAK
        assert res["tier_key"] == "PEAK"

    def test_facility_twelve_slots_progression(self):
        """
        Verify tier transitions for standard 12-slot bay:
        - 0-5 occupied: 0.0% - 41.7% -> STANDARD (₹50)
        - 6-9 occupied: 50.0% - 75.0% -> MODERATE (₹75)
        - 10-12 occupied: 83.3% - 100.0% -> PEAK (₹100)
        """
        # 5 out of 12 (41.7%)
        p5 = get_surge_pricing(5, 12)
        assert p5["occupancy_percentage"] == 41.7
        assert p5["hourly_rate"] == 50

        # 6 out of 12 (50.0%)
        p6 = get_surge_pricing(6, 12)
        assert p6["occupancy_percentage"] == 50.0
        assert p6["hourly_rate"] == 75

        # 9 out of 12 (75.0%)
        p9 = get_surge_pricing(9, 12)
        assert p9["occupancy_percentage"] == 75.0
        assert p9["hourly_rate"] == 75

        # 10 out of 12 (83.3%)
        p10 = get_surge_pricing(10, 12)
        assert p10["occupancy_percentage"] == 83.3
        assert p10["hourly_rate"] == 100

    def test_edge_cases_safety(self):
        """Test zero capacity, negative slots, and overflow."""
        # Zero total capacity
        assert calculate_occupancy_percentage(0, 0) == 0.0
        p_zero = get_surge_pricing(0, 0)
        assert p_zero["occupancy_percentage"] == 0.0
        assert p_zero["hourly_rate"] == 50

        # Negative occupied slots clamped
        assert calculate_occupancy_percentage(-5, 12) == 0.0

        # Overflow occupied slots clamped to total
        assert calculate_occupancy_percentage(20, 12) == 100.0
