import asyncio
import json
import logging
import ssl
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
        try:
            with open(sensor_config_file, "r") as f:
                self.sensor_config = json.load(f)
        except Exception:
            self.sensor_config = {}

    async def start_server(self) -> None:
        logger.info("Setting up SSL context...")
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.load_cert_chain(
            certfile=bssci_config.CERT_FILE, keyfile=bssci_config.KEY_FILE
        )
        ssl_ctx.load_verify_locations(cafile=bssci_config.CA_FILE)
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        logger.info("SSL context configured successfully")

        logger.info(f"Starting TLS server on {bssci_config.LISTEN_HOST}:{bssci_config.LISTEN_PORT}")
        server = await asyncio.start_server(
            self.handle_client,
            bssci_config.LISTEN_HOST,
            bssci_config.LISTEN_PORT,
            ssl=ssl_ctx,
        )

        logger.info("Starting queue watcher task...")
        asyncio.create_task(self.queue_watcher())

        logger.info("TLS Server is ready and listening for connections")
        async with server:
            await server.serve_forever()

    async def send_attach_request(
        self, writer: asyncio.streams.StreamWriter, sensor: dict[str, Any]
    ) -> None:
        try:
            # Normalize nwKey to exactly 32 characters
            nw_key = sensor["nwKey"][:32] if len(sensor["nwKey"]) >= 32 else sensor["nwKey"]
            
            if (
                len(sensor["eui"]) == 16
                and len(nw_key) == 32
                and len(sensor["shortAddr"]) == 4
            ):
                logger.info(f"Sending attach request for sensor EUI: {sensor['eui']}, Short Address: {sensor['shortAddr']}")
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
                logger.debug(f"Attach request sent for sensor {sensor['eui']} with opID {self.opID}")
                self.opID -= 1
            else:
                logger.warning(f"Invalid sensor configuration for EUI {sensor.get('eui', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to send attach request for sensor {sensor.get('eui', 'unknown')}: {e}")

    async def attach_file(self, writer: asyncio.streams.StreamWriter) -> None:
        for sensor in self.sensor_config:
            try:
                await self.send_attach_request(writer, sensor)
            except Exception:
                pass

    async def send_status_requests(self) -> None:
        while True:
            await asyncio.sleep(bssci_config.STATUS_INTERVAL)
            logger.info(f"Sending status requests to {len(self.connected_base_stations)} base stations")
            for writer, bs_eui in self.connected_base_stations.items():
                try:
                    msg_pack = encode_message(messages.build_status_request(self.opID))
                    writer.write(
                        IDENTIFIER
                        + len(msg_pack).to_bytes(4, byteorder="little")
                        + msg_pack
                    )
                    await writer.drain()
                    logger.debug(f"Status request sent to base station {bs_eui} with opID {self.opID}")
                    self.opID -= 1
                except Exception as e:
                    logger.error(f"Failed to send status request to base station {bs_eui}: {e}")

    async def handle_client(
        self, reader: asyncio.streams.StreamReader, writer: asyncio.streams.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        logger.info(f"New connection established from {addr}")

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                # try:
                for message in decode_messages(data):
                    msg_type = message.get("command", "")
                    logger.debug(f"Received message type '{msg_type}' from {addr}")
                    if msg_type == "con":
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
                        logger.info(f"Base station {bs_eui} initiated connection from {addr}")
                    elif msg_type == "conCmp":
                        if (
                            writer in self.connecting_base_stations
                            and writer not in self.connected_base_stations
                        ):
                            bs_eui = self.connecting_base_stations[writer]
                            self.connected_base_stations[writer] = bs_eui
                            logger.info(f"Base station {bs_eui} connection completed successfully")
                            logger.info(f"Attaching {len(self.sensor_config)} sensors to base station {bs_eui}")
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
                        data_dict = {
                            "code": message["code"],
                            "memLoad": message["memLoad"],
                            "cpuLoad": message["cpuLoad"],
                            "dutyCycle": message["dutyCycle"],
                            "time": message["time"],
                            "uptime": message["uptime"],
                        }
                        await self.mqtt_out_queue.put(
                            {
                                "topic": f"bs/{self.connected_base_stations[writer]}",
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

                    elif msg_type == "attPrpRsp":
                        msg_pack = encode_message(
                            messages.build_attach_complete(message.get("opId", ""))
                        )
                        writer.write(
                            IDENTIFIER
                            + len(msg_pack).to_bytes(4, byteorder="little")
                            + msg_pack
                        )
                        await writer.drain()

                    elif msg_type == "ulData":
                        eui = int(message["epEui"]).to_bytes(8, byteorder="big").hex()
                        bs_eui = self.connected_base_stations[writer]
                        logger.info(f"Uplink data received from endpoint {eui} via base station {bs_eui}")
                        logger.debug(f"Data details - SNR: {message['snr']}, RSSI: {message['rssi']}, Packet count: {message['packetCnt']}")
                        data_dict = {
                            "bs_eui": bs_eui,
                            "rxTime": message["rxTime"],
                            "snr": message["snr"],
                            "rssi": message["rssi"],
                            "cnt": message["packetCnt"],
                            "data": message["userData"],
                        }
                        await self.mqtt_out_queue.put(
                            {"topic": f"ep/{eui}/ul", "payload": json.dumps(data_dict)}
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

        except Exception as e:
            logger.error(f"Error handling connection from {addr}: {e}")
        finally:
            try:
                with open(self.sensor_config_file, "w") as f:
                    json.dump(self.sensor_config, f, indent=4)
                logger.debug(f"Sensor configuration saved to {self.sensor_config_file}")
            except Exception as e:
                logger.error(f"Failed to save sensor configuration: {e}")
            
            logger.info(f"Connection to {addr} closed")
            writer.close()
            await writer.wait_closed()
            if writer in self.connected_base_stations:
                bs_eui = self.connected_base_stations.pop(writer)
                logger.info(f"Base station {bs_eui} disconnected")
            if writer in self.connecting_base_stations:
                self.connecting_base_stations.pop(writer)

    async def queue_watcher(self) -> None:
        try:
            while True:
                msg = dict(await self.mqtt_in_queue.get())
                if (
                    "eui" in msg.keys()
                    and "nwKey" in msg.keys()
                    and "shortAddr" in msg.keys()
                    and "bidi" in msg.keys()
                ):
                    logger.info(f"Processing configuration for endpoint {msg['eui']}")
                    if self.connected_base_stations:
                        logger.info(f"Sending attach request to {len(self.connected_base_stations)} connected base stations")
                        for writer, bs_eui in self.connected_base_stations.items():
                            logger.info(f"Sending attach request for sensor EUI: {msg['eui']} to base station: {bs_eui}")
                            await self.send_attach_request(writer, msg)
                    else:
                        logger.warning("No base stations connected - attach requests will be sent when base stations connect")
                    self.update_or_add_entry(msg)
        except asyncio.CancelledError:
            pass  # normal beim Client disconnect

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
