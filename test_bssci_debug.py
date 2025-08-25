
import asyncio
import ssl
import socket
import msgpack
from datetime import datetime

IDENTIFIER = bytes("MIOTYB01", 'utf-8')

class BSScIDebugClient:
    def __init__(self, host="localhost", port=16017, use_ssl=True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.reader = None
        self.writer = None
        self.connected = False

    async def test_connection_methods(self):
        """Test different connection methods to diagnose the issue"""
        print(f"🔍 BSSCI CONNECTION DIAGNOSTICS")
        print(f"=" * 60)
        print(f"Target: {self.host}:{self.port}")
        print(f"Expected SSL: {self.use_ssl}")
        
        # Test 1: Basic TCP connection
        print(f"\n📋 Test 1: Basic TCP Connection")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            if result == 0:
                print(f"✅ TCP connection successful")
            else:
                print(f"❌ TCP connection failed (error {result})")
                return False
        except Exception as e:
            print(f"❌ TCP connection error: {e}")
            return False

        # Test 2: Raw socket connection to check what server expects
        print(f"\n📋 Test 2: Raw Connection Test")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=5.0
            )
            
            # Try to send a simple byte to see if server responds or closes
            writer.write(b"TEST")
            await writer.drain()
            
            # Wait a bit to see what happens
            await asyncio.sleep(1)
            
            try:
                data = await asyncio.wait_for(reader.read(1024), timeout=2.0)
                if data:
                    print(f"✅ Server responded with {len(data)} bytes")
                    print(f"   Data: {data[:50]}...")
                else:
                    print(f"❌ Server closed connection immediately")
            except asyncio.TimeoutError:
                print(f"⏰ Server didn't respond (may be waiting for SSL handshake)")
                
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            print(f"❌ Raw connection error: {e}")

        # Test 3: SSL Connection
        if self.use_ssl:
            print(f"\n📋 Test 3: SSL Connection Test")
            try:
                # Create a lenient SSL context
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self.host, self.port, ssl=ssl_context
                    ), timeout=10.0
                )
                
                print(f"✅ SSL connection successful")
                ssl_obj = writer.get_extra_info('ssl_object')
                if ssl_obj:
                    print(f"   SSL version: {ssl_obj.version()}")
                    print(f"   Cipher: {ssl_obj.cipher()}")
                
                # Store for actual testing
                self.reader = reader
                self.writer = writer
                self.connected = True
                return True
                
            except Exception as e:
                print(f"❌ SSL connection error: {e}")
                print(f"   This suggests the server may not be configured for SSL")
                
        # Test 4: Non-SSL Connection
        print(f"\n📋 Test 4: Non-SSL Connection Test")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=5.0
            )
            
            print(f"✅ Non-SSL connection successful")
            
            # Store for actual testing
            self.reader = reader
            self.writer = writer
            self.connected = True
            return True
            
        except Exception as e:
            print(f"❌ Non-SSL connection error: {e}")
            
        return False

    async def send_bssci_message(self, message):
        """Send a BSSCI protocol message"""
        if not self.connected:
            print(f"❌ Not connected to server")
            return None
            
        try:
            print(f"📤 Sending BSSCI message: {message}")
            
            # Encode message
            msg_pack = msgpack.packb(message)
            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder="little") + msg_pack
            
            print(f"   Message size: {len(full_message)} bytes")
            print(f"   Identifier: {IDENTIFIER}")
            print(f"   Payload size: {len(msg_pack)} bytes")
            
            # Send message
            self.writer.write(full_message)
            await self.writer.drain()
            print(f"✅ Message sent successfully")
            
            # Try to read response
            print(f"⏳ Waiting for response...")
            try:
                data = await asyncio.wait_for(self.reader.read(4096), timeout=10.0)
                if not data:
                    print(f"❌ Server closed connection")
                    self.connected = False
                    return None
                    
                print(f"📨 Received {len(data)} bytes")
                
                # Parse response
                if len(data) >= 12:
                    recv_identifier = data[:8]
                    recv_length = int.from_bytes(data[8:12], byteorder="little")
                    
                    print(f"   Response identifier: {recv_identifier}")
                    print(f"   Response payload size: {recv_length}")
                    
                    if recv_identifier == IDENTIFIER:
                        if len(data) >= 12 + recv_length:
                            msg_data = data[12:12 + recv_length]
                            try:
                                response = msgpack.unpackb(msg_data, raw=False, strict_map_key=False)
                                print(f"✅ Parsed response: {response}")
                                return response
                            except Exception as e:
                                print(f"❌ Failed to parse response: {e}")
                                print(f"   Raw data: {msg_data}")
                        else:
                            print(f"❌ Incomplete response received")
                    else:
                        print(f"❌ Invalid response identifier")
                else:
                    print(f"❌ Response too short: {len(data)} bytes")
                    
            except asyncio.TimeoutError:
                print(f"⏰ No response received (timeout)")
                
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            self.connected = False
            
        return None

    async def run_bssci_protocol_test(self):
        """Run basic BSSCI protocol test"""
        print(f"\n🔗 BSSCI PROTOCOL TEST")
        print(f"=" * 60)
        
        if not self.connected:
            print(f"❌ Not connected - cannot run protocol test")
            return
            
        # Test 1: Connection Request
        connection_msg = {
            "command": "con",
            "opId": 9001,
            "bsEui": 0x70B3D59CD0000022,
            "snBsUuid": [0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80,
                        0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0, 0x11]
        }
        
        print(f"\n📋 Test: Connection Request (con)")
        response = await self.send_bssci_message(connection_msg)
        
        if response and response.get("command") == "conRsp":
            print(f"✅ Connection response received")
            
            # Test 2: Connection Complete
            print(f"\n📋 Test: Connection Complete (conCmp)")
            complete_msg = {
                "command": "conCmp",
                "opId": 9001
            }
            await self.send_bssci_message(complete_msg)
            
            # Give server time to process and start attachment
            await asyncio.sleep(5)
            
        else:
            print(f"❌ Connection handshake failed")

    async def disconnect(self):
        """Clean disconnect"""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except:
                pass
        self.connected = False
        print(f"🔌 Disconnected")

async def main():
    print(f"🧪 BSSCI SERVER DIAGNOSTICS")
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test with SSL first (default server config)
    client = BSScIDebugClient(host="localhost", port=16017, use_ssl=True)
    
    try:
        success = await client.test_connection_methods()
        
        if success:
            await client.run_bssci_protocol_test()
        else:
            print(f"\n❌ Could not establish any connection to the server")
            print(f"💡 Suggestions:")
            print(f"   1. Check if the server is running")
            print(f"   2. Verify the port (16017)")
            print(f"   3. Check SSL configuration")
            print(f"   4. Look at server logs for connection attempts")
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
