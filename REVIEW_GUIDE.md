# College Mini-Project Review & Viva Guide

**Project Title:** Concurrency-Safe Urban Parking Allocator With Surge Analytics  
**Domain:** Distributed Systems, Web Engineering, Database Concurrency & Urban Mobility  
**Framework:** Python Flask, SQLAlchemy ORM, Chart.js, SQLite / PostgreSQL  

---

## 1. Quick Demonstration Script (For 5-10 Minute Presentation)

### Step 1: System Overview (1 Minute)
1. Open the Home Page (`http://127.0.0.1:5000/`).
2. Point out the live metric ribbon: Total Capacity, Available Slots, Occupied Slots, Overall City Occupancy %, and Active Vehicles.
3. Explain that the city is divided into **4 distinct metropolitan zones** (Downtown, Silicon Tech Park, Metro Interchange, Airport Aerocity) with different capacities, amenities, and base hourly tariffs.

### Step 2: Zone Availability & Dynamic Surge Pricing (2 Minutes)
1. Navigate to **Availability** (`/availability`).
2. Show the filter dropdowns: filter by Zone or Demand Level.
3. Point out Zone B (Silicon Tech Park): with 8 out of 10 slots occupied (80%), the demand level is **High Demand (1.6x multiplier)** and the tariff has dynamically increased from ₹50/hr to ₹80/hr.
4. Point out Zone C (Metro Interchange): with only 25% occupancy, it operates at **Standard Base Tariff (1.0x)** at ₹40/hr.
5. Emphasize: *The pricing is 100% data-driven and computed directly from database occupancy via the formula `(Occupied / Total) × 100` with anti-gouging caps (1.0x to 2.0x).*

### Step 3: Concurrency-Safe Booking & Instant Cancellation (3 Minutes)
1. Navigate to **Book Parking** (`/book`).
2. Select Zone A. Point out the interactive visual bay layout with green (Available), red (Occupied), and yellow (Maintenance) slots.
3. Click an available slot (e.g. `A-07`).
4. Show the modal with locked-in rate preview (₹78/hr, 1.3x Moderate Surge).
5. Enter driver name (`Rohan Sharma`) and vehicle number (`KA-01-AB-1234`). Click **Confirm Booking**.
6. The booking is instantly confirmed with a unique reference code (e.g. `BKG-20261025-XXXXXX`).
7. Point out that slot `A-07` on the visual grid immediately updates to red **OCCUPIED**.
8. Show the cancellation feature: enter the reference in the Lookup & Cancel section and click **Release / Cancel Slot**.
9. Slot `A-07` instantly reverts to green **AVAILABLE** in the database.

### Step 4: Analytics Dashboard (1.5 Minutes)
1. Navigate to **Analytics** (`/analytics`).
2. Showcase the 4 interactive Chart.js charts:
   - **Zone Capacity & Occupancy:** Stacked bar chart showing vacant vs parked vehicles per zone.
   - **Dynamic Tariff & Multiplier:** Current price per hour per zone.
   - **Metropolitan Distribution:** Donut chart of city-wide bay status.
   - **Urban Mobility Curve:** Hourly occupancy trend throughout peak rush hours.
3. Click **Refresh Analytics Data** to show dynamic API re-fetching without full-page reloads.

### Step 5: Administrator Panel (1.5 Minutes)
1. Click **Admin Login** (`/admin/login`).
2. Log in with `admin` / `Admin@12345`.
3. Show the executive dashboard with cumulative revenue, active parked vehicles, and recent transaction records.
4. Show **Manage Zones**: demonstrate adding a new zone or toggling active status.
5. Show **Manage Slots**: demonstrate setting a slot to `MAINTENANCE` hold or clearing an occupied slot.
6. Show **Booking Audit Log**: search by vehicle registration number or filter by status.

### Step 6: Automated Concurrency Verification (1 Minute)
1. Switch to terminal/command prompt.
2. Run: `pytest -v`
3. Show that all **32 automated tests pass in ~5 seconds**, including the 12-thread simultaneous race condition stress test where exactly 1 thread wins and 11 are cleanly rejected.

---

## 2. Key Code Files Roadmap

| Feature | Primary Source Files |
|---|---|
| **Database Models & Constraints** | `app/models.py` (`AdminUser`, `ParkingZone`, `ParkingSlot`, `Booking`, partial index `idx_active_slot_booking`) |
| **Concurrency & Allocation Logic** | `app/services/allocation_service.py` (`allocate_slot`, `auto_allocate_slot`, `cancel_booking_by_reference`) |
| **Surge Pricing Algorithm** | `app/services/pricing_service.py` (`calculate_surge_multiplier`, `compute_zone_pricing`, `PRICING_TIERS`) |
| **Application Factory & Config** | `app/__init__.py`, `config.py`, `wsgi.py` |
| **Frontend UI Templates** | `templates/base.html`, `templates/index.html`, `templates/availability.html`, `templates/book.html`, `templates/analytics.html`, `templates/about.html`, `templates/admin/` |
| **Interactive JavaScript** | `static/js/main.js`, `static/js/booking.js`, `static/js/analytics.js` |
| **Automated Tests** | `tests/test_concurrency.py`, `tests/test_booking.py`, `tests/test_pricing.py`, `tests/test_admin.py`, `tests/test_rollback.py` |

