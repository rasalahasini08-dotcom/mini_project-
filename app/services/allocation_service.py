"""
allocation_service.py - Concurrency-Safe Parking Allocation Engine.

Core Concurrency Protections:
1. Database Transactions: Atomic status transition and reservation insertion.
2. Database-Supported Concurrency Strategy:
   - PostgreSQL: Row-level locking via 'SELECT ... FOR UPDATE' (with_for_update).
   - SQLite: Atomic conditional updates ('UPDATE ... WHERE id = ? AND status = 'AVAILABLE'').
3. Database Partial Unique Constraint:
   Schema-level index 'idx_active_slot_booking' strictly forbids more than one ACTIVE booking per slot.
4. Auto-Allocation Engine:
   Allocates optimal available slots concurrency-safely without collisions.
5. Transaction Rollback:
   Immediate session rollback on any error or constraint violation.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.exc import IntegrityError, OperationalError
from app.models import db, ParkingZone, ParkingSlot, Booking
from app.services.pricing_service import get_zone_pricing_data


def generate_booking_reference() -> str:
    """Generate a clean, professional booking reference identifier."""
    date_part = datetime.utcnow().strftime("%Y%m%d")
    unique_part = uuid.uuid4().hex[:8].upper()
    return f"BKG-{date_part}-{unique_part}"


def allocate_slot(
    slot_id: int,
    driver_name: str,
    vehicle_number: str,
    contact_number: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Concurrency-Safe slot booking transaction.

    Steps:
    1. Validate input parameters.
    2. Check DB dialect: apply row-level locking on PostgreSQL.
    3. Perform atomic conditional update on slot status (AVAILABLE -> OCCUPIED).
    4. Calculate dynamic surge pricing locked in at booking moment.
    5. Insert Booking record with status 'ACTIVE'.
    6. Commit transaction atomically; rollback on conflict or error.

    Returns:
        (success: bool, response_dict: dict, http_status_code: int)
    """
    driver_name = (driver_name or "").strip()
    vehicle_number = (vehicle_number or "").strip().upper()
    contact_number = (contact_number or "").strip() if contact_number else None

    # Frontend/Backend Input Validation
    if not driver_name:
        return False, {"error": "VALIDATION_ERROR", "message": "Driver name is required."}, 400
    if len(driver_name) < 2 or len(driver_name) > 100:
        return False, {"error": "VALIDATION_ERROR", "message": "Driver name must be between 2 and 100 characters."}, 400
    if not vehicle_number:
        return False, {"error": "VALIDATION_ERROR", "message": "Vehicle registration number is required."}, 400
    if len(vehicle_number) < 4 or len(vehicle_number) > 20:
        return False, {"error": "VALIDATION_ERROR", "message": "Vehicle registration number must be between 4 and 20 characters."}, 400

    try:
        # Determine dialect for database-specific locking
        dialect = db.session.bind.dialect.name if db.session.bind else "sqlite"

        # 1. Row-level locking on PostgreSQL
        if dialect == "postgresql":
            slot = (
                db.session.query(ParkingSlot)
                .filter(ParkingSlot.id == slot_id)
                .with_for_update(nowait=False)
                .first()
            )
            if not slot:
                db.session.rollback()
                return False, {"error": "SLOT_NOT_FOUND", "message": f"Parking slot #{slot_id} does not exist."}, 404
            if slot.status != "AVAILABLE":
                db.session.rollback()
                return False, {
                    "error": "SLOT_ALREADY_OCCUPIED",
                    "message": f"Slot {slot.slot_number} is currently {slot.status} and cannot be reserved."
                }, 409
        else:
            # 2. SQLite / General Dialect: Verify existence
            slot = db.session.query(ParkingSlot).filter(ParkingSlot.id == slot_id).first()
            if not slot:
                db.session.rollback()
                return False, {"error": "SLOT_NOT_FOUND", "message": f"Parking slot #{slot_id} does not exist."}, 404

        zone = slot.zone
        if not zone or not zone.is_active:
            db.session.rollback()
            return False, {"error": "ZONE_INACTIVE", "message": "The parking zone for this slot is currently inactive."}, 400

        # Calculate current dynamic surge price for the zone
        pricing_data = get_zone_pricing_data(zone)
        locked_rate = pricing_data["effective_rate"]
        locked_multiplier = pricing_data["multiplier"]

        now_utc = datetime.utcnow()

        # 3. Atomic Conditional Update:
        # This update only succeeds if the slot is currently AVAILABLE.
        # If another concurrent worker booked it milliseconds before, rows_updated is 0.
        rows_updated = (
            db.session.query(ParkingSlot)
            .filter(ParkingSlot.id == slot_id, ParkingSlot.status == "AVAILABLE")
            .update(
                {"status": "OCCUPIED", "updated_at": now_utc},
                synchronize_session="fetch"
            )
        )

        if rows_updated == 0:
            db.session.rollback()
            return False, {
                "error": "SLOT_ALREADY_OCCUPIED",
                "message": f"Slot {slot.slot_number} was just reserved by another user. Race condition prevented."
            }, 409

        # 4. Insert Booking record
        bkg_ref = generate_booking_reference()
        new_booking = Booking(
            booking_reference=bkg_ref,
            slot_id=slot.id,
            driver_name=driver_name,
            vehicle_number=vehicle_number,
            contact_number=contact_number,
            hourly_rate=locked_rate,
            multiplier=locked_multiplier,
            status="ACTIVE",
            booked_at=now_utc
        )
        db.session.add(new_booking)

        # 5. Atomic Commit
        db.session.commit()

        return True, {
            "message": f"Slot {slot.slot_number} successfully allocated!",
            "booking": {
                "booking_reference": bkg_ref,
                "slot_id": slot.id,
                "slot_number": slot.slot_number,
                "zone_code": zone.code,
                "zone_name": zone.name,
                "driver_name": driver_name,
                "vehicle_number": vehicle_number,
                "contact_number": contact_number,
                "hourly_rate": locked_rate,
                "multiplier": locked_multiplier,
                "demand_level": pricing_data["demand_level"],
                "status": "ACTIVE",
                "booked_at": now_utc.isoformat(),
            }
        }, 201

    except IntegrityError as err:
        db.session.rollback()
        return False, {
            "error": "CONCURRENCY_INTEGRITY_CONFLICT",
            "message": f"Duplicate active booking blocked by database unique index: {str(err.orig if hasattr(err, 'orig') else err)}"
        }, 409

    except OperationalError as err:
        db.session.rollback()
        return False, {
            "error": "DATABASE_BUSY",
            "message": f"High concurrency lock contention detected. Please retry in a moment: {str(err)}"
        }, 503

    except Exception as err:
        db.session.rollback()
        return False, {
            "error": "TRANSACTION_FAILURE",
            "message": f"Transaction rolled back due to internal error: {str(err)}"
        }, 500


