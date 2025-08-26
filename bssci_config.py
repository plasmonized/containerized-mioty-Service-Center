LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16017  # Internal container port

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

MQTT_BROKER = "akahlig.selfhost.co"
MQTT_PORT = 1887
MQTT_USERNAME = "bssci"
MQTT_PASSWORD = "test=1234"
BASE_TOPIC = "bssci/"

SENSOR_CONFIG_FILE = "endpoints.json"
STATUS_INTERVAL = 60  # seconds

# HTTP Forwarding Configuration (optional)
HTTP_FORWARD_ENABLED = True
HTTP_FORWARD_URL = "https://mioty-cloud.replit.app"

# Service Center Integration (optional)
SERVICE_CENTER_URL = "https://your-service-center.replit.app"