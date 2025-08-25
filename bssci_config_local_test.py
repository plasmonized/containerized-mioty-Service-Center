
"""
BSSCI Configuration for Local Testing (No SSL)
This configuration disables SSL/TLS for local testing purposes.
"""

# Server Configuration
LISTEN_HOST = "0.0.0.0"  # Bind to all interfaces for Replit
LISTEN_PORT = 16017

# SSL/TLS Configuration - DISABLED FOR LOCAL TESTING
USE_SSL = False  # Set to False to disable SSL
CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem" 
CA_FILE = "certs/ca_cert.pem"

# MQTT Configuration - Using test prefix
MQTT_BROKER = "akahlig.selfhost.co"
MQTT_PORT = 1887
MQTT_TOPIC_PREFIX = "test/"  # Use test/ instead of bssci/
MQTT_USERNAME = None
MQTT_PASSWORD = None

# Status Request Interval (seconds)
STATUS_INTERVAL = 60

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
