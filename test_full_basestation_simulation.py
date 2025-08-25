
#!/usr/bin/env python3
"""
Full Base Station Simulation for BSSCI Testing
Simulates a complete mioty base station connecting to your BSSCI server
"""

import asyncio
import json
import logging
import struct
import time
from datetime import datetime
from typing import List, Dict, Any
import random

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

IDENTIFIER = b"MIOTYB01"

class BSScIBaseStationSimulator:
    def __init__(self, host="localhost", port=16017):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.bs_eui = 0x7465737442530001  # Test base station EUI
        self.sc_eui = 0x7465737453430001  # Test service center EUI
        self.op_id = 1000
        self.connected = False
        
        # Load sensors from endpoints.json
        try:
            with open("endpoints.json", "r") as f:
                self.sensors = json.load(f)
            logger.info(f"Loaded {len(self.sensors)} sensors from endpoints.json")
        except Exception as e:
            logger.error(f"Failed to load endpoints.json: {e}")
            self.sensors = []

    def encode_message(self, message: Dict[str, Any]) -> bytes:
        """Encode BSSCI message"""
        if message["command"] == "con":
            # Connection request
            data = struct.pack("<HQQ16B", 
                             message["opId"], 
                             message["bsEui"], 
                             message["snBsUuid"][0],  # Simplified UUID
                             *message["snBsUuid"])
            return b"con" + b"\x00" + data
        
        elif message["command"] == "conCmp":
            # Connection complete
            data = struct.pack("<H", message["opId"])
            return b"conCmp" + b"\x00\x00\x00" + data
            
        elif message["command"] == "attPrpRsp":
            # Attachment response
            data = struct.pack("<H", message["opId"])
            return b"attPrpRsp" + b"\x00" + data
            
        elif message["command"] == "ulData":
            # Uplink data
            user_data = message["userData"]
            data = struct.pack("<HQQHHHH", 
                             message["opId"],
                             message["epEui"],
                             message["rxTime"],
                             message["snr"],
                             message["rssi"], 
                             message["packetCnt"],
                             len(user_data))
            data += bytes(user_data)
            return b"ulData" + b"\x00\x00" + data
            
        return b""

    def decode_message(self, data: bytes) -> Dict[str, Any]:
        """Decode BSSCI message"""
        if len(data) < 8:
            return {}
            
        command = data[:8].rstrip(b'\x00').decode('ascii', errors='ignore')
        payload = data[8:]
        
        if command == "conRsp":
            if len(payload) >= 18:
                sc_eui, op_id, sn_resume = struct.unpack("<QH?", payload[:11])
                return {
                    "command": "conRsp",
                    "scEui": sc_eui,
                    "opId": op_id,
                    "snResume": sn_resume,
                    "snScUuid": list(payload[11:27]) if len(payload) >= 27 else []
                }
        
        elif command == "attPrp":
            if len(payload) >= 42:
                op_id, ep_eui = struct.unpack("<HQ", payload[:10])
                nw_key = payload[10:42].hex()
                short_addr = struct.unpack("<H", payload[42:44])[0] if len(payload) >= 44 else 0
                bidi = bool(payload[44]) if len(payload) > 44 else False
                
                return {
                    "command": "attPrp",
                    "opId": op_id,
                    "epEui": ep_eui,
                    "nwKey": nw_key,
                    "shortAddr": f"{short_addr:04X}",
                    "bidi": bidi
                }
        
        return {"command": command, "raw_payload": payload.hex()}

    async def connect(self) -> bool:
        """Connect to BSSCI server"""
        try:
            logger.info(f"🔗 Connecting to BSSCI server at {self.host}:{self.port}")
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            logger.info("✅ TCP connection established")
            return True
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send BSSCI message"""
        encoded = self.encode_message(message)
        full_message = IDENTIFIER + len(encoded).to_bytes(4, byteorder="little") + encoded
        
        logger.info(f"📤 Sending {message['command']}: {message}")
        self.writer.write(full_message)
        await self.writer.drain()

    async def receive_message(self) -> Dict[str, Any]:
        """Receive BSSCI message"""
        try:
            # Read identifier
            identifier = await self.reader.read(8)
            if identifier != IDENTIFIER:
                logger.warning(f"Invalid identifier: {identifier}")
                return {}
            
            # Read length
            length_data = await self.reader.read(4)
            length = int.from_bytes(length_data, byteorder="little")
            
            # Read payload
            payload = await self.reader.read(length)
            
            message = self.decode_message(payload)
            logger.info(f"📨 Received {message.get('command', 'unknown')}: {message}")
            return message
            
        except Exception as e:
            logger.error(f"❌ Error receiving message: {e}")
            return {}

    async def perform_handshake(self) -> bool:
        """Perform BSSCI connection handshake"""
        logger.info("🤝 Starting BSSCI handshake")
        
        # Send connection request
        con_message = {
            "command": "con",
            "opId": self.op_id,
            "bsEui": self.bs_eui,
            "snBsUuid": [16, 32, 48, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 17]
        }
        
        await self.send_message(con_message)
        
        # Wait for connection response
        response = await self.receive_message()
        if response.get("command") != "conRsp":
            logger.error("❌ Expected connection response")
            return False
        
        # Send connection complete
        con_cmp_message = {
            "command": "conCmp", 
            "opId": self.op_id
        }
        
        await self.send_message(con_cmp_message)
        logger.info("✅ BSSCI handshake completed")
        self.connected = True
        return True

    async def handle_attach_requests(self) -> None:
        """Handle sensor attachment requests from service center"""
        logger.info("👂 Listening for attachment requests...")
        
        while self.connected:
            try:
                message = await asyncio.wait_for(self.receive_message(), timeout=1.0)
                
                if message.get("command") == "attPrp":
                    logger.info(f"🔗 Attachment request for sensor {message.get('epEui', 'unknown'):016X}")
                    
                    # Send attachment response (acceptance)
                    response = {
                        "command": "attPrpRsp",
                        "opId": message.get("opId", 0)
                    }
                    
                    await self.send_message(response)
                    
                    # Wait for attachment complete
                    await self.receive_message()
                    
                    logger.info(f"✅ Sensor {message.get('epEui', 0):016X} attached successfully")
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"❌ Error handling attachment: {e}")
                break

    async def simulate_sensor_data(self) -> None:
        """Simulate sensor data transmission"""
        logger.info("📡 Starting sensor data simulation")
        
        # Wait a bit for attachments to complete
        await asyncio.sleep(3)
        
        packet_counter = 1
        
        while self.connected:
            try:
                # Pick a random sensor
                if not self.sensors:
                    await asyncio.sleep(5)
                    continue
                    
                sensor = random.choice(self.sensors)
                sensor_eui = int(sensor["eui"], 16)
                
                # Generate realistic sensor data
                temperature = random.randint(150, 350)  # 15.0 - 35.0°C (in 0.1°C)
                humidity = random.randint(300, 800)     # 30.0 - 80.0% (in 0.1%)
                battery = random.randint(28, 42)        # 2.8 - 4.2V (in 0.1V)
                
                sensor_data = [
                    (temperature >> 8) & 0xFF, temperature & 0xFF,
                    (humidity >> 8) & 0xFF, humidity & 0xFF,
                    battery,
                    packet_counter & 0xFF
                ]
                
                uplink_message = {
                    "command": "ulData",
                    "opId": self.op_id + packet_counter,
                    "epEui": sensor_eui,
                    "rxTime": int(time.time() * 1_000_000_000),  # nanoseconds
                    "snr": random.randint(-100, 200),  # -10.0 to 20.0 dB
                    "rssi": random.randint(-1200, -400),  # -120 to -40 dBm
                    "packetCnt": packet_counter,
                    "userData": sensor_data
                }
                
                await self.send_message(uplink_message)
                
                # Wait for uplink response
                await self.receive_message()
                
                logger.info(f"📊 Sensor data sent: EUI={sensor['eui']}, Temp={temperature/10:.1f}°C, Hum={humidity/10:.1f}%, Bat={battery/10:.1f}V")
                
                packet_counter += 1
                
                # Send data every 10-30 seconds
                await asyncio.sleep(random.randint(10, 30))
                
            except Exception as e:
                logger.error(f"❌ Error sending sensor data: {e}")
                await asyncio.sleep(5)

    async def run_simulation(self) -> None:
        """Run the complete base station simulation"""
        try:
            logger.info("🚀 STARTING FULL BASE STATION SIMULATION")
            logger.info("=" * 60)
            
            # Connect to server
            if not await self.connect():
                return
            
            # Perform handshake
            if not await self.perform_handshake():
                return
            
            logger.info("🎯 Base station connected and ready")
            logger.info(f"📍 Base Station EUI: {self.bs_eui:016X}")
            logger.info(f"📊 Will simulate data for {len(self.sensors)} sensors")
            
            # Start handling attachments and sending data concurrently
            attach_task = asyncio.create_task(self.handle_attach_requests())
            data_task = asyncio.create_task(self.simulate_sensor_data())
            
            logger.info("✅ Simulation running - check your web UI for:")
            logger.info("   • Connected base stations")
            logger.info("   • Registered sensors") 
            logger.info("   • Live sensor data")
            logger.info("   • MQTT messages")
            logger.info("\nPress Ctrl+C to stop simulation...")
            
            # Run until interrupted
            await asyncio.gather(attach_task, data_task)
            
        except KeyboardInterrupt:
            logger.info("\n🛑 Simulation stopped by user")
        except Exception as e:
            logger.error(f"❌ Simulation error: {e}")
        finally:
            self.connected = False
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
            logger.info("🔌 Disconnected from server")

async def main():
    """Main function"""
    simulator = BSScIBaseStationSimulator()
    await simulator.run_simulation()

if __name__ == "__main__":
    asyncio.run(main())