def auto_allocate_slot(
    zone_id: int,
    driver_name: str,
    vehicle_number: str,
    slot_type: Optional[str] = None,
    contact_number: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Automatic slot allocation service.
    Finds the first available slot in the specified zone and allocates it safely.
    Handles high concurrency by attempting atomic lock-and-set across candidate slots.
    """
    zone = db.session.get(ParkingZone, zone_id)
    if not zone or not zone.is_active:
        return False, {"error": "ZONE_NOT_FOUND", "message": "Selected parking zone is not active or does not exist."}, 404

    # Candidate query
    query = ParkingSlot.query.filter_by(zone_id=zone.id, status="AVAILABLE")
    if slot_type and slot_type != "Any":
        query = query.filter_by(slot_type=slot_type)

    candidate_slots = query.order_by(ParkingSlot.slot_number.asc()).all()

    if not candidate_slots:
        return False, {
            "error": "ZONE_FULL",
            "message": f"No available slots in {zone.name} matching your preference."
        }, 409

    # Attempt allocation sequentially with atomic safety
    for candidate in candidate_slots:
        success, res, code = allocate_slot(
            slot_id=candidate.id,
            driver_name=driver_name,
            vehicle_number=vehicle_number,
            contact_number=contact_number
        )
        if success:
            return success, res, code
        if code != 409:
            # If failed for reasons other than concurrency collision, return error
            return success, res, code

    return False, {
        "error": "ALL_SLOTS_TAKEN",
        "message": f"All available slots in {zone.name} were claimed by concurrent users. Please choose another zone."
    }, 409


def cancel_booking_by_reference(booking_reference: str) -> Tuple[bool, Dict[str, Any], int]:
    """
    Cancel an active booking atomically, recording cancellation timestamp
    and releasing the parking slot back to 'AVAILABLE'.
    """
    booking_reference = (booking_reference or "").strip().upper()
    if not booking_reference:
        return False, {"error": "VALIDATION_ERROR", "message": "Booking reference is required."}, 400

    try:
        booking = (
            db.session.query(Booking)
            .filter_by(booking_reference=booking_reference)
            .first()
        )

        if not booking:
            db.session.rollback()
            return False, {
                "error": "BOOKING_NOT_FOUND",
                "message": f"No reservation record found for reference '{booking_reference}'."
            }, 404

        if booking.status != "ACTIVE":
            db.session.rollback()
            return False, {
                "error": "ALREADY_PROCESSED",
                "message": f"Booking '{booking_reference}' is already '{booking.status}'."
            }, 400

        slot = booking.slot
        now_utc = datetime.utcnow()

        # Mark booking cancelled
        booking.status = "CANCELLED"
        booking.cancelled_at = now_utc

        # Free the slot
        if slot:
            slot.status = "AVAILABLE"
            slot.updated_at = now_utc

        db.session.commit()

        return True, {
            "message": f"Booking '{booking_reference}' cancelled successfully. Slot {slot.slot_number if slot else ''} is now AVAILABLE.",
            "booking_reference": booking_reference,
            "slot_number": slot.slot_number if slot else None,
            "cancelled_at": now_utc.isoformat(),
        }, 200

    except Exception as err:
        db.session.rollback()
        return False, {
            "error": "CANCELLATION_FAILED",
            "message": f"Failed to cancel booking: {str(err)}"
        }, 500
