LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16018

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

MQTT_BROKER = ""
MQTT_PORT = 1887
MQTT_USERNAME = ""
MQTT_PASSWORD = ""
BASE_TOPIC = "bssci/"

SENSOR_CONFIG_FILE = "endpoints.json"
STATUS_INTERVAL = 30  # seconds
DEDUPLICATION_DELAY = 2  # seconds to wait for duplicate messages before forwarding

# Auto-detach configuration
AUTO_DETACH_HOURS = 48  # hours of inactivity before auto-detaching sensors
AUTO_DETACH_CHECK_INTERVAL = 3600  # seconds between auto-detach checks (1 hour)
