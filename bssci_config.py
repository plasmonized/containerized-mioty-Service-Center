
import os
from pathlib import Path

# Load environment variables from .env file
def load_env_file():
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value

# Load .env file if it exists
load_env_file()

# Server configuration
LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "16018"))

# Certificate configuration
CERT_FILE = os.getenv("CERT_FILE", "certs/service_center_cert.pem")
KEY_FILE = os.getenv("KEY_FILE", "certs/service_center_key.pem")
CA_FILE = os.getenv("CA_FILE", "certs/ca_cert.pem")

# MQTT configuration with environment variable support
MQTT_BROKER = os.getenv("MQTT_BROKER", "")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1887"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
BASE_TOPIC = os.getenv("BASE_TOPIC", "bssci/")

# File and timing configuration (regular settings, not secrets)
SENSOR_CONFIG_FILE = "endpoints.json"
STATUS_INTERVAL = 30
DEDUPLICATION_DELAY = 2

# Auto-detach configuration (regular settings, not secrets)
AUTO_DETACH_HOURS = 48
AUTO_DETACH_CHECK_INTERVAL = 3600
