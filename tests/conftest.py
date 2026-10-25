import os
import tempfile
import pytest
from app import create_app
from app.models import db, AdminUser, ParkingZone, ParkingSlot, Booking


@pytest.fixture
def app():
    """Create an isolated test application with temporary SQLite database file."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "DATABASE_PATH": db_path,
        "SECRET_KEY": "test-secret-key-2026",
        "WTF_CSRF_ENABLED": False,
        "TESTING_NO_SEED": False,
    }

    app = create_app(test_config=test_config)

    yield app

    # Teardown
    for ext in ["", "-wal", "-shm"]:
        p = db_path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """CLI test runner."""
    return app.test_cli_runner()
