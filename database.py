"""
database.py - Legacy Compatibility Module.
The application core has been upgraded to Flask-SQLAlchemy with support for
both SQLite (development) and PostgreSQL (production).

Active implementation:
- Models: app.models (AdminUser, ParkingZone, ParkingSlot, Booking)
- Allocation Engine: app.services.allocation_service
- Pricing Engine: app.services.pricing_service
"""

from app.models import db, AdminUser, ParkingZone, ParkingSlot, Booking
from app.services.allocation_service import allocate_slot, cancel_booking_by_reference
from app.services.pricing_service import get_system_wide_stats, get_all_zones_pricing_summary

__all__ = [
    "db",
    "AdminUser",
    "ParkingZone",
    "ParkingSlot",
    "Booking",
    "allocate_slot",
    "cancel_booking_by_reference",
    "get_system_wide_stats",
    "get_all_zones_pricing_summary",
]
