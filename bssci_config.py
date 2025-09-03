LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16018  # Internal container port

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

import os

MQTT_BROKER = os.getenv("MQTT_BROKER", "your-mqtt-broker.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "bssci")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
BASE_TOPIC = os.getenv("BASE_TOPIC", "bssci/")

SENSOR_CONFIG_FILE = "endpoints.json"
STATUS_INTERVAL = 30  # seconds
DEDUPLICATION_DELAY = 2  # seconds to wait for duplicate messages before forwarding

# Auto-detach Configuration
AUTO_DETACH_ENABLED = True
AUTO_DETACH_TIMEOUT = 72 * 3600  # 72 hours in seconds (3 days)
AUTO_DETACH_WARNING_TIMEOUT = 36 * 3600  # 36 hours in seconds (1.5 days)
AUTO_DETACH_CHECK_INTERVAL = 3600  # Check every hour