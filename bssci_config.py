"""Configuration settings for mioty BSSCI Service Center."""

import os
from typing import Optional

# TLS Server Configuration
LISTEN_HOST: str = "0.0.0.0"
LISTEN_PORT: int = 8000

# SSL/TLS Certificate Configuration
CERT_FILE: str = "certs/service_center_cert.pem"
KEY_FILE: str = "certs/service_center_key.pem"
CA_FILE: str = "certs/ca_cert.pem"

# MQTT Configuration
MQTT_BROKER: str = "akahlig.selfhost.co"
MQTT_PORT: int = 1887
MQTT_USERNAME: Optional[str] = "Hasso"
MQTT_PASSWORD: Optional[str] = "tesT=1234"
BASE_TOPIC: str = "bssci/"

# Application Configuration
SENSOR_CONFIG_FILE: str = "endpoints.json"
STATUS_INTERVAL: int = 300  # seconds
DEDUPLICATION_DELAY: float = 2  # seconds

# Web Interface Configuration
WEB_HOST: str = "0.0.0.0"
WEB_PORT: int = 5000
WEB_DEBUG: bool = False

# Auto-detach Configuration
AUTO_DETACH_ENABLED: bool = True
AUTO_DETACH_TIMEOUT: int = 86400  # seconds

# Logging Configuration
LOG_LEVEL: str = "INFO"
LOG_FILE: Optional[str] = None
