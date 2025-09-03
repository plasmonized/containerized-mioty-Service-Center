import asyncio
import json
import logging
import ssl
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

import bssci_config
import messages
from protocol import encode_message

logger = logging.getLogger(__name__)

IDENTIFIER = bytes("MIOTYB01", "utf-8")


class TLSServer:
    def __init__(
        self,
        sensor_config_file: str,
        mqtt_out_queue: asyncio.Queue[dict[str, str]],
        mqtt_in_queue: asyncio.Queue[dict[str, str]],
    ) -> None:
        self.opID = -1
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue
        self.connected_base_stations: Dict[
            asyncio.streams.StreamWriter, str
        ] = {}
        self.connecting_base_stations: Dict[
            asyncio.streams.StreamWriter, str
        ] = {}
        self.sensor_config_file = sensor_config_file
        # EUI -> {status, base_stations: [], timestamp}
        self.registered_sensors: Dict[str, Dict[str, Any]] = {}
        # opID -> {sensor_eui, timestamp, base_station}
        self.pending_attach_requests: Dict[int, Dict[str, Any]] = {}
        # Track if status request task is running
        self._status_task_running = False

        # Deduplication variables
        # message_key -> {message, timestamp, snr, bs_eui}
        self.deduplication_buffer: Dict[str, Dict[str, Any]] = {}
        self.deduplication_delay = bssci_config.DEDUPLICATION_DELAY
        self.deduplication_stats = {
            'total_messages': 0,
            'duplicate_messages': 0,
            'published_messages': 0
        }

        # Auto-detach variables
        # eui -> timestamp of last message
        self.sensor_last_seen: Dict[str, float] = {}
        # eui -> whether warning was sent
        self.sensor_warning_sent: Dict[str, bool] = {}

        # Start the deduplication task
        asyncio.create_task(self.process_deduplication_buffer())

        # Start auto-detach monitoring if enabled
        if getattr(bssci_config, 'AUTO_DETACH_ENABLED', True):
            asyncio.create_task(self.auto_detach_monitor())

        try:
            with open(sensor_config_file, "r") as f:
                self.sensor_config = json.load(f)
        except Exception:
            self.sensor_config = []

        # Add queue logging
        logger.info("🔍 TLS Server Queue Assignment:")
        logger.info(f"   mqtt_out_queue ID: {id(self.mqtt_out_queue)}")
        logger.info(f"   mqtt_in_queue ID: {id(self.mqtt_in_queue)}")

    def _get_local_time(self) -> str:
        """Get current time in UTC+2 timezone"""
        utc_time = datetime.now(timezone.utc)
        local_time = utc_time + timedelta(hours=2)
        return local_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

    async def start_server(self) -> None:
        """Start the TLS server"""
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
                f"{ssl_ctx.minimum_version.name} - "
                f"{ssl_ctx.maximum_version.name}"
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
            self.client_connected_cb,
            bssci_config.LISTEN_HOST,
            bssci_config.LISTEN_PORT,
            ssl=ssl_ctx,
        )

        logger.info("📨 Starting MQTT queue watcher task...")
        asyncio.create_task(self.queue_watcher())

        logger.info(
            "✓ BSSCI TLS Server is ready and listening for "
            "base station connections"
        )
        async with server:
            await server.serve_forever()

    async def send_attach_request(
        self, writer: asyncio.streams.StreamWriter, sensor: dict[str, Any]
    ) -> None:
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        # Convert EUI to hex format if it's a number
        if bs_eui != "unknown" and isinstance(bs_eui, (int, str)) and str(bs_eui).isdigit():
            bs_eui_display = f"{int(bs_eui):016X}"
        else:
            bs_eui_display = bs_eui
        
        try:
            logger.info(f"📤 BSSCI ATTACH REQUEST INITIATED")
            logger.info(f"   =====================================")
            logger.info(f"   Sensor EUI: {sensor['eui']}")
            logger.info(f"   Target Base Station: {bs_eui_display}")
            logger.info(f"   Operation ID: {self.opID}")
            logger.info(f"   Timestamp: {self._get_local_time()}")

            # Comprehensive validation with detailed logging
            validation_errors = []
            validation_warnings = []

            # EUI validation
            if len(sensor["eui"]) != 16:
                validation_errors.append(f"EUI length {len(sensor['eui'])} != 16 characters")
            else:
                try:
                    int(sensor["eui"], 16)  # Test hex validity
                    logger.info(f"   ✓ EUI format valid: {sensor['eui']}")
                except ValueError:
                    validation_errors.append(f"EUI contains invalid hex characters: {sensor['eui']}")

            # Network Key validation and normalization
            original_nw_key = sensor["nwKey"]
            nw_key = original_nw_key[:32] if len(original_nw_key) >= 32 else original_nw_key

            if len(original_nw_key) != 32:
                if len(original_nw_key) > 32:
                    validation_warnings.append(f"Network key truncated from {len(original_nw_key)} to 32 characters")
                    logger.warning(f"   ⚠️  Network key too long, truncating: {original_nw_key} -> {nw_key}")
                else:
                    validation_errors.append(f"Network key length {len(original_nw_key)} < 32 characters required")
            else:
                try:
                    int(nw_key, 16)  # Test hex validity
                    logger.info(f"   ✓ Network key format valid: {nw_key[:8]}...{nw_key[-8:]}")
                except ValueError:
                    validation_errors.append(f"Network key contains invalid hex characters: {nw_key}")

            # Short Address validation
            if len(sensor["shortAddr"]) != 4:
                validation_errors.append(f"Short address length {len(sensor['shortAddr'])} != 4 characters")
            else:
                try:
                    int(sensor["shortAddr"], 16)  # Test hex validity
                    logger.info(f"   ✓ Short address format valid: {sensor['shortAddr']}")
                except ValueError:
                    validation_errors.append(f"Short address contains invalid hex characters: {sensor['shortAddr']}")

            # Bidirectional flag validation
            bidi_value = sensor.get("bidi", False)
            logger.info(f"   ✓ Bidirectional flag: {bidi_value}")

            # Check for existing registrations to this base station
            eui_lower = sensor["eui"].lower()
            if eui_lower in self.registered_sensors:
                reg_info = self.registered_sensors[eui_lower]
                if reg_info.get('status') == 'registered':
                    existing_bases = reg_info.get('base_stations', [])
                    if bs_eui in existing_bases:
                        validation_warnings.append(f"Sensor {sensor['eui']} already registered to base station {bs_eui}")
                        logger.warning(f"   ⚠️  Re-registering sensor to same base station")
                    else:
                        validation_warnings.append(f"Sensor {sensor['eui']} already registered to {len(existing_bases)} other base station(s): {existing_bases}")
                        logger.warning(f"   ⚠️  Adding registration to additional base station")

            # Log all warnings
            for warning in validation_warnings:
                logger.warning(f"   ⚠️  {warning}")

            if not validation_errors:
                logger.info(f"   ✅ All validations passed")
                logger.info(f"   📋 Final parameters:")
                logger.info(f"     EUI: {sensor['eui']}")
                logger.info(f"     Network Key: {nw_key[:8]}...{nw_key[-8:]}")
                logger.info(f"     Short Address: {sensor['shortAddr']}")
                logger.info(f"     Bidirectional: {bidi_value}")

                # Use normalized sensor data
                normalized_sensor = {
                    "eui": sensor["eui"],
                    "nwKey": nw_key,
                    "shortAddr": sensor["shortAddr"],
                    "bidi": bidi_value
                }

                # Build and encode the message
                attach_message = messages.build_attach_request(normalized_sensor, self.opID)
                logger.debug(f"   📝 Built attach message: {attach_message}")

                msg_pack = encode_message(attach_message)
                full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack

                logger.info(f"   📤 Transmitting attach request...")
                logger.info(f"     Message size: {len(full_message)} bytes")
                logger.info(f"     Payload size: {len(msg_pack)} bytes")

                writer.write(full_message)
                await writer.drain()

                # Track this attach request for correlation with response
                self.pending_attach_requests[self.opID] = {
                    'sensor_eui': sensor['eui'],
                    'timestamp': asyncio.get_event_loop().time(),
                    'base_station': bs_eui,
                    'sensor_config': normalized_sensor
                }

                logger.info(f"✅ BSSCI ATTACH REQUEST TRANSMITTED")
                logger.info(f"   Operation ID {self.opID} sent to base station {bs_eui_display}")
                logger.info(f"   Tracking request for correlation with response")
                logger.info(f"   Awaiting response from base station...")
                logger.info(f"   =====================================")

                self.opID -= 1
            else:
                logger.error(f"❌ ATTACH REQUEST VALIDATION FAILED")
                logger.error(f"   Sensor EUI: {sensor.get('eui', 'unknown')}")
                logger.error(f"   Base Station: {bs_eui_display}")
                logger.error(f"   Validation errors found:")
                for i, error in enumerate(validation_errors, 1):
                    logger.error(f"     {i}. {error}")
                logger.error(f"   ❌ Attach request NOT sent due to validation failures")
                logger.error(f"   =====================================")

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR during attach request preparation")
            logger.error(f"   Sensor EUI: {sensor.get('eui', 'unknown')}")
            logger.error(f"   Base Station: {bs_eui_display}")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception message: {str(e)}")
            import traceback
            logger.error(f"   Full traceback:")
            for line in traceback.format_exc().strip().split('\n'):
                logger.error(f"     {line}")
            logger.error(f"   =====================================")
            raise  # Re-raise to handle upstream

    async def attach_file(self, writer: asyncio.streams.StreamWriter) -> None:
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        logger.info(f"🔗 BATCH SENSOR ATTACHMENT started for base station {bs_eui}")
        logger.info(f"   Total sensors to process: {len(self.sensor_config)}")

        successful_attachments = 0
        failed_attachments = 0

        for i, sensor in enumerate(self.sensor_config, 1):
            try:
                logger.info(f"   Processing sensor {i}/{len(self.sensor_config)}: {sensor['eui']}")
                await self.send_attach_request(writer, sensor)
                successful_attachments += 1

                # Small delay between requests to avoid overwhelming the base station
                await asyncio.sleep(0.1)

            except Exception as e:
                failed_attachments += 1
                logger.error(f"   ❌ Failed to attach sensor {sensor.get('eui', 'unknown')}: {e}")
                logger.error(f"     Exception type: {type(e).__name__}")

        logger.info(f"✅ BATCH SENSOR ATTACHMENT completed for base station {bs_eui}")
        logger.info(f"   Successful: {successful_attachments}")
        logger.info(f"   Failed: {failed_attachments}")
        logger.info(f"   Total processed: {len(self.sensor_config)}")

        if failed_attachments > 0:
            logger.warning(f"   ⚠️  {failed_attachments} sensors failed to attach - check individual sensor logs above")

    async def send_status_requests(self) -> None:
        logger.info(f"📊 STATUS REQUEST TASK STARTED")
        logger.info(f"   Status request interval: {bssci_config.STATUS_INTERVAL} seconds")

        try:
            while True:
                await asyncio.sleep(bssci_config.STATUS_INTERVAL)
                if self.connected_base_stations:
                    logger.info(f"📊 PERIODIC STATUS REQUEST CYCLE STARTING")
                    logger.info(f"   Connected base stations: {len(self.connected_base_stations)}")
                    logger.info(f"   Base stations: {list(self.connected_base_stations.values())}")

                    requests_sent = 0
                    failed_requests = 0

                    for writer, bs_eui in self.connected_base_stations.copy().items():  # Use copy to avoid dict change during iteration
                        try:
                            logger.info(f"📤 Sending status request to base station {bs_eui}")
                            logger.info(f"   Operation ID: {self.opID}")

                            msg_pack = encode_message(messages.build_status_request(self.opID))
                            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack

                            writer.write(full_message)
                            await writer.drain()
                            logger.info(f"✅ Status request transmitted to {bs_eui} (opID: {self.opID})")
                            requests_sent += 1
                            self.opID -= 1

                        except Exception as e:
                            failed_requests += 1
                            logger.error(f"❌ Failed to send status request to base station {bs_eui}")
                            logger.error(f"   Error: {type(e).__name__}: {e}")
                            logger.warning(f"🔌 Removing disconnected base station {bs_eui} from active list")
                            # Remove disconnected base station
                            if writer in self.connected_base_stations:
                                self.connected_base_stations.pop(writer)

                    logger.info(f"📊 STATUS REQUEST CYCLE COMPLETE")
                    logger.info(f"   Requests sent: {requests_sent}")
                    logger.info(f"   Failed requests: {failed_requests}")
                    logger.info(f"   Remaining connected base stations: {len(self.connected_base_stations)}")

                else:
                    logger.info(f"⏸️  STATUS REQUEST CYCLE SKIPPED - No base stations connected")

        except asyncio.CancelledError:
            logger.info(f"📊 STATUS REQUEST TASK CANCELLED")
            self._status_task_running = False
            raise
        except Exception as e:
            logger.error(f"❌ STATUS REQUEST TASK ERROR: {e}")
            self._status_task_running = False
            raise

    async def send_detach_request(self, writer: asyncio.streams.StreamWriter, sensor_eui: str) -> bool:
        """Send detach request for a specific sensor"""
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        logger.info(f"🔌 DETACHING SENSOR from base station {bs_eui}")
        logger.info(f"   Sensor EUI: {sensor_eui}")

        try:
            # Build and encode the detach message
            detach_message = messages.build_detach_request(sensor_eui, self.opID)
            logger.debug(f"   📝 Built detach message: {detach_message}")

            msg_pack = encode_message(detach_message)
            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack

            logger.info(f"   📤 Transmitting detach request...")
            logger.info(f"     Message size: {len(full_message)} bytes")

            writer.write(full_message)
            await writer.drain()
            self.opID += 1

            # Remove from registered sensors
            eui_key = sensor_eui.lower()
            if eui_key in self.registered_sensors:
                # Remove this base station from the sensor's list
                if 'base_stations' in self.registered_sensors[eui_key]:
                    self.registered_sensors[eui_key]['base_stations'] = [
                        bs for bs in self.registered_sensors[eui_key]['base_stations']
                        if bs['base_station_eui'] != bs_eui
                    ]

                    # If no base stations left, mark as not registered
                    if not self.registered_sensors[eui_key]['base_stations']:
                        self.registered_sensors[eui_key]['registered'] = False
                        logger.info(f"   ✅ Sensor {sensor_eui} fully detached from all base stations")
                    else:
                        logger.info(f"   ✅ Sensor {sensor_eui} detached from {bs_eui}, still connected to {len(self.registered_sensors[eui_key]['base_stations'])} other base stations")

            # Notify via MQTT
            if self.mqtt_out_queue:
                detach_notification = {
                    "topic": f"ep/{sensor_eui}/status",
                    "payload": json.dumps({
                        "action": "detached",
                        "sensor_eui": sensor_eui,
                        "base_station_eui": bs_eui,
                        "timestamp": asyncio.get_event_loop().time()
                    })
                }
                await self.mqtt_out_queue.put(detach_notification)

            logger.info(f"✅ DETACH REQUEST sent for sensor {sensor_eui}")
            return True

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR during detach request")
            logger.error(f"   Sensor EUI: {sensor_eui}")
            logger.error(f"   Base Station: {bs_eui}")
            logger.error(f"   Exception: {e}")
            return False

    async def detach_sensor(self, sensor_eui: str) -> bool:
        """Detach a sensor from all connected base stations"""
        logger.info(f"🔌 DETACHING SENSOR {sensor_eui} from ALL base stations")

        success_count = 0
        total_count = len(self.connected_base_stations)

        for writer in list(self.connected_base_stations.keys()):
            try:
                success = await self.send_detach_request(writer, sensor_eui)
                if success:
                    success_count += 1
                await asyncio.sleep(0.1)  # Small delay between requests
            except Exception as e:
                logger.error(f"   ❌ Failed to detach sensor {sensor_eui} from base station: {e}")

        logger.info(f"✅ SENSOR DETACH completed for {sensor_eui}")
        logger.info(f"   Successful: {success_count}/{total_count} base stations")

        return success_count > 0

    async def detach_all_sensors(self) -> int:
        """Detach all sensors from all base stations"""
        logger.info(f"🔌 DETACHING ALL SENSORS from all base stations")

        # Get list of all registered sensors
        registered_euis = [eui for eui in self.registered_sensors.keys()
                          if not eui.endswith('_failure') and self.registered_sensors[eui].get('registered', False)]

        logger.info(f"   Total registered sensors to detach: {len(registered_euis)}")

        detached_count = 0
        for sensor_eui in registered_euis:
            try:
                success = await self.detach_sensor(sensor_eui)
                if success:
                    detached_count += 1
                await asyncio.sleep(0.2)  # Small delay between sensors
            except Exception as e:
                logger.error(f"   ❌ Failed to detach sensor {sensor_eui}: {e}")

        logger.info(f"✅ BULK DETACH completed")
        logger.info(f"   Successfully detached: {detached_count}/{len(registered_euis)} sensors")

        return detached_count

    def clear_all_sensors(self) -> None:
        """Clear all sensor configurations and registrations"""
        logger.info(f"🗑️ CLEARING ALL SENSOR CONFIGURATIONS")

        # Clear sensor config
        old_count = len(self.sensor_config)
        self.sensor_config = []

        # Clear registered sensors
        old_registered = len([k for k in self.registered_sensors.keys() if not k.endswith('_failure')])
        self.registered_sensors.clear()

        # Clear pending requests
        self.pending_attach_requests.clear()

        logger.info(f"✅ ALL SENSORS CLEARED")
        logger.info(f"   Configurations removed: {old_count}")
        logger.info(f"   Registrations removed: {old_registered}")

    def detach_sensor_sync(self, sensor_eui: str) -> bool:
        """Synchronous wrapper for detaching a sensor from all connected base stations"""
        try:
            logger.info(f"🔌 SYNC DETACHING SENSOR {sensor_eui} from ALL base stations")

            success_count = 0
            total_count = len(self.connected_base_stations)

            # Remove from registered sensors immediately
            eui_key = sensor_eui.lower()
            if eui_key in self.registered_sensors:
                self.registered_sensors[eui_key]['registered'] = False
                self.registered_sensors[eui_key]['base_stations'] = []
                logger.info(f"   ✅ Sensor {sensor_eui} marked as detached in local registry")
                success_count = total_count  # Consider it successful if we can update local state

            logger.info(f"✅ SYNC SENSOR DETACH completed for {sensor_eui}")
            logger.info(f"   Local detach: {success_count}/{total_count} base stations")

            return success_count > 0

        except Exception as e:
            logger.error(f"❌ Error in sync detach for {sensor_eui}: {e}")
            return False

    def detach_all_sensors_sync(self) -> int:
        """Synchronous wrapper for detaching all sensors from all base stations"""
        try:
            logger.info(f"🔌 SYNC DETACHING ALL SENSORS from all base stations")

            # Get list of all registered sensors
            registered_euis = [eui for eui in self.registered_sensors.keys()
                              if not eui.endswith('_failure') and self.registered_sensors[eui].get('registered', False)]

            logger.info(f"   Total registered sensors to detach: {len(registered_euis)}")

            detached_count = 0
            for sensor_eui in registered_euis:
                try:
                    success = self.detach_sensor_sync(sensor_eui)
                    if success:
                        detached_count += 1
                except Exception as e:
                    logger.error(f"   ❌ Failed to sync detach sensor {sensor_eui}: {e}")

            logger.info(f"✅ SYNC BULK DETACH completed")
            logger.info(f"   Successfully detached: {detached_count}/{len(registered_euis)} sensors")

            return detached_count

        except Exception as e:
            logger.error(f"❌ Error in sync detach all: {e}")
            return 0


    async def send_status_requests(self) -> None:
        logger.info(f"📊 STATUS REQUEST TASK STARTED")
        logger.info(f"   Status request interval: {bssci_config.STATUS_INTERVAL} seconds")

        try:
            while True:
                await asyncio.sleep(bssci_config.STATUS_INTERVAL)
                if self.connected_base_stations:
                    logger.info(f"📊 PERIODIC STATUS REQUEST CYCLE STARTING")
                    logger.info(f"   Connected base stations: {len(self.connected_base_stations)}")
                    logger.info(f"   Base stations: {list(self.connected_base_stations.values())}")

                    for writer in list(self.connected_base_stations.keys()):
                        try:
                            bs_eui = self.connected_base_stations.get(writer, "unknown")
                            logger.info(f"   📊 Sending status request to {bs_eui}")

                            status_message = messages.build_status_request(self.opID)
                            msg_pack = encode_message(status_message)
                            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack

                            writer.write(full_message)
                            await writer.drain()
                            self.opID += 1

                        except Exception as e:
                            logger.error(f"   ❌ Failed to send status to {bs_eui}: {e}")

                    logger.info(f"📊 STATUS REQUEST CYCLE COMPLETED")
                else:
                    logger.debug(f"📊 No base stations connected - skipping status requests")

        except Exception as e:
            logger.error(f"❌ STATUS REQUEST TASK FAILED: {e}")
            raise

    async def client_connected_cb(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Wrapper for client connection callback to handle exceptions properly"""
        try:
            await self.handle_client(reader, writer)
        except Exception as e:
            addr = writer.get_extra_info('peername', 'unknown')
            if "EOF occurred in violation of protocol" in str(e) or "SSL" in str(e):
                logger.debug(f"SSL connection from {addr} closed normally")
            else:
                logger.error(f"Unhandled exception in client handler for {addr}: {e}")
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle incoming client connections"""
        addr = writer.get_extra_info('peername')
        logger.info(f"🔗 New connection from {addr}")

        connection_start_time = asyncio.get_event_loop().time()
        message_count = 0
        base_station_eui = None

        try:
            # Add to connecting base stations
            self.connecting_base_stations[writer] = None

            while True:
                try:
                    # Read BSSCI protocol identifier (8 bytes)
                    identifier_data = await asyncio.wait_for(reader.read(8), timeout=60.0)
                    if not identifier_data:
                        logger.info(f"🔌 Connection from {addr} closed by client")
                        break
                    
                    if len(identifier_data) != 8:
                        logger.error(f"❌ Incomplete identifier from {addr}: expected 8 bytes, got {len(identifier_data)}")
                        break
                    
                    # Verify BSSCI identifier
                    if identifier_data != IDENTIFIER:
                        logger.error(f"❌ Invalid protocol identifier from {addr}: {identifier_data}")
                        break

                    # Read message length (4 bytes, little-endian)
                    length_data = await asyncio.wait_for(reader.read(4), timeout=60.0)
                    if not length_data or len(length_data) != 4:
                        logger.error(f"❌ Incomplete length data from {addr}")
                        break

                    message_length = int.from_bytes(length_data, byteorder='little')
                    if message_length > 10000:  # Reasonable limit
                        logger.warning(f"⚠️  Unusually large message ({message_length} bytes) from {addr}")

                    # Read the actual message
                    message_data = await asyncio.wait_for(reader.read(message_length), timeout=60.0)
                    if len(message_data) != message_length:
                        logger.error(f"❌ Incomplete message from {addr}: expected {message_length}, got {len(message_data)}")
                        break

                    # Parse and handle the message using msgpack
                    try:
                        import msgpack
                        unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
                        unpacker.feed(message_data)
                        message = None
                        for msg in unpacker:
                            message = msg
                            break
                        
                        if message is None:
                            logger.error(f"❌ Failed to decode message from {addr}")
                            continue
                            
                        message_count += 1

                        logger.info(f"📨 BSSCI message #{message_count} received from {addr}")
                        logger.info(f"   Message type: {message.get('command', 'unknown')}")
                        logger.debug(f"   Full message: {message}")

                        # Handle the message and get base station EUI
                        bs_eui = await self.handle_message(message, writer)
                        if bs_eui and not base_station_eui:
                            base_station_eui = bs_eui
                            # Move from connecting to connected
                            self.connecting_base_stations.pop(writer, None)
                            self.connected_base_stations[writer] = bs_eui
                            logger.info(f"✅ Base station {bs_eui} fully connected from {addr}")

                    except Exception as e:
                        logger.error(f"❌ Error processing message from {addr}: {e}")
                        logger.debug(f"Raw message data: {message_data.hex()}")
                        continue

                except asyncio.TimeoutError:
                    logger.warning(f"⏰ Timeout waiting for data from {addr}")
                    break
                except (ConnectionResetError, BrokenPipeError, OSError) as e:
                    logger.info(f"🔌 Connection from {addr} closed: {e}")
                    break
                except Exception as e:
                    if "EOF occurred in violation of protocol" in str(e) or "SSL" in str(e):
                        logger.info(f"🔌 SSL connection from {addr} closed by remote")
                        break
                    logger.error(f"❌ Error reading from {addr}: {e}")
                    break

        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.info(f"🔌 Connection from {addr} closed: {e}")
        except Exception as e:
            if "EOF occurred in violation of protocol" in str(e) or "SSL" in str(e):
                logger.info(f"🔌 SSL connection from {addr} closed by remote")
            else:
                logger.error(f"❌ Connection error from {addr}: {e}")
        finally:
            # Clean up connection tracking
            self.connecting_base_stations.pop(writer, None)
            if base_station_eui:
                self.connected_base_stations.pop(writer, None)
                logger.info(f"🔌 Base station {base_station_eui} disconnected from {addr}")
            else:
                logger.info(f"🔌 Connection to {addr} closed")

            connection_duration = asyncio.get_event_loop().time() - connection_start_time
            logger.info(f"   Connection duration: {connection_duration:.2f} seconds")
            logger.info(f"   Messages processed: {message_count}")

            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.debug(f"Error closing connection to {addr}: {e}")

            # Save sensor configuration after connection closes
            self.save_sensor_config()

    async def handle_message(self, message: dict, writer: asyncio.StreamWriter) -> str:
        """Handle incoming BSSCI protocol messages from base stations"""
        command = message.get('command', 'unknown')
        
        if command == 'con':
            # Connection establishment message from base station
            bs_eui = message.get('bsEui')
            if bs_eui:
                # Convert EUI to proper hex format for display
                bs_eui_hex = f"{bs_eui:016X}"
                logger.info(f"🏢 Base station connecting with EUI: {bs_eui_hex}")
                logger.info(f"   Model: {message.get('model', 'unknown')}")
                logger.info(f"   Vendor: {message.get('vendor', 'unknown')}")
                logger.info(f"   SW Version: {message.get('swVersion', 'unknown')}")
                
                # Send connection response
                await self.send_connection_response(writer, message)
                
                # Schedule attach requests after connection stabilizes
                logger.info(f"✅ Base station {bs_eui_hex} connection established, scheduling attach requests")
                asyncio.create_task(self.schedule_attach_requests(writer, bs_eui_hex))
                
                return bs_eui_hex
            else:
                logger.warning("Connection message missing base station EUI")
                
        elif command == 'conRsp':
            # Connection response from base station
            logger.debug(f"Connection response received: {message}")
            
        elif command == 'error':
            # Error message from base station
            error_code = message.get('code', 'unknown')
            error_msg = message.get('message', 'no details')
            logger.error(f"🚨 Base station error {error_code}: {error_msg}")
            logger.debug(f"Full error message: {message}")
            
        elif command == 'conCmp':
            # Connection complete from base station
            logger.info(f"✅ Connection complete received from base station")
            logger.debug(f"Connection complete message: {message}")
            # Connection is now fully established according to BSSCI spec
            
        elif command == 'attPrp':
            # Attach prepare response
            eui = message.get('eui')
            result = message.get('result', 'unknown')
            logger.info(f"📡 Attach prepare response for {eui}: {result}")
            
        elif command == 'attPrpRsp':
            # Attach propagate response from base station
            op_id = message.get('opId')
            result = message.get('result', 'success')  # Default to success if not specified
            logger.info(f"✅ Attach propagate response received (opId: {op_id}): {result}")
            logger.debug(f"Full attach propagate response: {message}")
            
            # Record successful sensor registration with base station
            if op_id in self.pending_attach_requests:
                attach_info = self.pending_attach_requests[op_id]
                sensor_eui = attach_info.get('sensor_eui', '').lower()
                base_station_eui = attach_info.get('base_station')
                
                if sensor_eui and base_station_eui:
                    # Initialize sensor registration if not exists
                    if sensor_eui not in self.registered_sensors:
                        self.registered_sensors[sensor_eui] = {
                            'base_stations': [],
                            'timestamp': asyncio.get_event_loop().time()
                        }
                    
                    # Add base station if not already registered
                    if base_station_eui not in self.registered_sensors[sensor_eui]['base_stations']:
                        self.registered_sensors[sensor_eui]['base_stations'].append(base_station_eui)
                        logger.info(f"📋 Sensor {sensor_eui.upper()} now registered with {len(self.registered_sensors[sensor_eui]['base_stations'])} base stations")
                        logger.info(f"   Base stations: {', '.join(self.registered_sensors[sensor_eui]['base_stations'])}")
                
                # Remove from pending requests
                del self.pending_attach_requests[op_id]
            
        elif command == 'statusCmp':
            # Status complete message
            eui = message.get('eui')
            logger.debug(f"Status complete for {eui}: {message}")
            
        elif command == 'ulDataRsp':
            # Uplink data response
            eui = message.get('eui')
            logger.debug(f"Uplink data response for {eui}: {message}")
            
        elif command == 'ulDataInd':
            # Uplink data indication - sensor data received
            await self.handle_sensor_data(message, writer)
            
        else:
            logger.warning(f"Unknown BSSCI command: {command}")
            logger.debug(f"Full message: {message}")
            
        return None

    async def send_connection_response(self, writer: asyncio.StreamWriter, con_message: dict) -> None:
        """Send connection response to base station"""
        try:
            import msgpack
            
            # Build connection response according to BSSCI spec v1.0.0 section 5.3.2
            response = {
                "command": "conRsp",
                "opId": con_message.get('opId', 0),  # Required: Match the opId from request
                "scEui": 0x001122334455667788,  # Required: Service Center EUI64
                "version": "1.0.0",  # Optional: Supported protocol version
                "vendor": "BSSCI Service Center",  # Optional: Vendor name
                "model": "Python Implementation",  # Optional: Model name
                "name": "BSSCI-SC",  # Optional: Service Center name
                "swVersion": "1.0.0",  # Optional: Software version
                "snResume": False,  # Optional: Not resuming previous session
                "snScUuid": [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0, 
                            0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]  # Required: SC session UUID (16 bytes)
            }
            
            # Encode response
            response_data = msgpack.packb(response)
            
            # Send with BSSCI protocol format
            message_length = len(response_data)
            full_message = IDENTIFIER + message_length.to_bytes(4, 'little') + response_data
            
            writer.write(full_message)
            await writer.drain()
            
            logger.debug(f"Sent connection response: {response}")
            
        except Exception as e:
            logger.error(f"Failed to send connection response: {e}")

    async def handle_sensor_data(self, message: dict, writer: asyncio.StreamWriter) -> None:
        """Handle incoming sensor data from base stations"""
        try:
            eui = message.get('eui')
            if not eui:
                return
                
            # Add message to deduplication buffer
            await self.add_to_deduplication_buffer(message, writer)
            
        except Exception as e:
            logger.error(f"Error handling sensor data: {e}")

    async def schedule_attach_requests(self, writer: asyncio.StreamWriter, bs_eui: str) -> None:
        """Schedule attach requests to be sent after connection stabilizes"""
        try:
            # Wait for connection to stabilize
            await asyncio.sleep(2.0)
            
            # Check if connection is still active
            if writer in self.connected_base_stations:
                logger.info(f"📤 Sending delayed attach requests to base station {bs_eui}")
                
                successful_attachments = 0
                for sensor in self.sensor_config:
                    try:
                        await self.send_attach_request(writer, sensor)
                        successful_attachments += 1
                        await asyncio.sleep(0.2)  # Small delay between requests
                    except Exception as e:
                        logger.error(f"Failed to send delayed attach request for {sensor.get('eui')}: {e}")
                        break  # Stop if connection fails
                
                logger.info(f"✅ Sent {successful_attachments}/{len(self.sensor_config)} attach requests to {bs_eui}")
            else:
                logger.warning(f"⚠️  Base station {bs_eui} disconnected before attach requests could be sent")
                
        except Exception as e:
            logger.error(f"Error in scheduled attach requests for {bs_eui}: {e}")

    async def process_deduplication_buffer(self) -> None:
        """Processes the deduplication buffer, forwards best messages, and cleans up old entries."""
        logger.info(f"🧠 Starting deduplication buffer processing task with delay: {self.deduplication_delay}s")
        while True:
            await asyncio.sleep(self.deduplication_delay)
            current_time = asyncio.get_event_loop().time()

            # Find messages that have been in the buffer longer than the delay
            messages_to_publish = []
            for key, value in list(self.deduplication_buffer.items()): # Use list to allow modification during iteration
                if current_time - value['timestamp'] >= self.deduplication_delay:
                    messages_to_publish.append((key, value))
                    del self.deduplication_buffer[key] # Remove from buffer

            # Sort messages to publish by SNR (highest first)
            messages_to_publish.sort(key=lambda item: item[1]['snr'], reverse=True)

            for message_key, message_data in messages_to_publish:
                message = message_data['message']
                bs_eui = message_data['bs_eui']
                eui = int(message["epEui"]).to_bytes(8, byteorder="big").hex()
                snr = message_data['snr']
                packet_cnt = message["packetCnt"]

                data_dict = {
                    "bs_eui": bs_eui,
                    "rxTime": message["rxTime"],
                    "snr": snr,
                    "rssi": message["rssi"],
                    "cnt": packet_cnt,
                    "data": message["userData"],
                }

                mqtt_topic = f"ep/{eui}/ul"
                payload_json = json.dumps(data_dict)

                logger.info(f"📤 PUBLISHING DEDUPLICATED MESSAGE")
                logger.info(f"   =====================================")
                logger.info(f"   Full Topic: {bssci_config.BASE_TOPIC.rstrip('/')}/{mqtt_topic}")
                logger.info(f"   Sensor EUI: {eui}")
                logger.info(f"   Base Station: {bs_eui}")
                logger.info(f"   Payload Size: {len(payload_json)} bytes")
                logger.info(f"   Data Preview: SNR={data_dict['snr']:.1f}dB, RSSI={data_dict['rssi']:.1f}dBm, Count={data_dict['cnt']}")
                logger.info(f"   Queue size before add: {self.mqtt_out_queue.qsize()}")
                logger.debug(f"   Full Payload: {payload_json}")

                try:
                    await self.mqtt_out_queue.put(
                        {"topic": mqtt_topic, "payload": payload_json}
                    )
                    logger.info(f"✅ DEDUPLICATED MQTT message queued successfully")
                    logger.info(f"   Queue size after add: {self.mqtt_out_queue.qsize()}")

                    # Update statistics
                    self.deduplication_stats['published_messages'] += 1
                    total_msg = self.deduplication_stats['total_messages']
                    dup_msg = self.deduplication_stats['duplicate_messages']
                    pub_msg = self.deduplication_stats['published_messages']
                    dup_rate = (dup_msg / total_msg * 100) if total_msg > 0 else 0

                    logger.info(f"📊 DEDUPLICATION STATISTICS:")
                    logger.info(f"   Total messages received: {total_msg}")
                    logger.info(f"   Duplicate messages filtered: {dup_msg}")
                    logger.info(f"   Messages published: {pub_msg}")
                    logger.info(f"   Duplication rate: {dup_rate:.1f}%")

                except Exception as mqtt_err:
                    logger.error(f"❌ FAILED to queue deduplicated MQTT message")
                    logger.error(f"   Error: {type(mqtt_err).__name__}: {mqtt_err}")
                    logger.error(f"   Topic: {mqtt_topic}")
                    logger.error(f"   Payload: {payload_json}")
                logger.info(f"   =======================================")

            # Clean up old entries from the buffer that were not published
            oldest_allowed_time = current_time - (self.deduplication_delay * 2) # Keep entries for a bit longer to ensure they are processed
            for key, value in list(self.deduplication_buffer.items()):
                 if current_time - value['timestamp'] > oldest_allowed_time:
                     logger.warning(f"   🧹 Cleaning up old unduplicated message from buffer: {key}")
                     del self.deduplication_buffer[key]

    async def auto_detach_monitor(self) -> None:
        """Monitor sensors for auto-detach based on inactivity"""
        logger.info(f"🕐 AUTO-DETACH MONITOR STARTED")
        logger.info(f"   Auto-detach timeout: {getattr(bssci_config, 'AUTO_DETACH_TIMEOUT', 259200)} seconds ({getattr(bssci_config, 'AUTO_DETACH_TIMEOUT', 259200) / 3600:.1f} hours)")
        logger.info(f"   Warning timeout: {getattr(bssci_config, 'AUTO_DETACH_WARNING_TIMEOUT', 129600)} seconds ({getattr(bssci_config, 'AUTO_DETACH_WARNING_TIMEOUT', 129600) / 3600:.1f} hours)")
        logger.info(f"   Check interval: {getattr(bssci_config, 'AUTO_DETACH_CHECK_INTERVAL', 3600)} seconds")

        try:
            while True:
                await asyncio.sleep(getattr(bssci_config, 'AUTO_DETACH_CHECK_INTERVAL', 3600))
                current_time = asyncio.get_event_loop().time()

                auto_detach_timeout = getattr(bssci_config, 'AUTO_DETACH_TIMEOUT', 259200)
                warning_timeout = getattr(bssci_config, 'AUTO_DETACH_WARNING_TIMEOUT', 129600)

                sensors_to_detach = []
                sensors_to_warn = []

                # Check all registered sensors
                for eui_key, sensor_info in list(self.registered_sensors.items()):
                    if eui_key.endswith('_failure') or not sensor_info.get('registered', False):
                        continue

                    last_seen = self.sensor_last_seen.get(eui_key, sensor_info.get('timestamp', 0))
                    time_since_last_seen = current_time - last_seen

                    # Check for auto-detach
                    if time_since_last_seen > auto_detach_timeout:
                        sensors_to_detach.append((eui_key, time_since_last_seen))

                    # Check for warning (only if not already sent and not scheduled for detach)
                    elif (time_since_last_seen > warning_timeout and
                          not self.sensor_warning_sent.get(eui_key, False) and
                          eui_key not in [s[0] for s in sensors_to_detach]):
                        sensors_to_warn.append((eui_key, time_since_last_seen))

                # Process warnings
                for eui_key, inactive_time in sensors_to_warn:
                    await self.send_inactivity_warning(eui_key, inactive_time, warning_timeout, auto_detach_timeout)
                    self.sensor_warning_sent[eui_key] = True

                # Process auto-detaches
                for eui_key, inactive_time in sensors_to_detach:
                    await self.auto_detach_inactive_sensor(eui_key, inactive_time)

                if sensors_to_detach or sensors_to_warn:
                    logger.info(f"🕐 AUTO-DETACH MONITOR CYCLE COMPLETE")
                    logger.info(f"   Warnings sent: {len(sensors_to_warn)}")
                    logger.info(f"   Sensors auto-detached: {len(sensors_to_detach)}")
                elif len(self.registered_sensors) > 0:
                    logger.debug(f"🕐 AUTO-DETACH MONITOR: All {len(self.registered_sensors)} sensors within activity thresholds")

        except asyncio.CancelledError:
            logger.info(f"🕐 AUTO-DETACH MONITOR CANCELLED")
            raise
        except Exception as e:
            logger.error(f"❌ AUTO-DETACH MONITOR ERROR: {e}")
            raise

    async def send_inactivity_warning(self, eui_key: str, inactive_time: float, warning_timeout: float, detach_timeout: float) -> None:
        """Send warning notification for inactive sensor"""
        eui = eui_key.upper()
        hours_inactive = inactive_time / 3600
        hours_until_detach = (detach_timeout - inactive_time) / 3600

        logger.warning(f"⚠️  SENSOR INACTIVITY WARNING")
        logger.warning(f"   Sensor EUI: {eui}")
        logger.warning(f"   Inactive for: {hours_inactive:.1f} hours")
        logger.warning(f"   Warning threshold: {warning_timeout / 3600:.1f} hours")
        logger.warning(f"   Auto-detach in: {hours_until_detach:.1f} hours")

        # Update sensor status with warning
        if eui_key in self.registered_sensors:
            self.registered_sensors[eui_key]['warning_status'] = {
                'active': True,
                'inactive_hours': round(hours_inactive, 1),
                'hours_until_detach': round(hours_until_detach, 1),
                'warning_sent_time': self._get_local_time()
            }

        # Send MQTT warning notification
        if self.mqtt_out_queue:
            warning_payload = {
                "action": "inactivity_warning",
                "sensor_eui": eui,
                "inactive_hours": round(hours_inactive, 1),
                "hours_until_detach": round(hours_until_detach, 1),
                "warning_threshold_hours": warning_timeout / 3600,
                "detach_threshold_hours": detach_timeout / 3600,
                "timestamp": asyncio.get_event_loop().time()
            }

            await self.mqtt_out_queue.put({
                "topic": f"ep/{eui}/warning",
                "payload": json.dumps(warning_payload)
            })

            logger.warning(f"📤 Inactivity warning notification sent via MQTT for {eui}")

    async def auto_detach_inactive_sensor(self, eui_key: str, inactive_time: float) -> None:
        """Auto-detach a sensor due to inactivity"""
        eui = eui_key.upper()
        hours_inactive = inactive_time / 3600

        logger.warning(f"🔌 AUTO-DETACH TRIGGERED")
        logger.warning(f"   Sensor EUI: {eui}")
        logger.warning(f"   Inactive for: {hours_inactive:.1f} hours")
        logger.warning(f"   Threshold: {getattr(bssci_config, 'AUTO_DETACH_TIMEOUT', 259200) / 3600:.1f} hours")

        # Perform detach
        success = await self.detach_sensor(eui)

        if success:
            # Update sensor status to indicate auto-detach
            if eui_key in self.registered_sensors:
                self.registered_sensors[eui_key]['auto_detached'] = {
                    'detached': True,
                    'reason': 'inactivity',
                    'inactive_hours': round(hours_inactive, 1),
                    'detach_time': self._get_local_time()
                }

            # Remove from last seen and warning tracking
            self.sensor_last_seen.pop(eui_key, None)
            self.sensor_warning_sent.pop(eui_key, None)

            logger.warning(f"✅ AUTO-DETACH COMPLETED for sensor {eui}")

            # Send MQTT auto-detach notification
            if self.mqtt_out_queue:
                detach_payload = {
                    "action": "auto_detached",
                    "sensor_eui": eui,
                    "reason": "inactivity",
                    "inactive_hours": round(hours_inactive, 1),
                    "threshold_hours": getattr(bssci_config, 'AUTO_DETACH_TIMEOUT', 259200) / 3600,
                    "timestamp": asyncio.get_event_loop().time()
                }

                await self.mqtt_out_queue.put({
                    "topic": f"ep/{eui}/status",
                    "payload": json.dumps(detach_payload)
                })

                logger.warning(f"📤 Auto-detach notification sent via MQTT for {eui}")
        else:
            logger.error(f"❌ AUTO-DETACH FAILED for sensor {eui}")

            # Send MQTT failure notification
            if self.mqtt_out_queue:
                failure_payload = {
                    "action": "auto_detach_failed",
                    "sensor_eui": eui,
                    "inactive_hours": round(hours_inactive, 1),
                    "timestamp": asyncio.get_event_loop().time()
                }

                await self.mqtt_out_queue.put({
                    "topic": f"ep/{eui}/error",
                    "payload": json.dumps(failure_payload)
                })


    async def queue_watcher(self) -> None:
        logger.info("📨 MQTT queue watcher started - monitoring for configuration updates")
        logger.info(f"   Watching queue ID: {id(self.mqtt_in_queue)}")
        try:
            while True:
                logger.debug(f"⏳ Queue watcher waiting for message (queue size: {self.mqtt_in_queue.qsize()})")
                msg = dict(await self.mqtt_in_queue.get())
                logger.info(f"📥 MQTT CONFIGURATION MESSAGE received")
                logger.debug(f"   Raw message: {msg}")

                if (
                    "eui" in msg.keys()
                    and "nwKey" in msg.keys()
                    and "shortAddr" in msg.keys()
                    and "bidi" in msg.keys()
                ):
                    logger.info(f"🔧 PROCESSING ENDPOINT CONFIGURATION")
                    logger.info(f"   Endpoint EUI: {msg['eui']}")
                    logger.info(f"   Short Address: {msg['shortAddr']}")
                    logger.info(f"   Network Key: {msg['nwKey'][:8]}...{msg['nwKey'][-8:]}")
                    logger.info(f"   Bidirectional: {msg['bidi']}")

                    if self.connected_base_stations:
                        logger.info(f"📤 PROPAGATING to {len(self.connected_base_stations)} connected base stations")
                        for writer, bs_eui in self.connected_base_stations.items():
                            logger.info(f"   Sending attach request to base station: {bs_eui}")
                            await self.send_attach_request(writer, msg)
                    else:
                        logger.warning("⚠️  NO BASE STATIONS CONNECTED")
                        logger.warning("   Configuration saved but attach requests will be sent when base stations connect")

                    logger.info(f"💾 UPDATING local configuration file")
                    self.update_or_add_entry(msg)
                    logger.info(f"✅ ENDPOINT CONFIGURATION processing complete for {msg['eui']}")
                else:
                    logger.error(f"❌ INVALID MQTT configuration message - missing required fields")
                    logger.error(f"   Required: eui, nwKey, shortAddr, bidi")
                    logger.error(f"   Received: {list(msg.keys())}")
        except asyncio.CancelledError:
            logger.info("📨 MQTT queue watcher stopped")
        except Exception as e:
            logger.error(f"❌ Error in MQTT queue watcher: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")

    def get_base_station_status(self) -> dict:
        """Get status of connected base stations"""
        connected_stations = []
        for writer, bs_eui in self.connected_base_stations.items():
            addr = writer.get_extra_info("peername")
            ssl_obj = writer.get_extra_info("ssl_object")

            station_info = {
                "eui": bs_eui,
                "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                "status": "connected"
            }

            # Add SSL certificate info if available
            if ssl_obj:
                try:
                    cert = ssl_obj.getpeercert()
                    if cert:
                        subject = cert.get('subject', [])
                        for field in subject:
                            for name, value in field:
                                if name == 'commonName':
                                    station_info['certificate_cn'] = value
                                    break
                except:
                    pass

            connected_stations.append(station_info)

        connecting_stations = []
        for writer, bs_eui in self.connecting_base_stations.items():
            addr = writer.get_extra_info("peername")
            connecting_stations.append({
                "eui": bs_eui,
                "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                "status": "connecting"
            })

        return {
            "connected": connected_stations,
            "connecting": connecting_stations,
            "total_connected": len(connected_stations),
            "total_connecting": len(connecting_stations)
        }

    def reload_sensor_config(self) -> None:
        """Reload sensor configuration from file"""
        try:
            with open(self.sensor_config_file, "r") as f:
                new_config = json.load(f)

            old_count = len(self.sensor_config)
            self.sensor_config = new_config
            new_count = len(self.sensor_config)

            logger.info(f"Sensor configuration reloaded: {old_count} -> {new_count} sensors")

            # Clear registration status for removed sensors
            configured_euis = {sensor['eui'].lower() for sensor in self.sensor_config}
            removed_euis = set(self.registered_sensors.keys()) - configured_euis
            for eui in removed_euis:
                self.registered_sensors.pop(eui, None)
                logger.info(f"Removed registration status for deleted sensor: {eui}")

        except Exception as e:
            logger.error(f"Failed to reload sensor configuration: {e}")

    def get_sensor_registration_status(self) -> Dict[str, Dict[str, Any]]:
        """Get registration status of all sensors"""
        status = {}
        # Use time.time() instead of asyncio event loop time for Flask thread compatibility
        try:
            # Try to get asyncio event loop time if available
            current_time = asyncio.get_event_loop().time()
        except RuntimeError:
            # Fall back to standard time if no event loop is running (Flask threads)
            import time
            current_time = time.time()

        for sensor in self.sensor_config:
            eui = sensor['eui'].lower()
            reg_info = self.registered_sensors.get(eui, {})

            # Get preferred downlink path from sensor config or from instance attribute
            preferred_path = sensor.get('preferredDownlinkPath', None)
            if hasattr(self, 'preferred_downlink_paths') and eui in self.preferred_downlink_paths:
                preferred_path = self.preferred_downlink_paths[eui]

            # Calculate activity status
            last_seen = self.sensor_last_seen.get(eui, reg_info.get('timestamp', 0))
            time_since_last_seen = current_time - last_seen if last_seen > 0 else 0
            hours_since_last_seen = time_since_last_seen / 3600

            # Determine activity status
            activity_status = "active"
            warning_info = None
            auto_detach_info = None

            if getattr(bssci_config, 'AUTO_DETACH_ENABLED', True) and last_seen > 0:
                warning_timeout = getattr(bssci_config, 'AUTO_DETACH_WARNING_TIMEOUT', 129600)
                detach_timeout = getattr(bssci_config, 'AUTO_DETACH_TIMEOUT', 259200)

                if time_since_last_seen > detach_timeout:
                    activity_status = "auto_detach_pending"
                elif time_since_last_seen > warning_timeout:
                    activity_status = "warning"
                    warning_info = {
                        'hours_inactive': round(hours_since_last_seen, 1),
                        'hours_until_detach': round((detach_timeout - time_since_last_seen) / 3600, 1),
                        'warning_sent': self.sensor_warning_sent.get(eui, False)
                    }

            # Check for auto-detach info from registration
            if 'auto_detached' in reg_info:
                auto_detach_info = reg_info['auto_detached']
                activity_status = "auto_detached"

            status[eui] = {
                'eui': sensor['eui'],
                'nwKey': sensor['nwKey'],
                'shortAddr': sensor['shortAddr'],
                'bidi': sensor['bidi'],
                'registered': eui in self.registered_sensors,
                'registration_info': reg_info,
                'base_stations': reg_info.get('base_stations', []),
                'total_registrations': len(reg_info.get('base_stations', [])),
                'preferredDownlinkPath': preferred_path,
                'activity_status': activity_status,
                'last_seen_timestamp': last_seen,
                'hours_since_last_seen': round(hours_since_last_seen, 1) if last_seen > 0 else None,
                'warning_info': warning_info,
                'auto_detach_info': auto_detach_info,
                'warning_status': reg_info.get('warning_status', None)
            }
        return status

    def clear_all_sensors(self) -> None:
        """Clear all sensor configurations and registrations"""
        logger.info(f"🗑️ CLEARING ALL SENSOR CONFIGURATIONS")

        # Clear sensor config
        old_count = len(self.sensor_config)
        self.sensor_config = []

        # Clear registered sensors
        old_registered = len([k for k in self.registered_sensors.keys() if not k.endswith('_failure')])
        self.registered_sensors.clear()

        # Clear pending requests
        self.pending_attach_requests.clear()

        logger.info(f"✅ ALL SENSORS CLEARED")
        logger.info(f"   Configurations removed: {old_count}")
        logger.info(f"   Registrations removed: {old_registered}")

    def update_preferred_downlink_path(self, eui: str, bs_eui: str, snr: float) -> None:
        """Update the preferred downlink path for a sensor based on signal quality"""
        eui_lower = eui.lower()

        # Find the sensor in configuration
        for sensor in self.sensor_config:
            if sensor["eui"].lower() == eui_lower:
                # Update preferred downlink path
                if "preferredDownlinkPath" not in sensor:
                    sensor["preferredDownlinkPath"] = {}

                sensor["preferredDownlinkPath"] = {
                    "baseStation": bs_eui,
                    "snr": round(snr, 2),
                    "lastUpdated": self._get_local_time(),
                    "messageCount": sensor["preferredDownlinkPath"].get("messageCount", 0) + 1
                }

                logger.info(f"📊 PREFERRED PATH UPDATED for sensor {eui}")
                logger.info(f"   Base Station: {bs_eui}")
                logger.info(f"   SNR: {snr:.2f} dB")
                logger.info(f"   Total messages: {sensor['preferredDownlinkPath']['messageCount']}")

                # Save configuration
                try:
                    with open(self.sensor_config_file, "w") as f:
                        json.dump(self.sensor_config, f, indent=4)
                except Exception as e:
                    logger.error(f"Failed to save preferred downlink path: {e}")
                break
        else:
            logger.warning(f"⚠️  Sensor {eui} not found in configuration for preferred path update")

    def update_or_add_entry(self, msg: dict[str, Any]) -> None:
        # Update existing entry or add new one
        for sensor in self.sensor_config:
            if sensor["eui"].lower() == msg["eui"].lower():
                sensor["nwKey"] = msg["nwKey"]
                sensor["shortAddr"] = msg["shortAddr"]
                sensor["bidi"] = msg["bidi"]
                logger.info(f"Updated configuration for existing endpoint {msg['eui']}")
                break
        else:
            # No existing entry found → add new one
            self.sensor_config.append(
                {
                    "eui": msg["eui"],
                    "nwKey": msg["nwKey"],
                    "shortAddr": msg["shortAddr"],
                    "bidi": msg["bidi"],
                }
            )
            logger.info(f"Added new endpoint configuration for {msg['eui']}")

        # Save updated configuration to file
        try:
            with open(self.sensor_config_file, "w") as f:
                json.dump(self.sensor_config, f, indent=4)
            logger.info(f"Configuration saved to {self.sensor_config_file}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")

    async def process_mqtt_messages(self) -> None:
        """Process incoming MQTT messages for sensor configuration and commands"""
        logger.info("🔄 MQTT MESSAGE PROCESSOR STARTING")
        logger.info(f"   Monitoring queue ID: {id(self.mqtt_in_queue)}")

        message_count = 0
        try:
            while True:
                logger.debug(f"⏳ Waiting for MQTT message (queue size: {self.mqtt_in_queue.qsize()})")
                message = await self.mqtt_in_queue.get()
                message_count += 1

                logger.info(f"🎉 MQTT MESSAGE #{message_count} RECEIVED!")
                logger.info(f"   EUI: {message.get('eui', 'unknown')}")
                logger.info(f"   Message Type: {message.get('message_type', 'config')}")
                logger.info(f"   Message Keys: {list(message.keys())}")

                try:
                    message_type = message.get('message_type', 'config')

                    if message_type == 'command':
                        # Process command messages
                        await self.process_mqtt_command(message)
                    else:
                        # Process configuration messages
                        # Validate required fields
                        required_fields = ['eui', 'nwKey', 'shortAddr']
                        missing_fields = [field for field in required_fields if field not in message]

                        if missing_fields:
                            logger.error(f"❌ Invalid sensor configuration - missing fields: {missing_fields}")
                            continue

                        # Process the sensor configuration
                        await self.process_sensor_config(message)

                except Exception as e:
                    logger.error(f"❌ Failed to process MQTT message: {e}")
                    logger.error(f"   Message: {message}")

        except Exception as e:
            logger.error(f"❌ MQTT MESSAGE PROCESSOR FAILED: {e}")
            raise

    async def process_mqtt_command(self, command: dict) -> None:
        """Process MQTT command messages"""
        eui = command.get('eui')
        action = command.get('action', '').lower()

        logger.info(f"🎯 PROCESSING MQTT COMMAND for {eui}: {action}")

        try:
            if action == 'detach':
                # Detach sensor from all base stations
                success = await self.detach_sensor(eui)

                # Send response
                response_payload = {
                    "action": "detach_response",
                    "sensor_eui": eui,
                    "success": success,
                    "timestamp": asyncio.get_event_loop().time()
                }

                await self.mqtt_out_queue.put({
                    "topic": f"ep/{eui}/response",
                    "payload": json.dumps(response_payload)
                })

                logger.info(f"✅ DETACH command processed for {eui}, success: {success}")

            elif action == 'attach':
                # Find sensor in config and attach
                sensor_config = None
                for sensor in self.sensor_config:
                    if sensor['eui'].lower() == eui.lower():
                        sensor_config = sensor
                        break

                if sensor_config:
                    # Attach to all connected base stations
                    success_count = 0
                    for writer in list(self.connected_base_stations.keys()):
                        try:
                            await self.send_attach_request(writer, sensor_config)
                            success_count += 1
                            await asyncio.sleep(0.1)
                        except Exception as e:
                            logger.error(f"Failed to attach {eui} to base station: {e}")

                    success = success_count > 0
                else:
                    logger.error(f"Sensor {eui} not found in configuration")
                    success = False

                # Send response
                response_payload = {
                    "action": "attach_response",
                    "sensor_eui": eui,
                    "success": success,
                    "attached_to": success_count if success else 0,
                    "timestamp": asyncio.get_event_loop().time()
                }

                await self.mqtt_out_queue.put({
                    "topic": f"ep/{eui}/response",
                    "payload": json.dumps(response_payload)
                })

                logger.info(f"✅ ATTACH command processed for {eui}, success: {success}")

            elif action == 'status':
                # Get sensor status
                eui_key = eui.lower()
                if eui_key in self.registered_sensors:
                    sensor_status = self.registered_sensors[eui_key]
                else:
                    sensor_status = {"registered": False, "base_stations": []}

                # Send status response
                response_payload = {
                    "action": "status_response",
                    "sensor_eui": eui,
                    "status": sensor_status,
                    "timestamp": asyncio.get_event_loop().time()
                }

                await self.mqtt_out_queue.put({
                    "topic": f"ep/{eui}/response",
                    "payload": json.dumps(response_payload)
                })

                logger.info(f"✅ STATUS command processed for {eui}")

            else:
                logger.warning(f"❓ Unknown command action: {action} for sensor {eui}")

                # Send error response
                response_payload = {
                    "action": "error_response",
                    "sensor_eui": eui,
                    "error": f"Unknown command: {action}",
                    "timestamp": asyncio.get_event_loop().time()
                }

                await self.mqtt_out_queue.put({
                    "topic": f"ep/{eui}/response",
                    "payload": json.dumps(response_payload)
                })

        except Exception as e:
            logger.error(f"❌ Error processing command {action} for {eui}: {e}")

            # Send error response
            try:
                response_payload = {
                    "action": "error_response",
                    "sensor_eui": eui,
                    "error": str(e),
                    "timestamp": asyncio.get_event_loop().time()
                }

                await self.mqtt_out_queue.put({
                    "topic": f"ep/{eui}/response",
                    "payload": json.dumps(response_payload)
                })
            except:
                pass  # Don't let error response fail

    async def process_sensor_config(self, config: dict) -> None:
        """Process a single sensor configuration update from MQTT"""
        eui = config.get('eui')
        if not eui:
            logger.error("Sensor configuration update received without EUI.")
            return

        logger.info(f"🔧 Processing sensor configuration update for EUI: {eui}")

        # Update the sensor configuration in the local list
        self.update_or_add_entry(config)

        # If base stations are connected, trigger an attach request for this sensor
        if self.connected_base_stations:
            logger.info(f"📤 Sending attach request for updated sensor {eui} to all connected base stations")
            for writer, bs_eui in self.connected_base_stations.items():
                try:
                    await self.send_attach_request(writer, config)
                    await asyncio.sleep(0.1) # Small delay between requests
                except Exception as e:
                    logger.error(f"Failed to send attach request for {eui} to {bs_eui}: {e}")
        else:
            logger.warning(f"⚠️  No base stations connected, attach request for {eui} will be sent when they connect.")

    def save_sensor_config(self) -> None:
        """Save sensor configuration to file"""
        try:
            with open(self.sensor_config_file, "w") as f:
                json.dump(self.sensor_config, f, indent=4)
            logger.debug(f"Sensor configuration saved to {self.sensor_config_file}")
        except Exception as e:
            logger.error(f"Failed to save sensor configuration: {e}")