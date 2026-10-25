import os
from datetime import datetime, timedelta
from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine
from flask_migrate import Migrate
from config import config_by_name
from app.models import db, AdminUser, ParkingZone, ParkingSlot, Booking

migrate = Migrate()


def configure_sqlite_pragmas():
    """Configure SQLite for WAL mode, busy timeout, and foreign key constraints."""
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        # Only apply PRAGMAs to SQLite connections
        if type(dbapi_connection).__module__ == "sqlite3":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA busy_timeout = 15000;")
            cursor.close()


def seed_initial_data():
    """
    Idempotent database seeder.
    Populates administrator credentials, urban parking zones, slots,
    and realistic demonstration bookings without duplicating existing records.
    """
    # 1. Seed Default Administrator Account
    admin_user = AdminUser.query.filter_by(username="admin").first()
    if not admin_user:
        admin = AdminUser(username="admin", role="admin")
        admin.set_password("Admin@12345")
        db.session.add(admin)

    # 2. Seed Realistic Urban Parking Zones
    if ParkingZone.query.count() == 0:
        zones_data = [
            {
                "code": "ZONE-A",
                "name": "Central Downtown Hub",
                "location": "5th Avenue & Commercial St, Financial District",
                "base_hourly_rate": 60.0,
                "total_slots": 12,
                "amenities": "Covered, 24/7 CCTV, Fast EV Chargers, Elevator Access",
                "description": "High-demand business center hub adjacent to corporate towers and retail malls."
            },
            {
                "code": "ZONE-B",
                "name": "Silicon Tech Park Bay",
                "location": "Innovation Expressway, Cyber Gateway",
                "base_hourly_rate": 50.0,
                "total_slots": 10,
                "amenities": "Automated Barrier Gate, EV Charging Station, Security Patrol",
                "description": "Dedicated corporate parking bay serving engineering campuses and tech incubators."
            },
            {
                "code": "ZONE-C",
                "name": "Metro Rail Transit Interchange",
                "location": "Terminal Concourse Station, North Exit",
                "base_hourly_rate": 40.0,
                "total_slots": 12,
                "amenities": "Transit Linked, Covered Walkway, Bicycle Sharing Dock",
                "description": "Park-and-ride facility connecting suburban commuters to rapid mass transit lines."
            },
            {
                "code": "ZONE-D",
                "name": "Airport Aerocity Transit",
                "location": "Aerocity Ring Road, Terminal 3 Approach",
                "base_hourly_rate": 80.0,
                "total_slots": 8,
                "amenities": "Valet Assistance, Luggage Bays, 24/7 Armed Security",
                "description": "Premium short-stay parking bay directly serving airport terminals and transit lounges."
            }
        ]

        created_zones = []
        for zd in zones_data:
            zone = ParkingZone(
                code=zd["code"],
                name=zd["name"],
                location=zd["location"],
                base_hourly_rate=zd["base_hourly_rate"],
                total_slots=zd["total_slots"],
                amenities=zd["amenities"],
                description=zd["description"],
                is_active=True
            )
            db.session.add(zone)
            created_zones.append(zone)

        db.session.flush()

        # 3. Create Slots for Each Zone
        for zone in created_zones:
            prefix = zone.code.replace("ZONE-", "")
            for i in range(1, zone.total_slots + 1):
                slot_type = "EV Charging" if i == 1 else ("Accessible" if i == 2 else "Standard")
                slot = ParkingSlot(
                    slot_number=f"{prefix}-{i:02d}",
                    zone_id=zone.id,
                    status="AVAILABLE",
                    slot_type=slot_type,
                    floor_level="Level 1"
                )
                db.session.add(slot)

        db.session.flush()

        # 4. Populate Demonstration Bookings (to showcase surge tiers and analytics)
        # Zone A (Downtown): 6 occupied out of 12 (50% -> Moderate Surge)
        zone_a = ParkingZone.query.filter_by(code="ZONE-A").first()
        if zone_a:
            slots_a = zone_a.slots.order_by(ParkingSlot.slot_number.asc()).limit(6).all()
            demo_drivers = [
                ("Rohan Sharma", "KA-01-AB-1234", 1.3, 78.0),
                ("Ananya Iyer", "KA-05-MM-5678", 1.3, 78.0),
                ("Vikramaditya Roy", "DL-03-CC-9012", 1.3, 78.0),
                ("Sneha Kulkarni", "MH-12-PQ-3456", 1.3, 78.0),
                ("Karthik Nair", "TN-07-ZZ-7890", 1.3, 78.0),
                ("Pooja Verma", "HR-26-EE-2345", 1.3, 78.0),
            ]
            for idx, slot in enumerate(slots_a):
                driver, vehicle, mult, rate = demo_drivers[idx]
                slot.status = "OCCUPIED"
                bkg = Booking(
                    booking_reference=f"BKG-DEMO-{idx + 1:04d}",
                    slot_id=slot.id,
                    driver_name=driver,
                    vehicle_number=vehicle,
                    hourly_rate=rate,
                    multiplier=mult,
                    status="ACTIVE",
                    booked_at=datetime.utcnow() - timedelta(minutes=25 * (idx + 1))
                )
                db.session.add(bkg)

        # Zone B (Tech Bay): 8 occupied out of 10 (80% -> High Demand)
        zone_b = ParkingZone.query.filter_by(code="ZONE-B").first()
        if zone_b:
            slots_b = zone_b.slots.order_by(ParkingSlot.slot_number.asc()).limit(8).all()
            demo_tech_drivers = [
                ("Amitav Sen", "KA-51-MD-1122", 1.6, 80.0),
                ("Divya Menon", "KA-04-NX-3344", 1.6, 80.0),
                ("Rahul Dravid", "KA-01-RD-1973", 1.6, 80.0),
                ("Tanvi Deshmukh", "MH-14-BT-5566", 1.6, 80.0),
                ("Farhan Akhtar", "MH-02-FA-7788", 1.6, 80.0),
                ("Meera Nambiar", "KL-07-MN-9900", 1.6, 80.0),
                ("Siddharth Rao", "AP-09-SR-2233", 1.6, 80.0),
                ("Neha Singhal", "UP-16-NS-4455", 1.6, 80.0),
            ]
            for idx, slot in enumerate(slots_b):
                driver, vehicle, mult, rate = demo_tech_drivers[idx]
                slot.status = "OCCUPIED"
                bkg = Booking(
                    booking_reference=f"BKG-TECH-{idx + 1:04d}",
                    slot_id=slot.id,
                    driver_name=driver,
                    vehicle_number=vehicle,
                    hourly_rate=rate,
                    multiplier=mult,
                    status="ACTIVE",
                    booked_at=datetime.utcnow() - timedelta(minutes=15 * (idx + 1))
                )
                db.session.add(bkg)

        # Zone C (Metro): 3 occupied out of 12 (25% -> Standard Base Rate)
        zone_c = ParkingZone.query.filter_by(code="ZONE-C").first()
        if zone_c:
            slots_c = zone_c.slots.order_by(ParkingSlot.slot_number.asc()).limit(3).all()
            for idx, slot in enumerate(slots_c):
                slot.status = "OCCUPIED"
                bkg = Booking(
                    booking_reference=f"BKG-METRO-{idx + 1:04d}",
                    slot_id=slot.id,
                    driver_name=f"Metro Commuter {idx + 1}",
                    vehicle_number=f"DL-01-MC-{1000 + idx}",
                    hourly_rate=40.0,
                    multiplier=1.0,
                    status="ACTIVE",
                    booked_at=datetime.utcnow() - timedelta(minutes=40 * (idx + 1))
                )
                db.session.add(bkg)

        # Zone D (Airport): 2 occupied out of 8 (25% -> Standard Base Rate)
        zone_d = ParkingZone.query.filter_by(code="ZONE-D").first()
        if zone_d:
            slots_d = zone_d.slots.order_by(ParkingSlot.slot_number.asc()).limit(2).all()
            for idx, slot in enumerate(slots_d):
                slot.status = "OCCUPIED"
                bkg = Booking(
                    booking_reference=f"BKG-AERO-{idx + 1:04d}",
                    slot_id=slot.id,
                    driver_name=f"Transit Traveler {idx + 1}",
                    vehicle_number=f"MH-01-TR-{2000 + idx}",
                    hourly_rate=80.0,
                    multiplier=1.0,
                    status="ACTIVE",
                    booked_at=datetime.utcnow() - timedelta(minutes=60 * (idx + 1))
                )
                db.session.add(bkg)

    db.session.commit()


def create_app(config_name: str = None, test_config: dict = None) -> Flask:
    """Application factory for the Concurrency-Safe Urban Parking Allocator."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    if test_config:
        app.config.from_object(config_by_name["testing"])
        app.config.update(test_config)
    else:
        env_mode = config_name or os.environ.get("FLASK_ENV", "development").lower()
        app.config.from_object(config_by_name.get(env_mode, config_by_name["development"]))

    # Setup database & migrations
    configure_sqlite_pragmas()
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from app.routes.main_routes import main_bp
    from app.routes.booking_routes import booking_bp
    from app.routes.analytics_routes import analytics_bp
    from app.routes.admin_routes import admin_bp
    from app.routes.api_routes import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # Auto-initialize database tables and demo seed
    with app.app_context():
        db.create_all()
        # Seed demo data only if not in testing mode with empty custom data
        if not app.config.get("TESTING_NO_SEED", False):
            seed_initial_data()

    return app
