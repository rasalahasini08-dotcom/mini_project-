from datetime import datetime
from typing import Dict, Any
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class AdminUser(db.Model):
    """Administrator account model for secure backend dashboard access."""
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), default="admin", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password: str) -> None:
        """Hash and store the administrator password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify the password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(db.Model):
    """Registered driver / commuter account model for personal booking management."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=True)
    contact_number = db.Column(db.String(25), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    bookings = db.relationship("Booking", back_populates="user", lazy="dynamic")

    def set_password(self, password: str) -> None:
        """Hash and store user password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify user password."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "vehicle_number": self.vehicle_number,
            "contact_number": self.contact_number,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ParkingZone(db.Model):
    """
    Parking Zone model representing an urban parking facility or section.
    Holds location information, total capacity, base rate, and amenities.
    """
    __tablename__ = "parking_zones"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)  # e.g., 'ZONE-A'
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    base_hourly_rate = db.Column(db.Float, nullable=False, default=50.0)
    total_slots = db.Column(db.Integer, nullable=False, default=10)
    description = db.Column(db.Text, nullable=True)
    amenities = db.Column(db.String(200), default="Covered, 24/7 Security", nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    slots = db.relationship("ParkingSlot", back_populates="zone", cascade="all, delete-orphan", lazy="dynamic")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "location": self.location,
            "base_hourly_rate": self.base_hourly_rate,
            "total_slots": self.total_slots,
            "description": self.description,
            "amenities": self.amenities,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ParkingSlot(db.Model):
    """
    Individual parking slot within a zone.
    Tracked with atomic state: 'AVAILABLE', 'OCCUPIED', or 'MAINTENANCE'.
    """
    __tablename__ = "parking_slots"

    id = db.Column(db.Integer, primary_key=True)
    slot_number = db.Column(db.String(20), nullable=False, index=True)  # e.g., 'A-01'
    zone_id = db.Column(db.Integer, db.ForeignKey("parking_zones.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="AVAILABLE")  # AVAILABLE, OCCUPIED, MAINTENANCE
    slot_type = db.Column(db.String(30), default="Standard", nullable=False)  # Standard, EV Charging, Compact, Accessible
    floor_level = db.Column(db.String(20), default="Level 1", nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    zone = db.relationship("ParkingZone", back_populates="slots")
    bookings = db.relationship("Booking", back_populates="slot", cascade="all, delete-orphan", lazy="dynamic")

    __table_args__ = (
        UniqueConstraint("zone_id", "slot_number", name="uq_zone_slot_number"),
    )

    def to_dict(self, include_active_booking: bool = True) -> Dict[str, Any]:
        active_bkg = None
        if include_active_booking and self.status == "OCCUPIED":
            active = self.bookings.filter_by(status="ACTIVE").first()
            if active:
                active_bkg = active.to_dict()

        return {
            "id": self.id,
            "slot_number": self.slot_number,
            "zone_id": self.zone_id,
            "zone_code": self.zone.code if self.zone else None,
            "zone_name": self.zone.name if self.zone else None,
            "status": self.status,
            "is_available": self.status == "AVAILABLE",
            "slot_type": self.slot_type,
            "floor_level": self.floor_level,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "active_booking": active_bkg,
        }


class Booking(db.Model):
    """
    Reservation record for a parking slot.
    Statuses: 'ACTIVE', 'CANCELLED', 'COMPLETED'.
    
    Hard Concurrency Constraint:
    The partial unique index 'idx_active_slot_booking' ensures that at no point
    can the database store multiple ACTIVE bookings for the same slot_id.
    """
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    booking_reference = db.Column(db.String(36), unique=True, nullable=False, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("parking_slots.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    driver_name = db.Column(db.String(100), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=False, index=True)
    contact_number = db.Column(db.String(25), nullable=True)
    hourly_rate = db.Column(db.Float, nullable=False)
    multiplier = db.Column(db.Float, nullable=False, default=1.0)
    status = db.Column(db.String(20), nullable=False, default="ACTIVE")  # ACTIVE, CANCELLED, COMPLETED
    booked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    slot = db.relationship("ParkingSlot", back_populates="bookings")
    user = db.relationship("User", back_populates="bookings")

    __table_args__ = (
        Index(
            "idx_active_slot_booking",
            "slot_id",
            unique=True,
            postgresql_where=(status == "ACTIVE"),
            sqlite_where=(status == "ACTIVE"),
        ),
        Index("idx_bookings_booked_at_desc", booked_at.desc()),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "booking_reference": self.booking_reference,
            "slot_id": self.slot_id,
            "user_id": self.user_id,
            "slot_number": self.slot.slot_number if self.slot else None,
            "zone_code": self.slot.zone.code if self.slot and self.slot.zone else None,
            "zone_name": self.slot.zone.name if self.slot and self.slot.zone else None,
            "driver_name": self.driver_name,
            "vehicle_number": self.vehicle_number,
            "contact_number": self.contact_number,
            "hourly_rate": self.hourly_rate,
            "multiplier": self.multiplier,
            "status": self.status,
            "booked_at": self.booked_at.isoformat() if self.booked_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
        }
