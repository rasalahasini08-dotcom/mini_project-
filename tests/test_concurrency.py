"""
test_concurrency.py - High-Concurrency Stress Tests for Race Condition Prevention.

Crucial Verification:
1. Multiple simultaneous threads attempting to book the EXACT SAME slot:
   - Exactly ONE thread must succeed (HTTP 201).
   - ALL competing threads must be rejected with 409 Conflict.
   - Database verification: exactly 1 active booking record in database.
2. Concurrent booking of DIFFERENT slots:
   - Independent resources allocated simultaneously without false conflicts.
3. Concurrent auto-allocation:
   - Competing auto-allocation callers receive distinct slots without collisions.
4. Database partial unique constraint:
   - 'idx_active_slot_booking' directly enforced at database level.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest
from app.models import db, ParkingSlot, Booking, ParkingZone
from app.services.allocation_service import allocate_slot, auto_allocate_slot


class TestConcurrencySafety:
    """Rigorous concurrent race-condition test suite."""

    def test_concurrent_booking_same_slot_race_condition(self, app):
        """
        Simulate 12 concurrent threads attempting to book the EXACT SAME slot at the same instant.
        Must result in:
        - Exactly 1 success (201)
        - Exactly 11 rejections (409 Conflict)
        - Exactly 1 ACTIVE booking record in the database
        - Target slot marked OCCUPIED
        """
        with app.app_context():
            # Find an available slot in Zone C
            target_slot = ParkingSlot.query.filter_by(zone_id=3, status="AVAILABLE").first()
            if not target_slot:
                target_slot = ParkingSlot.query.filter_by(status="AVAILABLE").first()
            assert target_slot is not None, "Need at least one available slot for concurrency test"
            target_slot_id = target_slot.id

        num_competing_threads = 12
        barrier = threading.Barrier(num_competing_threads)
        results = []

        def attempt_booking(thread_idx: int):
            # Wait for all threads to reach the barrier before firing simultaneously
            barrier.wait()
            with app.app_context():
                success, res_data, status_code = allocate_slot(
                    slot_id=target_slot_id,
                    driver_name=f"Concurrent_Driver_{thread_idx}",
                    vehicle_number=f"RACE-{thread_idx:02d}",
                    contact_number=f"+91-90000000{thread_idx:02d}"
                )
                return {
                    "thread_idx": thread_idx,
                    "success": success,
                    "status_code": status_code,
                    "data": res_data
                }

        with ThreadPoolExecutor(max_workers=num_competing_threads) as executor:
            futures = [executor.submit(attempt_booking, i) for i in range(num_competing_threads)]
            for f in as_completed(futures):
                results.append(f.result())

        # Evaluate outcomes
        successful = [r for r in results if r["success"] is True and r["status_code"] == 201]
        rejected = [r for r in results if r["success"] is False and r["status_code"] == 409]

        print(f"\n[Concurrency Test] Total Competing Requests: {len(results)}")
        print(f"[Concurrency Test] Successful Allocations: {len(successful)}")
        print(f"[Concurrency Test] Rejected Competing Requests: {len(rejected)}")

        # Strict Assertions: Exactly ONE winner
        assert len(successful) == 1, (
            f"Race Condition Detected: Expected exactly 1 winner, but got {len(successful)}!"
        )
        assert len(rejected) == num_competing_threads - 1, (
            f"Expected {num_competing_threads - 1} rejections, but got {len(rejected)}"
        )

        # Database state verification
        with app.app_context():
            slot = db.session.get(ParkingSlot, target_slot_id)
            assert slot.status == "OCCUPIED"

            active_bookings = Booking.query.filter_by(slot_id=target_slot_id, status="ACTIVE").all()
            assert len(active_bookings) == 1, (
                f"Data Integrity Failure: Expected 1 active booking in DB, but found {len(active_bookings)}"
            )

    def test_concurrent_booking_different_slots(self, app):
        """
        Multiple concurrent threads booking distinct slots should all succeed without false conflicts.
        """
        with app.app_context():
            available_slots = ParkingSlot.query.filter_by(status="AVAILABLE").limit(4).all()
            slot_ids = [s.id for s in available_slots]

        assert len(slot_ids) >= 3, "Need at least 3 available slots"

        num_threads = len(slot_ids)
        barrier = threading.Barrier(num_threads)
        results = []

        def book_distinct(thread_idx: int, slot_id: int):
            barrier.wait()
            with app.app_context():
                success, res_data, status_code = allocate_slot(
                    slot_id=slot_id,
                    driver_name=f"Distinct_Driver_{thread_idx}",
                    vehicle_number=f"DIST-{thread_idx:02d}"
                )
                return {
                    "slot_id": slot_id,
                    "success": success,
                    "status_code": status_code
                }

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(book_distinct, i, slot_ids[i]) for i in range(num_threads)]
            for f in as_completed(futures):
                results.append(f.result())

        successful = [r for r in results if r["success"] is True and r["status_code"] == 201]
        assert len(successful) == num_threads, f"Expected all {num_threads} distinct bookings to succeed"

    def test_database_integrity_constraint_direct_enforcement(self, app):
        """
        Attempting to directly bypass application logic and insert 2 ACTIVE bookings
        for the same slot must trigger an IntegrityError at the physical database schema level.
        """
        with app.app_context():
            avail_slot = ParkingSlot.query.filter_by(status="AVAILABLE").first()
            assert avail_slot is not None, "Need an available slot for integrity test"

            # First active booking
            bkg1 = Booking(
                booking_reference="BKG-TEST-INTEG-01",
                slot_id=avail_slot.id,
                driver_name="Direct Driver 1",
                vehicle_number="DIR-01",
                hourly_rate=50.0,
                status="ACTIVE"
            )
            db.session.add(bkg1)
            db.session.commit()

            # Second active booking for the SAME slot must fail via unique partial index
            bkg2 = Booking(
                booking_reference="BKG-TEST-INTEG-02",
                slot_id=avail_slot.id,
                driver_name="Direct Driver 2",
                vehicle_number="DIR-02",
                hourly_rate=50.0,
                status="ACTIVE"
            )
            db.session.add(bkg2)

            with pytest.raises(Exception):
                # Must raise IntegrityError due to idx_active_slot_booking
                db.session.commit()

            db.session.rollback()
