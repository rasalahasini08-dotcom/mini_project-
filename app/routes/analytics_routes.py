from flask import Blueprint, render_template
from app.services.pricing_service import get_system_wide_stats, get_all_zones_pricing_summary, PRICING_TIERS

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
def analytics_dashboard():
    """Interactive Chart.js surge pricing and occupancy analytics dashboard."""
    stats = get_system_wide_stats()
    zone_summaries = get_all_zones_pricing_summary()
    return render_template(
        "analytics.html",
        stats=stats,
        zone_summaries=zone_summaries,
        pricing_tiers=PRICING_TIERS
    )
