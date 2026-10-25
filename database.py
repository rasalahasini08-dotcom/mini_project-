"""
database.py - Concurrency-Safe SQLite Database Operations for Urban Parking Allocator.

Key Concurrency Protections:
1. WAL (Write-Ahead Logging) mode: Enables concurrent read transactions while writes proceed.
2. BEGIN IMMEDIATE Transactions: Immediately acquires write lock to prevent race conditions.
3. Atomic Conditional Updates: 'UPDATE ... WHERE slot_id = ? AND status = 'AVAILABLE''
   ensures only one concurrent caller can change slot state from AVAILABLE to OCCUPIED.
4. Unique Partial Index: 'idx_active_slot_booking' at schema level strictly forbids multiple
   simultaneous ACTIVE bookings for the same slot.
5. Idempotent Initialization: Initializes exactly 12 parking slots (P01-P12) without wiping existing data.
"""

import os
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pricing import get_surge_pricing

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parking.db")
TOTAL_CONFIGURED_SLOTS = 12


def get_db_path() -> str:
    """Retrieve database path from environment variable or default fallback."""
    return os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Create a configured SQLite connection with foreign keys enabled,
    WAL mode, tuned busy timeout, and row factory.
    """
    path = db_path or get_db_path()
    # Ensure directory exists if path is in subfolder
    db_dir = os.path.dirname(os.path.abspath(path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(
        path,
        timeout=15.0,  # Wait up to 15s for locks during concurrent load
        isolation_level=None  # Explicit transaction control with BEGIN IMMEDIATE
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # Set WAL mode and busy timeout for high concurrency
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize database schema and populate initial 12 parking slots (P01..P12).
    This function is strictly idempotent and preserves existing booking history.
    """
    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.cursor()

        # 1. Parking Slots Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parking_slots (
                slot_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('AVAILABLE', 'OCCUPIED')),
                updated_at TIMESTAMP NOT NULL
            );
        """)

        # 2. Bookings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id TEXT PRIMARY KEY,
                slot_id TEXT NOT NULL REFERENCES parking_slots(slot_id),
                user_name TEXT NOT NULL,
                vehicle_number TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'CANCELLED')),
                hourly_rate INTEGER NOT NULL,
                booked_at TIMESTAMP NOT NULL,
                cancelled_at TIMESTAMP NULL
            );
        """)

        # 3. Unique Partial Index: Hard database constraint preventing multiple active bookings
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_active_slot_booking
            ON bookings(slot_id)
            WHERE status = 'ACTIVE';
        """)

        # 4. Secondary index for fast history lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookings_time
            ON bookings(booked_at DESC);
        """)

        # 5. Populate initial slots P01 to P12 if they do not already exist
        now_iso = datetime.now().isoformat()
        initial_slots = [(f"P{i:02d}", "AVAILABLE", now_iso) for i in range(1, TOTAL_CONFIGURED_SLOTS + 1)]
        cursor.executemany("""
            INSERT OR IGNORE INTO parking_slots (slot_id, status, updated_at)
            VALUES (?, ?, ?);
        """, initial_slots)

        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()


