"""
pricing.py - Dynamic Surge Pricing Engine for Urban Parking Allocator.

This module computes real-time parking occupancy rates and dynamic hourly pricing
based on strict occupancy thresholds:
- Tier 1 (Standard):       Occupancy < 50%           -> ₹50 / hour
- Tier 2 (Moderate Surge):  50% <= Occupancy < 80%   -> ₹75 / hour
- Tier 3 (Peak Surge):      Occupancy >= 80%          -> ₹100 / hour

Formulas:
Occupancy Percentage = (Occupied Slots / Total Active Slots) * 100
"""

from typing import Dict, Any

# Pricing Constants
PRICE_TIER_STANDARD = 50
PRICE_TIER_MODERATE = 75
PRICE_TIER_PEAK = 100

THRESHOLD_MODERATE = 50.0
THRESHOLD_PEAK = 80.0


def calculate_occupancy_percentage(occupied_slots: int, total_slots: int) -> float:
    """
    Calculate the current parking occupancy rate as a percentage rounded to 1 decimal place.

    Args:
        occupied_slots (int): Number of currently occupied parking slots.
        total_slots (int): Total number of active parking slots in the facility.

    Returns:
        float: Occupancy percentage between 0.0 and 100.0.
    """
    if total_slots <= 0:
        return 0.0

    if occupied_slots < 0:
        occupied_slots = 0
    elif occupied_slots > total_slots:
        occupied_slots = total_slots

    percentage = (occupied_slots / total_slots) * 100.0
    return round(percentage, 1)


def get_surge_pricing(occupied_slots: int, total_slots: int = 12) -> Dict[str, Any]:
    """
    Determine dynamic surge pricing and tier explanation from real-time occupancy.

    Args:
        occupied_slots (int): Number of currently occupied slots.
        total_slots (int): Total active capacity (default: 12).

    Returns:
        dict: Detailed breakdown including hourly_rate, occupancy_percent, tier_name,
              tier_description, and threshold boundaries.
    """
    occupancy_pct = calculate_occupancy_percentage(occupied_slots, total_slots)

    if occupancy_pct < THRESHOLD_MODERATE:
        tier_key = "STANDARD"
        tier_name = "Standard Rate"
        hourly_rate = PRICE_TIER_STANDARD
        description = "Low to moderate demand (< 50% occupancy). Standard base parking rate applies."
        badge_variant = "success"
    elif occupancy_pct < THRESHOLD_PEAK:
        tier_key = "MODERATE"
        tier_name = "Moderate Surge"
        hourly_rate = PRICE_TIER_MODERATE
        description = "Elevated parking demand (50% to < 80% occupancy). 1.5x moderate surge pricing applied."
        badge_variant = "warning"
    else:
        tier_key = "PEAK"
        tier_name = "Peak Surge"
        hourly_rate = PRICE_TIER_PEAK
        description = "High congestion / critical occupancy (>= 80% occupancy). 2.0x peak surge pricing applied."
        badge_variant = "danger"

    return {
        "occupied_slots": occupied_slots,
        "total_slots": total_slots,
        "available_slots": max(0, total_slots - occupied_slots),
        "occupancy_percentage": occupancy_pct,
        "hourly_rate": hourly_rate,
        "currency": "INR",
        "currency_symbol": "₹",
        "tier_key": tier_key,
        "tier_name": tier_name,
        "badge_variant": badge_variant,
        "description": description,
        "thresholds": {
            "standard_max": THRESHOLD_MODERATE,
            "moderate_min": THRESHOLD_MODERATE,
            "moderate_max": THRESHOLD_PEAK,
            "peak_min": THRESHOLD_PEAK
        }
    }
