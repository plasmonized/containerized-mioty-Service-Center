
import json
import logging
import ssl
import socket
import threading
import time
from datetime import datetime
from queue import Queue, Empty
from typing import Any, Dict

import bssci_config
import messages
from protocol import decode_messages, encode_message
import requests

logger = logging.getLogger(__name__)

IDENTIFIER = bytes("MIOTYB01", "utf-8")


class SyncTLSServer:
    def __init__(
        self,
        sensor_config_file: str,
        mqtt_out_queue: Queue,
        mqtt_in_queue: Queue,
    ) -> None:
        self.opID = -1
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue
        self.connected_base_stations: Dict[socket.socket, str] = {}
        self.connecting_base_stations: Dict[socket.socket, str] = {}
        self.sensor_config_file = sensor_config_file
        self.registered_sensors: Dict[str, Dict[str, Any]] = {}
        self.pending_attach_requests: Dict[int, Dict[str, Any]] = {}
        self.running = True
        
        try:
            with open(sensor_config_file, "r") as f:
                self.sensor_config = json.load(f)
        except Exception:
            self.sensor_config = []

    def start_server(self) -> None:
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

            logger.info("✓ SSL context configured successfully")

        except Exception as e:
            logger.error(f"❌ SSL configuration error: {e}")
            raise

        logger.info(f"🚀 Starting BSSCI TLS server...")
        logger.info(f"   Listen address: {bssci_config.LISTEN_HOST}:{bssci_config.LISTEN_PORT}")

        # Create server socket
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((bssci_config.LISTEN_HOST, bssci_config.LISTEN_PORT))
        server_socket.listen(5)

        # Start MQTT queue watcher
        queue_thread = threading.Thread(target=self.queue_watcher, daemon=True)
        queue_thread.start()

        # Start status request task
        status_thread = threading.Thread(target=self.send_status_requests, daemon=True)
        status_thread.start()

        logger.info("✓ BSSCI TLS Server is ready and listening for connections")

        try:
            while self.running:
                try:
                    client_socket, addr = server_socket.accept()
                    logger.info(f"🔗 New connection from {addr}")
                    
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, ssl_ctx, addr),
                        daemon=True
                    )
                    client_thread.start()
                    
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")
                        time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Server shutting down...")
        finally:
            self.running = False
            server_socket.close()

    def handle_client(self, client_socket: socket.socket, ssl_ctx: ssl.SSLContext, addr):
        try:
            # Wrap socket with SSL
            ssl_socket = ssl_ctx.wrap_socket(client_socket, server_side=True)
            
            logger.info(f"✓ SSL handshake successful with {addr}")
            
            # Get certificate info
            cert = ssl_socket.getpeercert()
            if cert:
                subject = cert.get('subject', [])
                cn = None
                for field in subject:
                    for name, value in field:
                        if name == 'commonName':
                            cn = value
                            break
                logger.info(f"   Client certificate CN: {cn}")

            messages_processed = 0
            
            while self.running:
                try:
                    data = ssl_socket.recv(4096)
                    if not data:
                        break
                        
                    for message in decode_messages(data):
                        messages_processed += 1
                        msg_type = message.get("command", "")
                        
                        logger.info(f"📨 BSSCI message #{messages_processed} from {addr}: {msg_type}")
                        
                        if msg_type == "con":
                            self.handle_connection_request(ssl_socket, message, addr)
                        elif msg_type == "conCmp":
                            self.handle_connection_complete(ssl_socket, message, addr)
                        elif msg_type == "ping":
                            self.handle_ping(ssl_socket, message)
                        elif msg_type == "pingCmp":
                            logger.debug(f"Ping complete from {addr}")
                        elif msg_type == "statusRsp":
                            self.handle_status_response(ssl_socket, message)
                        elif msg_type == "attPrpRsp":
                            self.handle_attach_response(ssl_socket, message)
                        elif msg_type == "ulData":
                            self.handle_uplink_data(ssl_socket, message)
                        else:
                            logger.warning(f"Unknown message type: {msg_type}")
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"SSL error with {addr}: {e}")
        finally:
            try:
                ssl_socket.close()
            except:
                pass
            
            # Remove from connected stations
            if ssl_socket in self.connected_base_stations:
                bs_eui = self.connected_base_stations.pop(ssl_socket)
                logger.info(f"❌ Base station {bs_eui} disconnected")
            if ssl_socket in self.connecting_base_stations:
                self.connecting_base_stations.pop(ssl_socket)

    def handle_connection_request(self, ssl_socket, message, addr):
        logger.info(f"📨 BSSCI CONNECTION REQUEST from {addr}")
        bs_eui = int(message["bsEui"]).to_bytes(8, byteorder="big").hex()
        
        msg = encode_message(
            messages.build_connection_response(
                message.get("opId", ""), message.get("snBsUuid", "")
            )
        )
        ssl_socket.send(IDENTIFIER + len(msg).to_bytes(4, byteorder="little") + msg)
        
        self.connecting_base_stations[ssl_socket] = bs_eui
        logger.info(f"📤 CONNECTION RESPONSE sent to {bs_eui}")

    def handle_connection_complete(self, ssl_socket, message, addr):
        logger.info(f"📨 CONNECTION COMPLETE from {addr}")
        
        if ssl_socket in self.connecting_base_stations:
            bs_eui = self.connecting_base_stations.pop(ssl_socket)
            self.connected_base_stations[ssl_socket] = bs_eui
            
            logger.info(f"✅ Base station {bs_eui} connected successfully")
            logger.info(f"   Total connected: {len(self.connected_base_stations)}")
            
            # Start sensor attachment
            threading.Thread(target=self.attach_sensors, args=(ssl_socket,), daemon=True).start()

    def attach_sensors(self, ssl_socket):
        bs_eui = self.connected_base_stations.get(ssl_socket, "unknown")
        logger.info(f"🔗 Starting sensor attachment for {bs_eui}")
        
        for sensor in self.sensor_config:
            try:
                self.send_attach_request(ssl_socket, sensor)
                time.sleep(0.1)  # Small delay between requests
            except Exception as e:
                logger.error(f"Failed to attach sensor {sensor.get('eui')}: {e}")

    def send_attach_request(self, ssl_socket, sensor):
        bs_eui = self.connected_base_stations.get(ssl_socket, "unknown")
        
        logger.info(f"📤 Sending attach request for {sensor['eui']} to {bs_eui}")
        
        attach_message = messages.build_attach_request(sensor, self.opID)
        msg_pack = encode_message(attach_message)
        full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack
        
        ssl_socket.send(full_message)
        
        # Track request
        self.pending_attach_requests[self.opID] = {
            'sensor_eui': sensor['eui'],
            'timestamp': time.time(),
            'base_station': bs_eui
        }
        
        self.opID -= 1

    def handle_ping(self, ssl_socket, message):
        msg_pack = encode_message(messages.build_ping_response(message.get("opId", "")))
        ssl_socket.send(IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack)

    def handle_status_response(self, ssl_socket, message):
        bs_eui = self.connected_base_stations.get(ssl_socket, "unknown")
        
        logger.info(f"📊 Status response from {bs_eui}")
        logger.info(f"   CPU: {message['cpuLoad']:.1%}, Memory: {message['memLoad']:.1%}")
        
        data_dict = {
            "code": message["code"],
            "memLoad": message["memLoad"],
            "cpuLoad": message["cpuLoad"],
            "dutyCycle": message["dutyCycle"],
            "time": message["time"],
            "uptime": message["uptime"],
        }
        
        self.mqtt_out_queue.put({
            "topic": f"bs/{bs_eui}",
            "payload": json.dumps(data_dict)
        })
        
        # Send status complete
        msg_pack = encode_message(messages.build_status_complete(message.get("opId", "")))
        ssl_socket.send(IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack)

    def handle_attach_response(self, ssl_socket, message):
        op_id = message.get("opId", "unknown")
        bs_eui = self.connected_base_stations.get(ssl_socket, "unknown")
        
        logger.info(f"📨 Attach response from {bs_eui} (opID: {op_id})")
        
        # Track successful registration
        if op_id in self.pending_attach_requests:
            request = self.pending_attach_requests.pop(op_id)
            sensor_eui = request['sensor_eui']
            
            eui_key = sensor_eui.lower()
            if eui_key not in self.registered_sensors:
                self.registered_sensors[eui_key] = {
                    'status': 'registered',
                    'base_stations': [],
                    'timestamp': time.time()
                }
            
            if bs_eui not in self.registered_sensors[eui_key]['base_stations']:
                self.registered_sensors[eui_key]['base_stations'].append(bs_eui)
            
            logger.info(f"✅ Sensor {sensor_eui} registered to {bs_eui}")
        
        # Send attach complete
        msg_pack = encode_message(messages.build_attach_complete(message.get("opId", "")))
        ssl_socket.send(IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack)

    def handle_uplink_data(self, ssl_socket, message):
        eui = int(message["epEui"]).to_bytes(8, byteorder="big").hex()
        bs_eui = self.connected_base_stations.get(ssl_socket, "unknown")
        
        logger.info(f"📊 Uplink data from sensor {eui} via {bs_eui}")
        logger.info(f"   SNR: {message['snr']:.2f}dB, RSSI: {message['rssi']:.2f}dBm")
        logger.info(f"   Payload: {message['userData']}")
        
        data_dict = {
            "bs_eui": bs_eui,
            "rxTime": message["rxTime"],
            "snr": message["snr"],
            "rssi": message["rssi"],
            "cnt": message["packetCnt"],
            "data": message["userData"],
        }
        
        # Forward to MQTT
        self.mqtt_out_queue.put({
            "topic": f"ep/{eui}/ul",
            "payload": json.dumps(data_dict)
        })
        
        # Send response
        msg_pack = encode_message(messages.build_ul_response(message.get("opId", "")))
        ssl_socket.send(IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack)

    def send_status_requests(self):
        """Periodic status requests"""
        logger.info("📊 Status request task started")
        
        while self.running:
            try:
                time.sleep(bssci_config.STATUS_INTERVAL)
                
                if self.connected_base_stations:
                    logger.info(f"📊 Sending status requests to {len(self.connected_base_stations)} base stations")
                    
                    for ssl_socket, bs_eui in list(self.connected_base_stations.items()):
                        try:
                            msg_pack = encode_message(messages.build_status_request(self.opID))
                            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack
                            ssl_socket.send(full_message)
                            self.opID -= 1
                        except Exception as e:
                            logger.error(f"Failed to send status to {bs_eui}: {e}")
                            # Remove failed connection
                            if ssl_socket in self.connected_base_stations:
                                self.connected_base_stations.pop(ssl_socket)
            except Exception as e:
                logger.error(f"Status request error: {e}")

    def queue_watcher(self):
        """Watch for MQTT configuration messages"""
        logger.info("📨 MQTT queue watcher started")
        
        while self.running:
            try:
                msg = self.mqtt_in_queue.get(timeout=1)
                logger.info(f"📥 Configuration message: {msg.get('eui')}")
                
                if all(key in msg for key in ["eui", "nwKey", "shortAddr", "bidi"]):
                    # Update config and send to all base stations
                    self.update_sensor_config(msg)
                    
                    for ssl_socket in list(self.connected_base_stations.keys()):
                        try:
                            self.send_attach_request(ssl_socket, msg)
                        except Exception as e:
                            logger.error(f"Failed to send config to base station: {e}")
                            
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Queue watcher error: {e}")

    def update_sensor_config(self, msg):
        """Update sensor configuration"""
        for sensor in self.sensor_config:
            if sensor["eui"].lower() == msg["eui"].lower():
                sensor.update(msg)
                break
        else:
            self.sensor_config.append(msg)
        
        # Save to file
        try:
            with open(self.sensor_config_file, "w") as f:
                json.dump(self.sensor_config, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get_base_station_status(self):
        """Get connected base stations"""
        return {
            "connected": [{"eui": eui, "status": "connected"} for eui in self.connected_base_stations.values()],
            "total_connected": len(self.connected_base_stations)
        }

    def get_sensor_registration_status(self):
        """Get sensor registration status"""
        status = {}
        for sensor in self.sensor_config:
            eui = sensor['eui'].lower()
            reg_info = self.registered_sensors.get(eui, {})
            status[eui] = {
                'eui': sensor['eui'],
                'registered': eui in self.registered_sensors,
                'base_stations': reg_info.get('base_stations', [])
            }
        return status
