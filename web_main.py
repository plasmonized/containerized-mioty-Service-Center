
import asyncio
import logging
import threading
import time
from web_ui import app
from main import main as bssci_main

# Configure logging with timezone
from datetime import datetime, timezone, timedelta

class TimezoneFormatter(logging.Formatter):
    def __init__(self, fmt, datefmt=None):
        super().__init__(fmt, datefmt)
        # Set timezone to UTC+2 (Central European Time)
        self.timezone = timezone(timedelta(hours=2))

    def formatTime(self, record, datefmt=None):
        # Convert UTC timestamp to local timezone
        utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
        local_time = utc_time.astimezone(self.timezone)
        if datefmt:
            return local_time.strftime(datefmt)
        else:
            return local_time.strftime('%Y-%m-%d %H:%M:%S')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Apply timezone formatter to all handlers
timezone_formatter = TimezoneFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    '%Y-%m-%d %H:%M:%S'
)
for handler in logging.root.handlers:
    handler.setFormatter(timezone_formatter)

logger = logging.getLogger(__name__)

# Global reference for TLS server instance
tls_server_instance = None

def run_web_ui():
    """Run the Flask web UI in a separate thread"""
    logger.info("Starting Web UI on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def run_bssci_service():
    """Run the BSSCI service"""
    logger.info("Starting BSSCI Service")
    asyncio.run(bssci_main())

def get_tls_server():
    """Get the TLS server instance"""
    try:
        import main
        return getattr(main, 'tls_server_instance', None)
    except Exception as e:
        print(f"Error getting TLS server: {e}")
        return None

if __name__ == "__main__":
    logger.info("Starting BSSCI Service Center with Web UI")
    
    # Start web UI in a separate thread
    web_thread = threading.Thread(target=run_web_ui, daemon=True)
    web_thread.start()
    
    # Give web UI time to start
    time.sleep(2)
    logger.info("Web UI available at http://localhost:5000")
    
    # Run BSSCI service in main thread
    try:
        run_bssci_service()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
