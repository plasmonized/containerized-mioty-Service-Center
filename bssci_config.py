LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16018  # Internal container port

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

MQTT_BROKER = "akahlig.selfhost.co"
MQTT_PORT = 1887
MQTT_USERNAME = "bssci"
MQTT_PASSWORD = "test=1234"
BASE_TOPIC = "bssci/"

SENSOR_CONFIG_FILE = "endpoints.json"
# Status request interval (in seconds)
STATUS_INTERVAL = 30

# Message deduplication settings
MESSAGE_DEDUPLICATION_DELAY = 2.0  # Wait time in seconds for duplicate messages