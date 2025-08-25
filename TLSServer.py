import asyncio
import json
import logging
import ssl
from datetime import datetime
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
        self.connected_base_stations: Dict[asyncio.streams.StreamWriter, str] = {}
        self.connecting_base_stations: Dict[asyncio.streams.StreamWriter, str] = {}
        self.sensor_config_file = sensor_config_file
        self.registered_sensors: Dict[str, Dict[str, Any]] = {}  # EUI -> {status, base_station, timestamp}
        try:
            with open(sensor_config_file, "r") as f:
                self.sensor_config = json.load(f)
        except Exception:
            self.sensor_config = []

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
            logger.info(f"   TLS Protocol versions: {ssl_ctx.minimum_version.name} - {ssl_ctx.maximum_version.name}")
            logger.info("✓ SSL context configured successfully with client certificate verification")
            
        except FileNotFoundError as e:
            logger.error(f"❌ SSL certificate file not found: {e}")
            raise
        except ssl.SSLError as e:
            logger.error(f"❌ SSL configuration error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error setting up SSL: {e}")
            raise

        logger.info(f"🚀 Starting BSSCI TLS server...")
        logger.info(f"   Listen address: {bssci_config.LISTEN_HOST}:{bssci_config.LISTEN_PORT}")
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

        logger.info("✓ BSSCI TLS Server is ready and listening for base station connections")
        async with server:
            await server.serve_forever()

    async def send_attach_request(
        self, writer: asyncio.streams.StreamWriter, sensor: dict[str, Any]
    ) -> None:
        bs_eui = self.connected_base_stations.get(writer, "unknown")
        try:
            # Normalize nwKey to exactly 32 characters
            nw_key = sensor["nwKey"][:32] if len(sensor["nwKey"]) >= 32 else sensor["nwKey"]
            
            # Enhanced validation logging
            validation_errors = []
            if len(sensor["eui"]) != 16:
                validation_errors.append(f"EUI length {len(sensor['eui'])} != 16")
            if len(nw_key) != 32:
                validation_errors.append(f"nwKey length {len(nw_key)} != 32")
            if len(sensor["shortAddr"]) != 4:
                validation_errors.append(f"shortAddr length {len(sensor['shortAddr'])} != 4")
            
            if not validation_errors:
                logger.info(f"📤 BSSCI ATTACH REQUEST")
                logger.info(f"   Sensor EUI: {sensor['eui']}")
                logger.info(f"   Short Address: {sensor['shortAddr']}")
                logger.info(f"   Network Key: {nw_key[:8]}...{nw_key[-8:]}")
                logger.info(f"   Bidirectional: {sensor.get('bidi', False)}")
                logger.info(f"   Target Base Station: {bs_eui}")
                logger.info(f"   Operation ID: {self.opID}")
                
                # Use normalized sensor data
                normalized_sensor = {
                    "eui": sensor["eui"],
                    "nwKey": nw_key,
                    "shortAddr": sensor["shortAddr"],
                    "bidi": sensor.get("bidi", False)
                }
                msg_pack = encode_message(
                    messages.build_attach_request(normalized_sensor, self.opID)
                )
                writer.write(
                    IDENTIFIER
                    + len(msg_pack).to_bytes(4, byteorder="little")
                    + msg_pack
                )
                await writer.drain()
                logger.info(f"✅ BSSCI attach request transmitted successfully (opID: {self.opID})")
                self.opID -= 1
            else:
                logger.error(f"❌ INVALID SENSOR CONFIGURATION for EUI {sensor.get('eui', 'unknown')}")
                for error in validation_errors:
                    logger.error(f"   Validation error: {error}")
        except Exception as e:
            logger.error(f"❌ FAILED to send attach request for sensor {sensor.get('eui', 'unknown')} to base station {bs_eui}: {e}")
            logger.error(f"   Exception type: {type(e).__name__}")
            import traceback
            logger.debug(f"   Traceback: {traceback.format_exc()}")

    async def attach_file(self, writer: asyncio.streams.StreamWriter) -> None:
        for sensor in self.sensor_config:
            try:
                await self.send_attach_request(writer, sensor)
            except Exception:
                pass

    async def send_status_requests(self) -> None:
        while True:
            await asyncio.sleep(bssci_config.STATUS_INTERVAL)
            if self.connected_base_stations:
                logger.info(f"📊 PERIODIC STATUS REQUEST CYCLE")
                logger.info(f"   Requesting status from {len(self.connected_base_stations)} connected base stations")
                logger.info(f"   Status interval: {bssci_config.STATUS_INTERVAL} seconds")
                
                for writer, bs_eui in self.connected_base_stations.copy().items():  # Use copy to avoid dict change during iteration
                    try:
                        logger.debug(f"📤 Sending status request to base station {bs_eui} (opID: {self.opID})")
                        msg_pack = encode_message(messages.build_status_request(self.opID))
                        writer.write(
                            IDENTIFIER
                            + len(msg_pack).to_bytes(4, byteorder="little")
                            + msg_pack
                        )
                        await writer.drain()
                        logger.debug(f"✅ Status request transmitted to {bs_eui}")
                        self.opID -= 1
                    except Exception as e:
                        logger.error(f"❌ Base station {bs_eui} connection lost during status request")
                        logger.error(f"   Error: {e}")
                        logger.warning(f"🔌 Removing disconnected base station {bs_eui} from active list")
                        # Remove disconnected base station
                        if writer in self.connected_base_stations:
                            self.connected_base_stations.pop(writer)
            else:
                logger.debug(f"⏸️  No base stations connected - skipping status request cycle")

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
                    logger.info(f"   ✓ SSL handshake successful - Client certificate CN: {cn}")
                else:
                    logger.warning(f"   ⚠️  SSL handshake completed but no client certificate provided")
            else:
                logger.error(f"   ❌ No SSL object found - connection may not be encrypted")
                
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
                            
                            logger.info(f"✅ BSSCI CONNECTION ESTABLISHED with base station {bs_eui}")
                            logger.info(f"   Connection duration: {connection_time:.2f} seconds")
                            logger.info(f"   Total connected base stations: {len(self.connected_base_stations)}")
                            logger.info(f"   Connected stations: {list(self.connected_base_stations.values())}")
                            logger.info(f"🔗 INITIATING SENSOR ATTACHMENTS")
                            logger.info(f"   Will attach {len(self.sensor_config)} configured sensors to base station {bs_eui}")
                            
                            await self.attach_file(writer)
                            asyncio.create_task(self.send_status_requests())

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
                            import datetime
                            bs_time = datetime.datetime.fromtimestamp(message['time'] / 1_000_000_000)
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
                        logger.info(f"📤 Publishing base station status to MQTT topic: {mqtt_topic}")
                        await self.mqtt_out_queue.put(
                            {
                                "topic": mqtt_topic,
                                "payload": json.dumps(data_dict),
                            }
                        )
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
                        # Enhanced logging for sensor registration responses
                        ep_eui = message.get("epEui")
                        result_code = message.get("resultCode", -1)
                        op_id = message.get("opId", "unknown")
                        bs_eui = self.connected_base_stations.get(writer, "unknown")
                        
                        logger.info(f"📨 BSSCI ATTACH RESPONSE received from base station {bs_eui}")
                        logger.info(f"   Operation ID: {op_id}")
                        logger.info(f"   Result Code: {result_code}")
                        
                        if ep_eui:
                            eui_hex = int(ep_eui).to_bytes(8, byteorder="big").hex()
                            logger.info(f"   Endpoint EUI: {eui_hex}")
                            
                            if result_code == 0:  # Success
                                self.registered_sensors[eui_hex.lower()] = {
                                    'status': 'registered',
                                    'base_station': bs_eui,
                                    'timestamp': asyncio.get_event_loop().time(),
                                    'result_code': result_code,
                                    'registration_time': datetime.now().isoformat()
                                }
                                logger.info(f"✅ SENSOR REGISTRATION SUCCESSFUL")
                                logger.info(f"   Sensor {eui_hex} is now registered to base station {bs_eui}")
                                logger.info(f"   Total registered sensors: {len(self.registered_sensors)}")
                            else:
                                # Log detailed error information
                                error_descriptions = {
                                    1: "Invalid EUI",
                                    2: "Invalid network key", 
                                    3: "Invalid short address",
                                    4: "Sensor already registered",
                                    5: "Maximum sensors reached",
                                    6: "Registration timeout",
                                    7: "Base station error"
                                }
                                error_desc = error_descriptions.get(result_code, f"Unknown error ({result_code})")
                                logger.error(f"❌ SENSOR REGISTRATION FAILED")
                                logger.error(f"   Sensor {eui_hex} registration failed: {error_desc}")
                                logger.error(f"   Base station {bs_eui} rejected the registration")
                        else:
                            logger.error(f"❌ ATTACH RESPONSE missing endpoint EUI")
                        
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
                        
                        # Parse received timestamp if available
                        import datetime
                        try:
                            rx_datetime = datetime.datetime.fromtimestamp(rx_time / 1_000_000_000)
                            rx_time_str = rx_datetime.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        except:
                            rx_time_str = str(rx_time)
                        
                        logger.info(f"📡 SENSOR UPLINK DATA RECEIVED")
                        logger.info(f"   =================================")
                        logger.info(f"   Endpoint EUI: {eui}")
                        logger.info(f"   Via Base Station: {bs_eui}")
                        logger.info(f"   Reception Time: {rx_time_str}")
                        logger.info(f"   Operation ID: {op_id}")
                        logger.info(f"   Signal Quality:")
                        logger.info(f"     SNR: {message['snr']:.2f} dB")
                        logger.info(f"     RSSI: {message['rssi']:.2f} dBm")
                        logger.info(f"   Packet Counter: {message['packetCnt']}")
                        logger.info(f"   Payload:")
                        logger.info(f"     Length: {len(message['userData'])} bytes")
                        logger.info(f"     Data (hex): {' '.join(f'{b:02x}' for b in message['userData'])}")
                        logger.info(f"     Data (dec): {message['userData']}")
                        
                        # Check if this sensor is registered
                        is_registered = eui.lower() in self.registered_sensors
                        if is_registered:
                            reg_info = self.registered_sensors[eui.lower()]
                            logger.info(f"   Registration Status: ✅ REGISTERED")
                            logger.info(f"     Registered to: {reg_info.get('base_station', 'unknown')}")
                            logger.info(f"     Registration time: {reg_info.get('registration_time', 'unknown')}")
                        else:
                            logger.warning(f"   Registration Status: ⚠️  NOT REGISTERED")
                            logger.warning(f"     This sensor may not be configured in endpoints.json")
                        
                        data_dict = {
                            "bs_eui": bs_eui,
                            "rxTime": message["rxTime"],
                            "snr": message["snr"],
                            "rssi": message["rssi"],
                            "cnt": message["packetCnt"],
                            "data": message["userData"],
                        }
                        
                        mqtt_topic = f"ep/{eui}/ul"
                        logger.info(f"📤 MQTT PUBLICATION")
                        logger.info(f"   Topic: {mqtt_topic}")
                        logger.info(f"   Payload size: {len(json.dumps(data_dict))} bytes")
                        
                        await self.mqtt_out_queue.put(
                            {"topic": mqtt_topic, "payload": json.dumps(data_dict)}
                        )
                        
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
                        logger.info(f"   =================================")

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

    async def queue_watcher(self) -> None:
        logger.info("📨 MQTT queue watcher started - monitoring for configuration updates")
        try:
            while True:
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
        for sensor in self.sensor_config:
            eui = sensor['eui'].lower()
            status[eui] = {
                'eui': sensor['eui'],
                'nwKey': sensor['nwKey'],
                'shortAddr': sensor['shortAddr'],
                'bidi': sensor['bidi'],
                'registered': eui in self.registered_sensors,
                'registration_info': self.registered_sensors.get(eui, {})
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
