
import json
import logging
import socket
import ssl
import threading
import time
from datetime import datetime
import queue

import bssci_config
from messages import build_connection_response, encode_message, decode_message
from protocol import IDENTIFIER

logger = logging.getLogger(__name__)

class SyncTLSServer:
    def __init__(self, sensor_config_file, mqtt_in_queue, mqtt_out_queue):
        self.sensor_config_file = sensor_config_file
        self.mqtt_in_queue = mqtt_in_queue
        self.mqtt_out_queue = mqtt_out_queue
        
        # Load sensor configuration
        self.sensor_config = self._load_sensor_config()
        
        # Connection tracking
        self.connected_base_stations = {}
        self.connecting_base_stations = {}
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
        
        logger.info("🏗️ Sync TLS Server initialized")
        logger.info(f"📁 Sensor config file: {sensor_config_file}")
        logger.info(f"📊 Loaded {len(self.sensor_config)} sensor configurations")

    def _load_sensor_config(self):
        """Load sensor configuration from JSON file"""
        try:
            with open(self.sensor_config_file, 'r') as f:
                config = json.load(f)
            logger.info(f"✅ Loaded {len(config)} sensor configurations")
            return config
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
            self._accept_connections()
            
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
        connection_start_time = time.time()
        messages_processed = 0
        
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
                    messages_processed += 1
                    self.stats['messages_processed'] += 1
                    
                    logger.info(f"📨 BSSCI message #{messages_processed} from {addr}")
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
                    
        except Exception as e:
            logger.error(f"❌ Client handler error for {addr}: {e}")
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
                self.connecting_base_stations[addr] = bs_eui
                logger.info(f"📤 Connection response sent to base station {bs_eui}")
            
        except Exception as e:
            logger.error(f"❌ Error handling connection request: {e}")

    def _handle_connection_complete(self, client_socket, addr, message):
        """Handle BSSCI connection complete"""
        logger.info(f"📨 Connection complete from {addr}")
        
        try:
            if addr in self.connecting_base_stations:
                bs_eui = self.connecting_base_stations.pop(addr)
                self.connected_base_stations[addr] = bs_eui
                self.stats['connections_established'] += 1
                
                logger.info(f"✅ Base station {bs_eui} connected successfully")
                logger.info(f"📊 Total connected base stations: {len(self.connected_base_stations)}")
                
        except Exception as e:
            logger.error(f"❌ Error handling connection complete: {e}")

    def _handle_uplink_message(self, client_socket, addr, message):
        """Handle uplink data message"""
        try:
            if addr not in self.connected_base_stations:
                logger.warning(f"⚠️ Uplink from non-connected base station {addr}")
                return
            
            bs_eui = self.connected_base_stations[addr]
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
            if addr in self.connected_base_stations:
                bs_eui = self.connected_base_stations[addr]
                logger.info(f"📊 Status response from base station {bs_eui}")
                logger.info(f"   CPU Load: {message.get('cpuLoad', 'N/A')}")
                logger.info(f"   Memory Load: {message.get('memLoad', 'N/A')}")
        except Exception as e:
            logger.error(f"❌ Error handling status response: {e}")

    def _cleanup_client(self, client_socket, addr):
        """Clean up client connection"""
        logger.info(f"🧹 Cleaning up client connection {addr}")
        
        try:
            client_socket.close()
        except:
            pass
            
        # Remove from tracking dictionaries
        if addr in self.connected_base_stations:
            bs_eui = self.connected_base_stations.pop(addr)
            logger.info(f"❌ Base station {bs_eui} disconnected")
            
        if addr in self.connecting_base_stations:
            self.connecting_base_stations.pop(addr)
            
        if addr in self.client_threads:
            self.client_threads.pop(addr)

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

    def stop(self):
        """Stop the TLS server"""
        logger.info("🛑 Stopping synchronous TLS server...")
        
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
                
        # Wait for client threads to finish
        for thread in self.client_threads.values():
            thread.join(timeout=2)
            
        logger.info("✅ Synchronous TLS server stopped")

    def get_stats(self):
        """Get server statistics"""
        uptime = time.time() - self.stats['start_time']
        return {
            **self.stats,
            'connected_base_stations': len(self.connected_base_stations),
            'connecting_base_stations': len(self.connecting_base_stations),
            'uptime_seconds': uptime
        }
