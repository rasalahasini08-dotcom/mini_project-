/# Concurrency-Safe Urban Parking Allocator With Surge Analytics

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-teal.svg)](https://flask.palletsprojects.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red.svg)](https://www.sqlalchemy.org/)
[![Tests](https://img.shields.io/badge/Tests-32%20Passed-brightgreen.svg)](https://pytest.org/)
[![Database](https://img.shields.io/badge/Database-SQLite%20%7C%20PostgreSQL-indigo.svg)](https://www.postgresql.org/)
[![Deployment](https://img.shields.io/badge/Deploy-Render%20Ready-success.svg)](https://render.com/)

A full-stack, enterprise-grade urban parking management and dynamic surge allocation web application built for college engineering capstone and mini-project reviews. Engineered specifically to solve the classical **race condition and double-booking anomaly** across parallel threads and multiple application server workers, combined with transparent, occupancy-driven **surge pricing analytics**.

---

## Table of Contents

1. [Project Overview & Key Objectives](#1-project-overview--key-objectives)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture & Data Flow](#3-system-architecture--data-flow)
4. [Concurrency-Safe Allocation Engine](#4-concurrency-safe-allocation-engine)
5. [Dynamic Surge Analytics & Pricing Engine](#5-dynamic-surge-analytics--pricing-engine)
6. [Database Schema & Models](#6-database-schema--models)
7. [Website Pages & Features](#7-website-pages--features)
8. [REST API Endpoints](#8-rest-api-endpoints)
9. [Local Installation & Setup](#9-local-installation--setup)
10. [Automated Testing & Concurrency Verification](#10-automated-testing--concurrency-verification)
11. [Public Deployment Guide (Render + PostgreSQL)](#11-public-deployment-guide-render--postgresql)
12. [College Project Review & Viva FAQ](#12-college-project-review--viva-faq)

---

## 1. Project Overview & Key Objectives

In high-density urban mobility environments, thousands of drivers and navigation systems concurrently compete for limited parking spaces. Naive web applications that rely on client-side button disabling or in-memory Python locks suffer from catastrophic **race conditions**: two drivers query the bay at the same millisecond, both are told the slot is available, and both are granted duplicate active reservations.

### Core Objectives:
- **Zero Double-Bookings:** Enforce strict ACID transaction boundaries and database-level partial unique constraints.
- **Cross-Worker Concurrency Defense:** Use database row-level locking (`SELECT ... FOR UPDATE` in PostgreSQL) and atomic conditional updates (`UPDATE ... WHERE status = 'AVAILABLE'`) that remain 100% collision-free across multiple Gunicorn worker processes.
- **Multi-Zone Urban Operations:** Manage distinct metropolitan zones (Downtown Commercial, Silicon Tech Park, Metro Transit, Airport Aerocity) with independent capacities, amenities, and baseline tariffs.
- **Transparent Surge Pricing:** Dynamically compute congestion tariffs based on live bay occupancy using mathematical formulas and anti-gouging caps.
- **Interactive Visual Analytics:** Provide live data-driven Chart.js visualizations for occupancy, surge trends, and metropolitan load distribution.
- **Protected Administrative Panel:** Complete governance suite with password hashing, session-based authentication, slot maintenance controls, and transaction audit records.

---

## 2. Technology Stack

| Layer | Technologies Used |
|---|---|
| **Backend Framework** | Python 3.11+, Flask 3.1 (Application Factory Pattern) |
| **ORM & Abstraction** | SQLAlchemy 2.0, Flask-SQLAlchemy 3.1 |
| **Database Migrations** | Flask-Migrate 4.1, Alembic |
| **Development Database** | SQLite (WAL mode, `busy_timeout=15000`, Foreign Keys enabled) |
| **Production Database** | PostgreSQL 15+ (with `psycopg2-binary` connection pooling) |
| **Production WSGI Server** | Gunicorn 21+ (`--workers 2 --threads 4`) |
| **Frontend UI** | HTML5, CSS3 (Custom Responsive Deep Navy/Teal Design System), Vanilla JS (ES6+) |
| **Data Visualizations** | Chart.js 4.4 (Stacked Bar, Radar/Tariff, Donut, Utilization Curves) |
| **Automated Testing** | pytest 8.0+ (32 Automated Tests: Concurrency, Pricing, Auth, Rollback) |
| **Deployment Platform** | Render / Railway (with HTTPS SSL & managed PostgreSQL) |

---

## 3. System Architecture & Data Flow

```
+-------------------------------------------------------------------------+
|                              Client Layer                               |
|        Web Browser / Mobile App / REST API Client (Fetch / AJAX)        |
+------------------------------------+------------------------------------+
                                     |
                                     | HTTPS / JSON
                                     v
+------------------------------------+------------------------------------+
|                         Flask Application Layer                         |
|   +-----------------------------------------------------------------+   |
|   | Blueprints: main_bp, booking_bp, analytics_bp, admin_bp, api_bp |   |
|   +-----------------------------------------------------------------+   |
|                                    |                                    |
|   +--------------------------------+--------------------------------+   |
|   | Allocation Engine Service      | Dynamic Surge Pricing Service  |   |
|   | (ACID Transactions & Locks)    | (Occupancy-Elastic Multiplier) |   |
|   +--------------------------------+--------------------------------+   |
+------------------------------------+------------------------------------+
                                     |
                                     | SQLAlchemy ORM
                                     v
+------------------------------------+------------------------------------+
|                         Persistence Engine                              |
|                                                                         |
|  [PostgreSQL (Production)]               [SQLite (Development)]         |
|  - SELECT ... FOR UPDATE (Row Lock)      - Atomic UPDATE WHERE status   |
|  - Partial Unique Index                  - WAL Mode & Busy Timeout 15s  |
|  - Connection Pooling (size=10, ov=20)   - Partial Unique Index         |
+-------------------------------------------------------------------------+
```

### Allocation Pipeline:
1. **User Request:** Client submits driver name, vehicle registration number, and desired slot.
2. **Route Validation:** Flask route sanitizes inputs and validates string lengths.
3. **Transaction Initialization:** Allocation engine begins an atomic database transaction.
4. **Lock Acquisition:**
   - On PostgreSQL: Acquires exclusive row-level lock via `with_for_update()`.
   - On SQLite: Executes conditional atomic status update (`UPDATE ... WHERE id = ? AND status = 'AVAILABLE'`).
5. **Conflict Evaluation:** If `rowcount == 0`, transaction rolls back and returns `HTTP 409 Conflict`.
6. **Tariff Lock-In:** Dynamic surge price is computed from current occupancy and locked into the booking record.
7. **Reservation Insertion:** Creates `Booking` record with `status='ACTIVE'` and reference `BKG-YYYYMMDD-XXXXXXXX`.
8. **Schema Barrier:** Unique partial index `idx_active_slot_booking` physically blocks any secondary concurrent insertion for that slot.
9. **Commit & Response:** Transaction commits cleanly; returns `HTTP 201 Created` with full booking receipt.

---

## 4. Concurrency-Safe Allocation Engine

### Why In-Memory Locks Fail in Production
A common beginner mistake is using Python's `threading.Lock()`. In production, applications run under Gunicorn with **multiple worker OS processes** (e.g. Worker 1, Worker 2). Because operating system processes do **not** share memory, an in-memory lock in Worker 1 is completely invisible to Worker 2. Two concurrent requests arriving at different workers will bypass the lock and double-book the slot.

### Our Multi-Layered Defense:
1. **Database Row-Level Locking (PostgreSQL):**
   ```python
   slot = db.session.query(ParkingSlot).filter(ParkingSlot.id == slot_id).with_for_update().first()
   ```
   Locks the physical database row until the transaction commits or aborts.
2. **Atomic Conditional Status Transitions:**
   ```python
   rows_updated = db.session.query(ParkingSlot).filter(
       ParkingSlot.id == slot_id,
       ParkingSlot.status == 'AVAILABLE'
   ).update({'status': 'OCCUPIED', 'updated_at': now_utc}, synchronize_session='fetch')
   ```
   Guarantees that if two threads execute this statement simultaneously, exactly one sees `rows_updated == 1`. Competing threads see `rows_updated == 0` and are rejected with HTTP 409.
3. **Database Partial Unique Schema Index:**
   ```python
   Index(
       "idx_active_slot_booking",
       "slot_id",
       unique=True,
       postgresql_where=(status == "ACTIVE"),
       sqlite_where=(status == "ACTIVE"),
   )
   ```
   At the physical database engine level, this index strictly forbids more than one row with `status='ACTIVE'` for the same `slot_id`.
4. **Immediate Transaction Rollback:**
   On any conflict, constraint violation, or hardware timeout, `db.session.rollback()` is invoked immediately, guaranteeing zero corrupted or orphaned states.

---

## 5. Dynamic Surge Analytics & Pricing Engine

The pricing engine implements an occupancy-elastic formula that balances urban parking turnover and prevents severe traffic congestion.

### Mathematical Formulation:
$$\text{Occupancy Percentage} = \left(\frac{\text{Occupied Slots}}{\text{Total Configured Slots}}\right) \times 100$$

$$\text{Effective Hourly Tariff} = \text{Base Hourly Rate} \times \text{Surge Multiplier}$$

### Configurable Surge Tiers:
| Tier Name | Occupancy Threshold | Multiplier | Policy Description |
|---|---|---|---|
| **Standard Tier** | $< 50\%$ | **1.0x** | Baseline pricing. High bay availability. |
| **Moderate Surge** | $50\% \text{ to } < 75\%$ | **1.3x** | Elevated demand. Moderate surge to incentivize turnover. |
| **High Demand** | $75\% \text{ to } < 90\%$ | **1.6x** | High pressure. Surge applied to preserve vacant bays. |
| **Peak Surge** | $\ge 90\%$ | **2.0x** | Peak congestion warning. Anti-gouging maximum cap. |

*Guarantees: Clamped between a minimum multiplier of 1.0x and a maximum anti-gouging ceiling of 2.0x. Shared calculation logic ensures the frontend and backend always match.*

---

## 6. Database Schema & Models

```
+-----------------------------------+          +-----------------------------------+
|           parking_zones           |          |           parking_slots           |
+-----------------------------------+          +-----------------------------------+
| id (PK, Integer)                  | 1      * | id (PK, Integer)                  |
| code (String, Unique, Index)      +--------->| slot_number (String, Index)       |
| name (String)                     |          | zone_id (FK -> parking_zones.id)  |
| location (String)                 |          | status (AVAILABLE/OCCUPIED/MAINT) |
| base_hourly_rate (Float)          |          | slot_type (Standard/EV/Access)    |
| total_slots (Integer)             |          | floor_level (String)              |
| amenities (String)                |          | updated_at (DateTime)             |
| is_active (Boolean)               |          +-----------------+-----------------+
| created_at (DateTime)             |                            | 1
+-----------------------------------+                            |
                                                                 | *
+-----------------------------------+          +-----------------+-----------------+
|            admin_users            |          |             bookings              |
+-----------------------------------+          +-----------------------------------+
| id (PK, Integer)                  |          | id (PK, Integer)                  |
| username (String, Unique, Index)  |          | booking_reference (Unique, Index) |
| password_hash (String)            |          | slot_id (FK -> parking_slots.id)  |
| role (String)                     |          | driver_name (String)              |
| created_at (DateTime)             |          | vehicle_number (String, Index)    |
+-----------------------------------+          | contact_number (String)           |
                                               | hourly_rate (Float)               |
                                               | multiplier (Float)                |
                                               | status (ACTIVE/CANCELLED/DONE)    |
                                               | booked_at (DateTime, Index)       |
                                               | cancelled_at (DateTime)           |
                                               +-----------------------------------+
                                               | UNIQUE INDEX on slot_id           |
                                               | WHERE status = 'ACTIVE'           |
                                               +-----------------------------------+
```

---

## 7. Website Pages & Features

### A. Home Page (`/`)
- Hero introduction explaining the concurrency allocation architecture.
- Live city-wide KPI ribbon: Total Capacity, Available Slots, Occupied Slots, Overall City Occupancy %, Active Vehicles.
- Real-time urban zones snapshot cards with live status badges and progress bars.
- 3-pillar engineering explanation (Concurrency Safety, Dynamic Surge Pricing, Instant Release & Audit).

### B. Parking Availability Page (`/availability`)
- Multi-zone grid cards with location, capacity, occupied, available, occupancy %, base rate, surge multiplier, and amenities.
- Real-time filters by Zone and by Demand Tier (Standard, Moderate, High, Peak Surge).
- High-density comparative zone table with direct booking action buttons.

### C. Parking Booking Page (`/book`)
- Zone selector updating the live visual slot bay grid dynamically.
- Interactive color-coded slot bay layout (Green: Available, Red: Occupied, Yellow: Maintenance).
- Slot type badges: EV Charging (`⚡`), Accessible (`♿`), Standard (`🚗`).
- Dual booking modes:
  - **Manual Selection:** Click any available slot on the grid.
  - **Optimal Auto-Allocation:** Enter details and let the system assign the best vacant bay collision-free.
- Dynamic locked-in rate preview with transparent surge breakdown.
- Booking confirmation card with reference ID, printable receipt, and one-click cancellation button.
- Instant booking lookup and cancellation search tool by reference.

### D. Analytics Dashboard (`/analytics`)
- Visualizations built with Chart.js:
  1. **Zone-Wise Capacity & Occupancy:** Stacked bar chart comparing occupied vs available slots per zone.
  2. **Dynamic Tariff by Zone:** Hourly rate (₹/hr) and surge multiplier per zone.
  3. **City-Wide Distribution:** Donut chart of metropolitan bay utilization.
  4. **Urban Mobility Curve:** 24-hour utilization trend across peak rush hours.
- Dynamic refresh button polling live data via `/api/analytics/data`.
- Complete surge pricing formula breakdown and tier explanation cards.

### E. Admin Dashboard (`/admin/dashboard`, `/admin/zones`, `/admin/slots`, `/admin/bookings`)
- Protected by PBKDF2/SHA256 password hashing and session authorization.
- Executive summary metrics: Estimated Revenue, Active Parked Vehicles, Available Capacity, City Occupancy Load.
- Zone Management: Create new parking zones, provision slots automatically, toggle zone active/inactive.
- Slot Management: Filter slots by zone and status, assign maintenance holds, or force clear occupied bays.
- Booking Audit Records: Full transaction ledger with search by vehicle, driver, or booking reference.

### F. About & Architecture Page (`/about`)
- Visual flowchart of the Concurrency-Safe Allocation Engine.
- Surge pricing analytics data pipeline diagram.
- Comparison matrix: Naive in-memory locks vs database row-level locking.
- Academic review guide with examiner viva questions and comprehensive engineering answers.

---

## 8. REST API Endpoints

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `GET` | `/api/health` | Health check for deployment monitoring | `200` |
| `GET` | `/api/status` | System-wide statistics and live occupancy load | `200`, `500` |
| `GET` | `/api/zones` | All active zones with live pricing and slot metrics | `200`, `500` |
| `GET` | `/api/zones/<id>/slots` | Live slots within a specific zone | `200`, `404` |
| `GET` | `/api/pricing` | Pricing rules, tiers, thresholds, and current tariffs | `200`, `500` |
| `POST` | `/api/book` | Concurrency-safe slot booking transaction | `201`, `400`, `404`, `409`, `503` |
| `POST` | `/api/auto-allocate` | Automatic optimal slot allocation | `201`, `400`, `404`, `409` |
| `POST` | `/api/cancel` | Cancel booking reference and release slot | `200`, `400`, `404`, `500` |
| `GET` | `/api/analytics/data` | Structured dataset formatted for Chart.js rendering | `200`, `500` |
| `GET` | `/api/history` | Historical booking transactions audit trail | `200`, `500` |

---

## 9. Local Installation & Setup

### Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/urban-parking-allocator.git
cd urban-parking-allocator
```

### 2. Create and Activate Virtual Environment
**On Windows:**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```
**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the example environment configuration:
```bash
cp .env.example .env
```
*(On Windows: `copy .env.example .env`)*

### 5. Run the Application
```bash
python app.py
```
Open your web browser and navigate to:
```
http://127.0.0.1:5000/
```

### Default Administrator Credentials:
- **URL:** `http://127.0.0.1:5000/admin/login`
- **Username:** `admin`
- **Password:** `Admin@12345`

---

## 10. Automated Testing & Concurrency Verification

The test suite contains **32 automated tests** covering concurrency safety, race condition prevention, dynamic surge calculations, input validation, transaction rollback, and administrator authentication.

### Run All Tests:
```bash
pytest -v
```

### Run Concurrency Stress Tests Specifically:
```bash
pytest tests/test_concurrency.py -v -s
```

### Test Suite Summary:
```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1
collected 32 items

tests/test_admin.py::TestAdminAuthentication::test_unauthorized_dashboard_redirects_to_login PASSED [  3%]
tests/test_admin.py::TestAdminAuthentication::test_admin_login_invalid_password PASSED [  6%]
tests/test_admin.py::TestAdminAuthentication::test_admin_login_success_and_logout PASSED [  9%]
tests/test_admin.py::TestAdminOperations::test_create_zone PASSED        [ 12%]
tests/test_admin.py::TestAdminOperations::test_toggle_zone_active PASSED [ 15%]
tests/test_admin.py::TestAdminOperations::test_toggle_slot_maintenance PASSED [ 18%]
tests/test_booking.py::TestApplicationEndpoints::test_health_check PASSED [ 21%]
tests/test_booking.py::TestApplicationEndpoints::test_page_renders PASSED [ 25%]
tests/test_booking.py::TestBookingWorkflow::test_book_available_slot_success PASSED [ 28%]
tests/test_booking.py::TestBookingWorkflow::test_reject_booking_occupied_slot PASSED [ 31%]
tests/test_booking.py::TestBookingWorkflow::test_auto_allocate_slot PASSED [ 34%]
tests/test_booking.py::TestBookingWorkflow::test_cancel_active_booking PASSED [ 37%]
tests/test_booking.py::TestBookingWorkflow::test_double_cancellation_rejected PASSED [ 40%]
tests/test_booking.py::TestValidationAndErrors::test_missing_driver_name_rejected PASSED [ 43%]
tests/test_booking.py::TestValidationAndErrors::test_missing_vehicle_number_rejected PASSED [ 46%]
tests/test_booking.py::TestValidationAndErrors::test_nonexistent_slot_rejected PASSED [ 50%]
tests/test_booking.py::TestValidationAndErrors::test_cancel_nonexistent_booking_rejected PASSED [ 53%]
tests/test_concurrency.py::TestConcurrencySafety::test_concurrent_booking_same_slot_race_condition PASSED [ 56%]
tests/test_concurrency.py::TestConcurrencySafety::test_concurrent_booking_different_slots PASSED [ 59%]
tests/test_concurrency.py::TestConcurrencySafety::test_database_integrity_constraint_direct_enforcement PASSED [ 62%]
tests/test_pricing.py::TestPricingCalculations::test_occupancy_boundary_zero_percent PASSED [ 65%]
tests/test_pricing.py::TestPricingCalculations::test_occupancy_boundary_forty_nine_percent PASSED [ 68%]
tests/test_pricing.py::TestPricingCalculations::test_occupancy_boundary_fifty_percent PASSED [ 71%]
tests/test_pricing.py::TestPricingCalculations::test_occupancy_boundary_seventy_four_percent PASSED [ 75%]
tests/test_pricing.py::TestPricingCalculations::test_occupancy_boundary_seventy_five_percent PASSED [ 78%]
tests/test_pricing.py::TestPricingCalculations::test_occupancy_boundary_eighty_nine_percent PASSED [ 81%]
tests/test_pricing.py::TestPricingCalculations::test_occupancy_boundary_ninety_percent PASSED [ 84%]
tests/test_pricing.py::TestPricingCalculations::test_occupancy_boundary_hundred_percent PASSED [ 87%]
tests/test_pricing.py::TestPricingCalculations::test_compute_zone_pricing_standard_tier PASSED [ 90%]
tests/test_pricing.py::TestPricingCalculations::test_compute_zone_pricing_peak_surge PASSED [ 93%]
tests/test_pricing.py::TestPricingCalculations::test_pricing_api_endpoint PASSED [ 96%]
tests/test_rollback.py::TestTransactionRollback::test_allocation_rollback_on_commit_exception PASSED [100%]

============================= 32 passed in 5.49s ==============================
```

---

## 11. Public Deployment Guide (Render + PostgreSQL)

Deploying the application to a public HTTPS URL on [Render.com](https://render.com/) is straightforward and 100% free-tier compatible.

### Step 1: Push Code to GitHub
1. Create a new GitHub repository named `urban-parking-allocator`.
2. Push your project files:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Concurrency-Safe Urban Parking Allocator"
   git branch -M main
   git remote add origin https://github.com/<your-username>/urban-parking-allocator.git
   git push -u origin main
   ```

### Step 2: Create Managed PostgreSQL Database on Render
1. Log in to [dashboard.render.com](https://dashboard.render.com/).
2. Click **New +** &rarr; **PostgreSQL**.
3. Configure:
   - **Name:** `parking-postgres-db`
   - **Database:** `parking_db`
   - **User:** `parking_user`
   - **Plan:** Free
4. Click **Create Database**.
5. Once provisioned, copy the **Internal Database URL** (e.g. `postgres://parking_user:...@dpg-...:5432/parking_db`).

### Step 3: Create Web Service on Render
1. In the Render Dashboard, click **New +** &rarr; **Web Service**.
2. Connect your GitHub repository `urban-parking-allocator`.
3. Configure the service settings:
   - **Name:** `urban-parking-allocator`
   - **Environment:** `Python 3`
   - **Region:** Same region as your database (e.g., Oregon or Frankfurt)
   - **Branch:** `main`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
   - **Plan:** Free

### Step 4: Configure Environment Variables
Under the **Environment Variables** tab of your Render Web Service, add:
- `FLASK_ENV` = `production`
- `FLASK_DEBUG` = `0`
- `SECRET_KEY` = `<any-long-random-string-or-click-generate>`
- `DATABASE_URL` = `<paste-your-postgresql-internal-database-url>`
- `BASE_HOURLY_RATE` = `50.0`

*(Note: If your database URL begins with `postgres://`, our application's `config.py` automatically converts it to `postgresql://` as required by SQLAlchemy 2.0).*

### Step 5: Deploy & Verify Public HTTPS URL
1. Click **Create Web Service** (or **Manual Deploy** &rarr; **Deploy latest commit**).
2. Monitor the **Logs** tab. You should see:
   ```
   ==> Building service...
   ==> Installing dependencies...
   ==> Running 'gunicorn wsgi:app --bind 0.0.0.0:$PORT'
   [INFO] Starting gunicorn 21.2.0
   [INFO] Listening at: http://0.0.0.0:10000
   ```
3. Once the build completes with `Your service is live 🎉`, click the public HTTPS link provided by Render:
   ```
   https://urban-parking-allocator.onrender.com/
   ```
4. Test the health check endpoint:
   ```
   https://urban-parking-allocator.onrender.com/api/health
   ```
   Expected response:
   ```json
   {
     "database_engine": "postgresql",
     "service": "Concurrency-Safe Urban Parking Allocator With Surge Analytics",
     "status": "healthy",
     "version": "2.0.0"
   }
   ```

*Free Tier Note: Render's free web services automatically spin down after 15 minutes of inactivity. When a new request arrives, it may take 30–50 seconds to wake up.*

---

## 12. College Project Review & Viva FAQ

### Q1: What is the primary technical problem this project solves?
**Answer:** It eliminates the **race condition and double-booking anomaly** in concurrent reservation systems. When multiple users or autonomous vehicles simultaneously request the same parking slot, our system guarantees that exactly one transaction succeeds while all competing requests receive a clean HTTP 409 Conflict rejection, with zero database corruption.

### Q2: Why did you not just use Python's `threading.Lock()` or JavaScript button disabling?
**Answer:**
1. **Frontend disabling is cosmetic:** It can be bypassed via duplicate tabs, network latency, curl commands, or mobile clients.
2. **In-memory Python locks fail in production:** In multi-process WSGI servers like Gunicorn, each worker process runs in an isolated OS address space. A Python lock in Worker 1 cannot synchronize Worker 2.
3. **Database-level synchronization is mandatory:** Synchronization must occur at the persistence layer using database transactions, row-level locks, and schema unique constraints.

### Q3: How does the system handle SQLite vs PostgreSQL?
**Answer:**
- **SQLite (Local Dev):** Configured with WAL (Write-Ahead Logging) mode and atomic conditional updates (`UPDATE ... WHERE id = ? AND status = 'AVAILABLE'`). SQLite serializes writes at the file level while allowing concurrent reads.
- **PostgreSQL (Production):** The allocation engine dynamically detects PostgreSQL and applies row-level locking via `with_for_update()`.
- **Both Databases:** Enforce the identical partial unique constraint `idx_active_slot_booking` at the schema level.

### Q4: How is the surge price calculated?
**Answer:**
$$\text{Occupancy} = \left(\frac{\text{Occupied Slots}}{\text{Total Slots}}\right) \times 100$$
Based on documented thresholds:
- $<50\%$: 1.0x (Standard)
- $50\% - 74\%$: 1.3x (Moderate)
- $75\% - 89\%$: 1.6x (High)
- $\ge 90\%$: 2.0x (Peak Surge)

Tariffs are protected by anti-gouging caps (min 1.0x, max 2.0x). The rate computed at the exact instant of reservation is permanently locked into the driver's booking record.

---

## License & Academic Disclaimer
Developed for educational demonstration, final year engineering reviews, and college mini-project presentations. All parking telemetry and simulated demand rates are designated as educational demonstration data.
