"""
pricing.py - Backward Compatibility Shim.
Delegates to app.services.pricing_service.
"""

from app.services.pricing_service import (
    calculate_surge_multiplier,
    compute_zone_pricing,
    get_zone_pricing_data,
    get_all_zones_pricing_summary,
    get_system_wide_stats,
    PRICING_TIERS
)


def get_surge_pricing(occupied_slots: int, total_slots: int = 12):
    """Legacy helper for backward compatibility."""
    return compute_zone_pricing(
        zone_id=1,
        zone_name="Standard Facility",
        zone_code="P-BAY",
        base_rate=50.0,
        occupied_slots=occupied_slots,
        total_slots=total_slots
    )
