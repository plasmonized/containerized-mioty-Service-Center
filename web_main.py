
import asyncio
import logging
import threading
import time
from web_ui import app
from main import main as bssci_main

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_web_ui():
    """Run the Flask web UI in a separate thread"""
    logger.info("Starting Web UI on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def run_bssci_service():
    """Run the BSSCI service"""
    logger.info("Starting BSSCI Service")
    asyncio.run(bssci_main())

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
