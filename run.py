"""Development entry point for RobloxForge.

Usage:
    python run.py                 # http://127.0.0.1:5000
    PORT=8000 python run.py       # custom port
    HOST=0.0.0.0 python run.py    # expose on the network

For production use a real WSGI server, e.g.:
    pip install waitress
    waitress-serve --host 0.0.0.0 --port 5000 run:app
"""

from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") not in ("0", "false", "False")

    print(f"\n  RobloxForge running on http://{host}:{port}\n")
    app.run(host=host, port=port, debug=debug, threaded=True)
