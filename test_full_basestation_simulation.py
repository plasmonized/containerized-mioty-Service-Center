
import asyncio
import ssl
import msgpack
import json
import time
import random
from datetime import datetime
from protocol import encode_message

IDENTIFIER = bytes("MIOTYB01", 'utf-8')

class FullBaseStationSimulator:
    def __init__(self, host="localhost", port=16017):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.connected = False
        self.bs_eui = "70b3d59cd0000022"  # Our base station EUI
        self.registered_sensors = {}
        self.data_transmission_active = False
        
        # Sensor configurations from endpoints.json
        self.sensors = [
            {"eui": "0123456789ABCDEF", "nwKey": "00112233445566778899AABBCCDDEEFF", "shortAddr": "0000"},
            {"eui": "74731d0000000089", "nwKey": "b49dfc69de7193c4b3faa36a51d76512", "shortAddr": "0000"},
            {"eui": "74731d00000000f8", "nwKey": "e516d50d89729e5073c4a6c9be729233", "shortAddr": "0000"},
            {"eui": "74731d00000000f9", "nwKey": "96c75144ae9cc861c8f2c82248bc103f", "shortAddr": "0000"},
            {"eui": "fca84a030000130a", "nwKey": "C43FE1803F1629FEEE67B364DFCDEF53", "shortAddr": "130A"},
            {"eui": "fca84a010000118f", "nwKey": "9DC473375F52D45A940EF6706B618306", "shortAddr": "118F"},
        ]

    async def connect(self):
        """Connect to BSSCI server with automatic SSL detection"""
        print(f"🔌 Connecting to BSSCI server at {self.host}:{self.port}")
        
        # Try non-SSL first (for local testing)
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=5.0
            )
            print("✅ Connected via non-SSL (local testing mode)")
            self.connected = True
            return
        except Exception as e:
            print(f"⚠️  Non-SSL connection failed: {e}")
        
        # Fallback to SSL
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, ssl=ssl_context), timeout=5.0
            )
            print("✅ Connected via SSL/TLS")
            self.connected = True
        except Exception as e:
            print(f"❌ SSL connection failed: {e}")
            raise

    async def disconnect(self):
        """Clean disconnect"""
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            await self.writer.wait_closed()
        self.connected = False
        print("🔌 Disconnected from BSSCI server")

    async def send_message(self, message_dict, expect_response=True, timeout=10.0):
        """Send a BSSCI protocol message"""
        if not self.connected:
            raise Exception("Not connected to server")
        
        try:
            # Encode message
            msg_pack = encode_message(message_dict)
            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder='little') + msg_pack
            
            # Send message
            self.writer.write(full_message)
            await self.writer.drain()
            
            command = message_dict.get('command', 'unknown')
            op_id = message_dict.get('opId', 'N/A')
            print(f"📤 Sent: {command} (opId: {op_id})")
            
            if expect_response:
                try:
                    response_data = await asyncio.wait_for(self.reader.read(4096), timeout=timeout)
                    if response_data and len(response_data) >= 12:
                        if response_data[:8] == IDENTIFIER:
                            length = int.from_bytes(response_data[8:12], byteorder='little')
                            if len(response_data) >= 12 + length:
                                msg_data = response_data[12:12+length]
                                response = msgpack.unpackb(msg_data, raw=False, strict_map_key=False)
                                resp_command = response.get('command', 'unknown')
                                resp_op_id = response.get('opId', 'N/A')
                                print(f"📨 Received: {resp_command} (opId: {resp_op_id})")
                                return response
                    print("❌ Invalid or incomplete response")
                    return None
                except asyncio.TimeoutError:
                    print(f"⏰ Response timeout after {timeout}s")
                    return None
            
            return True
            
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            raise

    async def perform_connection_handshake(self):
        """Perform BSSCI connection handshake"""
        print(f"\n🤝 PHASE 1: CONNECTION HANDSHAKE")
        print("=" * 50)
        
        # Step 1: Send connection request
        print("📋 Step 1: Connection Request")
        connection_msg = {
            "command": "con",
            "opId": 5001,
            "bsEui": int(self.bs_eui, 16),
            "snBsUuid": [0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80,
                        0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0, 0x11]
        }
        
        response = await self.send_message(connection_msg)
        if not response or response.get("command") != "conRsp":
            raise Exception("Connection handshake failed")
        
        print("✅ Connection response received")
        
        # Step 2: Send connection complete
        print("\n📋 Step 2: Connection Complete")
        complete_msg = {
            "command": "conCmp",
            "opId": 5001
        }
        
        await self.send_message(complete_msg, expect_response=False)
        print("✅ Connection complete sent")
        
        # Wait for server to process and start attachment proposals
        print("⏳ Waiting for server to process connection...")
        await asyncio.sleep(2)
        
        return True

    async def handle_sensor_registration(self):
        """Handle incoming sensor attachment proposals from server"""
        print(f"\n🔗 PHASE 2: SENSOR REGISTRATION")
        print("=" * 50)
        
        registered_count = 0
        max_registrations = len(self.sensors)
        
        print(f"🎯 Expecting up to {max_registrations} sensor registrations...")
        
        # Listen for attachment proposals for a reasonable time
        start_time = asyncio.get_event_loop().time()
        timeout = 30.0  # 30 seconds to handle all registrations
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                # Check for incoming messages
                response_data = await asyncio.wait_for(self.reader.read(4096), timeout=2.0)
                
                if response_data and len(response_data) >= 12:
                    if response_data[:8] == IDENTIFIER:
                        length = int.from_bytes(response_data[8:12], byteorder='little')
                        if len(response_data) >= 12 + length:
                            msg_data = response_data[12:12+length]
                            message = msgpack.unpackb(msg_data, raw=False, strict_map_key=False)
                            
                            if message.get("command") == "attPrp":
                                # Handle attachment proposal
                                op_id = message.get("opId")
                                ep_eui = message.get("epEui")
                                
                                if ep_eui:
                                    eui_hex = int(ep_eui).to_bytes(8, byteorder="big").hex()
                                    print(f"📨 Attachment proposal for sensor: {eui_hex} (opId: {op_id})")
                                    
                                    # Send attachment response (accept)
                                    attach_response = {
                                        "command": "attPrpRsp",
                                        "opId": op_id
                                    }
                                    
                                    await self.send_message(attach_response, expect_response=False)
                                    
                                    # Store registered sensor
                                    self.registered_sensors[eui_hex] = {
                                        "op_id": op_id,
                                        "registered_at": time.time(),
                                        "packet_count": 0
                                    }
                                    
                                    registered_count += 1
                                    print(f"✅ Sensor {eui_hex} registered ({registered_count}/{max_registrations})")
                                    
                                    if registered_count >= max_registrations:
                                        print(f"🎉 All {registered_count} sensors registered!")
                                        break
                            
            except asyncio.TimeoutError:
                # No message received in timeout period
                continue
            except Exception as e:
                print(f"❌ Error during registration: {e}")
                break
        
        print(f"\n📊 Registration Summary:")
        print(f"   Total registered: {registered_count}")
        print(f"   Registration time: {asyncio.get_event_loop().time() - start_time:.2f}s")
        
        if registered_count > 0:
            print(f"   Registered sensors:")
            for eui, info in self.registered_sensors.items():
                print(f"     - {eui} (opId: {info['op_id']})")
        
        return registered_count > 0

    async def simulate_sensor_data_transmission(self, duration_minutes=5):
        """Simulate continuous sensor data transmission"""
        print(f"\n📡 PHASE 3: LIVE SENSOR DATA TRANSMISSION")
        print("=" * 50)
        print(f"🕐 Duration: {duration_minutes} minutes")
        print(f"📊 Registered sensors: {len(self.registered_sensors)}")
        
        if not self.registered_sensors:
            print("❌ No registered sensors - cannot transmit data")
            return
        
        self.data_transmission_active = True
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + (duration_minutes * 60)
        
        transmission_count = 0
        op_id_counter = 6000
        
        # Create realistic sensor data patterns
        sensor_data_patterns = {
            "temperature": {"base": 22.5, "variation": 3.0, "trend": 0.01},
            "humidity": {"base": 45.0, "variation": 8.0, "trend": -0.02},
            "pressure": {"base": 1013.25, "variation": 2.0, "trend": 0.001},
            "battery": {"base": 3.6, "variation": 0.1, "trend": -0.0001}
        }
        
        print("🚀 Starting data transmission simulation...")
        
        try:
            while asyncio.get_event_loop().time() < end_time and self.data_transmission_active:
                # Select a random sensor
                sensor_eui = random.choice(list(self.registered_sensors.keys()))
                sensor_info = self.registered_sensors[sensor_eui]
                
                # Generate realistic sensor data
                current_time = time.time()
                time_factor = (current_time - start_time) / 3600  # Hours elapsed
                
                # Simulate different sensor types
                if "89" in sensor_eui:  # Temperature sensor
                    temp_data = sensor_data_patterns["temperature"]
                    value = temp_data["base"] + (temp_data["variation"] * random.uniform(-1, 1)) + (temp_data["trend"] * time_factor)
                    user_data = [
                        0x01,  # Temperature sensor type
                        int(value * 10) & 0xFF,  # Temperature * 10, low byte
                        (int(value * 10) >> 8) & 0xFF,  # Temperature * 10, high byte
                        sensor_info["packet_count"] & 0xFF,  # Packet counter
                        random.randint(80, 100),  # Battery percentage
                        random.randint(0, 255),  # Random data
                        random.randint(0, 255),  # Random data
                        random.randint(0, 255)   # Random data
                    ]
                
                elif "f8" in sensor_eui or "f9" in sensor_eui:  # Humidity sensor
                    hum_data = sensor_data_patterns["humidity"]
                    humidity = hum_data["base"] + (hum_data["variation"] * random.uniform(-1, 1)) + (hum_data["trend"] * time_factor)
                    user_data = [
                        0x02,  # Humidity sensor type
                        int(humidity) & 0xFF,  # Humidity percentage
                        random.randint(20, 30),  # Temperature
                        sensor_info["packet_count"] & 0xFF,  # Packet counter
                        random.randint(75, 95),  # Battery percentage
                        random.randint(0, 255),  # Random data
                        random.randint(0, 255),  # Random data
                        random.randint(0, 255)   # Random data
                    ]
                
                elif "130a" in sensor_eui or "118f" in sensor_eui:  # Pressure sensor
                    press_data = sensor_data_patterns["pressure"]
                    pressure = press_data["base"] + (press_data["variation"] * random.uniform(-1, 1)) + (press_data["trend"] * time_factor)
                    pressure_int = int(pressure * 100)  # Pressure in centipascals
                    user_data = [
                        0x03,  # Pressure sensor type
                        pressure_int & 0xFF,
                        (pressure_int >> 8) & 0xFF,
                        (pressure_int >> 16) & 0xFF,
                        sensor_info["packet_count"] & 0xFF,  # Packet counter
                        random.randint(85, 100),  # Battery percentage
                        random.randint(0, 255),  # Random data
                        random.randint(0, 255)   # Random data
                    ]
                
                else:  # Generic sensor
                    user_data = [
                        0xFF,  # Generic sensor type
                        random.randint(0, 255),
                        random.randint(0, 255),
                        sensor_info["packet_count"] & 0xFF,
                        random.randint(70, 100),  # Battery percentage
                        random.randint(0, 255),
                        random.randint(0, 255),
                        random.randint(0, 255)
                    ]
                
                # Create uplink data message
                uplink_msg = {
                    "command": "ulData",
                    "opId": op_id_counter,
                    "epEui": int(sensor_eui, 16),
                    "rxTime": int(current_time * 1_000_000_000),  # Nanoseconds
                    "snr": random.uniform(5.0, 25.0),  # Signal-to-noise ratio
                    "rssi": random.uniform(-120.0, -60.0),  # Received signal strength
                    "packetCnt": sensor_info["packet_count"],
                    "userData": user_data
                }
                
                # Send uplink data
                response = await self.send_message(uplink_msg, expect_response=True, timeout=5.0)
                
                if response and response.get("command") == "ulDataRsp":
                    transmission_count += 1
                    sensor_info["packet_count"] += 1
                    
                    # Print progress every 10 transmissions
                    if transmission_count % 10 == 0:
                        elapsed = asyncio.get_event_loop().time() - start_time
                        remaining = end_time - asyncio.get_event_loop().time()
                        print(f"📊 Progress: {transmission_count} transmissions | "
                              f"Elapsed: {elapsed/60:.1f}m | Remaining: {remaining/60:.1f}m")
                else:
                    print(f"❌ Transmission failed for sensor {sensor_eui}")
                
                op_id_counter += 1
                
                # Random delay between transmissions (simulate realistic timing)
                await asyncio.sleep(random.uniform(2.0, 8.0))
        
        except KeyboardInterrupt:
            print("\n⏹️  Data transmission stopped by user")
            self.data_transmission_active = False
        except Exception as e:
            print(f"❌ Error during data transmission: {e}")
            self.data_transmission_active = False
        
        final_elapsed = asyncio.get_event_loop().time() - start_time
        
        print(f"\n📊 TRANSMISSION SUMMARY:")
        print(f"   Total transmissions: {transmission_count}")
        print(f"   Duration: {final_elapsed/60:.1f} minutes")
        print(f"   Average rate: {transmission_count/(final_elapsed/60):.1f} msgs/min")
        print(f"   Sensors used: {len(self.registered_sensors)}")
        
        # Show per-sensor statistics
        print(f"\n📈 Per-sensor statistics:")
        for eui, info in self.registered_sensors.items():
            print(f"   {eui}: {info['packet_count']} packets transmitted")

    async def send_periodic_status_reports(self):
        """Send periodic base station status reports"""
        print(f"\n📊 BACKGROUND TASK: Periodic Status Reports")
        
        op_id_counter = 7000
        start_time = time.time()
        
        try:
            while self.data_transmission_active:
                await asyncio.sleep(30)  # Send status every 30 seconds
                
                if not self.connected:
                    break
                
                # Generate realistic status data
                uptime = int(time.time() - start_time)
                
                status_msg = {
                    "command": "statusRsp",
                    "opId": op_id_counter,
                    "code": 0,  # Status OK
                    "memLoad": random.uniform(0.15, 0.35),  # 15-35% memory usage
                    "cpuLoad": random.uniform(0.05, 0.25),  # 5-25% CPU usage
                    "dutyCycle": random.uniform(0.08, 0.15),  # 8-15% duty cycle
                    "time": int(time.time() * 1_000_000_000),  # Current time in nanoseconds
                    "uptime": uptime
                }
                
                response = await self.send_message(status_msg, expect_response=True, timeout=5.0)
                
                if response and response.get("command") == "statusCmp":
                    print(f"📊 Status report sent (uptime: {uptime//3600:02d}:{(uptime%3600)//60:02d}:{uptime%60:02d})")
                
                op_id_counter += 1
                
        except Exception as e:
            print(f"❌ Error in status reporting: {e}")

    async def run_full_simulation(self, data_duration_minutes=5):
        """Run complete base station simulation"""
        print("🏗️  FULL BASE STATION COMMUNICATION SIMULATION")
        print("=" * 80)
        print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 Simulating: Connection + Registration + {data_duration_minutes}min data transmission")
        
        try:
            # Phase 1: Connect to server
            await self.connect()
            
            # Phase 2: Perform connection handshake
            await self.perform_connection_handshake()
            
            # Phase 3: Handle sensor registration
            registration_success = await self.handle_sensor_registration()
            
            if not registration_success:
                print("❌ Sensor registration failed - cannot continue")
                return
            
            # Phase 4: Start background status reporting
            status_task = asyncio.create_task(self.send_periodic_status_reports())
            
            # Phase 5: Simulate live sensor data
            await self.simulate_sensor_data_transmission(data_duration_minutes)
            
            # Cancel background tasks
            status_task.cancel()
            try:
                await status_task
            except asyncio.CancelledError:
                pass
            
            print(f"\n🎉 SIMULATION COMPLETE!")
            print(f"✅ Successfully simulated full base station communication")
            print(f"📊 Check server logs and MQTT broker for published data")
            print(f"🌐 Monitor web UI at http://localhost:5000 for real-time updates")
            
        except Exception as e:
            print(f"❌ Simulation failed: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await self.disconnect()

async def main():
    """Main function to run the simulation"""
    print("🤖 Base Station Communication Simulator")
    print("This will simulate a complete mioty base station connecting to your BSSCI server")
    print()
    
    # Check if server is running
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("localhost", 16017), timeout=2.0
        )
        writer.close()
        await writer.wait_closed()
        print("✅ BSSCI server detected on localhost:16017")
    except:
        print("❌ BSSCI server not reachable on localhost:16017")
        print("💡 Make sure to start your BSSCI server first:")
        print("   python main.py")
        return
    
    # Get simulation duration
    try:
        duration = input("\n🕐 Enter data transmission duration in minutes [default: 5]: ").strip()
        duration = int(duration) if duration else 5
        if duration < 1:
            duration = 5
    except ValueError:
        duration = 5
    
    print(f"\n🚀 Starting simulation with {duration} minute(s) of data transmission...")
    
    # Create and run simulator
    simulator = FullBaseStationSimulator()
    await simulator.run_full_simulation(duration)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Simulation interrupted by user")
    except Exception as e:
        print(f"❌ Simulation error: {e}")
