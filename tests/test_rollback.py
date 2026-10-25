from unittest.mock import patch
import pytest
from app.models import db, ParkingSlot, Booking
from app.services.allocation_service import allocate_slot


class TestTransactionRollback:
    """Verify database transaction rollback and atomicity guarantees."""

    def test_allocation_rollback_on_commit_exception(self, app):
        """
        Simulate an unexpected database exception during the booking commit phase.
        Guarantees that:
        - The transaction is rolled back cleanly.
        - The target slot status remains 'AVAILABLE' (no dirty state).
        - No orphan booking record is persisted.
        """
        with app.app_context():
            slot = ParkingSlot.query.filter_by(status="AVAILABLE").first()
            assert slot is not None
            slot_id = slot.id
            slot_num = slot.slot_number

        # Patch db.session.commit to raise an unexpected database exception
        with patch.object(db.session, "commit", side_effect=Exception("Simulated Database Hardware Failure")):
            with app.app_context():
                success, res, code = allocate_slot(
                    slot_id=slot_id,
                    driver_name="Rollback Driver",
                    vehicle_number="FAIL-999"
                )

                assert success is False
                assert code == 500
                assert res["error"] == "TRANSACTION_FAILURE"

        # Verify that after rollback, the slot is still AVAILABLE
        with app.app_context():
            slot_after = db.session.get(ParkingSlot, slot_id)
            assert slot_after.status == "AVAILABLE", (
                f"Atomicity Violation: Slot {slot_num} was left as '{slot_after.status}' after transaction failure!"
            )

            # Ensure no booking was persisted
            failed_booking = Booking.query.filter_by(vehicle_number="FAIL-999").first()
            assert failed_booking is None, "Atomicity Violation: Orphan booking record was persisted!"
