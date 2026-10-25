/# Concurrency-Safe Urban Parking Allocator With Surge Analytics

A full-stack, production-ready web application engineered to manage urban parking bays, eliminate race conditions during simultaneous allocation requests, track persistent audit trails, and dynamically adjust hourly parking rates based on real-time occupancy.

Developed as a college mini-project demonstrating **Operating System concurrency controls**, **ACID database transactions**, **dynamic surge pricing algorithms**, and **RESTful API engineering**.

---

## 📌 1. Project Overview & Problem Statement

### The Problem:
In high-density urban parking infrastructure, distributed drivers frequently attempt to reserve the same parking slot at nearly the same instant. Conventional web systems that rely on naive **"check-then-book"** application logic suffer from **race conditions**:
1. Thread A checks if Slot `P01` is `AVAILABLE` (returns `True`).
2. Thread B checks if Slot `P01` is `AVAILABLE` (returns `True`).
3. Thread A writes an active booking for `P01`.
4. Thread B writes an active booking for `P01`.
5. **Outcome:** A double-booking catastrophe where two drivers are allocated the exact same physical slot.

Furthermore, static pricing models fail to manage parking congestion during peak hours or incentivize turnover.

### The Solution:
**Urban Parking Allocator** resolves both challenges:
- **Zero Double-Bookings:** Implements a three-tier defense using atomic conditional database writes (`UPDATE ... WHERE status = 'AVAILABLE'`), schema-level partial unique indexing, and immediate write-lock transactions.
- **Dynamic Surge Pricing:** Implements an automated surge pricing engine that calculates occupancy percentages in real-time and transitions between Standard (₹50/hr), Moderate Surge (₹75/hr), and Peak Surge (₹100/hr) tiers.
- **Persistent Audit Logging:** Maintains historical records of all bookings and cancellations for analytics and reconciliation.

---

## 🛠️ 2. Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python 3.11+ / Flask 3.1 | Core business logic, transactional REST API, routing |
| **WSGI Server** | Gunicorn 26.2 | Production-ready HTTP server for cloud deployment |
| **Database** | SQLite 3 (WAL Mode) | Relational persistence, foreign keys, partial unique indexing |
| **Testing** | Pytest 9.1 | Automated unit, functional, boundary, and concurrent stress testing |
| **Frontend** | Vanilla HTML5, CSS3, JavaScript | Responsive dashboard, real-time metrics, modal dialogs, toast alerts |
| **Cloud Hosting** | Render / Railway / PythonAnywhere | Public web service with environment configuration |

---

## 🏗️ 3. System Architecture

```
[ Client Browser / Mobile ]
            |
            | HTTP / REST (JSON)
            v
[ Flask Web Application (app.py) ]
    ├── Presentation Route: GET /
    ├── REST API Endpoints:
    │     ├── GET  /api/status   (Metrics & Pricing)
    │     ├── GET  /api/slots    (12 Parking Bays)
    │     ├── POST /api/book     (Concurrency-Safe Booking)
    │     ├── POST /api/cancel   (Cancellation & Release)
    │     ├── GET  /api/pricing  (Surge Analytics)
    │     └── GET  /api/history  (Audit Log)
    │
    ├── [ Surge Pricing Engine (pricing.py) ]
    │     └── Computes: (Occupied / Total) * 100 -> ₹50 / ₹75 / ₹100
    │
    └── [ Database Layer (database.py) ]
          ├── SQLite 3 (PRAGMA journal_mode = WAL)
          ├── BEGIN IMMEDIATE Write-Lock Transactions
          ├── Atomic Conditional Update (WHERE status = 'AVAILABLE')
          └── Hard Schema Barrier (Partial UNIQUE Index)
```

---

## 🗄️ 4. Database Schema Design

### 1. `parking_slots` Table
Stores the physical bay inventory (12 slots: `P01` to `P12`).

```sql
CREATE TABLE IF NOT EXISTS parking_slots (
    slot_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('AVAILABLE', 'OCCUPIED')),
    updated_at TIMESTAMP NOT NULL
);
```

### 2. `bookings` Table
Stores booking transactions and cancellation audit details.

```sql
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
```

### 3. Concurrency Defense Constraints & Indexes
```sql
-- 1. Partial Unique Index: Hard constraint preventing multiple ACTIVE bookings for the same slot
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_slot_booking
ON bookings(slot_id)
WHERE status = 'ACTIVE';

-- 2. Audit Trail Index
CREATE INDEX IF NOT EXISTS idx_bookings_time
ON bookings(booked_at DESC);
```

---

## ⚡ 5. Concurrency Control Deep-Dive

To achieve true race-condition immunity, the system employs **three distinct defensive barriers**:

1. **Immediate Write-Lock Acquisition (`BEGIN IMMEDIATE`):**
   Standard SQLite transactions start deferred (`DEFERRED`), delaying locks until a write occurs, which invites lock-upgrade conflicts under load. `BEGIN IMMEDIATE` instructs SQLite to acquire a write reservation upfront, safely serializing concurrent booking transactions while allowing concurrent reads.