---

## 3. Top Examiner Viva Questions & Detailed Answers

### Q1: What is a Race Condition in parking allocation, and how did you prevent it?
**Examiner's Intent:** To check if you understand multi-threading, concurrency hazards, and database synchronization.  
**Answer:**  
A race condition occurs when two or more concurrent processes query the database at the same instant, both observe that a parking slot has `status = 'AVAILABLE'`, and both attempt to reserve it. Without concurrency controls, both transactions commit, causing a double-booking.  
We prevented this using a multi-layer defense:
1. **Row-Level Locking in PostgreSQL:** We use SQLAlchemy's `with_for_update()` to place an exclusive write lock on the target slot row during the transaction.
2. **Atomic Conditional Updates in SQLite & PostgreSQL:** We execute:
   ```sql
   UPDATE parking_slots SET status = 'OCCUPIED' WHERE id = :slot_id AND status = 'AVAILABLE';
   ```
   The database engine evaluates this condition atomically. If two threads run this simultaneously, exactly one thread sees `rowcount == 1`. The second thread sees `rowcount == 0` and is safely aborted with an HTTP 409 Conflict.
3. **Database Schema Partial Unique Index:** We enforced:
   ```sql
   CREATE UNIQUE INDEX idx_active_slot_booking ON bookings(slot_id) WHERE status = 'ACTIVE';
   ```
   Even if application code had a flaw, the physical database engine strictly forbids two simultaneous ACTIVE bookings for the same slot.

---

### Q2: Why did you not just use Python's `threading.Lock()` or `asyncio`?
**Examiner's Intent:** To test if you understand the difference between single-process threading and multi-process WSGI production deployment.  
**Answer:**  
In production, Flask runs under a WSGI application server like **Gunicorn** with multiple worker processes (`gunicorn --workers 2 --threads 4`).  
Each Gunicorn worker is an independent operating system process with its own separate address space. An in-memory lock (`threading.Lock()`) only synchronizes threads inside Worker #1. If Request A arrives at Worker #1 and Request B arrives at Worker #2 at the same time, Worker #2 has no knowledge of Worker #1's lock. They would both execute the booking and create a double-booking.  
Therefore, concurrency synchronization **must** happen at the database level where state is centralized and ACID compliance is guaranteed.

---

### Q3: Explain how the dynamic surge pricing algorithm works.
**Examiner's Intent:** To evaluate if your pricing model is legitimate, mathematical, and transparent.  
**Answer:**  
Our surge pricing engine is occupancy-elastic:
$$\text{Occupancy \%} = \left(\frac{\text{Occupied Slots}}{\text{Total Slots}}\right) \times 100$$
We define 4 policy tiers:
- **Standard Tier (< 50%):** 1.0x multiplier (baseline fee).
- **Moderate Tier (50% to 74%):** 1.3x multiplier (+30% surge to balance vehicle turnover).
- **High Demand Tier (75% to 89%):** 1.6x multiplier (+60% surge).
- **Peak Surge Tier (>= 90%):** 2.0x multiplier (+100% surge cap).

Tariffs are protected by anti-gouging bounds (clamped between 1.0x and 2.0x). The rate computed at the exact instant of booking is permanently locked into the driver's booking record so their fee does not increase after reserving.

---

### Q4: How is administrative access secured?
**Examiner's Intent:** To test web security best practices (passwords, sessions, auth guards).  
**Answer:**  
1. Passwords are never stored in plain text. They are hashed using `werkzeug.security.generate_password_hash` using PBKDF2 with SHA256 and salt.
2. Protected routes are guarded by a custom `@admin_required` Python decorator that checks `session.get('admin_logged_in')`.
3. If an unauthenticated user attempts to access `/admin/dashboard`, they are redirected with HTTP 302 to `/admin/login`.
4. When the admin logs out, `session.clear()` is called to destroy the session cookie.

---

### Q5: How do you handle transaction rollback if an error occurs midway?
**Examiner's Intent:** To evaluate ACID atomicity and error resilience.  
**Answer:**  
In `app/services/allocation_service.py`, the entire booking operation is wrapped in a `try...except` block with explicit `db.session.rollback()`.  
If an exception occurs (such as an IntegrityError, database timeout, or hardware error) after the slot status is updated but before the booking is committed, `db.session.rollback()` reverts all pending changes. The slot remains `AVAILABLE` and no orphan booking is saved. This is verified by our automated test in `tests/test_rollback.py`.
