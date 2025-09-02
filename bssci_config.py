"""Configuration settings for mioty BSSCI Service Center."""

import os
from typing import Optional

# TLS Server Configuration
LISTEN_HOST: str = "0.0.0.0"
LISTEN_PORT: int = 8000

# SSL/TLS Certificate Configuration
CERT_FILE: str = os.getenv("CERT_FILE", "certs/service_center_cert.pem")
KEY_FILE: str = os.getenv("KEY_FILE", "certs/service_center_key.pem")
CA_FILE: str = os.getenv("CA_FILE", "certs/ca_cert.pem")

# MQTT Configuration
MQTT_BROKER: str = "akahlig.selfhost.co"
MQTT_PORT: int = 1887
MQTT_USERNAME: Optional[str] = "Hasso"
MQTT_PASSWORD: Optional[str] = "tesT=1234"
BASE_TOPIC: str = "bssci/"

# Application Configuration
SENSOR_CONFIG_FILE: str = os.getenv("SENSOR_CONFIG_FILE", "endpoints.json")
STATUS_INTERVAL: int = int(os.getenv("STATUS_INTERVAL", "300"))  # seconds
DEDUPLICATION_DELAY: float = float(os.getenv("DEDUPLICATION_DELAY", "2.0"))  # seconds

# Web Interface Configuration
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.getenv("WEB_PORT", "5000"))
WEB_DEBUG: bool = os.getenv("WEB_DEBUG", "false").lower() == "true"

# Auto-detach Configuration
AUTO_DETACH_ENABLED: bool = os.getenv("AUTO_DETACH_ENABLED", "true").lower() == "true"
AUTO_DETACH_TIMEOUT: int = int(os.getenv("AUTO_DETACH_TIMEOUT", "86400"))  # seconds
AUTO_DETACH_HOURS: int = int(os.getenv("AUTO_DETACH_HOURS", "24"))  # hours
AUTO_DETACH_CHECK_INTERVAL: int = int(os.getenv("AUTO_DETACH_CHECK_INTERVAL", "3600"))  # seconds

# Logging Configuration
LOG_LEVEL: str = "INFO"
LOG_FILE: Optional[str] = None
