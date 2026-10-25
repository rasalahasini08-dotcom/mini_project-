"""
app.py - Main entry point for the Concurrency-Safe Urban Parking Allocator.
Runs the Flask application development server.
"""

import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    print(f"Urban Parking Allocator server running on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
