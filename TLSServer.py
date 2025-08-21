import asyncio
import json
import ssl
from typing import Any, Dict

import bssci_config
import messages
from protocol import decode_messages, encode_message

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
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.load_cert_chain(
            certfile=bssci_config.CERT_FILE, keyfile=bssci_config.KEY_FILE
        )
        ssl_ctx.load_verify_locations(cafile=bssci_config.CA_FILE)
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED

        server = await asyncio.start_server(
            self.handle_client,
            bssci_config.LISTEN_HOST,
            bssci_config.LISTEN_PORT,
            ssl=ssl_ctx,
        )

        asyncio.create_task(self.queue_watcher())

        async with server:
            await server.serve_forever()

    async def send_attach_request(
        self, writer: asyncio.streams.StreamWriter, sensor: dict[str, Any]
    ) -> None:
        try:
            if (
                len(sensor["eui"]) == 16
                and len(sensor["nwKey"]) == 32
                and len(sensor["shortAddr"]) == 4
            ):
                print(f"Sensor: {sensor['eui']} {sensor['shortAddr']}")
                msg_pack = encode_message(
                    messages.build_attach_request(sensor, self.opID)
                )
                writer.write(
                    IDENTIFIER
                    + len(msg_pack).to_bytes(4, byteorder="little")
                    + msg_pack
                )
                await writer.drain()
                self.opID -= 1
        except Exception:
            pass

    async def attach_file(self, writer: asyncio.streams.StreamWriter) -> None:
        for sensor in self.sensor_config:
            try:
                await self.send_attach_request(writer, sensor)
            except Exception:
                pass

    async def send_status_requests(self) -> None:
        while True:
            await asyncio.sleep(bssci_config.STATUS_INTERVAL)
            for writer, bs_eui in self.connected_base_stations.items():
                msg_pack = encode_message(messages.build_status_request(self.opID))
                writer.write(
                    IDENTIFIER
                    + len(msg_pack).to_bytes(4, byteorder="little")
                    + msg_pack
                )
                await writer.drain()
                self.opID -= 1

    async def handle_client(
        self, reader: asyncio.streams.StreamReader, writer: asyncio.streams.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        print(f"[INFO] Verbindung von {addr} hergestellt.")

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                # try:
                for message in decode_messages(data):
                    # print(message)
                    msg_type = message.get("command", "")
                    # print(msg_type)
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
                        self.connecting_base_stations[writer] = (
                            int(message["bsEui"]).to_bytes(8, byteorder="big").hex()
                        )
                    elif msg_type == "conCmp":
                        if (
                            writer in self.connecting_base_stations
                            and writer not in self.connected_base_stations
                        ):
                            self.connected_base_stations[writer] = (
                                self.connecting_base_stations[writer]
                            )
                            await self.attach_file(writer)
                            asyncio.create_task(self.send_status_requests())

                    elif msg_type == "ping":
                        # print("[PING] Ping-Anfrage empfangen.")
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
                        pass

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
                        print(message)
                        data_dict = {
                            "bs_eui": self.connected_base_stations[writer],
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
            print(f"[ERROR] Fehler bei Verbindung {addr}: {e}")
        finally:
            with open(self.sensor_config_file, "w") as f:
                json.dump(self.sensor_config, f, indent=4)
            print(f"[INFO] Verbindung zu {addr} geschlossen.")
            writer.close()
            await writer.wait_closed()
            if writer in self.connected_base_stations:
                self.connected_base_stations.pop(writer)

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
                    for writer, bs_eui in self.connected_base_stations.items():
                        await self.send_attach_request(writer, msg)
                    self.update_or_add_entry(msg)
        except asyncio.CancelledError:
            pass  # normal beim Client disconnect

    def update_or_add_entry(self, msg: dict[str, Any]) -> None:
        for sensor in self.sensor_config:
            if sensor["eui"].lower() == msg["eui"].lower():
                sensor["nwKey"] = msg["nwKey"]
                sensor["shortAddr"] = msg["shortAddr"]
                sensor["bidi"] = msg["bidi"]
                return  # Eintrag wurde aktualisiert

        # Wenn kein Eintrag gefunden wurde → neu hinzufügen
        self.sensor_config.append(
            {
                "eui": msg["eui"],
                "nwKey": msg["nwKey"],
                "shortAddr": msg["shortAddr"],
                "bidi": msg["bidi"],
            }
        )
