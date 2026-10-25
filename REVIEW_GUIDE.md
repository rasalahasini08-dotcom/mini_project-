# College Mini-Project Review & Viva Guide
## Concurrency-Safe Urban Parking Allocator With Surge Analytics

This document is prepared to help you confidently present and demonstrate your project to college faculty, reviewers, and external examiners during the mini-project review.

---

## 🎯 1. Key Concept Explanations (What to say to Faculty)

### Q1: What problem does this project solve?
> **Answer:**
> "In smart city parking systems, multiple users or automated vehicle navigation systems frequently attempt to book the same vacant parking bay simultaneously. Conventional applications suffer from race conditions where two users read the slot as available and both end up booking it.
>
> Our project solves this by guaranteeing **concurrency-safe parking allocation** with zero duplicate bookings, combined with **dynamic surge pricing analytics** that adjust hourly parking rates based on real-time occupancy to mitigate bay congestion."

---

### Q2: Why is concurrency safety necessary, and what is a race condition here?
> **Answer:**
> "A race condition occurs when the system's outcome depends on the non-deterministic timing or interleaving of competing threads.
> 
> Without concurrency control:
> - User A and User B check slot `P01` at the same microsecond.
> - Both queries return `status == 'AVAILABLE'`.
> - User A updates the slot to `OCCUPIED`.
> - User B also updates the slot to `OCCUPIED` and creates a second active booking.
> 
> Concurrency safety is necessary to preserve **ACID consistency and isolation**, ensuring that a physical parking bay can only ever be allocated to exactly one driver at a time."

---

### Q3: How exactly does your system prevent simultaneous booking conflicts?
> **Answer:**
> "We implement a **3-tier defensive architecture**:
> 1. **Immediate Write Locking (`BEGIN IMMEDIATE`):**
>    Standard SQLite transactions are deferred (`DEFERRED`), delaying locks until write operations. We use `BEGIN IMMEDIATE` to immediately reserve a write lock, serializing competing booking transactions while allowing concurrent reads.
> 2. **Atomic Conditional SQL Update:**
>    ```sql
>    UPDATE parking_slots
>    SET status = 'OCCUPIED', updated_at = ?
>    WHERE slot_id = ? AND status = 'AVAILABLE';
>    ```
>    This is the core synchronization primitive. Even if two threads execute this statement simultaneously, the database engine executes it atomically. Exactly one transaction gets `cursor.rowcount == 1` (the winner). The second transaction gets `cursor.rowcount == 0` because the slot is no longer `'AVAILABLE'`. The backend catches this, executes a clean rollback, and returns a controlled `HTTP 409 Conflict`.
> 3. **Database Partial Unique Index (Defense-in-Depth):**
>    ```sql
>    CREATE UNIQUE INDEX idx_active_slot_booking ON bookings(slot_id) WHERE status = 'ACTIVE';
>    ```
>    At the schema level, SQLite will physically reject any attempt to insert two bookings with `status = 'ACTIVE'` for the same slot with an `sqlite3.IntegrityError`."

---

### Q4: How are occupancy percentage and surge pricing calculated?
> **Answer:**
> "Occupancy is computed from active database rows:
> $$\text{Occupancy \%} = \left(\frac{\text{Occupied Slots}}{\text{Total Active Slots}}\right) \times 100$$
> For our 12-slot bay, the hourly rate transitions dynamically:
> - **Occupancy < 50% (0 to 5 occupied slots):** Standard Tier = **₹50 / hr**
> - **Occupancy 50% to < 80% (6 to 9 occupied slots):** Moderate Surge (1.5x) = **₹75 / hr**
> - **Occupancy ≥ 80% (10 to 12 occupied slots):** Peak Surge (2.0x) = **₹100 / hr**
> 
> The pricing is calculated by an isolated module (`pricing.py`) and is locked into the booking record at confirmation time so the driver's bill is fixed upon booking."

---

### Q5: What do database transactions do in your project?
> **Answer:**
> "Transactions provide **ACID properties**:
> - **Atomicity:** When booking a slot, two operations must happen together: updating `parking_slots` to `OCCUPIED` and inserting a new row into `bookings`. If either operation fails, the transaction is rolled back, preventing orphaned bookings or ghost occupied slots.
> - **Consistency:** Enforced by schema foreign keys, CHECK constraints (`status IN ('AVAILABLE', 'OCCUPIED')`), and the partial unique index.
> - **Isolation:** Transactions run in serializable write isolation using `BEGIN IMMEDIATE` with `WAL` mode.
> - **Durability:** Committed transactions are flushed to disk."

