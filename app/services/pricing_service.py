"""
pricing_service.py - Dynamic Surge Pricing Engine for Urban Parking Allocator.

Mathematical Model:
Occupancy Percentage = (Occupied Slots / Total Slots) * 100

Demand-Based Multiplier Tiers:
- Tier 1: Normal (< 50% Occupancy)      -> Multiplier 1.0x (Standard Base Rate)
- Tier 2: Moderate (50% to < 75%)        -> Multiplier 1.3x (+30% Surge)
- Tier 3: High (75% to < 90%)            -> Multiplier 1.6x (+60% Surge)
- Tier 4: Peak Surge (>= 90% Occupancy)  -> Multiplier 2.0x (+100% Surge Cap)

Guarantees:
- Transparent, reproducible calculations.
- Clamped between MIN_SURGE_MULTIPLIER (1.0) and MAX_SURGE_MULTIPLIER (2.0).
- Explicitly identified as demonstration data per academic and ethics requirements.
"""

from typing import Dict, Any, List, Optional
from app.models import ParkingZone, ParkingSlot, Booking

# Default constants
DEFAULT_BASE_RATE = 50.0
MIN_MULTIPLIER = 1.0
MAX_MULTIPLIER = 2.0

PRICING_TIERS = [
    {
        "tier": "Standard",
        "min_occupancy": 0.0,
        "max_occupancy": 50.0,
        "multiplier": 1.0,
        "badge_class": "badge-success",
        "description": "Normal demand. Standard baseline fee applied."
    },
    {
        "tier": "Moderate",
        "min_occupancy": 50.0,
        "max_occupancy": 75.0,
        "multiplier": 1.3,
        "badge_class": "badge-warning",
        "description": "Elevated bay occupancy. 1.3x surge applied to incentivize turnover."
    },
    {
        "tier": "High",
        "min_occupancy": 75.0,
        "max_occupancy": 90.0,
        "multiplier": 1.6,
        "badge_class": "badge-orange",
        "description": "High demand pressure. 1.6x surge applied to balance capacity."
    },
    {
        "tier": "Peak Surge",
        "min_occupancy": 90.0,
        "max_occupancy": 100.0,
        "multiplier": 2.0,
        "badge_class": "badge-danger",
        "description": "Peak congestion warning. 2.0x maximum surge tariff enforced."
    }
]


Tuple_Tier = Dict[str, Any]


def calculate_surge_multiplier(occupancy_pct: float) -> Dict[str, Any]:
    """
    Determine the surge multiplier and tier classification based on occupancy percentage.
    """
    pct = max(0.0, min(100.0, float(occupancy_pct)))

    if pct < 50.0:
        return PRICING_TIERS[0]
    elif pct < 75.0:
        return PRICING_TIERS[1]
    elif pct < 90.0:
        return PRICING_TIERS[2]
    else:
        return PRICING_TIERS[3]


Tuple_Tier = Dict[str, Any]


def compute_zone_pricing(
    zone_id: int,
    zone_name: str,
    zone_code: str,
    base_rate: float,
    occupied_slots: int,
    total_slots: int
) -> Dict[str, Any]:
    """
    Pure calculation function computing surge pricing for a specific zone.
    Shared by both backend transactions and analytics visualizers.
    """
    total = max(1, total_slots)
    occupied = max(0, min(total, occupied_slots))
    available = max(0, total - occupied)
    occupancy_pct = round((occupied / total) * 100.0, 1)

    tier_info = calculate_surge_multiplier(occupancy_pct)
    multiplier = tier_info["multiplier"]
    effective_rate = round(base_rate * multiplier, 2)
    surge_surcharge = round(effective_rate - base_rate, 2)

    return {
        "zone_id": zone_id,
        "zone_code": zone_code,
        "zone_name": zone_name,
        "base_rate": base_rate,
        "total_slots": total,
        "occupied_slots": occupied,
        "available_slots": available,
        "occupancy_percentage": occupancy_pct,
        "demand_level": tier_info["tier"],
        "multiplier": multiplier,
        "badge_class": tier_info["badge_class"],
        "description": tier_info["description"],
        "effective_rate": effective_rate,
        "surge_surcharge": surge_surcharge,
        "currency_symbol": "₹",
        "formula": f"({occupied} / {total}) × 100 = {occupancy_pct}% -> {multiplier}x multiplier",
        "is_demonstration_data": True
    }


def get_zone_pricing_data(zone: ParkingZone) -> Dict[str, Any]:
    """
    Retrieve live pricing for a specific ParkingZone database instance.
    """
    total = zone.slots.count()
    if total == 0:
        total = zone.total_slots or 10

    occupied = zone.slots.filter(ParkingSlot.status == "OCCUPIED").count()
    return compute_zone_pricing(
        zone_id=zone.id,
        zone_name=zone.name,
        zone_code=zone.code,
        base_rate=zone.base_hourly_rate,
        occupied_slots=occupied,
        total_slots=total
    )


def get_all_zones_pricing_summary() -> List[Dict[str, Any]]:
    """
    Retrieve live pricing summaries across all active parking zones.
    """
    zones = ParkingZone.query.filter_by(is_active=True).order_by(ParkingZone.code.asc()).all()
    return [get_zone_pricing_data(z) for z in zones]


def get_system_wide_stats() -> Dict[str, Any]:
    """
    Aggregate live stats across all parking zones in the city.
    """
    zones = ParkingZone.query.filter_by(is_active=True).all()
    all_slots = ParkingSlot.query.join(ParkingZone).filter(ParkingZone.is_active == True).all()

    total_capacity = len(all_slots)
    occupied_count = sum(1 for s in all_slots if s.status == "OCCUPIED")
    available_count = sum(1 for s in all_slots if s.status == "AVAILABLE")
    maintenance_count = sum(1 for s in all_slots if s.status == "MAINTENANCE")

    active_bookings = Booking.query.filter_by(status="ACTIVE").count()
    total_bookings = Booking.query.count()

    overall_pct = round((occupied_count / total_capacity * 100.0), 1) if total_capacity > 0 else 0.0

    zone_summaries = [get_zone_pricing_data(z) for z in zones]

    return {
        "total_capacity": total_capacity,
        "occupied_slots": occupied_count,
        "available_slots": available_count,
        "maintenance_slots": maintenance_count,
        "overall_occupancy_percentage": overall_pct,
        "active_bookings": active_bookings,
        "total_historical_bookings": total_bookings,
        "zones_count": len(zones),
        "zone_summaries": zone_summaries,
        "pricing_tiers": PRICING_TIERS,
        "is_demonstration_data": True
    }
