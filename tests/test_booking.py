import pytest
from app.models import db, ParkingZone, ParkingSlot, Booking


class TestApplicationEndpoints:
    """Verify application pages and core health endpoints."""

    def test_health_check(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "healthy"
        assert "database_engine" in data

    def test_page_renders(self, client):
        for path in ["/", "/availability", "/book", "/analytics", "/about"]:
            res = client.get(path)
            assert res.status_code == 200, f"Page {path} failed to render (status {res.status_code})"


class TestBookingWorkflow:
    """Verify booking allocation, rejection, and cancellation lifecycle."""

    def test_book_available_slot_success(self, app, client):
        with app.app_context():
            # Find an available slot
            slot = ParkingSlot.query.filter_by(status="AVAILABLE").first()
            assert slot is not None
            slot_id = slot.id
            slot_num = slot.slot_number

        # Submit booking
        payload = {
            "slot_id": slot_id,
            "driver_name": "Test Driver",
            "vehicle_number": "KA-01-AB-9999",
            "contact_number": "+91-9876543210"
        }
        res = client.post("/api/book", json=payload)
        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        assert data["booking"]["slot_number"] == slot_num
        assert data["booking"]["status"] == "ACTIVE"

        # Verify database state
        with app.app_context():
            updated_slot = db.session.get(ParkingSlot, slot_id)
            assert updated_slot.status == "OCCUPIED"
            bkg = Booking.query.filter_by(booking_reference=data["booking"]["booking_reference"]).first()
            assert bkg is not None
            assert bkg.status == "ACTIVE"

    def test_reject_booking_occupied_slot(self, app, client):
        with app.app_context():
            occupied_slot = ParkingSlot.query.filter_by(status="OCCUPIED").first()
            assert occupied_slot is not None
            slot_id = occupied_slot.id

        payload = {
            "slot_id": slot_id,
            "driver_name": "Second Driver",
            "vehicle_number": "MH-02-CD-5555"
        }
        res = client.post("/api/book", json=payload)
        assert res.status_code == 409
        data = res.get_json()
        assert data["success"] is False
        assert data["error"] == "SLOT_ALREADY_OCCUPIED"

    def test_auto_allocate_slot(self, app, client):
        with app.app_context():
            zone = ParkingZone.query.filter_by(code="ZONE-A").first()
            assert zone is not None
            zone_id = zone.id

        payload = {
            "zone_id": zone_id,
            "driver_name": "Auto Driver",
            "vehicle_number": "DL-01-AUTO-11"
        }
        res = client.post("/api/auto-allocate", json=payload)
        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        assert "booking" in data
        assert data["booking"]["status"] == "ACTIVE"

    def test_cancel_active_booking(self, app, client):
        with app.app_context():
            active_bkg = Booking.query.filter_by(status="ACTIVE").first()
            assert active_bkg is not None
            ref = active_bkg.booking_reference
            slot_id = active_bkg.slot_id

        # Cancel the booking
        res = client.post("/api/cancel", json={"booking_reference": ref})
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True

        # Verify slot is released back to AVAILABLE
        with app.app_context():
            slot = db.session.get(ParkingSlot, slot_id)
            assert slot.status == "AVAILABLE"
            cancelled_bkg = Booking.query.filter_by(booking_reference=ref).first()
            assert cancelled_bkg.status == "CANCELLED"
            assert cancelled_bkg.cancelled_at is not None

    def test_double_cancellation_rejected(self, app, client):
        with app.app_context():
            active_bkg = Booking.query.filter_by(status="ACTIVE").first()
            assert active_bkg is not None
            ref = active_bkg.booking_reference

        # First cancellation
        res1 = client.post("/api/cancel", json={"booking_reference": ref})
        assert res1.status_code == 200

        # Second cancellation attempt
        res2 = client.post("/api/cancel", json={"booking_reference": ref})
        assert res2.status_code == 400
        data = res2.get_json()
        assert data["error"] == "ALREADY_PROCESSED"


class TestValidationAndErrors:
    """Verify input validation and bad request handling."""

    def test_missing_driver_name_rejected(self, client):
        payload = {
            "slot_id": 1,
            "driver_name": "",
            "vehicle_number": "KA-01-AB-1234"
        }
        res = client.post("/api/book", json=payload)
        assert res.status_code == 400
        data = res.get_json()
        assert data["error"] == "VALIDATION_ERROR"

    def test_missing_vehicle_number_rejected(self, client):
        payload = {
            "slot_id": 1,
            "driver_name": "Valid Driver",
            "vehicle_number": ""
        }
        res = client.post("/api/book", json=payload)
        assert res.status_code == 400
        data = res.get_json()
        assert data["error"] == "VALIDATION_ERROR"

    def test_nonexistent_slot_rejected(self, client):
        payload = {
            "slot_id": 99999,
            "driver_name": "Valid Driver",
            "vehicle_number": "KA-01-AB-1234"
        }
        res = client.post("/api/book", json=payload)
        assert res.status_code == 404

    def test_cancel_nonexistent_booking_rejected(self, client):
        res = client.post("/api/cancel", json={"booking_reference": "BKG-NON-EXISTENT"})
        assert res.status_code == 404
