import logging
import threading
import time
import sys
import os

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging for the application"""

    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/bssci.log'),
            logging.StreamHandler()
        ]
    )


def run_web_ui():
    """Run the Flask web UI"""
    try:
        from web_ui import app
        app.run(host='0.0.0.0', port=5000, debug=False,
                use_reloader=False)
    except Exception as e:
        logger.error(f"Error starting web UI: {e}")


def run_bssci_service():
    """Run the main BSSCI service"""
    try:
        from main import run_bssci_service as main_service
        main_service()
    except Exception as e:
        logger.error(f"Error starting BSSCI service: {e}")


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