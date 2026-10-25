"""
test_booking.py - Functional Tests for Parking Allocation, Cancellation & Schema Integrity.

Verifies:
- Application startup & health
- Idempotent 12-slot initialization (P01..P12)
- Successful booking of available slots
- Rejection of occupied slots (409 Conflict)
- Cancellation & timestamp recording
- Rebooking released slots
- Audit trail preservation
- Validation errors and malformed requests
"""

import os
import tempfile
import pytest
from app import create_app
from database import get_connection, get_all_slots, get_recent_history, TOTAL_CONFIGURED_SLOTS


@pytest.fixture
def test_client():
    """Create an isolated test application instance with a fresh temporary SQLite database."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": db_path,
        "SECRET_KEY": "test-key"
    })

    with app.test_client() as client:
        yield client, db_path

    # Cleanup temporary test database files
    for ext in ["", "-wal", "-shm"]:
        p = db_path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


class TestApplicationAndSlots:
    """Tests application startup, healthcheck, and slot initialization."""

    def test_startup_and_health(self, test_client):
        client, _ = test_client
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "healthy"

    def test_dashboard_renders(self, test_client):
        client, _ = test_client
        res = client.get("/")
        assert res.status_code == 200
        assert b"Urban Parking Allocator" in res.data

    def test_twelve_slots_initialized(self, test_client):
        client, db_path = test_client
        res = client.get("/api/slots")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["total"] == TOTAL_CONFIGURED_SLOTS
        assert len(data["data"]) == TOTAL_CONFIGURED_SLOTS

        slot_ids = [s["slot_id"] for s in data["data"]]
        expected_ids = [f"P{i:02d}" for i in range(1, 13)]
        assert slot_ids == expected_ids

        # All slots must initially be AVAILABLE
        for slot in data["data"]:
            assert slot["status"] == "AVAILABLE"
            assert slot["is_available"] is True
            assert slot["active_booking"] is None


class TestBookingWorkflow:
    """Tests the complete lifecycle of booking, rejecting occupied, cancelling, and rebooking."""

    def test_book_available_slot(self, test_client):
        client, _ = test_client
        payload = {
            "slot_id": "P01",
            "user_name": "Rohan Sharma",
            "vehicle_number": "KA-01-AB-1234"
        }
        res = client.post("/api/book", json=payload)
        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        bkg = data["booking"]
        assert bkg["slot_id"] == "P01"
        assert bkg["user_name"] == "Rohan Sharma"
        assert bkg["vehicle_number"] == "KA-01-AB-1234"
        assert bkg["status"] == "ACTIVE"
        assert bkg["hourly_rate"] == 50  # 0/12 occupied at time of quote

        # Verify slot status changed to OCCUPIED
        slot_res = client.get("/api/slots")
        slots = {s["slot_id"]: s for s in slot_res.get_json()["data"]}
        assert slots["P01"]["status"] == "OCCUPIED"
        assert slots["P01"]["is_available"] is False
        assert slots["P01"]["active_booking"]["booking_id"] == bkg["booking_id"]

    def test_reject_booking_occupied_slot(self, test_client):
        client, _ = test_client
        # 1. Book P02
        client.post("/api/book", json={
            "slot_id": "P02",
            "user_name": "First Driver",
            "vehicle_number": "KA-02-1111"
        })

        # 2. Attempt to book P02 again
        res2 = client.post("/api/book", json={
            "slot_id": "P02",
            "user_name": "Second Driver",
            "vehicle_number": "DL-01-2222"
        })
        assert res2.status_code == 409
        data2 = res2.get_json()
        assert data2["success"] is False
        assert data2["error"] == "SLOT_ALREADY_OCCUPIED"

    def test_cancel_active_booking(self, test_client):
        client, _ = test_client
        # Book P03
        bkg_res = client.post("/api/book", json={
            "slot_id": "P03",
            "user_name": "Amit Verma",
            "vehicle_number": "MH-12-PQ-9999"
        })
        booking_id = bkg_res.get_json()["booking"]["booking_id"]

        # Cancel booking
        cancel_res = client.post("/api/cancel", json={"booking_id": booking_id})
        assert cancel_res.status_code == 200
        cancel_data = cancel_res.get_json()
        assert cancel_data["success"] is True
        assert cancel_data["slot_id"] == "P03"

        # Verify slot is back to AVAILABLE
        slot_res = client.get("/api/slots")
        slots = {s["slot_id"]: s for s in slot_res.get_json()["data"]}
        assert slots["P03"]["status"] == "AVAILABLE"
        assert slots["P03"]["is_available"] is True

    def test_rebook_cancelled_slot(self, test_client):
        client, _ = test_client
        # Book P04
        r1 = client.post("/api/book", json={"slot_id": "P04", "user_name": "Driver 1", "vehicle_number": "KA-04-1111"})
        bkg1_id = r1.get_json()["booking"]["booking_id"]

        # Cancel P04
        client.post("/api/cancel", json={"booking_id": bkg1_id})

        # Re-book P04 with different driver
        r2 = client.post("/api/book", json={"slot_id": "P04", "user_name": "Driver 2", "vehicle_number": "KA-04-2222"})
        assert r2.status_code == 201
        data2 = r2.get_json()
        assert data2["success"] is True
        assert data2["booking"]["slot_id"] == "P04"
        assert data2["booking"]["user_name"] == "Driver 2"

    def test_preserve_booking_audit_history(self, test_client):
        client, db_path = test_client
        # Book and cancel
        r = client.post("/api/book", json={"slot_id": "P05", "user_name": "Audit Test", "vehicle_number": "HR-26-8888"})
        bkg_id = r.get_json()["booking"]["booking_id"]
        client.post("/api/cancel", json={"booking_id": bkg_id})

        # Fetch history via API
        h_res = client.get("/api/history")
        assert h_res.status_code == 200
        history = h_res.get_json()["data"]
        assert len(history) >= 1

        record = next((item for item in history if item["booking_id"] == bkg_id), None)
        assert record is not None
        assert record["status"] == "CANCELLED"
        assert record["cancelled_at"] is not None
        assert record["slot_id"] == "P05"

    def test_occupancy_and_surge_updates_after_bookings(self, test_client):
        client, _ = test_client
        # Initial stats: 0 occupied, ₹50
        s0 = client.get("/api/status").get_json()["data"]
        assert s0["occupied_slots"] == 0
        assert s0["hourly_rate"] == 50

        # Book 6 slots (50% occupancy)
        for i in range(1, 7):
            client.post("/api/book", json={
                "slot_id": f"P{i:02d}",
                "user_name": f"User {i}",
                "vehicle_number": f"V-{i}"
            })

        s6 = client.get("/api/status").get_json()["data"]
        assert s6["occupied_slots"] == 6
        assert s6["occupancy_percentage"] == 50.0
        assert s6["hourly_rate"] == 75  # Moderate surge triggered

        # Book 4 more slots (total 10 occupied = 83.3% occupancy)
        for i in range(7, 11):
            client.post("/api/book", json={
                "slot_id": f"P{i:02d}",
                "user_name": f"User {i}",
                "vehicle_number": f"V-{i}"
            })

        s10 = client.get("/api/status").get_json()["data"]
        assert s10["occupied_slots"] == 10
        assert s10["occupancy_percentage"] == 83.3
        assert s10["hourly_rate"] == 100  # Peak surge triggered


class TestValidationAndErrors:
    """Tests bad requests, unknown slots, and edge conditions."""

    def test_invalid_slot_id_rejected(self, test_client):
        client, _ = test_client
        res = client.post("/api/book", json={
            "slot_id": "P99",
            "user_name": "Test",
            "vehicle_number": "XX-00"
        })
        assert res.status_code == 404
        assert res.get_json()["error"] == "SLOT_NOT_FOUND"

    def test_missing_fields_rejected(self, test_client):
        client, _ = test_client
        res = client.post("/api/book", json={"slot_id": "P01"})
        assert res.status_code == 400
        assert res.get_json()["error"] == "VALIDATION_ERROR"

    def test_cancel_nonexistent_booking(self, test_client):
        client, _ = test_client
        res = client.post("/api/cancel", json={"booking_id": "NONEXISTENT-ID"})
        assert res.status_code == 404
        assert res.get_json()["error"] == "BOOKING_NOT_FOUND"

    def test_cancel_already_cancelled_booking(self, test_client):
        client, _ = test_client
        r = client.post("/api/book", json={"slot_id": "P06", "user_name": "Test", "vehicle_number": "XX-11"})
        bkg_id = r.get_json()["booking"]["booking_id"]

        # Cancel once -> 200
        res1 = client.post("/api/cancel", json={"booking_id": bkg_id})
        assert res1.status_code == 200

        # Cancel again -> 400 ALREADY_CANCELLED
        res2 = client.post("/api/cancel", json={"booking_id": bkg_id})
        assert res2.status_code == 400
        assert res2.get_json()["error"] == "ALREADY_CANCELLED"