def get_all_slots(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch all 12 parking slots with their current status and active booking details.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        query = """
            SELECT
                s.slot_id,
                s.status AS slot_status,
                s.updated_at,
                b.booking_id,
                b.user_name,
                b.vehicle_number,
                b.hourly_rate,
                b.booked_at
            FROM parking_slots s
            LEFT JOIN bookings b ON s.slot_id = b.slot_id AND b.status = 'ACTIVE'
            ORDER BY s.slot_id ASC;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        slots = []
        for r in rows:
            slots.append({
                "slot_id": r["slot_id"],
                "status": r["slot_status"],
                "is_available": r["slot_status"] == "AVAILABLE",
                "updated_at": r["updated_at"],
                "active_booking": {
                    "booking_id": r["booking_id"],
                    "user_name": r["user_name"],
                    "vehicle_number": r["vehicle_number"],
                    "hourly_rate": r["hourly_rate"],
                    "booked_at": r["booked_at"]
                } if r["booking_id"] else None
            })
        return slots
    finally:
        conn.close()


def get_parking_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate summary statistics and real-time surge pricing from the database.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM parking_slots;")
        total_slots = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM parking_slots WHERE status = 'OCCUPIED';")
        occupied_slots = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'ACTIVE';")
        active_bookings = cursor.fetchone()[0]

        available_slots = total_slots - occupied_slots
        pricing_info = get_surge_pricing(occupied_slots, total_slots)

        return {
            "total_slots": total_slots,
            "occupied_slots": occupied_slots,
            "available_slots": available_slots,
            "active_bookings": active_bookings,
            "occupancy_percentage": pricing_info["occupancy_percentage"],
            "hourly_rate": pricing_info["hourly_rate"],
            "pricing": pricing_info
        }
    finally:
        conn.close()


def book_slot(
    slot_id: str,
    user_name: str,
    vehicle_number: str,
    db_path: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Concurrency-Safe slot booking transaction.

    Concurrency Protection Steps:
    1. Starts an IMMEDIATE transaction to claim write lock.
    2. Performs an atomic conditional update:
       UPDATE parking_slots SET status = 'OCCUPIED' WHERE slot_id = ? AND status = 'AVAILABLE'
    3. Checks cursor.rowcount. If 0, the slot was already taken or does not exist.
    4. Inserts booking with status = 'ACTIVE'.
    5. Schema partial unique index 'idx_active_slot_booking' provides secondary barrier.
    6. Commits cleanly; rolls back on any error.

    Returns:
        (success: bool, response_dict: dict, http_status_code: int)
    """
    slot_id = slot_id.strip().upper() if slot_id else ""
    user_name = user_name.strip() if user_name else ""
    vehicle_number = vehicle_number.strip().upper() if vehicle_number else ""

    if not slot_id or not user_name or not vehicle_number:
        return False, {
            "error": "VALIDATION_ERROR",
            "message": "Slot ID, Driver Name, and Vehicle Number are all required."
        }, 400

    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.cursor()

        # Step 1: Verify slot exists
        cursor.execute("SELECT slot_id, status FROM parking_slots WHERE slot_id = ?;", (slot_id,))
        slot_row = cursor.fetchone()
        if not slot_row:
            conn.execute("ROLLBACK;")
            return False, {
                "error": "SLOT_NOT_FOUND",
                "message": f"Parking slot '{slot_id}' does not exist in this facility."
            }, 404

        # Step 2: Atomic Conditional Update
        now_iso = datetime.now().isoformat()
        cursor.execute("""
            UPDATE parking_slots
            SET status = 'OCCUPIED', updated_at = ?
            WHERE slot_id = ? AND status = 'AVAILABLE';
        """, (now_iso, slot_id))

        if cursor.rowcount == 0:
            # Slot is already occupied (or another concurrent transaction won the race)
            conn.execute("ROLLBACK;")
            return False, {
                "error": "SLOT_ALREADY_OCCUPIED",
                "message": f"Slot '{slot_id}' is currently occupied or was just reserved by another user."
            }, 409

        # Step 3: Determine current surge price based on occupancy *before* this booking was finalized
        cursor.execute("SELECT COUNT(*) FROM parking_slots;")
        total_slots = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM parking_slots WHERE status = 'OCCUPIED';")
        occupied_slots = cursor.fetchone()[0]

        # Calculate locked-in rate for this booking
        pricing_data = get_surge_pricing(occupied_slots, total_slots)
        applied_rate = pricing_data["hourly_rate"]

        # Step 4: Insert booking record
        # Format: BKG-YYYYMMDD-8HEX
        booking_code = f"BKG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        cursor.execute("""
            INSERT INTO bookings (
                booking_id, slot_id, user_name, vehicle_number,
                status, hourly_rate, booked_at
            ) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?);
        """, (booking_code, slot_id, user_name, vehicle_number, applied_rate, now_iso))

        conn.execute("COMMIT;")

        return True, {
            "message": f"Slot '{slot_id}' booked successfully!",
            "booking": {
                "booking_id": booking_code,
                "slot_id": slot_id,
                "user_name": user_name,
                "vehicle_number": vehicle_number,
                "status": "ACTIVE",
                "hourly_rate": applied_rate,
                "booked_at": now_iso
            }
        }, 201

    except sqlite3.IntegrityError as err:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        return False, {
            "error": "INTEGRITY_CONFLICT",
            "message": f"Conflict detected: duplicate booking attempt prevented ({str(err)})."
        }, 409
    except sqlite3.OperationalError as err:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        return False, {
            "error": "DATABASE_LOCK_TIMEOUT",
            "message": f"System is under heavy concurrent load. Please retry in a moment ({str(err)})."
        }, 503
    except Exception as err:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        return False, {
            "error": "INTERNAL_ERROR",
            "message": f"An unexpected error occurred while booking slot: {str(err)}"
        }, 500
    finally:
        conn.close()


def cancel_booking(
    booking_id: str,
    db_path: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Cancel an active booking, record the cancellation timestamp,
    and release the parking slot back to 'AVAILABLE'.

    Maintains full audit history of previous bookings.

    Returns:
        (success: bool, response_dict: dict, http_status_code: int)
    """
    booking_id = booking_id.strip() if booking_id else ""
    if not booking_id:
        return False, {
            "error": "VALIDATION_ERROR",
            "message": "Booking ID is required for cancellation."
        }, 400

    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.cursor()

        # Step 1: Find active booking
        cursor.execute("""
            SELECT booking_id, slot_id, status
            FROM bookings
            WHERE booking_id = ?;
        """, (booking_id,))
        row = cursor.fetchone()

        if not row:
            conn.execute("ROLLBACK;")
            return False, {
                "error": "BOOKING_NOT_FOUND",
                "message": f"No booking found with ID '{booking_id}'."
            }, 404

        if row["status"] != "ACTIVE":
            conn.execute("ROLLBACK;")
            return False, {
                "error": "ALREADY_CANCELLED",
                "message": f"Booking '{booking_id}' has already been cancelled."
            }, 400

        slot_id = row["slot_id"]
        now_iso = datetime.now().isoformat()

        # Step 2: Mark booking as CANCELLED with timestamp
        cursor.execute("""
            UPDATE bookings
            SET status = 'CANCELLED', cancelled_at = ?
            WHERE booking_id = ? AND status = 'ACTIVE';
        """, (now_iso, booking_id))

        if cursor.rowcount == 0:
            conn.execute("ROLLBACK;")
            return False, {
                "error": "CONCURRENT_CANCELLATION",
                "message": "Booking status was modified concurrently."
            }, 409

        # Step 3: Release parking slot back to AVAILABLE
        cursor.execute("""
            UPDATE parking_slots
            SET status = 'AVAILABLE', updated_at = ?
            WHERE slot_id = ?;
        """, (now_iso, slot_id))

        conn.execute("COMMIT;")

        return True, {
            "message": f"Booking '{booking_id}' cancelled. Slot '{slot_id}' is now AVAILABLE.",
            "booking_id": booking_id,
            "slot_id": slot_id,
            "cancelled_at": now_iso
        }, 200

    except Exception as err:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        return False, {
            "error": "INTERNAL_ERROR",
            "message": f"Failed to cancel booking: {str(err)}"
        }, 500
    finally:
        conn.close()


def get_recent_history(limit: int = 20, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve audit history of recent bookings (both active and cancelled).
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                booking_id,
                slot_id,
                user_name,
                vehicle_number,
                status,
                hourly_rate,
                booked_at,
                cancelled_at
            FROM bookings
            ORDER BY booked_at DESC
            LIMIT ?;
        """, (limit,))
        rows = cursor.fetchall()
        history = []
        for r in rows:
            history.append({
                "booking_id": r["booking_id"],
                "slot_id": r["slot_id"],
                "user_name": r["user_name"],
                "vehicle_number": r["vehicle_number"],
                "status": r["status"],
                "hourly_rate": r["hourly_rate"],
                "booked_at": r["booked_at"],
                "cancelled_at": r["cancelled_at"]
            })
        return history
    finally:
        conn.close()
