from app.routes.main_routes import main_bp
from app.routes.booking_routes import booking_bp
from app.routes.analytics_routes import analytics_bp
from app.routes.admin_routes import admin_bp
from app.routes.api_routes import api_bp

__all__ = ["main_bp", "booking_bp", "analytics_bp", "admin_bp", "api_bp"]
