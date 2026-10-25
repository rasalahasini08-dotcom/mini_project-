"""
test_concurrency.py - High-Concurrency Stress Tests for Race Condition Prevention.

Crucial Verification:
1. Multiple simultaneous threads attempting to book the EXACT SAME slot:
   - Exactly ONE thread must succeed (HTTP 201).
   - ALL competing threads must be rejected with 409 Conflict.
   - Schema-level inspection verifies exactly 1 active booking in SQLite.
2. Concurrent booking of DIFFERENT slots:
   - Independent resources must be allocated simultaneously without false conflicts.
3. Database consistency & integrity constraint verification.
"""

import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest
from app import create_app
from database import get_connection, book_slot


@pytest.fixture
def concurrency_test_env():
    """Setup a dedicated SQLite database and Flask client for concurrency stress testing."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": db_path,
        "SECRET_KEY": "concurrency-test-key"
    })

    yield app, db_path

    # Teardown
    for ext in ["", "-wal", "-shm"]:
        p = db_path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


class TestConcurrencySafety:
    """Rigorous concurrent race-condition test suite."""

    def test_concurrent_booking_same_slot_race_condition(self, concurrency_test_env):
        """
        Simulate 12 concurrent users attempting to book slot 'P01' at the exact same instant.
        Must result in:
        - Exactly 1 success (HTTP 201)
        - Exactly 11 rejections (HTTP 409 Conflict / Controlled rejection)
        - Exactly 1 ACTIVE booking record in the database
        - Slot 'P01' status set to 'OCCUPIED'
        """
        app, db_path = concurrency_test_env
        target_slot = "P01"
        num_competing_threads = 12

        # Barrier to align threads to start at the exact same millisecond
        barrier = threading.Barrier(num_competing_threads)
        results = []

        def attempt_booking(thread_idx: int):
            # Wait for all threads to arrive at barrier before firing
            barrier.wait()
            # Direct database booking transaction under test
            success, res_data, status_code = book_slot(
                slot_id=target_slot,
                user_name=f"Racer_{thread_idx}",
                vehicle_number=f"RACE-{thread_idx:02d}",
                db_path=db_path
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
        rejected = [r for r in results if r["success"] is False and r["status_code"] in (409, 503)]

        print(f"\n[Concurrency Test] Total Competing Requests: {len(results)}")
        print(f"[Concurrency Test] Successful Allocations: {len(successful)}")
        print(f"[Concurrency Test] Rejected Competing Requests: {len(rejected)}")

        # Strict Assertions: Exactly ONE winner
        assert len(successful) == 1, (
            f"Concurrency Failure: Expected exactly 1 winner, but got {len(successful)}!"
        )
        assert len(rejected) == num_competing_threads - 1

        # Direct database inspection
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()

            # 1. Verify slot status is OCCUPIED
            cursor.execute("SELECT status FROM parking_slots WHERE slot_id = ?;", (target_slot,))
            slot_status = cursor.fetchone()[0]
            assert slot_status == "OCCUPIED"

            # 2. Verify active bookings count is EXACTLY 1
            cursor.execute("""
                SELECT COUNT(*) FROM bookings
                WHERE slot_id = ? AND status = 'ACTIVE';
            """, (target_slot,))
            active_count = cursor.fetchone()[0]
            assert active_count == 1, (
                f"Integrity Violation: Found {active_count} active bookings for slot {target_slot}!"
            )
        finally:
            conn.close()

    def test_concurrent_booking_different_slots(self, concurrency_test_env):
        """
        Simulate concurrent booking requests for DIFFERENT slots (P01 through P08).
        Ensures locking does not falsely block independent resource allocation.
        All independent requests should succeed.
        """
        app, db_path = concurrency_test_env
        slots_to_book = [f"P{i:02d}" for i in range(1, 9)]  # 8 different slots
        num_threads = len(slots_to_book)
        barrier = threading.Barrier(num_threads)
        results = []

        def book_specific_slot(slot_name: str, idx: int):
            barrier.wait()
            success, res_data, status_code = book_slot(
                slot_id=slot_name,
                user_name=f"Driver_{slot_name}",
                vehicle_number=f"CAR-{idx:02d}",
                db_path=db_path
            )
            return {
                "slot_id": slot_name,
                "success": success,
                "status_code": status_code
            }

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(book_specific_slot, slot, i) for i, slot in enumerate(slots_to_book)]
            for f in as_completed(futures):
                results.append(f.result())

        # All 8 independent slots must succeed
        successful = [r for r in results if r["success"] is True and r["status_code"] == 201]
        assert len(successful) == num_threads, f"Expected {num_threads} successes, got {len(successful)}"

        # Verify database state
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'ACTIVE';")
            total_active = cursor.fetchone()[0]
            assert total_active == num_threads

            cursor.execute("SELECT COUNT(*) FROM parking_slots WHERE status = 'OCCUPIED';")
            total_occupied = cursor.fetchone()[0]
            assert total_occupied == num_threads
        finally:
            conn.close()

    def test_database_integrity_constraint_direct_enforcement(self, concurrency_test_env):
        """
        Directly verify the database partial unique index:
        Attempting to insert two ACTIVE bookings for the same slot must raise sqlite3.IntegrityError.
        """
        app, db_path = concurrency_test_env
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            # First active booking
            cursor.execute("""
                INSERT INTO bookings (booking_id, slot_id, user_name, vehicle_number, status, hourly_rate, booked_at)
                VALUES ('BKG-TEST-1', 'P10', 'Driver A', 'REG-1', 'ACTIVE', 50, '2026-10-25T12:00:00');
            """)

            # Second active booking for SAME slot P10 must violate partial unique index
            with pytest.raises(Exception) as excinfo:
                cursor.execute("""
                    INSERT INTO bookings (booking_id, slot_id, user_name, vehicle_number, status, hourly_rate, booked_at)
                    VALUES ('BKG-TEST-2', 'P10', 'Driver B', 'REG-2', 'ACTIVE', 50, '2026-10-25T12:00:01');
                """)
            assert "UNIQUE constraint failed" in str(excinfo.value)
        finally:
            conn.close()
