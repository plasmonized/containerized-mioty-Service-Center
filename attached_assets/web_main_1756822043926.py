"""Web interface main module for mioty BSSCI Service Center."""

import asyncio
import os
from flask import Flask

import bssci_config
from web_ui import create_app


def main() -> None:
    """Main entry point for web interface."""
    app = create_app()

    # Configure Flask app
    app.config["DEBUG"] = bssci_config.WEB_DEBUG
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")

    print(f"Starting web interface on {bssci_config.WEB_HOST}:{bssci_config.WEB_PORT}")

    # Run Flask app
    app.run(
        host=bssci_config.WEB_HOST,
        port=bssci_config.WEB_PORT,
        debug=bssci_config.WEB_DEBUG,
        threaded=True,
    )


if __name__ == "__main__":
    main()
