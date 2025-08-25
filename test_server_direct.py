
#!/usr/bin/env python3
"""Simple test to check BSSCI server connectivity and basic protocol"""

import asyncio
import socket
import ssl
import msgpack
from protocol import encode_message

IDENTIFIER = bytes("MIOTYB01", 'utf-8')

async def test_server_direct():
    """Test basic server connectivity"""
    print("🔍 DIRECT SERVER CONNECTIVITY TEST")
    print("=" * 50)
    
    host = "localhost"
    port = 16017
    
    # Test 1: Basic TCP connectivity
    print(f"\n📡 Test 1: TCP Connection to {host}:{port}")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print("✅ TCP connection successful")
        else:
            print(f"❌ TCP connection failed with code: {result}")
            return
    except Exception as e:
        print(f"❌ TCP test failed: {e}")
        return
    
    # Test 2: Raw socket communication
    print(f"\n📡 Test 2: Raw Socket Communication")
    try:
        reader, writer = await asyncio.open_connection(host, port)
        print("✅ AsyncIO connection established")
        
        # Send a simple connection message
        test_msg = {
            "command": "con",
            "opId": 9999,
            "bsEui": 0x70B3D59CD0000022,
            "snBsUuid": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
        }
        
        msg_pack = encode_message(test_msg)
        full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder='little') + msg_pack
        
        print(f"📤 Sending test message:")
        print(f"   Message size: {len(full_message)} bytes")
        print(f"   Identifier: {IDENTIFIER.hex()}")
        print(f"   Length field: {len(msg_pack)}")
        print(f"   Full message (hex): {full_message.hex()}")
        
        writer.write(full_message)
        await writer.drain()
        
        # Try to read response
        print("📨 Waiting for response...")
        try:
            response_data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            print(f"✅ Response received: {len(response_data)} bytes")
            print(f"   Response (hex): {response_data.hex()}")
            
            if len(response_data) >= 8:
                if response_data[:8] == IDENTIFIER:
                    print("✅ Correct BSSCI identifier found")
                    if len(response_data) >= 12:
                        length = int.from_bytes(response_data[8:12], byteorder='little')
                        print(f"✅ Message length: {length}")
                        if len(response_data) >= 12 + length:
                            msg_data = response_data[12:12+length]
                            try:
                                response = msgpack.unpackb(msg_data, raw=False, strict_map_key=False)
                                print(f"✅ Parsed response: {response}")
                            except Exception as e:
                                print(f"❌ Failed to parse msgpack: {e}")
                                print(f"   Raw data: {msg_data.hex()}")
                        else:
                            print(f"❌ Incomplete message")
                    else:
                        print(f"❌ Response too short for length field")
                else:
                    print(f"❌ Wrong identifier: {response_data[:8].hex()}")
            else:
                print(f"❌ Response too short: {len(response_data)} bytes")
                
        except asyncio.TimeoutError:
            print("❌ Response timeout")
        
        writer.close()
        await writer.wait_closed()
        
    except Exception as e:
        print(f"❌ Socket communication test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_server_direct())