2. **Atomic Conditional SQL Update:**
   ```sql
   UPDATE parking_slots
   SET status = 'OCCUPIED', updated_at = ?
   WHERE slot_id = ? AND status = 'AVAILABLE';
   ```
   The database engine evaluates and updates the row atomically.
   - If two threads concurrently target slot `P01`, exactly **one thread** observes `cursor.rowcount == 1`.
   - The competing thread observes `cursor.rowcount == 0` because the condition `status = 'AVAILABLE'` is already false.
   - The competing thread triggers a clean rollback and returns `409 Conflict (SLOT_ALREADY_OCCUPIED)`.
3. **Database-Level Partial Unique Index:**
   `idx_active_slot_booking` acts as the fail-safe barrier. Even if an application-level bug bypassed checks, attempting to insert a second `ACTIVE` booking for the same slot triggers an `sqlite3.IntegrityError`, aborting the transaction.

---

## 📈 6. Surge Pricing Analytics Formula

Hourly parking rates automatically fluctuate based on real-time bay occupancy:

$$\text{Occupancy Percentage} = \left(\frac{\text{Number of Occupied Slots}}{\text{Total Active Capacity}}\right) \times 100$$

### Pricing Thresholds:
| Occupancy Range | Occupied Bays (out of 12) | Hourly Rate | Pricing Tier | Purpose |
| :---: | :---: | :---: | :---: | :--- |
| **0.0% to < 50.0%** | 0 to 5 bays | **₹50 / hr** | **Standard Rate** | Normal off-peak demand |
| **50.0% to < 80.0%** | 6 to 9 bays | **₹75 / hr** | **Moderate Surge** | 1.5x surge to encourage shorter stays |
| **≥ 80.0%** | 10 to 12 bays | **₹100 / hr** | **Peak Surge** | 2.0x peak surge to manage bay congestion |

> **Audit Guarantee:** When a slot is booked, the exact hourly rate is **locked into the booking record** at reservation time, ensuring transparent billing regardless of subsequent price fluctuations.

---

## 💻 7. Local Setup & Execution

### Prerequisites:
- Python 3.10 or higher
- Git

### Step-by-Step Installation:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/urban-parking-allocator.git
   cd urban-parking-allocator
   ```

2. **Create and activate a virtual environment:**
   - **Windows:**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Flask application:**
   ```bash
   python app.py
   ```
   Open your browser and navigate to:
   ```
   http://127.0.0.1:5000
   ```

---

## 🧪 8. Automated Testing Suite

The project includes 24 automated unit, integration, boundary, and multi-threaded concurrency tests.

### Run All Tests:
```bash
pytest -v
```

### Test Coverage Highlights:
- **`tests/test_pricing.py`**:
  - Tests boundary conditions: 0%, 49%, 50%, 79%, 80%, and 100%.
  - Verifies tier transitions across all 12 slots.
  - Tests edge cases (zero capacity, negative values, clamping).
- **`tests/test_booking.py`**:
  - App startup, healthcheck (`/api/health`), and 12-slot initialization (`P01`..`P12`).
  - Booking an available slot and verifying slot status transitions.
  - Rejection of booking on occupied slots (`409 Conflict`).
  - Cancellation of active bookings and verification of slot release.
  - Re-booking released slots.
  - Historical audit preservation (cancelled records remain with timestamps).
- **`tests/test_concurrency.py`**:
  - **Simultaneous Race Condition Test:** Fires 12 parallel threads targeting `P01` at the exact same millisecond using a `threading.Barrier`. Verifies exactly 1 thread succeeds (201 Created), 11 threads are rejected (409 Conflict), and database contains exactly 1 active booking.
  - **Independent Allocation Test:** Concurrently allocates 8 different slots (`P01`–`P08`) to ensure locking does not block independent resources.
  - **Direct Constraint Enforcement:** Verifies schema-level partial unique index.

---

## 🚀 9. Public Deployment (Render Guide)

This application is packaged to deploy on **Render** (or any cloud container/PaaS).

### Steps to Deploy on Render:
1. **Push your code to GitHub.**
2. Go to [Render Dashboard](https://dashboard.render.com/) and click **New + > Web Service**.
3. Select your repository.
4. Configure the Web Service:
   - **Name:** `urban-parking-allocator`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. **Persistent Storage (Recommended):**
   - By default, Render free web services have an ephemeral filesystem (the SQLite database file resets if the container spins down).
   - In Render, navigate to **Disks** and attach a persistent disk mounted at `/var/data`.
   - Add an Environment Variable in Render:
     - `DATABASE_PATH` = `/var/data/parking.db`
     - `SECRET_KEY` = `<your-generated-secret-key>`
6. Click **Deploy Web Service**.
7. Test the public URL (e.g. `https://urban-parking-allocator.onrender.com/api/health`).

---

## ⚖️ 10. Known Limitations & Future Enhancements

- **Single-Node SQLite:** SQLite with WAL mode is exceptionally fast and concurrency-safe for single-instance web services (handling hundreds of writes/sec). For multi-region distributed clusters, migrate the connection layer to PostgreSQL (`SELECT ... FOR UPDATE`).
- **Payment Gateway:** Currently tracks hourly rates and timestamps; future releases can integrate Razorpay or Stripe webhooks.
- **RFID / IoT Integration:** Slot availability can be synced directly with ultrasonic or magnetic parking sensors via MQTT.

---

## 📜 11. License
This project is open-source and developed for academic coursework and engineering evaluation.
