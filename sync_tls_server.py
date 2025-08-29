import json
import logging
import socket
import ssl
import threading
import time
from datetime import datetime
import queue
import asyncio

import bssci_config
from messages import build_connection_response
from protocol import encode_message, decode_message, IDENTIFIER

logger = logging.getLogger(__name__)

class SyncTLSServer:
    def __init__(self, sensor_config_file, mqtt_in_queue, mqtt_out_queue):
        self.sensor_config_file = sensor_config_file
        self.mqtt_in_queue = mqtt_in_queue
        self.mqtt_out_queue = mqtt_out_queue

        # Load sensor configuration
        self.sensor_config = self._load_sensor_config()

        # Connection tracking
        self.connected_base_stations = {}  # writer -> bs_eui
        self.connecting_base_stations = {}  # writer -> bs_eui
        self.base_station_registry = {}  # bs_eui -> writer (to prevent duplicates)
        self.client_threads = {}
        self.stats = {
            'messages_processed': 0,
            'connections_established': 0,
            'uplink_messages': 0,
            'start_time': time.time()
        }

        # Threading control
        self.running = False
        self.server_socket = None
        self.accept_thread = None
        self._status_task = None

        logger.info("🏗️ Sync TLS Server initialized")
        logger.info(f"📁 Sensor config file: {sensor_config_file}")
        logger.info(f"📊 Loaded {len(self.sensor_config)} sensor configurations")

    def _load_sensor_config(self):
        """Load sensor configuration from JSON file"""
        try:
            with open(self.sensor_config_file, 'r') as f:
                content = f.read().strip()
                if content:
                    self.sensor_config = json.loads(content)
                else:
                    self.sensor_config = []
            logger.info(f"✅ Loaded {len(self.sensor_config)} sensor configurations")
            return self.sensor_config
        except Exception as e:
            logger.error(f"❌ Failed to load sensor config: {e}")
            return []

    def start(self):
        """Start the TLS server"""
        logger.info("=" * 80)
        logger.info("🚀 STARTING SYNCHRONOUS TLS SERVER")
        logger.info("=" * 80)

        try:
            # Create SSL context
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(
                certfile=bssci_config.CERT_FILE,
                keyfile=bssci_config.KEY_FILE
            )
            ssl_ctx.load_verify_locations(cafile=bssci_config.CA_FILE)
            ssl_ctx.verify_mode = ssl.CERT_REQUIRED

            logger.info("🔐 SSL context configured successfully")
            logger.info(f"🏠 Listen address: {bssci_config.LISTEN_HOST}:{bssci_config.LISTEN_PORT}")

            # Create and bind server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((bssci_config.LISTEN_HOST, bssci_config.LISTEN_PORT))
            self.server_socket.listen(5)

            # Wrap with SSL
            self.server_socket = ssl_ctx.wrap_socket(self.server_socket, server_side=True)

            self.running = True
            logger.info("✅ TLS Server listening for connections")

            # Start accepting connections
            self.accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
            self.accept_thread.start()

        except Exception as e:
            logger.error(f"❌ Failed to start TLS server: {e}")
            raise

    def _accept_connections(self):
        """Accept incoming TLS connections"""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                logger.info(f"🔗 New TLS connection from {addr}")

                # Start client handler thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
                self.client_threads[addr] = client_thread

            except ssl.SSLError as e:
                if self.running:
                    logger.error(f"❌ SSL error accepting connection: {e}")
            except Exception as e:
                if self.running:
                    logger.error(f"❌ Error accepting connection: {e}")

    def _handle_client(self, client_socket, addr):
        """Handle individual client connection"""
        logger.info(f"🔄 Starting client handler for {addr}")

        try:
            while self.running:
                try:
                    # Read message identifier
                    data = client_socket.recv(4)
                    if not data or len(data) < 4:
                        logger.warning(f"⚠️ Connection closed by {addr}")
                        break

                    if data != IDENTIFIER:
                        logger.warning(f"⚠️ Invalid identifier from {addr}")
                        continue

                    # Read message length
                    length_data = client_socket.recv(4)
                    if len(length_data) < 4:
                        logger.warning(f"⚠️ Invalid length data from {addr}")
                        break

                    msg_length = int.from_bytes(length_data, byteorder='little')

                    # Read message content
                    msg_data = b""
                    while len(msg_data) < msg_length:
                        chunk = client_socket.recv(msg_length - len(msg_data))
                        if not chunk:
                            break
                        msg_data += chunk

                    if len(msg_data) < msg_length:
                        logger.warning(f"⚠️ Incomplete message from {addr}")
                        break

                    # Decode message
                    message = decode_message(msg_data)
                    msg_type = message.get("command", "")
                    self.stats['messages_processed'] += 1

                    logger.info(f"📨 BSSCI message from {addr}")
                    logger.info(f"   Message type: {msg_type}")

                    # Handle message based on type
                    if msg_type == "con":
                        self._handle_connection_request(client_socket, addr, message)
                    elif msg_type == "conCmp":
                        self._handle_connection_complete(client_socket, addr, message)
                    elif msg_type == "ul":
                        self._handle_uplink_message(client_socket, addr, message)
                    elif msg_type == "statusRsp":
                        self._handle_status_response(client_socket, addr, message)
                    else:
                        logger.warning(f"⚠️ Unknown message type: {msg_type}")

                except ssl.SSLError as e:
                    logger.error(f"❌ SSL error from {addr}: {e}")
                    break
                except Exception as e:
                    logger.error(f"❌ Error handling message from {addr}: {e}")
                    break

        finally:
            self._cleanup_client(client_socket, addr)

    def _handle_connection_request(self, client_socket, addr, message):
        """Handle BSSCI connection request"""
        logger.info(f"📨 Connection request from {addr}")
        logger.info(f"   Operation ID: {message.get('opId', 'unknown')}")

        try:
            # Build connection response
            response = build_connection_response(
                message.get("opId", ""),
                message.get("snBsUuid", "")
            )

            # Send response
            encoded_response = encode_message(response)
            client_socket.send(IDENTIFIER + len(encoded_response).to_bytes(4, byteorder="little") + encoded_response)

            # Track connecting base station
            if "bsEui" in message:
                bs_eui = int(message["bsEui"]).to_bytes(8, byteorder="big").hex()
                self.connecting_base_stations[client_socket] = bs_eui # Use client_socket as writer key
                logger.info(f"📤 Connection response sent to base station {bs_eui}")

        except Exception as e:
            logger.error(f"❌ Error handling connection request: {e}")

    def _handle_connection_complete(self, client_socket, addr, message):
        """Handle BSSCI connection complete"""
        logger.info(f"📨 Connection complete from {addr}")

        try:
            if client_socket in self.connecting_base_stations:
                bs_eui = self.connecting_base_stations.pop(client_socket)

                # Check for existing connection with same EUI
                if bs_eui in self.base_station_registry:
                    old_writer = self.base_station_registry[bs_eui]
                    logger.warning(f"⚠️ Base station {bs_eui} already connected, closing old connection")
                    try:
                        if old_writer in self.connected_base_stations:
                            self.connected_base_stations.pop(old_writer)
                        old_writer.close()
                        # No need to wait_closed here as it's a different thread's socket
                    except Exception as e:
                        logger.error(f"Error closing old connection for {bs_eui}: {e}")

                # Register new connection
                self.connected_base_stations[client_socket] = bs_eui
                self.base_station_registry[bs_eui] = client_socket
                self.stats['connections_established'] += 1
                self.stats['connected_clients'] = len(self.connected_base_stations)

                logger.info(f"✅ Base station {bs_eui} connection established")
                logger.info(f"📊 Connected base stations: {len(self.connected_base_stations)}")

                # Send attach requests for all configured sensors
                for sensor in self.sensor_config:
                    try:
                        # Assuming send_attach_request is an async method if used in an async context
                        # If this handler is not async, this needs to be handled differently, e.g., run in executor
                        asyncio.create_task(self.send_attach_request(client_socket, sensor))
                    except Exception as e:
                        logger.error(f"Failed to attach sensor {sensor.get('eui', 'unknown')}: {e}")

                # Start status request task if not already running
                if self._status_task is None or self._status_task.done():
                    self._status_task = asyncio.create_task(self.send_status_requests())

        except Exception as e:
            logger.error(f"❌ Error handling connection complete: {e}")

    def _handle_uplink_message(self, client_socket, addr, message):
        """Handle uplink data message"""
        try:
            if client_socket not in self.connected_base_stations:
                logger.warning(f"⚠️ Uplink from non-connected base station {addr}")
                return

            bs_eui = self.connected_base_stations[client_socket]
            ep_eui = message.get("epEui", "").lower()

            if not ep_eui:
                logger.warning("⚠️ Uplink message without endpoint EUI")
                return

            self.stats['uplink_messages'] += 1

            logger.info(f"📡 UPLINK MESSAGE from base station {bs_eui}")
            logger.info(f"   Endpoint EUI: {ep_eui}")
            logger.info(f"   Data length: {len(message.get('data', []))} bytes")

            # Add base station EUI to message
            message["bs_eui"] = bs_eui

            # Publish to MQTT
            mqtt_topic = f"ep/{ep_eui}/ul"
            mqtt_payload = json.dumps(message)

            mqtt_message = {
                'topic': mqtt_topic,
                'payload': mqtt_payload
            }

            self.mqtt_out_queue.put(mqtt_message)
            logger.info(f"📤 Published uplink to MQTT: {mqtt_topic}")

        except Exception as e:
            logger.error(f"❌ Error handling uplink message: {e}")

    def _handle_status_response(self, client_socket, addr, message):
        """Handle base station status response"""
        try:
            if client_socket in self.connected_base_stations:
                bs_eui = self.connected_base_stations[client_socket]
                logger.info(f"📊 Status response from base station {bs_eui}")
                logger.info(f"   CPU Load: {message.get('cpuLoad', 'N/A')}")
                logger.info(f"   Memory Load: {message.get('memLoad', 'N/A')}")
        except Exception as e:
            logger.error(f"❌ Error handling status response: {e}")

    def _cleanup_client(self, client_socket, addr):
        """Clean up client connection"""
        logger.info(f"🧹 Cleaning up client connection {addr}")

        # Clean up connection
        if client_socket in self.connected_base_stations:
            bs_eui = self.connected_base_stations.pop(client_socket)
            # Also remove from registry
            if bs_eui in self.base_station_registry and self.base_station_registry[bs_eui] == client_socket:
                self.base_station_registry.pop(bs_eui)
            self.stats['connected_clients'] = len(self.connected_base_stations)
            logger.info(f"❌ Base station {bs_eui} disconnected")

        if client_socket in self.connecting_base_stations:
            bs_eui = self.connecting_base_stations.pop(client_socket)
            # Remove from registry if it was there
            if bs_eui in self.base_station_registry and self.base_station_registry[bs_eui] == client_socket:
                self.base_station_registry.pop(bs_eui)

        logger.info(f"🔌 Connection from {addr} closed")
        logger.info(f"📊 Remaining connected: {len(self.connected_base_stations)}")

        try:
            client_socket.close()
        except:
            pass

        # Remove from client_threads
        if addr in self.client_threads:
            self.client_threads.pop(addr)

        # Save sensor configuration
        try:
            with open(self.sensor_config_file, 'w') as f:
                json.dump(self.sensor_config, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save sensor configuration: {e}")

    def update_sensor_config(self, config):
        """Update sensor configuration from MQTT"""
        try:
            eui = config.get("eui", "").upper()
            logger.info(f"🔧 Updating sensor configuration for EUI: {eui}")

            # Find existing sensor or add new one
            sensor_updated = False
            for sensor in self.sensor_config:
                if sensor.get("eui", "").upper() == eui:
                    sensor.update(config)
                    sensor_updated = True
                    break

            if not sensor_updated:
                self.sensor_config.append(config)

            # Save to file
            with open(self.sensor_config_file, 'w') as f:
                json.dump(self.sensor_config, f, indent=4)

            logger.info(f"✅ Sensor configuration updated for EUI: {eui}")

        except Exception as e:
            logger.error(f"❌ Error updating sensor config: {e}")

    async def send_attach_request(self, writer, sensor):
        """Send attach request to base station"""
        try:
            sensor_eui = sensor.get("eui", "").upper()
            logger.info(f"📲 Sending attach request for sensor {sensor_eui}")

            message = {
                "command": "attach",
                "sensorEui": sensor_eui,
                "config": sensor.get("config", {})
            }

            encoded_message = encode_message(message)
            writer.write(IDENTIFIER + len(encoded_message).to_bytes(4, byteorder="little") + encoded_message)
            await writer.drain()
            logger.info(f"✅ Attach request sent for sensor {sensor_eui}")
        except Exception as e:
            logger.error(f"❌ Failed to send attach request for sensor {sensor_eui}: {e}")

    async def send_status_requests(self):
        """Periodically send status requests to all connected base stations"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Send status every 30 seconds
                if not self.connected_base_stations:
                    continue

                logger.info("❓ Sending status requests to connected base stations")
                for writer, bs_eui in list(self.connected_base_stations.items()): # Use list to avoid modification during iteration
                    try:
                        message = {"command": "statusReq"}
                        encoded_message = encode_message(message)
                        writer.write(IDENTIFIER + len(encoded_message).to_bytes(4, byteorder="little") + encoded_message)
                        await writer.drain()
                    except Exception as e:
                        logger.error(f"❌ Failed to send status request to {bs_eui}: {e}")
                        # If sending fails, consider the connection dead and clean it up
                        self._cleanup_client(writer, None) # Pass None for addr as it might not be available

            except asyncio.CancelledError:
                logger.info("Status request task cancelled.")
                break
            except Exception as e:
                logger.error(f"❌ Error in status request loop: {e}")
                await asyncio.sleep(5) # Wait a bit before retrying after an error

    def get_base_station_status(self):
        """Get status of connected base stations for web UI"""
        connected_stations = []
        for writer, bs_eui in self.connected_base_stations.items():
            try:
                addr = writer.get_extra_info("peername") if hasattr(writer, 'get_extra_info') else None
                connected_stations.append({
                    "eui": bs_eui,
                    "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                    "status": "connected"
                })
            except Exception as e:
                logger.debug(f"Error getting station info for {bs_eui}: {e}")
                connected_stations.append({
                    "eui": bs_eui,
                    "status": "connected"
                })

        connecting_stations = []
        for writer, bs_eui in self.connecting_base_stations.items():
            try:
                addr = writer.get_extra_info("peername") if hasattr(writer, 'get_extra_info') else None
                connecting_stations.append({
                    "eui": bs_eui,
                    "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                    "status": "connecting"
                })
            except Exception as e:
                logger.debug(f"Error getting connecting station info for {bs_eui}: {e}")
                connecting_stations.append({
                    "eui": bs_eui,
                    "status": "connecting"
                })

        # Remove duplicates by EUI
        unique_connected = []
        seen_euis = set()
        for station in connected_stations:
            if station["eui"] not in seen_euis:
                unique_connected.append(station)
                seen_euis.add(station["eui"])

        return {
            "connected": unique_connected,
            "connecting": connecting_stations,
            "total_connected": len(unique_connected),
            "total_connecting": len(connecting_stations)
        }

    def get_sensor_registration_status(self):
        """Get registration status of all sensors for web UI"""
        status = {}
        connected_base_stations = list(set(self.connected_base_stations.values()))
        
        for sensor in self.sensor_config:
            eui = sensor['eui'].lower()
            status[eui] = {
                'eui': sensor['eui'],
                'nwKey': sensor['nwKey'],
                'shortAddr': sensor['shortAddr'],
                'bidi': sensor['bidi'],
                'registered': len(connected_base_stations) > 0,
                'registration_info': {
                    'status': 'registered' if len(connected_base_stations) > 0 else 'not_registered',
                    'base_stations': connected_base_stations,
                    'total_registrations': len(connected_base_stations)
                },
                'base_stations': connected_base_stations,
                'total_registrations': len(connected_base_stations)
            }
        return status

    def reload_sensor_config(self):
        """Reload sensor configuration from file for web UI"""
        try:
            with open(self.sensor_config_file, 'r') as f:
                self.sensor_config = json.load(f)
            logger.info(f"✅ Sensor configuration reloaded: {len(self.sensor_config)} sensors")
        except Exception as e:
            logger.error(f"❌ Failed to reload sensor config: {e}")
            self.sensor_config = []

    def clear_all_sensors(self):
        """Clear all sensor configurations for web UI"""
        self.sensor_config = []
        try:
            with open(self.sensor_config_file, "w") as f:
                json.dump(self.sensor_config, f, indent=4)
            logger.info(f"All sensor configurations cleared")
        except Exception as e:
            logger.error(f"Failed to clear sensor configurations: {e}")

    def stop(self):
        """Stop the TLS server"""
        logger.info("🛑 Stopping synchronous TLS server...")

        self.running = False

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        # Cancel status task if running
        if self._status_task:
            self._status_task.cancel()

        # Wait for client threads to finish
        for addr, thread in list(self.client_threads.items()): # Use list to avoid modification during iteration
            try:
                thread.join(timeout=2)
            except Exception as e:
                logger.error(f"Error joining thread for {addr}: {e}")

        logger.info("✅ Synchronous TLS server stopped")

    def get_base_station_status(self):
        """Get current base station connection status"""
        # Get unique base stations only (no duplicates)
        unique_base_stations = list(set(self.connected_base_stations.values()))
        return {
            'connected_count': len(unique_base_stations),
            'connecting_count': len(self.connecting_base_stations),
            'base_stations': unique_base_stations,
            'stats': self.stats.copy()
        }