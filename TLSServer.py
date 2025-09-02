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
        self.registered_sensors: Dict[str, Dict[str, Any]] = {}
        self.pending_attach_requests: Dict[int, Dict[str, Any]] = {}
        self._status_task_running = False

        # Deduplication variables
        self.deduplication_buffer: Dict[str, Dict[str, Any]] = {}
        self.deduplication_delay = bssci_config.DEDUPLICATION_DELAY
        self.deduplication_stats = {
            'total_messages': 0,
            'duplicate_messages': 0,
            'published_messages': 0
        }

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
            min_ver = ssl_ctx.minimum_version.name
            max_ver = ssl_ctx.maximum_version.name
            logger.info(f"   TLS Protocol versions: {min_ver} - {max_ver}")
            logger.info(
                "✓ SSL context configured successfully with client "
                "certificate verification"
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

        logger.info("🧠 Starting deduplication buffer processing task...")
        asyncio.create_task(self.process_deduplication_buffer())

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
        try:
            logger.info("📤 BSSCI ATTACH REQUEST INITIATED")
            logger.info("   =====================================")
            logger.info(f"   Sensor EUI: {sensor['eui']}")
            logger.info(f"   Target Base Station: {bs_eui}")
            logger.info(f"   Operation ID: {self.opID}")
            logger.info(f"   Timestamp: {self._get_local_time()}")

            # Comprehensive validation with detailed logging
            validation_errors = []
            validation_warnings = []

            # EUI validation
            if len(sensor["eui"]) != 16:
                validation_errors.append(
                    f"EUI length {len(sensor['eui'])} != 16 characters"
                )
            else:
                try:
                    int(sensor["eui"], 16)  # Test hex validity
                    logger.info(f"   ✓ EUI format valid: {sensor['eui']}")
                except ValueError:
                    validation_errors.append(
                        f"EUI contains invalid hex characters: {sensor['eui']}"
                    )

            # Network Key validation and normalization
            original_nw_key = sensor["nwKey"]
            nw_key = (original_nw_key[:32] if len(original_nw_key) >= 32
                     else original_nw_key)

            if len(original_nw_key) != 32:
                if len(original_nw_key) > 32:
                    validation_warnings.append(
                        f"Network key truncated from "
                        f"{len(original_nw_key)} to 32 characters"
                    )
                    logger.warning(
                        f"   ⚠️  Network key too long, truncating: "
                        f"{original_nw_key} -> {nw_key}"
                    )
                else:
                    validation_errors.append(
                        f"Network key length {len(original_nw_key)} < "
                        f"32 characters required"
                    )
            else:
                try:
                    int(nw_key, 16)  # Test hex validity
                    logger.info(
                        f"   ✓ Network key format valid: "
                        f"{nw_key[:8]}...{nw_key[-8:]}"
                    )
                except ValueError:
                    validation_errors.append(
                        f"Network key contains invalid hex characters: {nw_key}"
                    )

            # Short Address validation
            if len(sensor["shortAddr"]) != 4:
                validation_errors.append(
                    f"Short address length {len(sensor['shortAddr'])} != "
                    f"4 characters"
                )
            else:
                try:
                    int(sensor["shortAddr"], 16)  # Test hex validity
                    logger.info(
                        f"   ✓ Short address format valid: "
                        f"{sensor['shortAddr']}"
                    )
                except ValueError:
                    validation_errors.append(
                        f"Short address contains invalid hex characters: "
                        f"{sensor['shortAddr']}"
                    )

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
                        validation_warnings.append(
                            f"Sensor {sensor['eui']} already registered "
                            f"to base station {bs_eui}"
                        )
                        logger.warning(
                            "   ⚠️  Re-registering sensor to same base station"
                        )
                    else:
                        validation_warnings.append(
                            f"Sensor {sensor['eui']} already registered to "
                            f"{len(existing_bases)} other base station(s): "
                            f"{existing_bases}"
                        )
                        logger.warning(
                            "   ⚠️  Adding registration to additional "
                            "base station"
                        )

            # Log all warnings
            for warning in validation_warnings:
                logger.warning(f"   ⚠️  {warning}")

            if not validation_errors:
                logger.info("   ✅ All validations passed")
                logger.info("   📋 Final parameters:")
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
                logger.info(f"   Operation ID {self.opID} sent to base station {bs_eui}")
                logger.info(f"   Tracking request for correlation with response")
                logger.info(f"   Awaiting response from base station...")
                logger.info(f"   =====================================")

                self.opID -= 1
            else:
                logger.error("❌ ATTACH REQUEST VALIDATION FAILED")
                logger.error(f"   Sensor EUI: {sensor.get('eui', 'unknown')}")
                logger.error(f"   Base Station: {bs_eui}")
                logger.error("   Validation errors found:")
                for i, error in enumerate(validation_errors, 1):
                    logger.error(f"     {i}. {error}")
                logger.error(
                    "   ❌ Attach request NOT sent due to validation failures"
                )
                logger.error("   =====================================")

        except Exception as e:
            logger.error("❌ CRITICAL ERROR during attach request preparation")
            logger.error(f"   Sensor EUI: {sensor.get('eui', 'unknown')}")
            logger.error(f"   Base Station: {bs_eui}")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception message: {str(e)}")
            import traceback
            logger.error("   Full traceback:")
            for line in traceback.format_exc().strip().split('\n'):
                logger.error(f"     {line}")
            logger.error("   =====================================")
            raise  # Re-raise to handle upstream

    async def attach_file(self, writer: asyncio.streams.StreamWriter) -> None:
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        logger.info(
            f"🔗 BATCH SENSOR ATTACHMENT started for base station {bs_eui}"
        )
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

        logger.info(
            f"✅ BATCH SENSOR ATTACHMENT completed for base station {bs_eui}"
        )
        logger.info(f"   Successful: {successful_attachments}")
        logger.info(f"   Failed: {failed_attachments}")
        logger.info(f"   Total processed: {len(self.sensor_config)}")

        if failed_attachments > 0:
            logger.warning(
                f"   ⚠️  {failed_attachments} sensors failed to attach - "
                f"check individual sensor logs above"
            )

    async def send_status_requests(self) -> None:
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
                    logger.info(
                        f"   Base stations: "
                        f"{list(self.connected_base_stations.values())}"
                    )

                    requests_sent = 0
                    failed_requests = 0

                    # Use copy to avoid dict change during iteration
                    for writer, bs_eui in self.connected_base_stations.copy().items():
                        try:
                            logger.info(
                                f"📤 Sending status request to base station {bs_eui}"
                            )
                            logger.info(f"   Operation ID: {self.opID}")

                            msg_pack = encode_message(
                                messages.build_status_request(self.opID)
                            )
                            full_message = (
                                IDENTIFIER +
                                len(msg_pack).to_bytes(4, byteorder="little") +
                                msg_pack
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
                                f"base station {bs_eui}"
                            )
                            logger.error(f"   Error: {type(e).__name__}: {e}")
                            logger.warning(
                                f"🔌 Removing disconnected base station "
                                f"{bs_eui} from active list"
                            )
                            # Remove disconnected base station
                            if writer in self.connected_base_stations:
                                self.connected_base_stations.pop(writer)

                    logger.info("📊 STATUS REQUEST CYCLE COMPLETE")
                    logger.info(f"   Requests sent: {requests_sent}")
                    logger.info(f"   Failed requests: {failed_requests}")
                    logger.info(
                        f"   Remaining connected base stations: "
                        f"{len(self.connected_base_stations)}"
                    )

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
        addr = writer.get_extra_info("peername")
        ssl_obj = writer.get_extra_info("ssl_object")

        try:
            logger.info(f"🔗 New BSSCI connection attempt from {addr}")

            if ssl_obj:
                cert = ssl_obj.getpeercert()
                if cert:
                    subject = cert.get('subject', [])
                    cn = None
                    for field in subject:
                        for name, value in field:
                            if name == 'commonName':
                                cn = value
                                break
                    logger.info(
                        f"   ✓ SSL handshake successful - "
                        f"Client certificate CN: {cn}"
                    )
                else:
                    logger.warning(
                        "   ⚠️  SSL handshake completed but no client "
                        "certificate provided"
                    )
            else:
                logger.error(
                    "   ❌ No SSL object found - connection may not be encrypted"
                )

        except Exception as e:
            logger.error(f"   ❌ SSL connection error from {addr}: {e}")
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass
            return

        connection_start_time = asyncio.get_event_loop().time()
        messages_processed = 0

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                # try:
                for message in decode_messages(data):
                    msg_type = message.get("command", "")
                    messages_processed += 1

                    logger.info(f"📨 BSSCI message #{messages_processed} received from {addr}")
                    logger.info(f"   Message type: {msg_type}")
                    logger.debug(f"   Full message: {message}")

                    if msg_type == "con":
                        logger.info(f"📨 BSSCI CONNECTION REQUEST received from {addr}")
                        logger.info(f"   Operation ID: {message.get('opId', 'unknown')}")
                        logger.info(f"   Base Station UUID: {message.get('snBsUuid', 'unknown')}")

                        msg = encode_message(
                            messages.build_connection_response(
                                message.get("opId", ""), message.get("snBsUuid", "")
                            )
                        )
                        writer.write(
                            IDENTIFIER + len(msg).to_bytes(4, byteorder="little") + msg
                        )
                        await writer.drain()
                        bs_eui = int(message["bsEui"]).to_bytes(8, byteorder="big").hex()
                        self.connecting_base_stations[writer] = bs_eui
                        logger.info(f"📤 BSSCI CONNECTION RESPONSE sent to base station {bs_eui}")
                        logger.info(f"   Base station {bs_eui} is now in connecting state")

                    elif msg_type == "conCmp":
                        logger.info(f"📨 BSSCI CONNECTION COMPLETE received from {addr}")
                        if (
                            writer in self.connecting_base_stations
                            and writer not in self.connected_base_stations
                        ):
                            bs_eui = self.connecting_base_stations.pop(writer)  # Remove from connecting
                            self.connected_base_stations[writer] = bs_eui
                            connection_time = asyncio.get_event_loop().time() - connection_start_time

                            logger.info(
                                f"✅ BSSCI CONNECTION ESTABLISHED with "
                                f"base station {bs_eui}"
                            )
                            logger.info("   =====================================")
                            logger.info(f"   Base Station EUI: {bs_eui}")
                            logger.info(
                                f"   Connection established at: "
                                f"{self._get_local_time()}"
                            )
                            logger.info(
                                f"   Connection setup duration: "
                                f"{connection_time:.2f} seconds"
                            )
                            logger.info(f"   Client address: {addr}")
                            logger.info(
                                f"   Total connected base stations: "
                                f"{len(self.connected_base_stations)}"
                            )
                            logger.info(
                                f"   All connected stations: "
                                f"{list(self.connected_base_stations.values())}"
                            )

                            logger.info("🔗 INITIATING SENSOR ATTACHMENT PROCESS")
                            logger.info(
                                f"   Total sensors to attach: "
                                f"{len(self.sensor_config)}"
                            )
                            if self.sensor_config:
                                logger.info("   Sensors to be attached:")
                                for i, sensor in enumerate(self.sensor_config, 1):
                                    logger.info(
                                        f"     {i:2d}. EUI: {sensor['eui']}, "
                                        f"Short Addr: {sensor['shortAddr']}"
                                    )
                            else:
                                logger.warning(
                                    "   ⚠️  No sensors configured for attachment"
                                )
                            logger.info("   =====================================")

                            # Start attachment process
                            await self.attach_file(writer)

                            # Always ensure status request task is running
                            if (not hasattr(self, '_status_task_running') or
                                    not self._status_task_running):
                                logger.info(
                                    "📊 Starting periodic status request task "
                                    "for all base stations"
                                )
                                self._status_task_running = True
                                asyncio.create_task(self.send_status_requests())
                            else:
                                logger.info(
                                    "📊 Status request task already running, "
                                    "will include this base station"
                                )

                            # Start auto-detach task if not already running
                            if (not hasattr(self, '_auto_detach_task_running') or
                                    not self._auto_detach_task_running):
                                logger.info(
                                    "🕐 Starting auto-detach task for "
                                    "inactive sensors"
                                )
                                self._auto_detach_task_running = True
                                asyncio.create_task(
                                    self.auto_detach_inactive_sensors()
                                )
                            else:
                                logger.info("🕐 Auto-detach task already running")
                        else:
                            logger.warning(
                                "⚠️  Received connection complete from unknown "
                                "or already connected base station"
                            )

                    elif msg_type == "ping":
                        logger.debug(f"Ping request received from {addr}")
                        msg_pack = encode_message(
                            messages.build_ping_response(message.get("opId", ""))
                        )
                        writer.write(
                            IDENTIFIER
                            + len(msg_pack).to_bytes(4, byteorder="little")
                            + msg_pack
                        )
                        await writer.drain()

                    elif msg_type == "pingCmp":
                        logger.debug(f"Ping complete received from {addr}")

                    elif msg_type == "statusRsp":
                        bs_eui = self.connected_base_stations[writer]
                        op_id = message.get("opId", "unknown")

                        logger.info(f"📊 BASE STATION STATUS RESPONSE received from {bs_eui}")
                        logger.info(f"   Operation ID: {op_id}")
                        logger.info(f"   Status Code: {message['code']}")
                        logger.info(f"   Memory Load: {message['memLoad']:.1%}")
                        logger.info(f"   CPU Load: {message['cpuLoad']:.1%}")
                        logger.info(f"   Duty Cycle: {message['dutyCycle']:.1%}")

                        # Parse uptime to human readable format
                        uptime_seconds = message['uptime']
                        uptime_hours = uptime_seconds // 3600
                        uptime_minutes = (uptime_seconds % 3600) // 60
                        uptime_secs = uptime_seconds % 60
                        logger.info(f"   Uptime: {uptime_hours:02d}:{uptime_minutes:02d}:{uptime_secs:02d} ({uptime_seconds}s)")

                        # Parse timestamp
                        try:
                            bs_time = datetime.fromtimestamp(message['time'] / 1_000_000_000)
                            logger.info(f"   Base Station Time: {bs_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                        except:
                            logger.info(f"   Base Station Time: {message['time']} (raw)")

                        data_dict = {
                            "code": message["code"],
                            "memLoad": message["memLoad"],
                            "cpuLoad": message["cpuLoad"],
                            "dutyCycle": message["dutyCycle"],
                            "time": message["time"],
                            "uptime": message["uptime"],
                        }

                        mqtt_topic = f"bs/{bs_eui}"
                        payload = json.dumps(data_dict)

                        logger.info(f"📤 MQTT PUBLICATION - BASE STATION STATUS")
                        logger.info(f"   Topic: {bssci_config.BASE_TOPIC.rstrip('/')}/{mqtt_topic}")
                        logger.info(f"   Base Station EUI: {bs_eui}")
                        logger.info(f"   Payload size: {len(payload)} bytes")
                        logger.info(f"   Status data: Code={data_dict['code']}, CPU={data_dict['cpuLoad']:.1%}, Memory={data_dict['memLoad']:.1%}")
                        logger.info(f"   Queue size before add: {self.mqtt_out_queue.qsize()}")

                        try:
                            await self.mqtt_out_queue.put(
                                {
                                    "topic": mqtt_topic,
                                    "payload": payload,
                                }
                            )
                            logger.info(f"✅ Base station status queued for MQTT publication")
                            logger.info(f"   Queue size after add: {self.mqtt_out_queue.qsize()}")
                        except Exception as mqtt_err:
                            logger.error(f"❌ Failed to queue MQTT message: {mqtt_err}")
                        msg_pack = encode_message(
                            messages.build_status_complete(message.get("opId", ""))
                        )
                        writer.write(
                            IDENTIFIER
                            + len(msg_pack).to_bytes(4, byteorder="little")
                            + msg_pack
                        )
                        await writer.drain()
                        logger.debug(f"📤 STATUS COMPLETE sent for opID {op_id}")

                    elif msg_type == "attPrpRsp":
                        # Handle attach response according to BSSCI specification
                        # Per spec: attPrpRsp only contains command and opId fields
                        op_id = message.get("opId", "unknown")
                        bs_eui = self.connected_base_stations.get(writer, "unknown")

                        logger.info(f"📨 BSSCI ATTACH RESPONSE received from base station {bs_eui}")
                        logger.info(f"   =====================================")
                        logger.info(f"   Operation ID: {op_id}")
                        logger.info(f"   Raw message: {message}")
                        logger.info(f"   Note: Per BSSCI spec, attach response contains only command and opId")

                        # Try to correlate with pending attach request
                        pending_request = self.pending_attach_requests.get(op_id)
                        if pending_request:
                            sensor_eui = pending_request['sensor_eui']
                            sensor_config = pending_request['sensor_config']
                            request_time = pending_request['timestamp']
                            response_time = asyncio.get_event_loop().time()
                            processing_duration = response_time - request_time

                            logger.info(f"✅ ATTACH RESPONSE CORRELATED with pending request")
                            logger.info(f"   Sensor EUI: {sensor_eui}")
                            logger.info(f"   Base station: {bs_eui}")
                            logger.info(f"   Processing duration: {processing_duration:.3f} seconds")
                            logger.info(f"   Sensor Configuration:")
                            logger.info(f"     EUI: {sensor_config['eui']}")
                            logger.info(f"     Network Key: {sensor_config['nwKey'][:8]}...{sensor_config['nwKey'][-8:]}")
                            logger.info(f"     Short Address: {sensor_config['shortAddr']}")
                            logger.info(f"     Bidirectional: {sensor_config['bidi']}")

                            # According to BSSCI specification, receiving attach response indicates success
                            # Store successful registration - support multiple base stations
                            eui_key = sensor_eui.lower()
                            if eui_key not in self.registered_sensors:
                                self.registered_sensors[eui_key] = {
                                    'status': 'registered',
                                    'base_stations': [],
                                    'timestamp': response_time,
                                    'registration_time': self._get_local_time(),
                                    'registrations': []
                                }

                            # Add this base station if not already registered
                            if bs_eui not in self.registered_sensors[eui_key]['base_stations']:
                                self.registered_sensors[eui_key]['base_stations'].append(bs_eui)
                                self.registered_sensors[eui_key]['registrations'].append({
                                    'base_station': bs_eui,
                                    'op_id': op_id,
                                    'processing_duration': processing_duration,
                                    'registration_time': self._get_local_time()
                                })
                                self.registered_sensors[eui_key]['timestamp'] = response_time

                            logger.info(f"✅ SENSOR REGISTRATION SUCCESSFUL")
                            logger.info(f"   Sensor {sensor_eui} is now REGISTERED to base station {bs_eui}")
                            logger.info(f"   Registration completed at: {self._get_local_time()}")
                            logger.info(f"   Total base stations for this sensor: {len(self.registered_sensors[eui_key]['base_stations'])}")
                            logger.info(f"   All base stations for sensor: {self.registered_sensors[eui_key]['base_stations']}")
                            logger.info(f"   Total registered sensors: {len([k for k in self.registered_sensors.keys() if not k.endswith('_failure')])}")

                            # Remove from pending requests
                            del self.pending_attach_requests[op_id]

                        else:
                            logger.warning(f"⚠️  ATTACH RESPONSE for unknown operation ID")
                            logger.warning(f"   Operation ID {op_id} not found in pending requests")
                            logger.warning(f"   Available pending requests: {list(self.pending_attach_requests.keys())}")
                            logger.warning(f"   This could indicate:")
                            logger.warning(f"     - Response arrived after timeout")
                            logger.warning(f"     - Duplicate response")
                            logger.warning(f"     - Base station sent unsolicited response")

                            # Try to find a matching pending request by checking recent requests
                            # This is a fallback for when op_id correlation fails
                            recent_requests = [(k, v) for k, v in self.pending_attach_requests.items()]
                            if recent_requests:
                                # Use the most recent request as fallback
                                fallback_op_id, fallback_request = recent_requests[-1]
                                sensor_eui = fallback_request['sensor_eui']

                                logger.warning(f"   🔄 FALLBACK: Using most recent pending request")
                                logger.warning(f"   Fallback OP ID: {fallback_op_id}")
                                logger.warning(f"   Fallback Sensor EUI: {sensor_eui}")

                                # Store successful registration with fallback data
                                eui_key = sensor_eui.lower()
                                if eui_key not in self.registered_sensors:
                                    self.registered_sensors[eui_key] = {
                                        'status': 'registered',
                                        'base_stations': [],
                                        'timestamp': asyncio.get_event_loop().time(),
                                        'registration_time': self._get_local_time(),
                                        'registrations': []
                                    }

                                # Add this base station if not already registered
                                if bs_eui not in self.registered_sensors[eui_key]['base_stations']:
                                    self.registered_sensors[eui_key]['base_stations'].append(bs_eui)
                                    self.registered_sensors[eui_key]['registrations'].append({
                                        'base_station': bs_eui,
                                        'op_id': op_id,
                                        'registration_time': self._get_local_time(),
                                        'fallback_used': True
                                    })
                                    self.registered_sensors[eui_key]['timestamp'] = asyncio.get_event_loop().time()

                                logger.warning(f"   ✅ FALLBACK REGISTRATION: Sensor {sensor_eui} registered to {bs_eui}")

                                # Remove the fallback request
                                del self.pending_attach_requests[fallback_op_id]

                        logger.info(f"   Response received at: {self._get_local_time()}")
                        logger.info(f"   =====================================")

                        msg_pack = encode_message(
                            messages.build_attach_complete(message.get("opId", ""))
                        )
                        writer.write(
                            IDENTIFIER
                            + len(msg_pack).to_bytes(4, byteorder="little")
                            + msg_pack
                        )
                        await writer.drain()
                        logger.debug(f"📤 BSSCI ATTACH COMPLETE sent for opID {op_id}")

                    elif msg_type == "ulData":
                        eui = int(message["epEui"]).to_bytes(8, byteorder="big").hex()
                        bs_eui = self.connected_base_stations[writer]
                        op_id = message.get("opId", "unknown")
                        rx_time = message["rxTime"]
                        snr = message["snr"]
                        packet_cnt = message["packetCnt"]

                        # Create a unique key for deduplication
                        message_key = f"{eui}_{packet_cnt}"

                        self.deduplication_stats['total_messages'] += 1

                        # Check if message is a duplicate and if new one has better SNR
                        is_duplicate = message_key in self.deduplication_buffer
                        if is_duplicate:
                            existing_message = self.deduplication_buffer[message_key]
                            if snr > existing_message['snr']:
                                logger.info(
                                    f"🔄 DEDUPLICATION: Better signal found for {eui}"
                                )
                                logger.info(f"   Message counter: {packet_cnt}")
                                logger.info(
                                    f"   Previous SNR: "
                                    f"{existing_message['snr']:.2f} dB "
                                    f"(via {existing_message['bs_eui']})"
                                )
                                logger.info(f"   New SNR: {snr:.2f} dB (via {bs_eui})")
                                logger.info(
                                    f"   Updating preferred path: "
                                    f"{existing_message['bs_eui']} → {bs_eui}"
                                )

                                # Update preferred downlink path in sensor config
                                self.update_preferred_downlink_path(eui, bs_eui, snr)

                                self.deduplication_buffer[message_key] = {
                                    'message': message,
                                    'timestamp': asyncio.get_event_loop().time(),
                                    'snr': snr,
                                    'bs_eui': bs_eui
                                }
                            else:
                                logger.debug(
                                    f"   🔽 DEDUPLICATION: Filtered duplicate "
                                    f"message for {eui} with lower SNR "
                                    f"({snr:.2f} dB <= "
                                    f"{existing_message['snr']:.2f} dB)"
                                )
                                self.deduplication_stats['duplicate_messages'] += 1

                                # Send acknowledgment but don't queue for MQTT
                                msg_pack = encode_message(
                                    messages.build_ul_response(message.get("opId", ""))
                                )
                                writer.write(
                                    IDENTIFIER
                                    + len(msg_pack).to_bytes(4, byteorder="little")
                                    + msg_pack
                                )
                                await writer.drain()
                                continue  # Skip processing this duplicate

                        else:
                            logger.debug(f"📨 DEDUPLICATION: New message received for {eui}")
                            logger.debug(f"   Message counter: {packet_cnt}")
                            logger.debug(f"   SNR: {snr:.2f} dB (via {bs_eui})")

                            # Update preferred downlink path for new messages too
                            self.update_preferred_downlink_path(eui, bs_eui, snr)

                            self.deduplication_buffer[message_key] = {
                                'message': message,
                                'timestamp': asyncio.get_event_loop().time(),
                                'snr': snr,
                                'bs_eui': bs_eui
                            }

                        # Parse received timestamp if available
                        try:
                            rx_datetime = datetime.fromtimestamp(
                                rx_time / 1_000_000_000
                            )
                            rx_time_str = rx_datetime.strftime(
                                "%Y-%m-%d %H:%M:%S.%f"
                            )[:-3]
                        except Exception:
                            rx_time_str = str(rx_time)

                        logger.info("📡 UPLINK DATA BUFFERED FOR DEDUPLICATION")
                        logger.info("   =================================")
                        logger.info(f"   Endpoint EUI: {eui}")
                        logger.info(f"   Via Base Station: {bs_eui}")
                        logger.info(f"   Reception Time: {rx_time_str}")
                        logger.info(f"   Operation ID: {op_id}")
                        logger.info("   Signal Quality:")
                        logger.info(f"     SNR: {snr:.2f} dB")
                        logger.info(f"     RSSI: {message['rssi']:.2f} dBm")
                        logger.info(f"   Packet Counter: {packet_cnt}")
                        logger.info("   Payload:")
                        logger.info(f"     Length: {len(message['userData'])} bytes")
                        hex_data = ' '.join(f'{b:02x}' for b in message['userData'])
                        logger.info(f"     Data (hex): {hex_data}")
                        logger.info(f"     Data (dec): {message['userData']}")

                        # Check if sensor is registered and update activity timestamp
                        is_registered = eui.lower() in self.registered_sensors
                        if is_registered:
                            reg_info = self.registered_sensors[eui.lower()]
                            # Update last activity timestamp for auto-detach tracking
                            eui_key = eui.lower()
                            self.registered_sensors[eui_key]['last_data_timestamp'] = (
                                asyncio.get_event_loop().time()
                            )
                            self.registered_sensors[eui_key]['last_data_time_str'] = (
                                self._get_local_time()
                            )

                            logger.info("   Registration Status: ✅ REGISTERED")
                            base_stations = reg_info.get('base_stations', [])
                            logger.info(
                                f"     Registered to {len(base_stations)} "
                                f"base station(s): {base_stations}"
                            )
                            logger.info(f"     Data received via: {bs_eui}")
                            logger.info(
                                f"     Registration time: "
                                f"{reg_info.get('registration_time', 'unknown')}"
                            )
                            logger.info(f"     Last activity: {self._get_local_time()}")
                        else:
                            logger.warning("   Registration Status: ⚠️  NOT REGISTERED")
                            logger.warning(
                                "     This sensor may not be configured "
                                "in endpoints.json"
                            )

                        # Message will be published after deduplication delay
                        logger.info("⏳ Message queued for deduplication processing")
                        logger.info(
                            f"   Will be published in {self.deduplication_delay} "
                            f"seconds if no better signal received"
                        )
                        logger.info(
                            f"   Buffer size: {len(self.deduplication_buffer)} messages"
                        )
                        logger.info("   =================================")

                        msg_pack = encode_message(
                            messages.build_ul_response(message.get("opId", ""))
                        )
                        writer.write(
                            IDENTIFIER
                            + len(msg_pack).to_bytes(4, byteorder="little")
                            + msg_pack
                        )
                        await writer.drain()
                        logger.info(f"✅ UPLINK DATA PROCESSING COMPLETE for {eui}")
                        logger.info("   =================================")

                    elif msg_type == "ulDataCmp":
                        pass

                    elif msg_type == "detachResp":
                        eui = message.get("eui", "unknown")
                        result = message.get("resultCode", -1)
                        status = "OK" if result == 0 else f"Fehler {result}"
                        print(f"[DETACH] {eui} {status}")

                    else:
                        print(f"[WARN] Unbekannte Nachricht: {message}")

                    # except Exception as e:
                    #    print(f"[ERROR] Fehler beim Dekodieren der Nachricht: {e}")

        except asyncio.CancelledError:
            logger.info(f"🔌 Connection from {addr} was cancelled")
        except ConnectionResetError:
            logger.warning(f"🔌 Connection from {addr} was reset by peer")
        except ssl.SSLError as e:
            logger.error(f"❌ SSL/TLS error from {addr}: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error handling connection from {addr}: {e}")
        finally:
            connection_duration = asyncio.get_event_loop().time() - connection_start_time

            try:
                with open(self.sensor_config_file, "w") as f:
                    json.dump(self.sensor_config, f, indent=4)
                logger.debug(f"Sensor configuration saved to {self.sensor_config_file}")
            except Exception as e:
                logger.error(f"Failed to save sensor configuration: {e}")

            logger.info(f"🔌 Connection to {addr} closed")
            logger.info(f"   Connection duration: {connection_duration:.2f} seconds")
            logger.info(f"   Messages processed: {messages_processed}")

            writer.close()
            await writer.wait_closed()

            if writer in self.connected_base_stations:
                bs_eui = self.connected_base_stations.pop(writer)
                logger.info(f"❌ Base station {bs_eui} disconnected")
                logger.info(f"   Remaining connected base stations: {len(self.connected_base_stations)}")
            if writer in self.connecting_base_stations:
                self.connecting_base_stations.pop(writer)

    async def process_deduplication_buffer(self) -> None:
        """Process deduplication buffer, forward best messages, clean old entries."""
        logger.info(
            f"🧠 Starting deduplication buffer processing task with "
            f"delay: {self.deduplication_delay}s"
        )
        while True:
            await asyncio.sleep(self.deduplication_delay)
            current_time = asyncio.get_event_loop().time()

            # Find messages that have been in the buffer longer than the delay
            messages_to_publish = []
            # Use list to allow modification during iteration
            for key, value in list(self.deduplication_buffer.items()):
                if current_time - value['timestamp'] >= self.deduplication_delay:
                    messages_to_publish.append((key, value))
                    del self.deduplication_buffer[key]  # Remove from buffer

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
            # Keep entries for a bit longer to ensure they are processed
            oldest_allowed_time = current_time - (self.deduplication_delay * 2)
            for key, value in list(self.deduplication_buffer.items()):
                if current_time - value['timestamp'] > oldest_allowed_time:
                    logger.warning(
                        f"   🧹 Cleaning up old unduplicated message "
                        f"from buffer: {key}"
                    )
                    del self.deduplication_buffer[key]


    async def queue_watcher(self) -> None:
        logger.info(
            "📨 MQTT queue watcher started - monitoring for "
            "configuration updates and commands"
        )
        logger.info(f"   Watching queue ID: {id(self.mqtt_in_queue)}")
        try:
            while True:
                queue_size = self.mqtt_in_queue.qsize()
                logger.debug(
                    f"⏳ Queue watcher waiting for message "
                    f"(queue size: {queue_size})"
                )
                msg = dict(await self.mqtt_in_queue.get())
                logger.info("📥 MQTT MESSAGE received")
                logger.debug(f"   Raw message: {msg}")

                # Check if this is a command message
                if "mqtt_topic" in msg and "mqtt_payload" in msg:
                    topic = msg["mqtt_topic"]
                    payload = msg["mqtt_payload"]

                    if "/cmd" in topic:
                        logger.info(f"📡 MQTT COMMAND detected in topic: {topic}")
                        await self.process_mqtt_commands(topic, payload)
                        continue

                # Process sensor configuration messages
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
                        logger.info(
                            f"📤 PROPAGATING to "
                            f"{len(self.connected_base_stations)} "
                            f"connected base stations"
                        )
                        for writer, bs_eui in self.connected_base_stations.items():
                            logger.info(
                                f"   Sending attach request to "
                                f"base station: {bs_eui}"
                            )
                            await self.send_attach_request(writer, msg)
                    else:
                        logger.warning(
                            "No base stations connected - attach requests "
                            "will be sent when base stations connect"
                        )

                    logger.info("💾 UPDATING local configuration file")
                    self.update_or_add_entry(msg)
                    logger.info(
                        f"✅ ENDPOINT CONFIGURATION processing complete "
                        f"for {msg['eui']}"
                    )
                else:
                    logger.error(f"❌ INVALID MQTT message - missing required fields")
                    logger.error(f"   Expected config fields: eui, nwKey, shortAddr, bidi")
                    logger.error(f"   Or command fields: mqtt_topic, mqtt_payload")
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
                except Exception:
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
        for sensor in self.sensor_config:
            eui = sensor['eui'].lower()
            reg_info = self.registered_sensors.get(eui, {})

            # Get preferred downlink path from sensor config or from instance attribute
            preferred_path = sensor.get('preferredDownlinkPath', None)
            if hasattr(self, 'preferred_downlink_paths') and eui in self.preferred_downlink_paths:
                preferred_path = self.preferred_downlink_paths[eui]

            status[eui] = {
                'eui': sensor['eui'],
                'nwKey': sensor['nwKey'],
                'shortAddr': sensor['shortAddr'],
                'bidi': sensor['bidi'],
                'registered': eui in self.registered_sensors,
                'registration_info': reg_info,
                'base_stations': reg_info.get('base_stations', []),
                'total_registrations': len(reg_info.get('base_stations', [])),
                'preferredDownlinkPath': preferred_path
            }
        return status

    def clear_all_sensors(self) -> None:
        """Clear all sensor configurations"""
        self.sensor_config = []
        self.registered_sensors = {}
        try:
            with open(self.sensor_config_file, "w") as f:
                json.dump(self.sensor_config, f, indent=4)
            logger.info(f"All sensor configurations and registration status cleared")
        except Exception as e:
            logger.error(f"Failed to clear sensor configurations: {e}")

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

    async def detach_sensor(self, sensor_eui: str) -> bool:
        """Send detach request for a specific sensor to all connected base stations"""
        if not self.connected_base_stations:
            logger.warning(f"❌ DETACH REQUEST FAILED - No base stations connected")
            return False

        logger.info(f"📤 BSSCI DETACH REQUEST INITIATED")
        logger.info(f"   =====================================")
        logger.info(f"   Sensor EUI: {sensor_eui}")
        logger.info(f"   Target Base Stations: {len(self.connected_base_stations)}")
        logger.info(f"   Timestamp: {self._get_local_time()}")

        detach_count = 0
        failed_count = 0

        for writer, bs_eui in self.connected_base_stations.items():
            try:
                logger.info(f"📤 Sending detach request to base station {bs_eui}")
                logger.info(f"   Operation ID: {self.opID}")

                # Build detach message using the EUI directly as string
                detach_message = messages.build_detach_request(sensor_eui, self.opID)
                msg_pack = encode_message(detach_message)
                full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack

                writer.write(full_message)
                await writer.drain()

                logger.info(f"✅ Detach request sent to {bs_eui} (opID: {self.opID})")
                detach_count += 1
                self.opID -= 1

            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Failed to send detach request to {bs_eui}: {e}")

        # Update registration status
        eui_key = sensor_eui.lower()
        if eui_key in self.registered_sensors:
            self.registered_sensors[eui_key]['status'] = 'detached'
            self.registered_sensors[eui_key]['detach_time'] = self._get_local_time()
            self.registered_sensors[eui_key]['base_stations'] = []

        logger.info(f"✅ BSSCI DETACH REQUEST COMPLETED")
        logger.info(f"   Detach requests sent: {detach_count}")
        logger.info(f"   Failed requests: {failed_count}")
        logger.info(f"   =====================================")

        return detach_count > 0

    async def detach_all_sensors(self) -> bool:
        """Send detach requests for all registered sensors"""
        if not self.registered_sensors:
            logger.warning(f"❌ DETACH ALL FAILED - No registered sensors")
            return False

        logger.info(f"📤 BSSCI BULK DETACH REQUEST INITIATED")
        logger.info(f"   Total registered sensors: {len(self.registered_sensors)}")

        success_count = 0
        for eui_key in list(self.registered_sensors.keys()):
            sensor_eui = eui_key.upper()  # Convert back to uppercase for display
            try:
                success = await self.detach_sensor(sensor_eui)
                if success:
                    success_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to detach sensor {sensor_eui}: {e}")

        logger.info(f"✅ BULK DETACH COMPLETED - {success_count} sensors processed")
        return success_count > 0

    async def auto_detach_inactive_sensors(self) -> None:
        """Auto-detach sensors that haven't sent data for 48 hours"""
        logger.info("🕐 AUTO-DETACH TASK STARTED")
        logger.info("   Auto-detach interval: 48 hours (172800 seconds)")

        try:
            while True:
                await asyncio.sleep(3600)  # Check every hour
                current_time = asyncio.get_event_loop().time()
                cutoff_time = current_time - (48 * 3600)  # 48 hours ago

                sensors_to_detach = []
                for eui_key, sensor_info in self.registered_sensors.items():
                    if sensor_info.get('status') != 'registered':
                        continue

                    last_activity = sensor_info.get(
                        'last_data_timestamp',
                        sensor_info.get('timestamp', 0)
                    )
                    if last_activity < cutoff_time:
                        sensors_to_detach.append(eui_key)

                if sensors_to_detach:
                    logger.info(
                        f"🕐 AUTO-DETACH: Found {len(sensors_to_detach)} "
                        f"inactive sensors"
                    )
                    for eui_key in sensors_to_detach:
                        sensor_eui = eui_key.upper()
                        logger.info(
                            f"   Auto-detaching inactive sensor: {sensor_eui}"
                        )
                        try:
                            await self.detach_sensor(sensor_eui)
                            # Mark as auto-detached
                            if eui_key in self.registered_sensors:
                                reg_info = self.registered_sensors[eui_key]
                                reg_info['auto_detached'] = True
                                reg_info['auto_detach_reason'] = '48h_inactive'
                        except Exception as e:
                            logger.error(
                                f"❌ Auto-detach failed for {sensor_eui}: {e}"
                            )
                else:
                    logger.debug("🕐 AUTO-DETACH: No inactive sensors found")

        except asyncio.CancelledError:
            logger.info("🕐 AUTO-DETACH TASK CANCELLED")
            raise
        except Exception as e:
            logger.error(f"❌ AUTO-DETACH TASK ERROR: {e}")
            raise

    async def process_mqtt_commands(self, topic: str, payload: dict) -> None:
        """Process MQTT commands for sensor management"""
        try:
            # Extract EUI from topic (bssci/ep/{eui}/cmd)
            topic_parts = topic.split("/")
            if len(topic_parts) >= 3 and topic_parts[-1] == "cmd":
                sensor_eui = topic_parts[-2]
                command = payload.get("command", "").lower()

                logger.info(f"📡 MQTT COMMAND RECEIVED")
                logger.info(f"   Sensor EUI: {sensor_eui}")
                logger.info(f"   Command: {command}")
                logger.info(f"   Payload: {payload}")

                if command == "detach":
                    logger.info(f"🔌 Processing MQTT detach command for {sensor_eui}")
                    success = await self.detach_sensor(sensor_eui)

                    # Send response back to MQTT
                    response_topic = f"ep/{sensor_eui}/cmd/response"
                    response_payload = {
                        "command": "detach",
                        "status": "success" if success else "failed",
                        "sensor_eui": sensor_eui,
                        "timestamp": self._get_local_time()
                    }

                    await self.mqtt_out_queue.put({
                        "topic": response_topic,
                        "payload": json.dumps(response_payload)
                    })

                elif command == "status":
                    logger.info(f"📊 Processing MQTT status command for {sensor_eui}")
                    eui_key = sensor_eui.lower()
                    sensor_status = self.registered_sensors.get(eui_key, {})

                    # Send status response back to MQTT
                    response_topic = f"ep/{sensor_eui}/cmd/response"
                    response_payload = {
                        "command": "status",
                        "sensor_eui": sensor_eui,
                        "registered": eui_key in self.registered_sensors,
                        "status": sensor_status.get('status', 'unknown'),
                        "base_stations": sensor_status.get('base_stations', []),
                        "last_activity": sensor_status.get('last_data_timestamp', 0),
                        "timestamp": self._get_local_time()
                    }

                    await self.mqtt_out_queue.put({
                        "topic": response_topic,
                        "payload": json.dumps(response_payload)
                    })

                else:
                    logger.warning(f"⚠️  Unknown MQTT command: {command}")

        except Exception as e:
            logger.error(f"❌ Error processing MQTT command: {e}")

    def set_mqtt_interface(self, mqtt_interface) -> None:
        """Set the MQTT interface for bidirectional communication"""
        self.mqtt_interface = mqtt_interface
        logger.info("🔗 MQTT interface linked to TLS server")

    def update_or_add_entry(self, msg: dict[str, Any]) -> None:
        # Update existing entry or add new one
        for sensor in self.sensor_config:
            if sensor["eui"].lower() == msg["eui"].lower():
                sensor["nwKey"] = msg["nwKey"]
                sensor["shortAddr"] = msg["shortAddr"]
                sensor["bidi"] = msg["bidi"]
                logger.info(
                f"Updated configuration for existing endpoint {msg['eui']}"
            )
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