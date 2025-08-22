import os

LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
# Use port 5000 for Replit Deployments, fallback to 16017 for local/Docker
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "5000" if os.getenv("REPL_DEPLOYMENT") else "16017"))

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

MQTT_BROKER = os.getenv("MQTT_BROKER", "akahlig.selfhost.co")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1887"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "bssci")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "test=1234")
BASE_TOPIC = "bssci/"

# Ensure persistent storage for Docker deployments
if os.path.exists("/app/data"):
    SENSOR_CONFIG_FILE = "/app/data/endpoints.json"
else:
    SENSOR_CONFIG_FILE = "endpoints.json"

STATUS_INTERVAL = int(os.getenv("STATUS_INTERVAL", "60"))  # seconds
