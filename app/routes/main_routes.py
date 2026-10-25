from flask import Blueprint, render_template
from app.models import ParkingZone, ParkingSlot, Booking
from app.services.pricing_service import get_system_wide_stats, get_all_zones_pricing_summary

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    """Home landing page with live city statistics, features, and quick allocation CTA."""
    stats = get_system_wide_stats()
    zone_summaries = get_all_zones_pricing_summary()
    return render_template("index.html", stats=stats, zones=zone_summaries)


@main_bp.route("/availability")
def availability():
    """Zone availability page displaying real-time occupancy and rates per zone."""
    stats = get_system_wide_stats()
    zones = ParkingZone.query.filter_by(is_active=True).order_by(ParkingZone.code.asc()).all()
    zone_summaries = get_all_zones_pricing_summary()
    return render_template("availability.html", stats=stats, zones=zones, zone_summaries=zone_summaries)


@main_bp.route("/about")
def about():
    """System Architecture, Concurrency Problem, and Academic Review Guide page."""
    return render_template("about.html")
