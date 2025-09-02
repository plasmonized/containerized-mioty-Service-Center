"""Web UI for mioty BSSCI Service Center management."""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

import bssci_config

logger = logging.getLogger(__name__)

# Global variables for log storage and configuration
log_entries: List[Dict[str, Any]] = []
max_log_entries = 1000


class WebUILogHandler(logging.Handler):
    """Custom log handler to capture all logs with timezone support."""

    def __init__(self) -> None:
        """Initialize the log handler."""
        super().__init__()
        # Set timezone to UTC+2 (Central European Time)
        self.timezone = timezone(timedelta(hours=2))

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record."""
        global log_entries

        # Filter out noisy web request logs to reduce clutter
        if record.name == "werkzeug" and any(
            x in record.getMessage()
            for x in [
                "GET /api/",
                "GET /logs",
                "GET /sensors",
                "GET /config",
                "GET /",
                "GET /static/",
            ]
        ):
            return  # Skip web request logs

        # Convert UTC timestamp to local timezone
        utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
        local_time = utc_time.astimezone(self.timezone)
        current_time = local_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        message = record.getMessage()

        # Check if this exact message was logged in the last second (duplicate detection)
        if log_entries:
            last_entry = log_entries[-1]
            try:
                last_time = datetime.strptime(
                    last_entry["timestamp"], "%Y-%m-%d %H:%M:%S.%f"
                )
                time_diff = abs(
                    (local_time.replace(tzinfo=None) - last_time).total_seconds()
                )

                if (
                    time_diff < 1.0
                    and last_entry["message"] == message
                    and last_entry["logger"] == record.name
                ):
                    return  # Skip duplicate message
            except Exception:
                pass  # If timestamp parsing fails, continue with logging

        log_entry = {
            "timestamp": current_time,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "source": "memory",
        }
        log_entries.append(log_entry)

        # Keep only the last max_log_entries
        if len(log_entries) > max_log_entries:
            log_entries = log_entries[-max_log_entries:]


def create_app() -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "bssci-ui-secret-key")

    # Add our custom handler to the root logger (only once)
    if not any(isinstance(h, WebUILogHandler) for h in logging.getLogger().handlers):
        web_handler = WebUILogHandler()
        logging.getLogger().addHandler(web_handler)
        logging.getLogger().setLevel(logging.DEBUG)

        # Specifically capture important logs
        logging.getLogger("TLSServer").setLevel(logging.DEBUG)
        logging.getLogger("mqtt_interface").setLevel(logging.DEBUG)

    @app.route("/")
    def index() -> str:
        """Main dashboard page."""
        return render_template("index.html")

    @app.route("/sensors")
    def sensors() -> str:
        """Sensor management page."""
        try:
            with open(bssci_config.SENSOR_CONFIG_FILE, "r", encoding="utf-8") as f:
                sensors = json.load(f)
        except Exception:
            sensors = []
        return render_template("sensors.html", sensors=sensors)

    @app.route("/api/sensors", methods=["GET"])
    def get_sensors() -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
        """Get sensor list with status."""
        try:
            # Try to get data from TLS server first (includes registration status)
            try:
                tls_server = get_tls_server()
                if tls_server:
                    tls_server.reload_sensor_config()
                    # Get registration status which already includes preferred paths
                    sensor_status = tls_server.get_sensor_registration_status()
                    return jsonify(sensor_status)
            except Exception as e:
                logger.error(f"Error getting data from TLS server: {e}")

            # Fallback to file only
            with open(bssci_config.SENSOR_CONFIG_FILE, "r", encoding="utf-8") as f:
                sensors = json.load(f)
                # Convert to registration status format
                sensor_status = {}
                for sensor in sensors:
                    eui = sensor["eui"].lower()
                    sensor_status[eui] = {
                        "eui": sensor["eui"],
                        "nwKey": sensor["nwKey"],
                        "shortAddr": sensor["shortAddr"],
                        "bidi": sensor["bidi"],
                        "registered": False,
                        "registration_info": {},
                        "base_stations": [],
                        "total_registrations": 0,
                        "preferredDownlinkPath": sensor.get(
                            "preferredDownlinkPath", None
                        ),
                    }
                return jsonify(sensor_status)
        except Exception as e:
            logger.error(f"Error in get_sensors: {e}")
            return jsonify({})

    @app.route("/api/sensors", methods=["POST"])
    def add_sensor() -> Dict[str, Any]:
        """Add or update a sensor."""
        data = request.json
        try:
            with open(bssci_config.SENSOR_CONFIG_FILE, "r", encoding="utf-8") as f:
                sensors = json.load(f)
        except Exception:
            sensors = []

        # Check if sensor already exists
        for sensor in sensors:
            if sensor["eui"].lower() == data["eui"].lower():
                # Update existing sensor
                sensor.update(data)
                break
        else:
            # Add new sensor
            sensors.append(data)

        try:
            with open(bssci_config.SENSOR_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(sensors, f, indent=4)
            return jsonify({"success": True, "message": "Sensor saved successfully"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/sensors/<eui>", methods=["DELETE"])
    def delete_sensor(eui: str) -> Dict[str, Any]:
        """Delete sensor with automatic detach request."""
        try:
            # First, try to detach the sensor if it's registered
            detach_success = False
            try:
                tls_server = get_tls_server()
                if tls_server:
                    # Check if sensor is registered
                    sensor_status = tls_server.get_sensor_registration_status()
                    eui_key = eui.lower()
                    if (
                        eui_key in sensor_status
                        and sensor_status[eui_key].get("registered", False)
                    ):
                        detach_success = tls_server.detach_sensor(eui)
            except Exception as e:
                logger.warning(f"Failed to detach sensor {eui} during deletion: {e}")

            # Now delete from configuration file
            try:
                with open(bssci_config.SENSOR_CONFIG_FILE, "r", encoding="utf-8") as f:
                    sensors = json.load(f)
            except Exception:
                sensors = []

            sensors = [s for s in sensors if s["eui"].lower() != eui.lower()]

            with open(bssci_config.SENSOR_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(sensors, f, indent=4)

            message = "Sensor deleted successfully"
            if detach_success:
                message += " (detach request sent to base stations)"
            elif detach_success is False:
                message += " (sensor was not registered)"

            return jsonify({"success": True, "message": message})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/sensors/clear", methods=["POST"])
    def clear_all_sensors() -> Dict[str, Any]:
        """Clear all sensor configurations with bulk detach."""
        try:
            # First, detach all registered sensors
            detach_count = 0
            try:
                tls_server = get_tls_server()
                if tls_server:
                    success = tls_server.detach_all_sensors()
                    if success:
                        sensor_status = tls_server.get_sensor_registration_status()
                        detach_count = len(
                            [
                                s
                                for s in sensor_status.values()
                                if s.get("registered", False)
                            ]
                        )
            except Exception as e:
                logger.warning(f"Failed to detach sensors during clear all: {e}")

            # Now clear the configuration file
            with open(bssci_config.SENSOR_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=4)

            # Also clear from TLS server if available
            try:
                tls_server = get_tls_server()
                if tls_server:
                    tls_server.clear_all_sensors()
            except Exception:
                pass  # TLS server not available, that's okay

            message = "All sensors cleared successfully"
            if detach_count > 0:
                message += f" (detach requests sent for {detach_count} registered sensors)"

            return jsonify({"success": True, "message": message})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/sensors/reload", methods=["POST"])
    def reload_sensors() -> Dict[str, Any]:
        """Force reload sensor configuration in TLS server."""
        try:
            tls_server = get_tls_server()
            if tls_server:
                tls_server.reload_sensor_config()
                return jsonify(
                    {"success": True, "message": "Sensor configuration reloaded successfully"}
                )
            else:
                return jsonify({"success": False, "message": "TLS server not available"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/sensors/unregister/<sensor_eui>", methods=["DELETE"])
    def unregister_sensor(sensor_eui: str) -> Dict[str, Any]:
        """Unregister (detach) a specific sensor from all base stations."""
        try:
            tls_server = get_tls_server()
            if tls_server:
                # Send detach requests to all connected base stations
                success = tls_server.detach_sensor(sensor_eui)
                if success:
                    return jsonify(
                        {
                            "success": True,
                            "message": f"Sensor {sensor_eui} detach request sent to base stations",
                        }
                    )
                else:
                    return jsonify(
                        {
                            "success": False,
                            "message": "No connected base stations to send detach request",
                        }
                    )
            else:
                return jsonify({"success": False, "message": "TLS server not available"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/sensors/unregister-all", methods=["POST"])
    def unregister_all_sensors() -> Dict[str, Any]:
        """Unregister all sensors from all base stations."""
        try:
            tls_server = get_tls_server()
            if tls_server:
                success = tls_server.detach_all_sensors()
                return jsonify(
                    {"success": True, "message": "Detach requests sent for all registered sensors"}
                )
            else:
                return jsonify({"success": False, "message": "TLS server not available"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/config")
    def config() -> str:
        """Configuration management page."""
        config_data = {
            "LISTEN_HOST": bssci_config.LISTEN_HOST,
            "LISTEN_PORT": bssci_config.LISTEN_PORT,
            "MQTT_BROKER": bssci_config.MQTT_BROKER,
            "MQTT_PORT": bssci_config.MQTT_PORT,
            "MQTT_USERNAME": bssci_config.MQTT_USERNAME,
            "MQTT_PASSWORD": bssci_config.MQTT_PASSWORD,
            "BASE_TOPIC": bssci_config.BASE_TOPIC,
            "STATUS_INTERVAL": bssci_config.STATUS_INTERVAL,
            "DEDUPLICATION_DELAY": bssci_config.DEDUPLICATION_DELAY,
            "AUTO_DETACH_ENABLED": bssci_config.AUTO_DETACH_ENABLED,
            "AUTO_DETACH_TIMEOUT": bssci_config.AUTO_DETACH_TIMEOUT,
            "AUTO_DETACH_HOURS": getattr(bssci_config, 'AUTO_DETACH_HOURS', 24),
            "AUTO_DETACH_CHECK_INTERVAL": getattr(bssci_config, 'AUTO_DETACH_CHECK_INTERVAL', 3600),
        }
        return render_template("config.html", config=config_data)

    @app.route("/api/config", methods=["POST"])
    def update_config() -> Dict[str, Any]:
        """Update configuration settings."""
        data = request.json
        config_content = f'''"""Configuration settings for mioty BSSCI Service Center."""

import os
from typing import Optional

# TLS Server Configuration
LISTEN_HOST: str = os.getenv("LISTEN_HOST", "{data['LISTEN_HOST']}")
LISTEN_PORT: int = int(os.getenv("LISTEN_PORT", "{data['LISTEN_PORT']}"))

# SSL/TLS Certificate Configuration
CERT_FILE: str = os.getenv("CERT_FILE", "certs/service_center_cert.pem")
KEY_FILE: str = os.getenv("KEY_FILE", "certs/service_center_key.pem")
CA_FILE: str = os.getenv("CA_FILE", "certs/ca_cert.pem")

# MQTT Configuration
MQTT_BROKER: str = os.getenv("MQTT_BROKER", "{data['MQTT_BROKER']}")
MQTT_PORT: int = int(os.getenv("MQTT_PORT", "{data['MQTT_PORT']}"))
MQTT_USERNAME: Optional[str] = os.getenv("MQTT_USERNAME", "{data['MQTT_USERNAME']}")
MQTT_PASSWORD: Optional[str] = os.getenv("MQTT_PASSWORD", "{data['MQTT_PASSWORD']}")
BASE_TOPIC: str = os.getenv("BASE_TOPIC", "{data['BASE_TOPIC']}")

# Application Configuration
SENSOR_CONFIG_FILE: str = os.getenv("SENSOR_CONFIG_FILE", "endpoints.json")
STATUS_INTERVAL: int = int(os.getenv("STATUS_INTERVAL", "{data['STATUS_INTERVAL']}"))  # seconds
DEDUPLICATION_DELAY: float = float(os.getenv("DEDUPLICATION_DELAY", "{data['DEDUPLICATION_DELAY']}"))  # seconds

# Web Interface Configuration
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.getenv("WEB_PORT", "5000"))
WEB_DEBUG: bool = os.getenv("WEB_DEBUG", "false").lower() == "true"

# Auto-detach Configuration
AUTO_DETACH_ENABLED: bool = os.getenv("AUTO_DETACH_ENABLED", "{str(data.get('AUTO_DETACH_ENABLED', True)).lower()}").lower() == "true"
AUTO_DETACH_TIMEOUT: int = int(os.getenv("AUTO_DETACH_TIMEOUT", "{data.get('AUTO_DETACH_TIMEOUT', 86400)}"))  # seconds
AUTO_DETACH_HOURS: int = int(os.getenv("AUTO_DETACH_HOURS", "{data.get('AUTO_DETACH_HOURS', 24)}"))  # hours
AUTO_DETACH_CHECK_INTERVAL: int = int(os.getenv("AUTO_DETACH_CHECK_INTERVAL", "{data.get('AUTO_DETACH_CHECK_INTERVAL', 3600)}"))  # seconds

# Logging Configuration
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Optional[str] = os.getenv("LOG_FILE", None)
'''

        try:
            with open("bssci_config.py", "w", encoding="utf-8") as f:
                f.write(config_content)

            # Add note for container environments
            message = "Configuration updated successfully. Restart required."
            if os.environ.get("CONTAINER") == "1":
                message += " Note: In container environments, config changes are container-local."

            return jsonify({"success": True, "message": message})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/certificates")
    def certificates() -> str:
        """Certificate management page."""
        return render_template("certificates.html")

    @app.route("/logs")
    def logs() -> str:
        """Logs viewing page."""
        return render_template("logs.html")

    @app.route("/api/logs")
    def get_logs() -> Dict[str, Any]:
        """Get filtered logs."""
        global log_entries

        # Get query parameters for filtering
        level_filter = request.args.get("level", "all").upper()
        logger_filter = request.args.get("logger", "all")
        limit = int(request.args.get("limit", 100))

        # Filter logs based on parameters
        filtered_logs = log_entries

        if level_filter != "ALL":
            filtered_logs = [log for log in filtered_logs if log["level"] == level_filter]

        if logger_filter != "all":
            filtered_logs = [
                log for log in filtered_logs if logger_filter.lower() in log["logger"].lower()
            ]

        # Return the most recent logs (up to limit)
        recent_logs = (
            filtered_logs[-limit:] if len(filtered_logs) > limit else filtered_logs
        )

        return jsonify(
            {
                "logs": recent_logs,
                "total_logs": len(log_entries),
                "filtered_logs": len(filtered_logs),
                "source": "memory",
            }
        )

    @app.route("/api/logs/clear", methods=["POST"])
    def clear_logs() -> Dict[str, Any]:
        """Clear all logs."""
        global log_entries
        log_entries = []
        return jsonify({"success": True, "message": "Logs cleared successfully"})

    @app.route("/api/bssci/status")
    def bssci_status() -> Dict[str, Any]:
        """Get BSSCI service status."""
        # Check if TLS server is available in global scope
        tls_server = None
        mqtt_interface = None

        # Try to get server instances from different possible locations
        try:
            import sys
            main_module = sys.modules.get('__main__')
            if main_module:
                tls_server = getattr(main_module, 'tls_server', None)
                mqtt_interface = getattr(main_module, 'mqtt_interface', None)
            
            # Also try the main module directly
            if not tls_server:
                try:
                    import main
                    tls_server = getattr(main, 'tls_server', None)
                    mqtt_interface = getattr(main, 'mqtt_interface', None)
                except ImportError:
                    pass
        except Exception as e:
            logger.error(f"Error accessing server instances: {e}")

        status_data = {
            "service_status": "running" if tls_server else "stopped",
            "tls_server": tls_server.get_server_status() if tls_server else {
                "is_running": False,
                "listen_host": bssci_config.LISTEN_HOST,
                "listen_port": bssci_config.LISTEN_PORT,
                "deduplication_stats": {"total_messages": 0, "duplicate_messages": 0, "published_messages": 0},
                "uptime": "Stopped"
            },
            "base_stations": tls_server.get_base_station_status() if tls_server else {
                "connected_count": 0,
                "connecting_count": 0,
                "total_count": 0,
                "base_stations": []
            },
            "sensors": tls_server.get_sensor_status() if tls_server else {
                "total_sensors": 0,
                "registered_sensors": 0,
                "unregistered_sensors": 0,
                "pending_attach_requests": 0
            },
            "mqtt": {
                "broker": bssci_config.MQTT_BROKER,
                "port": bssci_config.MQTT_PORT,
                "base_topic": bssci_config.BASE_TOPIC,
                "status": "connected" if mqtt_interface and hasattr(mqtt_interface, 'client') else "disconnected"
            },
            "config": {
                "auto_detach_enabled": bssci_config.AUTO_DETACH_ENABLED,
                "auto_detach_hours": bssci_config.AUTO_DETACH_HOURS,
                "status_interval": bssci_config.STATUS_INTERVAL,
                "deduplication_delay": bssci_config.DEDUPLICATION_DELAY
            }
        }
        return jsonify(status_data)

    @app.route("/api/base_stations")
    def get_base_stations() -> Dict[str, Any]:
        """Get status of connected base stations."""
        try:
            tls_server = get_tls_server()

            if tls_server:
                status = tls_server.get_base_station_status()
                return jsonify(status)
            else:
                return jsonify(
                    {
                        "connected": [],
                        "connecting": [],
                        "total_connected": 0,
                        "total_connecting": 0,
                        "error": "TLS server not initialized",
                    }
                )
        except Exception as e:
            return jsonify(
                {
                    "connected": [],
                    "connecting": [],
                    "total_connected": 0,
                    "total_connecting": 0,
                    "error": str(e),
                }
            )

    @app.route("/api/certificates/status")
    def get_certificate_status() -> Dict[str, Any]:
        """Get status of SSL certificates."""
        try:
            cert_files = {
                "ca": "certs/ca_cert.pem",
                "service": "certs/service_center_cert.pem",
                "key": "certs/service_center_key.pem",
            }

            status = {"certificates": {}}

            for cert_type, file_path in cert_files.items():
                if os.path.exists(file_path):
                    status["certificates"][cert_type] = True
                    # Try to get certificate expiry date
                    try:
                        if cert_type != "key":  # Don't try to parse private key as certificate
                            from cryptography import x509
                            from cryptography.hazmat.backends import default_backend

                            with open(file_path, "rb") as f:
                                cert_data = f.read()
                                cert = x509.load_pem_x509_certificate(
                                    cert_data, default_backend()
                                )
                                expiry = cert.not_valid_after
                                status["certificates"][
                                    f"{cert_type}_expires"
                                ] = expiry.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass  # If we can't read the certificate, just mark as present
                else:
                    status["certificates"][cert_type] = False

            return jsonify({"success": True, "certificates": status["certificates"]})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/certificates/download/<filename>")
    def download_certificate(filename: str):
        """Download a certificate file."""
        from flask import abort

        # Security: only allow specific certificate files
        allowed_files = ["ca_cert.pem", "service_center_cert.pem", "service_center_key.pem"]
        if filename not in allowed_files:
            abort(404)

        file_path = os.path.join("certs", filename)
        if not os.path.exists(file_path):
            abort(404)

        return send_file(file_path, as_attachment=True, download_name=filename)

    @app.route("/api/certificates/upload/<cert_type>", methods=["POST"])
    def upload_certificate(cert_type: str) -> Dict[str, Any]:
        """Upload a new certificate."""
        if "certificate" not in request.files:
            return jsonify({"success": False, "message": "No file provided"})

        file = request.files["certificate"]
        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"})

        # Map cert types to filenames
        cert_mapping = {
            "ca": "ca_cert.pem",
            "service": "service_center_cert.pem",
            "key": "service_center_key.pem",
        }

        if cert_type not in cert_mapping:
            return jsonify({"success": False, "message": "Invalid certificate type"})

        try:
            # Ensure certs directory exists
            os.makedirs("certs", exist_ok=True)

            # Backup existing file
            target_file = os.path.join("certs", cert_mapping[cert_type])
            if os.path.exists(target_file):
                backup_file = target_file + ".backup"
                os.rename(target_file, backup_file)

            # Save new file
            file.save(target_file)

            return jsonify(
                {
                    "success": True,
                    "message": f"{cert_type.upper()} certificate uploaded successfully",
                }
            )
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/certificates/generate", methods=["POST"])
    def generate_certificates() -> Dict[str, Any]:
        """Generate new SSL certificates."""
        try:
            # Ensure certs directory exists
            os.makedirs("certs", exist_ok=True)

            # Generate CA private key
            result = subprocess.run(
                ["openssl", "genrsa", "-out", "certs/ca_key.pem", "2048"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return jsonify(
                    {"success": False, "message": f"CA key generation failed: {result.stderr}"}
                )

            # Generate CA certificate
            result = subprocess.run(
                [
                    "openssl",
                    "req",
                    "-new",
                    "-x509",
                    "-key",
                    "certs/ca_key.pem",
                    "-out",
                    "certs/ca_cert.pem",
                    "-days",
                    "365",
                    "-subj",
                    "/C=US/ST=State/L=City/O=BSSCI/CN=BSSCI-CA",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return jsonify(
                    {
                        "success": False,
                        "message": f"CA certificate generation failed: {result.stderr}",
                    }
                )

            # Generate service private key
            result = subprocess.run(
                ["openssl", "genrsa", "-out", "certs/service_center_key.pem", "2048"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return jsonify(
                    {
                        "success": False,
                        "message": f"Service key generation failed: {result.stderr}",
                    }
                )

            # Generate service certificate request
            result = subprocess.run(
                [
                    "openssl",
                    "req",
                    "-new",
                    "-key",
                    "certs/service_center_key.pem",
                    "-out",
                    "certs/service_center.csr",
                    "-subj",
                    "/C=US/ST=State/L=City/O=BSSCI/CN=bssci-service",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return jsonify(
                    {
                        "success": False,
                        "message": f"Service certificate request generation failed: {result.stderr}",
                    }
                )

            # Sign service certificate with CA
            result = subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-req",
                    "-in",
                    "certs/service_center.csr",
                    "-CA",
                    "certs/ca_cert.pem",
                    "-CAkey",
                    "certs/ca_key.pem",
                    "-CAcreateserial",
                    "-out",
                    "certs/service_center_cert.pem",
                    "-days",
                    "365",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return jsonify(
                    {
                        "success": False,
                        "message": f"Service certificate signing failed: {result.stderr}",
                    }
                )

            # Clean up temporary files
            temp_files = ["certs/service_center.csr", "certs/ca_cert.srl"]
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

            return jsonify(
                {"success": True, "message": "New certificates generated successfully"}
            )
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/certificates/backup")
    def backup_certificates():
        """Download all certificates as ZIP."""
        try:
            # Create temporary ZIP file
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")

            with zipfile.ZipFile(temp_zip.name, "w") as zipf:
                cert_files = ["ca_cert.pem", "service_center_cert.pem", "service_center_key.pem"]
                for cert_file in cert_files:
                    file_path = os.path.join("certs", cert_file)
                    if os.path.exists(file_path):
                        zipf.write(file_path, cert_file)

            return send_file(
                temp_zip.name, as_attachment=True, download_name="bssci_certificates_backup.zip"
            )
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/certificates/restore", methods=["POST"])
    def restore_certificates() -> Dict[str, Any]:
        """Restore certificates from ZIP backup."""
        if "backup" not in request.files:
            return jsonify({"success": False, "message": "No backup file provided"})

        file = request.files["backup"]
        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"})

        try:
            # Save uploaded ZIP to temporary location
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            file.save(temp_zip.name)

            # Extract certificates
            with zipfile.ZipFile(temp_zip.name, "r") as zipf:
                # Ensure certs directory exists
                os.makedirs("certs", exist_ok=True)

                # Extract only certificate files
                cert_files = ["ca_cert.pem", "service_center_cert.pem", "service_center_key.pem"]
                for cert_file in cert_files:
                    if cert_file in zipf.namelist():
                        target_path = os.path.join("certs", cert_file)
                        # Backup existing file
                        if os.path.exists(target_path):
                            os.rename(target_path, target_path + ".backup")
                        # Extract new file
                        zipf.extract(cert_file, "certs")

            # Clean up temporary file
            os.unlink(temp_zip.name)

            return jsonify(
                {"success": True, "message": "Certificates restored successfully from backup"}
            )
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/service/restart", methods=["POST"])
    def restart_service() -> Dict[str, Any]:
        """Restart the BSSCI service."""

        def restart_in_background() -> None:
            """Perform the restart operation in a separate thread."""
            try:
                time.sleep(1)  # Small delay to allow response to be sent

                # Execute kill commands
                try:
                    subprocess.run(
                        ["pkill", "-f", "python.*web_main.py"], check=False, timeout=10
                    )
                except Exception:
                    pass

                try:
                    subprocess.run(
                        ["pkill", "-f", "python.*main.py"], check=False, timeout=10
                    )
                except Exception:
                    pass

                try:
                    subprocess.run(
                        ["pkill", "-f", "python.*sync_main.py"], check=False, timeout=10
                    )
                except Exception:
                    pass

                time.sleep(2)  # Wait for processes to terminate

                # Start the service again
                try:
                    subprocess.Popen(
                        ["python", "web_main.py"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Error during restart: {e}")

        try:
            # Start restart in background thread
            restart_thread = threading.Thread(target=restart_in_background)
            restart_thread.daemon = True
            restart_thread.start()

            return jsonify({"success": True, "message": "Service restart initiated"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    return app


def get_bssci_service_status() -> Dict[str, Any]:
    """Get the status of the BSSCI service."""
    try:
        tls_server = get_tls_server()
        if tls_server:
            bs_status = tls_server.get_base_station_status()
            sensor_status = tls_server.get_sensor_registration_status()

            # Get MQTT status - assume active if TLS server is running
            mqtt_status = {
                "active": True,
                "broker_host": bssci_config.MQTT_BROKER,
                "broker_port": bssci_config.MQTT_PORT,
            }

            # Get TLS server status
            tls_status = {
                "active": True,
                "listening_port": bssci_config.LISTEN_PORT,
                "connected_base_stations": bs_status["total_connected"],
                "total_sensors": len(sensor_status),
                "registered_sensors": len([s for s in sensor_status.values() if s["registered"]]),
            }

            return {
                "running": True,
                "service_type": "web_ui",
                "base_stations": bs_status,
                "tls_server": tls_status,
                "mqtt_broker": mqtt_status,
                "total_sensors": len(sensor_status),
                "registered_sensors": len([s for s in sensor_status.values() if s["registered"]]),
                "pending_requests": (
                    len(tls_server.pending_attach_requests)
                    if hasattr(tls_server, "pending_attach_requests")
                    else 0
                ),
            }
        else:
            return {
                "running": False,
                "error": "TLS server not available",
                "service_type": "web_ui",
                "tls_server": {"active": False},
                "mqtt_broker": {"active": False},
                "base_stations": {
                    "total_connected": 0,
                    "total_connecting": 0,
                    "connected": [],
                    "connecting": [],
                },
            }
    except Exception as e:
        import traceback

        return {
            "running": False,
            "error": f"{type(e).__name__}: {str(e)}",
            "service_type": "web_ui",
            "tls_server": {"active": False},
            "mqtt_broker": {"active": False},
            "base_stations": {
                "total_connected": 0,
                "total_connecting": 0,
                "connected": [],
                "connecting": [],
            },
            "traceback": traceback.format_exc(),
        }


def get_tls_server():
    """Get the TLS server instance."""
    try:
        import sys
        main_module = sys.modules.get('__main__')
        if main_module:
            tls_server = getattr(main_module, 'tls_server', None)
            if tls_server:
                return tls_server
        
        # Try importing main module directly
        try:
            import main
            return getattr(main, 'tls_server', None)
        except ImportError:
            pass
            
        return None
    except Exception as e:
        logger.error(f"Error getting TLS server: {e}")
        return None


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)