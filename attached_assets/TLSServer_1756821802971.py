"""TLS Server implementation for mioty BSSCI protocol."""

import asyncio
import json
import logging
import ssl
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

import bssci_config
import messages
from protocol import decode_messages, encode_message

logger = logging.getLogger(__name__)

IDENTIFIER = bytes("MIOTYB01", "utf-8")


class TLSServer:
    """TLS Server for handling mioty BSSCI protocol communications."""

    def __init__(
        self,
        sensor_config_file: str,
        mqtt_out_queue: asyncio.Queue[dict[str, str]],
        mqtt_in_queue: asyncio.Queue[dict[str, str]],
    ) -> None:
        """Initialize TLS Server with configuration and queues."""
        self.opID = -1
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue
        self.connected_base_stations: Dict[asyncio.streams.StreamWriter, str] = {}
        self.connecting_base_stations: Dict[asyncio.streams.StreamWriter, str] = {}
        self.sensor_config_file = sensor_config_file
        self.registered_sensors: Dict[str, Dict[str, Any]] = {}
        self.pending_attach_requests: Dict[int, Dict[str, Any]] = {}
        self._status_task_running = False

        # Deduplication variables
        self.deduplication_buffer: Dict[str, Dict[str, Any]] = {}
        self.deduplication_delay = bssci_config.DEDUPLICATION_DELAY
        self.deduplication_stats = {
            "total_messages": 0,
            "duplicate_messages": 0,
            "published_messages": 0,
        }

        # Start the deduplication task
        asyncio.create_task(self.process_deduplication_buffer())

        try:
            with open(sensor_config_file, "r", encoding="utf-8") as f:
                self.sensor_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load sensor config: {e}")
            self.sensor_config = []

        # Add queue logging
        logger.info("🔍 TLS Server Queue Assignment:")
        logger.info(f"   mqtt_out_queue ID: {id(self.mqtt_out_queue)}")
        logger.info(f"   mqtt_in_queue ID: {id(self.mqtt_in_queue)}")

    def _get_local_time(self) -> str:
        """Get current time in UTC+2 timezone."""
        utc_time = datetime.now(timezone.utc)
        local_time = utc_time + timedelta(hours=2)
        return local_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    async def process_deduplication_buffer(self) -> None:
        """Process deduplication buffer to handle duplicate messages."""
        while True:
            try:
                await asyncio.sleep(1)  # Check every second
                current_time = asyncio.get_event_loop().time()
                messages_to_publish = []
                messages_to_remove = []

                for message_key, message_data in self.deduplication_buffer.items():
                    time_elapsed = current_time - message_data["timestamp"]
                    if time_elapsed >= self.deduplication_delay:
                        messages_to_publish.append((message_key, message_data))
                        messages_to_remove.append(message_key)

                # Publish delayed messages
                for message_key, message_data in messages_to_publish:
                    try:
                        await self.mqtt_out_queue.put(
                            {
                                "topic": message_data["topic"],
                                "payload": message_data["payload"],
                            }
                        )
                        self.deduplication_stats["published_messages"] += 1
                        logger.debug(f"Published deduplicated message: {message_key}")
                    except Exception as e:
                        logger.error(f"Failed to publish message {message_key}: {e}")

                # Remove published messages from buffer
                for message_key in messages_to_remove:
                    self.deduplication_buffer.pop(message_key, None)

            except Exception as e:
                logger.error(f"Error in deduplication buffer processing: {e}")

    async def start_server(self) -> None:
        """Start the TLS server for BSSCI connections."""
        logger.info("🔐 Setting up SSL/TLS context for BSSCI server...")
        logger.info(f"   Certificate file: {bssci_config.CERT_FILE}")
        logger.info(f"   Key file: {bssci_config.KEY_FILE}")
        logger.info(f"   CA file: {bssci_config.CA_FILE}")

        try:
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(
                certfile=bssci_config.CERT_FILE, keyfile=bssci_config.KEY_FILE
            )
            ssl_ctx.load_verify_locations(cafile=bssci_config.CA_FILE)
            ssl_ctx.verify_mode = ssl.CERT_REQUIRED

            # Log SSL context details
            logger.info(
                f"   TLS Protocol versions: "
                f"{ssl_ctx.minimum_version.name} - {ssl_ctx.maximum_version.name}"
            )
            logger.info(
                "✓ SSL context configured successfully with "
                "client certificate verification"
            )

        except FileNotFoundError as e:
            logger.error(f"❌ SSL certificate file not found: {e}")
            raise
        except ssl.SSLError as e:
            logger.error(f"❌ SSL configuration error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error setting up SSL: {e}")
            raise

        logger.info("🚀 Starting BSSCI TLS server...")
        logger.info(
            f"   Listen address: "
            f"{bssci_config.LISTEN_HOST}:{bssci_config.LISTEN_PORT}"
        )
        logger.info(f"   Sensor config file: {self.sensor_config_file}")
        logger.info(f"   Loaded sensors: {len(self.sensor_config)}")

        server = await asyncio.start_server(
            self.handle_client,
            bssci_config.LISTEN_HOST,
            bssci_config.LISTEN_PORT,
            ssl=ssl_ctx,
        )

        logger.info("📨 Starting MQTT queue watcher task...")
        asyncio.create_task(self.queue_watcher())

        logger.info(
            "✓ BSSCI TLS Server is ready and listening for " "base station connections"
        )
        async with server:
            await server.serve_forever()

    async def queue_watcher(self) -> None:
        """Watch for incoming MQTT messages and process them."""
        logger.info("👀 MQTT Queue Watcher started")
        while True:
            try:
                message = await self.mqtt_in_queue.get()
                logger.info(f"📨 Received MQTT message: {message}")

                # Handle sensor configuration
                if "eui" in message and "nwKey" in message:
                    await self.handle_sensor_config(message)
                elif "mqtt_topic" in message and "mqtt_payload" in message:
                    await self.handle_mqtt_command(message)
                else:
                    logger.warning(f"Unknown message format: {message}")

            except Exception as e:
                logger.error(f"Error processing MQTT queue message: {e}")

    async def handle_sensor_config(self, config: Dict[str, Any]) -> None:
        """Handle sensor configuration from MQTT."""
        eui = config["eui"]
        logger.info(f"🔧 Processing sensor configuration for EUI: {eui}")

        # Store sensor configuration
        self.registered_sensors[eui.lower()] = {
            "status": "configured",
            "config": config,
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Attempt to attach to all connected base stations
        for writer in self.connected_base_stations.keys():
            try:
                await self.send_attach_request(writer, config)
            except Exception as e:
                logger.error(f"Failed to attach sensor {eui}: {e}")

    async def handle_mqtt_command(self, message: Dict[str, Any]) -> None:
        """Handle MQTT commands for sensor operations."""
        topic = message["mqtt_topic"]
        payload = message["mqtt_payload"]

        logger.info(f"📡 Processing MQTT command on topic: {topic}")

        # Extract EUI from topic
        topic_parts = topic.split("/")
        if len(topic_parts) >= 3:
            eui = topic_parts[-2]  # Get EUI from topic structure

            if payload.get("action") == "detach":
                await self.handle_detach_command(eui)
            elif payload.get("action") == "status":
                await self.handle_status_command(eui)
            else:
                logger.warning(f"Unknown command action: {payload.get('action')}")

    async def handle_detach_command(self, eui: str) -> None:
        """Handle detach command for a sensor."""
        logger.info(f"🔌 Processing detach command for EUI: {eui}")

        eui_lower = eui.lower()
        if eui_lower in self.registered_sensors:
            # Send detach requests to all base stations
            for writer, bs_eui in self.connected_base_stations.items():
                try:
                    await self.send_detach_request(writer, eui)
                    logger.info(f"Sent detach request for {eui} to {bs_eui}")
                except Exception as e:
                    logger.error(f"Failed to send detach request: {e}")

            # Update sensor status
            self.registered_sensors[eui_lower]["status"] = "detached"
        else:
            logger.warning(f"Sensor {eui} not found in registered sensors")

    async def handle_status_command(self, eui: str) -> None:
        """Handle status command for a sensor."""
        logger.info(f"📊 Processing status command for EUI: {eui}")

        eui_lower = eui.lower()
        if eui_lower in self.registered_sensors:
            sensor_info = self.registered_sensors[eui_lower]
            status_message = {
                "topic": f"ep/{eui}/status",
                "payload": json.dumps(
                    {
                        "eui": eui,
                        "status": sensor_info["status"],
                        "timestamp": sensor_info["timestamp"],
                        "base_stations": sensor_info.get("base_stations", []),
                    }
                ),
            }
            await self.mqtt_out_queue.put(status_message)
        else:
            logger.warning(f"Sensor {eui} not found in registered sensors")

    async def send_attach_request(
        self, writer: asyncio.streams.StreamWriter, sensor: Dict[str, Any]
    ) -> None:
        """Send attach request to base station."""
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        try:
            logger.info("📤 BSSCI ATTACH REQUEST INITIATED")
            logger.info("   =====================================")
            logger.info(f"   Sensor EUI: {sensor['eui']}")
            logger.info(f"   Target Base Station: {bs_eui}")
            logger.info(f"   Operation ID: {self.opID}")
            logger.info(f"   Timestamp: {self._get_local_time()}")

            # Validate sensor configuration
            validation_errors = self._validate_sensor_config(sensor)

            if not validation_errors:
                # Normalize sensor data
                normalized_sensor = self._normalize_sensor_config(sensor)

                # Build and encode the message
                attach_message = messages.build_attach_request(
                    normalized_sensor, self.opID
                )
                msg_pack = encode_message(attach_message)
                full_message = (
                    IDENTIFIER
                    + len(msg_pack).to_bytes(4, byteorder="little")
                    + msg_pack
                )

                logger.info("📤 Transmitting attach request...")
                logger.info(f"     Message size: {len(full_message)} bytes")

                writer.write(full_message)
                await writer.drain()

                # Track this attach request
                self.pending_attach_requests[self.opID] = {
                    "sensor_eui": sensor["eui"],
                    "timestamp": asyncio.get_event_loop().time(),
                    "base_station": bs_eui,
                    "sensor_config": normalized_sensor,
                }

                logger.info("✅ BSSCI ATTACH REQUEST TRANSMITTED")
                self.opID -= 1
            else:
                logger.error("❌ ATTACH REQUEST VALIDATION FAILED")
                for error in validation_errors:
                    logger.error(f"     {error}")

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR during attach request: {e}")
            raise

    def _validate_sensor_config(self, sensor: Dict[str, Any]) -> list[str]:
        """Validate sensor configuration parameters."""
        errors = []

        # EUI validation
        eui = sensor.get("eui", "")
        if len(eui) != 16:
            errors.append(f"EUI length {len(eui)} != 16 characters")
        else:
            try:
                int(eui, 16)
            except ValueError:
                errors.append(f"EUI contains invalid hex characters: {eui}")

        # Network Key validation
        nw_key = sensor.get("nwKey", "")
        if len(nw_key) < 32:
            errors.append(f"Network key length {len(nw_key)} < 32 characters required")
        else:
            try:
                int(nw_key[:32], 16)
            except ValueError:
                errors.append("Network key contains invalid hex characters")

        # Short Address validation
        short_addr = sensor.get("shortAddr", "")
        if len(short_addr) != 4:
            errors.append(f"Short address length {len(short_addr)} != 4 characters")
        else:
            try:
                int(short_addr, 16)
            except ValueError:
                errors.append("Short address contains invalid hex characters")

        return errors

    def _normalize_sensor_config(self, sensor: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize sensor configuration parameters."""
        return {
            "eui": sensor["eui"],
            "nwKey": sensor["nwKey"][:32],  # Truncate if longer
            "shortAddr": sensor["shortAddr"],
            "bidi": sensor.get("bidi", False),
        }

    async def send_detach_request(
        self, writer: asyncio.streams.StreamWriter, eui: str
    ) -> None:
        """Send detach request to base station."""
        try:
            detach_message = messages.build_detach_request(eui, self.opID)
            msg_pack = encode_message(detach_message)
            full_message = (
                IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack
            )

            writer.write(full_message)
            await writer.drain()

            logger.info(f"Sent detach request for {eui} (opID: {self.opID})")
            self.opID -= 1

        except Exception as e:
            logger.error(f"Failed to send detach request for {eui}: {e}")
            raise

    async def attach_file(self, writer: asyncio.streams.StreamWriter) -> None:
        """Attach all sensors from configuration file to base station."""
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        logger.info(f"🔗 BATCH SENSOR ATTACHMENT started for base station {bs_eui}")
        logger.info(f"   Total sensors to process: {len(self.sensor_config)}")

        successful_attachments = 0
        failed_attachments = 0

        for i, sensor in enumerate(self.sensor_config, 1):
            try:
                logger.info(
                    f"   Processing sensor {i}/{len(self.sensor_config)}: "
                    f"{sensor['eui']}"
                )
                await self.send_attach_request(writer, sensor)
                successful_attachments += 1

                # Small delay between requests
                await asyncio.sleep(0.1)

            except Exception as e:
                failed_attachments += 1
                logger.error(
                    f"   ❌ Failed to attach sensor "
                    f"{sensor.get('eui', 'unknown')}: {e}"
                )

        logger.info(f"✅ BATCH SENSOR ATTACHMENT completed for base station {bs_eui}")
        logger.info(f"   Successful: {successful_attachments}")
        logger.info(f"   Failed: {failed_attachments}")

    async def send_status_requests(self) -> None:
        """Send periodic status requests to all connected base stations."""
        logger.info("📊 STATUS REQUEST TASK STARTED")
        logger.info(
            f"   Status request interval: {bssci_config.STATUS_INTERVAL} seconds"
        )

        try:
            while True:
                await asyncio.sleep(bssci_config.STATUS_INTERVAL)
                if self.connected_base_stations:
                    logger.info("📊 PERIODIC STATUS REQUEST CYCLE STARTING")
                    logger.info(
                        f"   Connected base stations: "
                        f"{len(self.connected_base_stations)}"
                    )

                    requests_sent = 0
                    failed_requests = 0

                    # Use copy to avoid dict change during iteration
                    for writer, bs_eui in self.connected_base_stations.copy().items():
                        try:
                            logger.info(
                                f"📤 Sending status request to base station {bs_eui}"
                            )

                            msg_pack = encode_message(
                                messages.build_status_request(self.opID)
                            )
                            full_message = (
                                IDENTIFIER
                                + len(msg_pack).to_bytes(4, byteorder="little")
                                + msg_pack
                            )

                            writer.write(full_message)
                            await writer.drain()

                            logger.info(
                                f"✅ Status request transmitted to {bs_eui} "
                                f"(opID: {self.opID})"
                            )
                            requests_sent += 1
                            self.opID -= 1

                        except Exception as e:
                            failed_requests += 1
                            logger.error(
                                f"❌ Failed to send status request to "
                                f"base station {bs_eui}: {e}"
                            )
                            # Remove disconnected base station
                            if writer in self.connected_base_stations:
                                self.connected_base_stations.pop(writer)

                    logger.info("📊 STATUS REQUEST CYCLE COMPLETE")
                    logger.info(f"   Requests sent: {requests_sent}")
                    logger.info(f"   Failed requests: {failed_requests}")

                else:
                    logger.info(
                        "⏸️  STATUS REQUEST CYCLE SKIPPED - "
                        "No base stations connected"
                    )

        except asyncio.CancelledError:
            logger.info("📊 STATUS REQUEST TASK CANCELLED")
            self._status_task_running = False
            raise
        except Exception as e:
            logger.error(f"❌ STATUS REQUEST TASK ERROR: {e}")
            self._status_task_running = False
            raise

    async def handle_client(
        self, reader: asyncio.streams.StreamReader, writer: asyncio.streams.StreamWriter
    ) -> None:
        """Handle incoming client connections."""
        addr = writer.get_extra_info("peername")
        ssl_obj = writer.get_extra_info("ssl_object")

        try:
            logger.info(f"🔗 New BSSCI connection attempt from {addr}")

            if ssl_obj:
                cert = ssl_obj.getpeercert()
                if cert:
                    subject = cert.get("subject", [])
                    cn = None
                    for field in subject:
                        for name, value in field:
                            if name == "commonName":
                                cn = value
                                break
                    logger.info(
                        f"   ✓ SSL handshake successful - "
                        f"Client certificate CN: {cn}"
                    )
                else:
                    logger.warning(
                        "   ⚠️  SSL handshake completed but "
                        "no client certificate provided"
                    )
            else:
                logger.error(
                    "   ❌ No SSL object found - " "connection may not be encrypted"
                )

        except Exception as e:
            logger.error(f"   ❌ SSL connection error from {addr}: {e}")
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            return

        connection_start_time = asyncio.get_event_loop().time()
        connection_id = f"{addr}_{connection_start_time}"

        try:
            # Add to connecting base stations
            self.connecting_base_stations[writer] = connection_id
            logger.info(f"📝 Added connection {connection_id} to connecting list")

            # Handle the connection
            await self._handle_connection_messages(reader, writer, addr)

        except Exception as e:
            logger.error(f"Connection handling error for {addr}: {e}")
        finally:
            # Clean up connection
            if writer in self.connecting_base_stations:
                self.connecting_base_stations.pop(writer)
            if writer in self.connected_base_stations:
                bs_eui = self.connected_base_stations.pop(writer)
                logger.info(f"🔌 Base station {bs_eui} disconnected")

            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_connection_messages(
        self,
        reader: asyncio.streams.StreamReader,
        writer: asyncio.streams.StreamWriter,
        addr: tuple,
    ) -> None:
        """Handle messages from a connected client."""
        buffer = b""
        last_activity = asyncio.get_event_loop().time()

        while True:
            try:
                # Read data with timeout
                data = await asyncio.wait_for(reader.read(4096), timeout=30.0)
                if not data:
                    logger.info(f"Connection {addr} closed by client")
                    break

                buffer += data
                last_activity = asyncio.get_event_loop().time()

                # Process complete messages
                while len(buffer) >= 12:  # Minimum message size
                    if buffer[:8] != IDENTIFIER:
                        logger.error(f"Invalid message identifier from {addr}")
                        break

                    msg_length = int.from_bytes(buffer[8:12], byteorder="little")
                    total_length = 12 + msg_length

                    if len(buffer) < total_length:
                        break  # Wait for more data

                    # Extract and process message
                    message_data = buffer[12:total_length]
                    buffer = buffer[total_length:]

                    await self._process_message(message_data, writer, addr)

            except asyncio.TimeoutError:
                # Check for connection timeout
                current_time = asyncio.get_event_loop().time()
                if current_time - last_activity > 300:  # 5 minutes timeout
                    logger.warning(f"Connection {addr} timed out")
                    break
            except Exception as e:
                logger.error(f"Message processing error for {addr}: {e}")
                break

    async def _process_message(
        self, message_data: bytes, writer: asyncio.streams.StreamWriter, addr: tuple
    ) -> None:
        """Process a single message from a base station."""
        try:
            # Decode messages with proper identifier header
            header = IDENTIFIER + b"\x00\x00\x00\x00"
            messages_list = decode_messages(header + message_data)

            for message in messages_list:
                msg_type = message.get("msgType")
                logger.info(f"📨 Received {msg_type} from {addr}")

                if msg_type == "con":
                    await self._handle_connection_message(message, writer, addr)
                elif msg_type == "ulData":
                    await self._handle_uplink_data(message, writer)
                elif msg_type == "attPrpRsp":
                    await self._handle_attach_response(message, writer)
                elif msg_type == "statusRsp":
                    await self._handle_status_response(message, writer)
                elif msg_type == "ping":
                    await self._handle_ping(message, writer)
                else:
                    logger.warning(f"Unknown message type: {msg_type}")

        except Exception as e:
            logger.error(f"Error processing message from {addr}: {e}")

    async def _handle_connection_message(
        self, message: Dict[str, Any], writer: asyncio.streams.StreamWriter, addr: tuple
    ) -> None:
        """Handle connection establishment message."""
        bs_eui = message.get("bsEui", f"unknown_{addr[0]}")

        # Move from connecting to connected
        if writer in self.connecting_base_stations:
            self.connecting_base_stations.pop(writer)

        self.connected_base_stations[writer] = bs_eui
        logger.info(f"✅ Base station {bs_eui} connected from {addr}")

        # Send connection complete response
        response = messages.build_connection_complete(message.get("opID", 0))
        await self._send_message(writer, response)

        # Start status request task if not running
        if not self._status_task_running:
            self._status_task_running = True
            asyncio.create_task(self.send_status_requests())

        # Attach sensors from config file
        if self.sensor_config:
            asyncio.create_task(self.attach_file(writer))

    async def _handle_uplink_data(
        self, message: Dict[str, Any], writer: asyncio.streams.StreamWriter
    ) -> None:
        """Handle uplink data from sensors."""
        eui = message.get("eui", "unknown")
        snr = message.get("snr", 0)
        rssi = message.get("rssi", 0)
        data = message.get("data", [])

        logger.info(f"📡 Uplink data from sensor {eui}: SNR={snr}, RSSI={rssi}")

        # Create message key for deduplication
        message_key = f"{eui}_{message.get('cnt', 0)}_{hash(tuple(data))}"

        # Check for duplicates
        current_time = asyncio.get_event_loop().time()
        if message_key in self.deduplication_buffer:
            self.deduplication_stats["duplicate_messages"] += 1
            logger.debug(f"Duplicate message detected: {message_key}")

            # Update with better SNR if available
            existing_snr = self.deduplication_buffer[message_key].get("snr", -999)
            if snr > existing_snr:
                self.deduplication_buffer[message_key].update(
                    {
                        "snr": snr,
                        "rssi": rssi,
                        "bs_eui": self.connected_base_stations.get(writer, "unknown"),
                    }
                )
                logger.debug(f"Updated message with better SNR: {snr} > {existing_snr}")
        else:
            # New message - add to deduplication buffer
            self.deduplication_stats["total_messages"] += 1

            payload_data = {
                "rxTime": message.get("rxTime", current_time * 1000000),
                "snr": snr,
                "rssi": rssi,
                "cnt": message.get("cnt", 0),
                "data": data,
                "bsEui": self.connected_base_stations.get(writer, "unknown"),
            }

            self.deduplication_buffer[message_key] = {
                "message": message,
                "timestamp": current_time,
                "snr": snr,
                "bs_eui": self.connected_base_stations.get(writer, "unknown"),
                "topic": f"ep/{eui}/ul",
                "payload": json.dumps(payload_data),
            }

            logger.debug(f"Added new message to deduplication buffer: {message_key}")

        # Send acknowledgment
        ack_response = messages.build_uplink_complete(message.get("opID", 0))
        await self._send_message(writer, ack_response)

    async def _handle_attach_response(
        self, message: Dict[str, Any], writer: asyncio.streams.StreamWriter
    ) -> None:
        """Handle attach response from base station."""
        op_id = message.get("opID", 0)
        status = message.get("status", "unknown")

        if op_id in self.pending_attach_requests:
            request_info = self.pending_attach_requests.pop(op_id)
            eui = request_info["sensor_eui"]
            bs_eui = request_info["base_station"]

            logger.info(f"📝 Attach response for {eui}: {status}")

            # Update sensor registration status
            eui_lower = eui.lower()
            if eui_lower not in self.registered_sensors:
                self.registered_sensors[eui_lower] = {
                    "status": "registered" if status == "success" else "failed",
                    "base_stations": [],
                    "timestamp": asyncio.get_event_loop().time(),
                }

            sensor_base_stations = self.registered_sensors[eui_lower]["base_stations"]
            if status == "success" and bs_eui not in sensor_base_stations:
                self.registered_sensors[eui_lower]["base_stations"].append(bs_eui)
                self.registered_sensors[eui_lower]["status"] = "registered"
        else:
            logger.warning(f"Received attach response for unknown opID: {op_id}")

    async def _handle_status_response(
        self, message: Dict[str, Any], writer: asyncio.streams.StreamWriter
    ) -> None:
        """Handle status response from base station."""
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        logger.info(f"📊 Status response from {bs_eui}: {message}")

        # Publish status to MQTT
        status_data = {
            "bsEui": bs_eui,
            "timestamp": asyncio.get_event_loop().time(),
            "status": message,
        }

        await self.mqtt_out_queue.put(
            {"topic": f"bs/{bs_eui}/status", "payload": json.dumps(status_data)}
        )

    async def _handle_ping(
        self, message: Dict[str, Any], writer: asyncio.streams.StreamWriter
    ) -> None:
        """Handle ping message from base station."""
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        logger.debug(f"🏓 Ping from {bs_eui}")

        # Send ping complete response
        ping_response = messages.build_ping_complete(message.get("opID", 0))
        await self._send_message(writer, ping_response)

    async def _send_message(
        self, writer: asyncio.streams.StreamWriter, message: Dict[str, Any]
    ) -> None:
        """Send a message to a base station."""
        try:
            msg_pack = encode_message(message)
            full_message = (
                IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack
            )

            writer.write(full_message)
            await writer.drain()

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise
