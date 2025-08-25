
import asyncio
import json
import random
import time
from datetime import datetime
from typing import Dict, Any

import protocol
import messages

IDENTIFIER = bytes("MIOTYB01", "utf-8")

class MiotyBaseStationSimulator:
    def __init__(self, host="localhost", port=16017):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.bs_eui = "74731D0000000001"  # Simulated base station EUI
        self.connected = False
        self.registered_sensors = []
        
        # Load sensor configurations
        try:
            with open("endpoints.json", "r") as f:
                self.sensor_configs = json.load(f)
        except:
            self.sensor_configs = []
        
        print(f"🏭 Base Station Simulator initialized")
        print(f"   Base Station EUI: {self.bs_eui}")
        print(f"   Available sensors: {len(self.sensor_configs)}")

    async def connect(self):
        """Connect to BSSCI server"""
        print(f"\n🔗 CONNECTING TO BSSCI SERVER")
        print(f"   Target: {self.host}:{self.port}")
        
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=10.0
            )
            print(f"✅ TCP connection established")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False

    async def send_message(self, message: Dict[str, Any]):
        """Send a BSSCI message"""
        try:
            msg_pack = protocol.encode_message(message)
            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack
            
            self.writer.write(full_message)
            await self.writer.drain()
            
            print(f"📤 Sent: {message['command']} (opId: {message.get('opId', 'N/A')})")
            return True
        except Exception as e:
            print(f"❌ Send error: {e}")
            return False

    async def receive_message(self):
        """Receive and decode BSSCI message"""
        try:
            data = await asyncio.wait_for(self.reader.read(4096), timeout=5.0)
            if not data:
                return None
                
            for message in protocol.decode_messages(data):
                print(f"📨 Received: {message['command']} (opId: {message.get('opId', 'N/A')})")
                return message
        except asyncio.TimeoutError:
            print(f"⏰ No response received")
            return None
        except Exception as e:
            print(f"❌ Receive error: {e}")
            return None

    async def perform_handshake(self):
        """Perform BSSCI connection handshake"""
        print(f"\n🤝 PERFORMING BSSCI HANDSHAKE")
        
        # Send connection request
        bs_uuid = [i for i in range(16)]  # Simple UUID
        con_message = {
            'command': 'con',
            'opId': 1001,
            'bsEui': int(self.bs_eui, 16),
            'snBsUuid': bs_uuid
        }
        
        if not await self.send_message(con_message):
            return False
            
        # Wait for connection response
        response = await self.receive_message()
        if not response or response.get('command') != 'conRsp':
            print(f"❌ Expected conRsp, got: {response}")
            return False
            
        # Send connection complete
        con_complete = {
            'command': 'conCmp',
            'opId': response.get('opId', 1001)
        }
        
        if not await self.send_message(con_complete):
            return False
            
        self.connected = True
        print(f"✅ BSSCI handshake completed")
        return True

    async def handle_attach_requests(self):
        """Handle incoming sensor attachment requests"""
        print(f"\n🔗 MONITORING FOR ATTACHMENT REQUESTS")
        
        while self.connected:
            try:
                message = await self.receive_message()
                if not message:
                    continue
                    
                if message.get('command') == 'attPrp':
                    # This is an attachment proposal from server
                    op_id = message.get('opId')
                    sensor_eui = message.get('eui', 'unknown')
                    
                    print(f"🔧 Processing attachment request:")
                    print(f"   Sensor EUI: {sensor_eui}")
                    print(f"   Operation ID: {op_id}")
                    
                    # Respond with attachment response (success)
                    response = {
                        'command': 'attPrpRsp',
                        'opId': op_id
                    }
                    
                    await self.send_message(response)
                    
                    # Wait for attachment complete
                    complete_msg = await self.receive_message()
                    if complete_msg and complete_msg.get('command') == 'attCmp':
                        print(f"✅ Sensor {sensor_eui} attached successfully")
                        self.registered_sensors.append(sensor_eui)
                    
                elif message.get('command') == 'statusReq':
                    # Handle status request
                    await self.send_status_response(message.get('opId'))
                    
            except Exception as e:
                print(f"❌ Error handling attachment: {e}")
                break

    async def send_status_response(self, op_id):
        """Send base station status response"""
        status_response = {
            'command': 'statusRsp',
            'opId': op_id,
            'code': 0,  # Success
            'memLoad': random.uniform(0.3, 0.8),  # 30-80%
            'cpuLoad': random.uniform(0.1, 0.6),  # 10-60%
            'dutyCycle': random.uniform(0.05, 0.15),  # 5-15%
            'time': int(time.time() * 1_000_000_000),  # nanoseconds
            'uptime': random.randint(3600, 86400)  # 1 hour to 1 day
        }
        
        await self.send_message(status_response)
        
        # Wait for status complete
        await self.receive_message()

    async def simulate_sensor_data(self):
        """Continuously send simulated sensor data"""
        print(f"\n📡 STARTING SENSOR DATA SIMULATION")
        
        packet_counters = {}
        
        while self.connected:
            if not self.sensor_configs:
                await asyncio.sleep(5)
                continue
                
            # Pick a random sensor
            sensor = random.choice(self.sensor_configs)
            sensor_eui = sensor['eui']
            
            # Initialize packet counter if needed
            if sensor_eui not in packet_counters:
                packet_counters[sensor_eui] = random.randint(1, 100)
            
            packet_counters[sensor_eui] += 1
            
            # Generate realistic sensor data
            sensor_data = self.generate_sensor_payload(sensor_eui)
            
            # Create uplink data message
            uplink_message = {
                'command': 'ulData',
                'opId': random.randint(5000, 9999),
                'epEui': int(sensor_eui, 16),
                'rxTime': int(time.time() * 1_000_000_000),  # nanoseconds
                'snr': random.uniform(5.0, 25.0),
                'rssi': random.uniform(-100.0, -50.0),
                'packetCnt': packet_counters[sensor_eui],
                'userData': sensor_data
            }
            
            print(f"📡 Sending sensor data from {sensor_eui}")
            print(f"   Packet #{packet_counters[sensor_eui]}")
            print(f"   Data: {[hex(b) for b in sensor_data]}")
            
            await self.send_message(uplink_message)
            
            # Wait for acknowledgment
            ack = await self.receive_message()
            if ack and ack.get('command') == 'ulDataRsp':
                print(f"✅ Data acknowledged")
            
            # Wait before next transmission (5-15 seconds)
            await asyncio.sleep(random.uniform(5, 15))

    def generate_sensor_payload(self, sensor_eui: str) -> list:
        """Generate realistic sensor payload data"""
        # Different sensor types based on EUI patterns
        if "74731D" in sensor_eui:
            # Environmental sensor (temperature, humidity, pressure)
            temp = int((random.uniform(15.0, 35.0) + 273.15) * 100)  # Kelvin * 100
            humidity = int(random.uniform(30.0, 90.0) * 100)  # % * 100
            pressure = int(random.uniform(980.0, 1030.0) * 10)  # hPa * 10
            
            return [
                (temp >> 8) & 0xFF, temp & 0xFF,  # Temperature
                (humidity >> 8) & 0xFF, humidity & 0xFF,  # Humidity  
                (pressure >> 8) & 0xFF, pressure & 0xFF,  # Pressure
                random.randint(0, 255)  # Battery level
            ]
            
        elif "FCA84A" in sensor_eui:
            # Motion/occupancy sensor
            motion = random.choice([0, 1])
            light = random.randint(0, 1000)
            battery = random.randint(50, 100)
            
            return [
                motion,  # Motion detected
                (light >> 8) & 0xFF, light & 0xFF,  # Light level
                battery,  # Battery %
                random.randint(0, 255)  # Status flags
            ]
            
        else:
            # Generic sensor with random data
            return [random.randint(0, 255) for _ in range(random.randint(4, 12))]

    async def disconnect(self):
        """Disconnect from server"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.connected = False
        print(f"🔌 Disconnected from BSSCI server")

async def run_simulation():
    """Run the complete base station simulation"""
    print(f"🏭 MIOTY BASE STATION SIMULATOR")
    print(f"=" * 60)
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    simulator = MiotyBaseStationSimulator()
    
    try:
        # Connect to server
        if not await simulator.connect():
            return
            
        # Perform handshake
        if not await simulator.perform_handshake():
            return
            
        print(f"\n🎯 SIMULATION ACTIVE")
        print(f"   Base station is connected and ready")
        print(f"   Will register sensors and send data continuously")
        print(f"   Check your web UI for live data!")
        print(f"   Press Ctrl+C to stop")
        
        # Run attachment handler and data simulation concurrently
        await asyncio.gather(
            simulator.handle_attach_requests(),
            simulator.simulate_sensor_data()
        )
        
    except KeyboardInterrupt:
        print(f"\n🛑 Simulation stopped by user")
    except Exception as e:
        print(f"❌ Simulation error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await simulator.disconnect()
        print(f"✅ Simulation complete")

if __name__ == "__main__":
    asyncio.run(run_simulation())