---

### Q6: How was the project tested?
> **Answer:**
> "We developed an automated test suite containing **24 tests** using Pytest:
> - **Functional Tests:** App startup, 12-slot seeding, booking, cancellation, rebooking, and audit trail retention.
> - **Boundary Value Tests:** Evaluated 0%, 49%, 50%, 79%, 80%, and 100% occupancy thresholds.
> - **Concurrent Stress Testing (`test_concurrency.py`):** We used Python's `ThreadPoolExecutor` and `threading.Barrier` to launch 12 parallel threads targeting slot `P01` at the exact same millisecond. The test verified that **exactly 1 thread succeeded** (HTTP 201), **11 threads were safely rejected** (HTTP 409), and direct SQL inspection verified only 1 active booking existed in the database."

---

## 🎬 2. Practical Live Demonstration Sequence

Follow this sequence during your project presentation:

1. **Open the Dashboard:**
   - Show the 12 clean parking slots (`P01` to `P12`), all showing green (`Available`).
   - Point out the metrics: Total: 12, Available: 12, Occupied: 0, Occupancy: 0%, Rate: ₹50/hr (Standard Tier highlighted).

2. **Demonstrate a Normal Booking:**
   - Click "Book Slot" on `P01`.
   - Enter Driver Name ("Rohan Sharma") and Vehicle ("KA-01-AB-1234").
   - Click "Confirm Booking".
   - Show the toast alert confirming booking.
   - Point out that `P01` turns red (`Occupied`) displaying the driver's details and locked rate.
   - Show that Available is now 11, Occupied is 1, Occupancy is 8.3%.
   - Point out the new entry in the Recent Allocation Audit Trail table.

3. **Demonstrate Dynamic Surge Pricing:**
   - Book 5 more slots (`P02` through `P06`).
   - Occupancy reaches 50.0% (6/12 occupied).
   - Point out that the Hourly Rate automatically jumps to **₹75/hr** and the "Moderate Surge" tier card is now highlighted.
   - Book 4 more slots (`P07` through `P10`).
   - Occupancy reaches 83.3% (10/12 occupied).
   - Point out that the Hourly Rate automatically jumps to **₹100/hr** and the "Peak Surge" tier card is highlighted.

4. **Demonstrate Cancellation & Rebooking:**
   - Click "Release Slot" on `P01`.
   - Confirm cancellation.
   - Point out that `P01` immediately turns green (`Available`).
   - Show that in the Audit Trail table, the booking status changed to `CANCELLED` with a cancellation timestamp (data is preserved for audit purposes).
   - Book `P01` again with a different vehicle to prove released slots can be reused.

5. **Demonstrate Automated Concurrency Verification:**
   - Open a terminal and run:
     ```bash
     pytest tests/test_concurrency.py -v
     ```
   - Show the examiners the 12-thread simultaneous race test passing with 1 winner and 11 controlled rejections.
   - Run the full suite:
     ```bash
     pytest -v
     ```
   - All 24 tests pass in under 3 seconds!

---

## 💡 3. Likely Faculty Questions & Short Sharp Answers

| Faculty Question | Recommended Answer |
| :--- | :--- |
| **Why SQLite instead of MySQL/PostgreSQL?** | SQLite is serverless, zero-configuration, and has ACID transaction compliance. For single-server deployments, SQLite in WAL mode can handle hundreds of writes per second with low overhead. The code is modular so switching to PostgreSQL is a 1-line connection swap. |
| **What happens if two drivers click "Book" at the same time?** | The atomic update query `UPDATE parking_slots SET status = 'OCCUPIED' WHERE slot_id = ? AND status = 'AVAILABLE'` resolves this. The database guarantees atomicity: only one thread receives `rowcount == 1`. The loser receives `rowcount == 0` and is cleanly rejected with a 409 Conflict. |
| **Why not just check if the slot is free in Python code with `if slot.is_available:`?** | That is the classic "check-then-act" anti-pattern. Between the time Python checks the status and the time Python executes the write, another thread can interleave and book the slot. The check and the lock must be atomic inside the database engine. |
| **Why does SQLite WAL mode matter?** | Default SQLite locks the entire database file during writes, blocking readers. WAL (Write-Ahead Logging) separates reads and writes, allowing concurrent readers to read the database without blocking while a write transaction is committing. |
| **What happens if a booking is cancelled? Is the history deleted?** | No. We never perform hard DELETEs on bookings. The booking is marked `CANCELLED` and timestamped (`cancelled_at`), releasing the slot back to `AVAILABLE`. This maintains an audit trail. |
