from functools import wraps
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from app.models import db, AdminUser, ParkingZone, ParkingSlot, Booking
from app.services.pricing_service import get_system_wide_stats, get_all_zones_pricing_summary
from app.services.allocation_service import cancel_booking_by_reference

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    """Decorator to enforce administrator authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please sign in to access the administrator panel.", "warning")
            return redirect(url_for("admin.login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """Administrator login handler with secure password verification."""
    if session.get("admin_logged_in"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = AdminUser.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.clear()
            session["admin_logged_in"] = True
            session["admin_id"] = user.id
            session["admin_username"] = user.username
            flash(f"Welcome back, Administrator {user.username}!", "success")
            next_page = request.args.get("next") or url_for("admin.dashboard")
            return redirect(next_page)
        else:
            flash("Invalid administrator credentials. Please check your username and password.", "danger")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    """Sign out administrator and clear session."""
    session.clear()
    flash("You have been logged out securely.", "info")
    return redirect(url_for("admin.login"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    """Main administrator analytics and operations dashboard."""
    stats = get_system_wide_stats()
    zones = ParkingZone.query.order_by(ParkingZone.code.asc()).all()
    recent_bookings = Booking.query.order_by(Booking.booked_at.desc()).limit(15).all()

    # Calculate total revenue from active and completed bookings
    active_and_completed = Booking.query.filter(Booking.status.in_(["ACTIVE", "COMPLETED"])).all()
    total_revenue = sum(b.hourly_rate for b in active_and_completed)

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        zones=zones,
        recent_bookings=recent_bookings,
        total_revenue=total_revenue
    )


@admin_bp.route("/zones", methods=["GET", "POST"])
@admin_required
def manage_zones():
    """Manage parking zones (view, add, toggle status)."""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            code = request.form.get("code", "").strip().upper()
            name = request.form.get("name", "").strip()
            location = request.form.get("location", "").strip()
            base_rate = float(request.form.get("base_hourly_rate", 50.0))
            num_slots = int(request.form.get("total_slots", 8))
            amenities = request.form.get("amenities", "").strip()

            if not code or not name or not location:
                flash("Zone code, name, and location are required.", "danger")
            elif ParkingZone.query.filter_by(code=code).first():
                flash(f"Zone code '{code}' already exists.", "danger")
            else:
                new_zone = ParkingZone(
                    code=code,
                    name=name,
                    location=location,
                    base_hourly_rate=base_rate,
                    total_slots=num_slots,
                    amenities=amenities or "Covered, 24/7 Security",
                    is_active=True
                )
                db.session.add(new_zone)
                db.session.flush()

                # Generate initial parking slots for the new zone
                prefix = code.replace("ZONE-", "").replace("ZONE", "").strip()
                if not prefix:
                    prefix = "Z"
                for i in range(1, num_slots + 1):
                    slot = ParkingSlot(
                        slot_number=f"{prefix}-{i:02d}",
                        zone_id=new_zone.id,
                        status="AVAILABLE",
                        slot_type="EV Charging" if i == 1 else "Standard",
                        floor_level="Level 1"
                    )
                    db.session.add(slot)

                db.session.commit()
                flash(f"Zone '{name}' ({code}) with {num_slots} slots created successfully!", "success")
                return redirect(url_for("admin.manage_zones"))

        elif action == "toggle_active":
            zone_id = request.form.get("zone_id", type=int)
            zone = db.session.get(ParkingZone, zone_id)
            if zone:
                zone.is_active = not zone.is_active
                db.session.commit()
                status_str = "activated" if zone.is_active else "deactivated"
                flash(f"Zone '{zone.name}' has been {status_str}.", "info")
            return redirect(url_for("admin.manage_zones"))

    zones = ParkingZone.query.order_by(ParkingZone.code.asc()).all()
    zone_summaries = get_all_zones_pricing_summary()
    return render_template("admin/zones.html", zones=zones, zone_summaries=zone_summaries)


@admin_bp.route("/slots", methods=["GET", "POST"])
@admin_required
def manage_slots():
    """Manage individual parking slots across zones."""
    zone_filter = request.args.get("zone_id", type=int)
    status_filter = request.args.get("status")

    if request.method == "POST":
        slot_id = request.form.get("slot_id", type=int)
        new_status = request.form.get("status")
        slot = db.session.get(ParkingSlot, slot_id)
        if slot and new_status in ["AVAILABLE", "MAINTENANCE"]:
            # If changing from occupied to available, ensure any active booking is handled
            if slot.status == "OCCUPIED" and new_status == "AVAILABLE":
                active_booking = slot.bookings.filter_by(status="ACTIVE").first()
                if active_booking:
                    cancel_booking_by_reference(active_booking.booking_reference)
            else:
                slot.status = new_status
                db.session.commit()
            flash(f"Slot {slot.slot_number} status updated to {new_status}.", "success")
        return redirect(url_for("admin.manage_slots", zone_id=zone_filter, status=status_filter))

    query = ParkingSlot.query.join(ParkingZone)
    if zone_filter:
        query = query.filter(ParkingSlot.zone_id == zone_filter)
    if status_filter:
        query = query.filter(ParkingSlot.status == status_filter)

    slots = query.order_by(ParkingZone.code.asc(), ParkingSlot.slot_number.asc()).all()
    zones = ParkingZone.query.order_by(ParkingZone.code.asc()).all()

    return render_template(
        "admin/slots.html",
        slots=slots,
        zones=zones,
        selected_zone=zone_filter,
        selected_status=status_filter
    )


@admin_bp.route("/bookings")
@admin_required
def manage_bookings():
    """View and search comprehensive booking audit records."""
    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()

    query = Booking.query.join(ParkingSlot).join(ParkingZone)

    if search_query:
        query = query.filter(
            db.or_(
                Booking.booking_reference.ilike(f"%{search_query}%"),
                Booking.driver_name.ilike(f"%{search_query}%"),
                Booking.vehicle_number.ilike(f"%{search_query}%"),
                ParkingSlot.slot_number.ilike(f"%{search_query}%")
            )
        )

    if status_filter and status_filter != "ALL":
        query = query.filter(Booking.status == status_filter)

    bookings = query.order_by(Booking.booked_at.desc()).limit(100).all()
    return render_template(
        "admin/bookings.html",
        bookings=bookings,
        search_query=search_query,
        selected_status=status_filter
    )


@admin_bp.route("/bookings/cancel/<booking_ref>", methods=["POST"])
@admin_required
def cancel_booking_admin(booking_ref):
    """Admin endpoint to manually cancel a booking and free the slot."""
    success, res, code = cancel_booking_by_reference(booking_ref)
    if success:
        flash(f"Booking {booking_ref} cancelled and slot released.", "success")
    else:
        flash(f"Failed to cancel booking: {res.get('message')}", "danger")
    return redirect(url_for("admin.manage_bookings"))
