import pytest
from app.models import db, AdminUser, ParkingZone, ParkingSlot, Booking


class TestAdminAuthentication:
    """Verify administrator route protection, login, and session authorization."""

    def test_unauthorized_dashboard_redirects_to_login(self, client):
        for path in ["/admin/dashboard", "/admin/zones", "/admin/slots", "/admin/bookings"]:
            res = client.get(path)
            assert res.status_code == 302
            assert "/admin/login" in res.headers["Location"]

    def test_admin_login_invalid_password(self, client):
        res = client.post("/admin/login", data={
            "username": "admin",
            "password": "WrongPassword!"
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"Invalid administrator credentials" in res.data

    def test_admin_login_success_and_logout(self, client):
        # Successful login
        res = client.post("/admin/login", data={
            "username": "admin",
            "password": "Admin@12345"
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"Administrator Control Center" in res.data

        # Access protected page while logged in
        dash_res = client.get("/admin/dashboard")
        assert dash_res.status_code == 200

        # Logout
        logout_res = client.get("/admin/logout", follow_redirects=True)
        assert logout_res.status_code == 200
        assert b"logged out securely" in logout_res.data

        # Verify no longer authorized
        post_logout_res = client.get("/admin/dashboard")
        assert post_logout_res.status_code == 302


class TestAdminOperations:
    """Verify administrator zone management, slot controls, and booking audit operations."""

    def login_admin(self, client):
        return client.post("/admin/login", data={
            "username": "admin",
            "password": "Admin@12345"
        }, follow_redirects=True)

    def test_create_zone(self, app, client):
        self.login_admin(client)

        payload = {
            "action": "create",
            "code": "ZONE-NEW",
            "name": "New Test Bay",
            "location": "North Sector Highway",
            "base_hourly_rate": "55.0",
            "total_slots": "6",
            "amenities": "Covered, Security"
        }
        res = client.post("/admin/zones", data=payload, follow_redirects=True)
        assert res.status_code == 200
        assert b"ZONE-NEW" in res.data

        with app.app_context():
            zone = ParkingZone.query.filter_by(code="ZONE-NEW").first()
            assert zone is not None
            assert zone.slots.count() == 6

    def test_toggle_zone_active(self, app, client):
        self.login_admin(client)

        with app.app_context():
            zone = ParkingZone.query.filter_by(code="ZONE-A").first()
            assert zone is not None
            zone_id = zone.id
            initial_state = zone.is_active

        res = client.post("/admin/zones", data={
            "action": "toggle_active",
            "zone_id": zone_id
        }, follow_redirects=True)
        assert res.status_code == 200

        with app.app_context():
            updated_zone = db.session.get(ParkingZone, zone_id)
            assert updated_zone.is_active != initial_state

    def test_toggle_slot_maintenance(self, app, client):
        self.login_admin(client)

        with app.app_context():
            avail_slot = ParkingSlot.query.filter_by(status="AVAILABLE").first()
            assert avail_slot is not None
            slot_id = avail_slot.id

        # Put on maintenance
        res = client.post("/admin/slots", data={
            "slot_id": slot_id,
            "status": "MAINTENANCE"
        }, follow_redirects=True)
        assert res.status_code == 200

        with app.app_context():
            slot = db.session.get(ParkingSlot, slot_id)
            assert slot.status == "MAINTENANCE"
