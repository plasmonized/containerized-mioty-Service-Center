"""Configuration settings for mioty BSSCI Service Center."""

import os
from typing import Optional

# TLS Server Configuration
LISTEN_HOST: str = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT: int = int(os.getenv("LISTEN_PORT", "8000"))

# SSL/TLS Certificate Configuration
CERT_FILE: str = os.getenv("CERT_FILE", "certificates/server.crt")
KEY_FILE: str = os.getenv("KEY_FILE", "certificates/server.key")
CA_FILE: str = os.getenv("CA_FILE", "certificates/ca.crt")

# MQTT Configuration
MQTT_BROKER: str = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME: Optional[str] = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD: Optional[str] = os.getenv("MQTT_PASSWORD")
BASE_TOPIC: str = os.getenv("BASE_TOPIC", "mioty")

# Application Configuration
SENSOR_CONFIG_FILE: str = os.getenv("SENSOR_CONFIG_FILE", "endpoints.json")
STATUS_INTERVAL: int = int(os.getenv("STATUS_INTERVAL", "300"))  # 5 minutes
DEDUPLICATION_DELAY: float = float(os.getenv("DEDUPLICATION_DELAY", "2.0"))  # 2 seconds

# Web Interface Configuration
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.getenv("WEB_PORT", "5000"))
WEB_DEBUG: bool = os.getenv("WEB_DEBUG", "false").lower() == "true"

# Auto-detach Configuration
AUTO_DETACH_ENABLED: bool = os.getenv("AUTO_DETACH_ENABLED", "true").lower() == "true"
AUTO_DETACH_TIMEOUT: int = int(os.getenv("AUTO_DETACH_TIMEOUT", "86400"))  # 24 hours

# Logging Configuration
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE: Optional[str] = os.getenv("LOG_FILE")
