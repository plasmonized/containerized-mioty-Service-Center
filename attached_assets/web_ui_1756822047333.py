"""Web UI for mioty BSSCI Service Center management."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Tuple

from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

import bssci_config

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)

    @app.route("/")
    def index() -> Union[str, Tuple[str, int]]:
        """Main dashboard page."""
        try:
            # Get basic system status
            status_data = {
                "service_center": "running",
                "tls_server": "active",
                "mqtt_client": "connected",
                "timestamp": datetime.now().isoformat(),
            }

            return render_template("dashboard.html", status=status_data)
        except Exception as e:
            logger.error(f"Error rendering dashboard: {e}")
            return f"Error loading dashboard: {e}", 500

    @app.route("/api/status")
    def api_status() -> Union[Response, Tuple[Response, int]]:
        """API endpoint for system status."""
        try:
            # Global reference to TLS server instance from main.py
            from main import tls_server_instance

            status = {
                "timestamp": datetime.now().isoformat(),
                "service_center": "running",
                "connected_base_stations": 0,
                "registered_sensors": 0,
                "deduplication_stats": {},
            }

            if tls_server_instance:
                status["connected_base_stations"] = len(
                    tls_server_instance.connected_base_stations
                )
                status["registered_sensors"] = len(
                    tls_server_instance.registered_sensors
                )
                status["deduplication_stats"] = tls_server_instance.deduplication_stats

            return jsonify(status)
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/sensors")
    def sensors() -> Union[str, Tuple[str, int]]:
        """Sensor management page."""
        try:
            # Load sensor configuration
            sensor_config = []
            try:
                with open(bssci_config.SENSOR_CONFIG_FILE, "r", encoding="utf-8") as f:
                    sensor_config = json.load(f)
            except FileNotFoundError:
                logger.warning(
                    f"Sensor config file not found: {bssci_config.SENSOR_CONFIG_FILE}"
                )
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in sensor config: {e}")

            return render_template("sensors.html", sensors=sensor_config)
        except Exception as e:
            logger.error(f"Error rendering sensors page: {e}")
            return f"Error loading sensors: {e}", 500

    @app.route("/api/sensors")
    def api_sensors() -> Union[Response, Tuple[Response, int]]:
        """API endpoint for sensor list."""
        try:
            # Load sensor configuration
            sensor_config = []
            try:
                with open(bssci_config.SENSOR_CONFIG_FILE, "r", encoding="utf-8") as f:
                    sensor_config = json.load(f)
            except FileNotFoundError:
                sensor_config = []

            # Get runtime sensor status
            from main import tls_server_instance

            runtime_status = {}
            if tls_server_instance:
                runtime_status = tls_server_instance.registered_sensors

            # Combine configuration with runtime status
            sensors_with_status = []
            for sensor in sensor_config:
                eui = sensor["eui"].lower()
                sensor_data = {
                    "eui": sensor["eui"],
                    "shortAddr": sensor["shortAddr"],
                    "bidi": sensor.get("bidi", False),
                    "status": "configured",
                }

                if eui in runtime_status:
                    sensor_data.update(
                        {
                            "status": runtime_status[eui].get("status", "unknown"),
                            "base_stations": runtime_status[eui].get(
                                "base_stations", []
                            ),
                            "last_seen": runtime_status[eui].get("timestamp", 0),
                        }
                    )

                sensors_with_status.append(sensor_data)

            return jsonify({"sensors": sensors_with_status})
        except Exception as e:
            logger.error(f"Error getting sensors: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/sensors/<eui>/detach", methods=["POST"])
    def api_detach_sensor(eui: str) -> Union[Response, Tuple[Response, int]]:
        """API endpoint to detach a sensor."""
        try:
            from main import tls_server_instance

            if not tls_server_instance:
                return jsonify({"error": "TLS server not available"}), 503

            # Queue detach command
            detach_command = {
                "mqtt_topic": f"{bssci_config.BASE_TOPIC}/ep/{eui}/cmd",
                "mqtt_payload": {"action": "detach", "eui": eui},
            }

            # Use asyncio to put command in queue
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                tls_server_instance.mqtt_in_queue.put(detach_command)
            )
            loop.close()

            return jsonify(
                {"success": True, "message": f"Detach command sent for {eui}"}
            )
        except Exception as e:
            logger.error(f"Error detaching sensor {eui}: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/base-stations")
    def base_stations() -> Union[str, Tuple[str, int]]:
        """Base stations management page."""
        try:
            return render_template("base_stations.html")
        except Exception as e:
            logger.error(f"Error rendering base stations page: {e}")
            return f"Error loading base stations: {e}", 500

    @app.route("/api/base-stations")
    def api_base_stations() -> Union[Response, Tuple[Response, int]]:
        """API endpoint for base station list."""
        try:
            from main import tls_server_instance

            base_stations = []
            if tls_server_instance:
                connected_stations = tls_server_instance.connected_base_stations
                reg_sensors = tls_server_instance.registered_sensors
                for writer, bs_eui in connected_stations.items():
                    addr = writer.get_extra_info("peername")
                    base_stations.append(
                        {
                            "eui": bs_eui,
                            "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                            "status": "connected",
                            "connected_sensors": [
                                sensor_eui
                                for sensor_eui, sensor_data in reg_sensors.items()
                                if bs_eui in sensor_data.get("base_stations", [])
                            ],
                        }
                    )

            return jsonify({"base_stations": base_stations})
        except Exception as e:
            logger.error(f"Error getting base stations: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/config")
    def config() -> Union[str, Tuple[str, int]]:
        """Configuration management page."""
        try:
            config_data = {
                "listen_host": bssci_config.LISTEN_HOST,
                "listen_port": bssci_config.LISTEN_PORT,
                "mqtt_broker": bssci_config.MQTT_BROKER,
                "mqtt_port": bssci_config.MQTT_PORT,
                "base_topic": bssci_config.BASE_TOPIC,
                "status_interval": bssci_config.STATUS_INTERVAL,
                "deduplication_delay": bssci_config.DEDUPLICATION_DELAY,
            }

            return render_template("config.html", config=config_data)
        except Exception as e:
            logger.error(f"Error rendering config page: {e}")
            return f"Error loading configuration: {e}", 500

    @app.errorhandler(404)
    def not_found(error) -> Tuple[str, int]:
        """Handle 404 errors."""
        return (
            render_template(
                "error.html", error_code=404, error_message="Page not found"
            ),
            404,
        )

    @app.errorhandler(500)
    def internal_error(error) -> Tuple[str, int]:
        """Handle 500 errors."""
        return (
            render_template(
                "error.html", error_code=500, error_message="Internal server error"
            ),
            500,
        )

    return app
