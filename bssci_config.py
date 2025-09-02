LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16018  # Internal container port

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

import os

MQTT_BROKER = os.getenv("MQTT_BROKER", "akahlig.selfhost.co")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1887"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "bssci")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
BASE_TOPIC = os.getenv("BASE_TOPIC", "bssci/")

SENSOR_CONFIG_FILE = "endpoints.json"
STATUS_INTERVAL = 30  # seconds
DEDUPLICATION_DELAY = 2  # seconds to wait for duplicate messages before forwarding
AUTO_DETACH_HOURS = 48  # hours after which inactive sensors are auto-detached