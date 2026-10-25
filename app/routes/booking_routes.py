from flask import Blueprint, render_template, request, flash, redirect, url_for
from app.models import ParkingZone, ParkingSlot, Booking
from app.services.pricing_service import get_all_zones_pricing_summary

booking_bp = Blueprint("booking", __name__)


@booking_bp.route("/book")
def book_page():
    """Interactive slot selection and booking interface."""
    zones = ParkingZone.query.filter_by(is_active=True).order_by(ParkingZone.code.asc()).all()
    selected_zone_id = request.args.get("zone_id", type=int)
    if not selected_zone_id and zones:
        selected_zone_id = zones[0].id

    zone_summaries = get_all_zones_pricing_summary()
    return render_template(
        "book.html",
        zones=zones,
        selected_zone_id=selected_zone_id,
        zone_summaries=zone_summaries
    )
