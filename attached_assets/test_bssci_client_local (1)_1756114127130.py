import asyncio
import ssl
import msgpack
from protocol import encode_message

IDENTIFIER = bytes("MIOTYB01", 'utf-8')

class BSScITestClient:
    def __init__(self, host="0.0.0.0", port=16017, use_ssl=True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.reader = None
        self.writer = None

    async def connect(self):
        """Establish a persistent connection"""
        try:
            if self.use_ssl:
                # Create SSL context for client
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE  # Skip server verification for testing
                
                # Load client certificate for mutual authentication
                try:
                    ssl_context.load_cert_chain('certs/client_cert.pem', 'certs/client_key.pem')
                    print("[SSL] Client certificate loaded")
                except Exception as cert_error:
                    print(f"[SSL] Warning: Could not load client certificate: {cert_error}")
                
                # Connect with SSL
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port, ssl=ssl_context
                )
                print("Connected to BSSCI server (SSL/TLS secured)")
            else:
                # Connect without SSL for insecure mode
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port
                )
                print("Connected to BSSCI server (insecurely)")

        except Exception as e:
            print(f"Connection error: {e}")
            raise

    async def disconnect(self):
        """Close the connection"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            print("Disconnected from BSSCI server")

    async def send_message(self, message_dict):
        """Send a message using the existing connection"""
        try:
            if not self.writer or self.writer.is_closing():
                raise Exception("Connection lost")

            # Encode the message
            msg_pack = encode_message(message_dict)

            # Send with BSSCI protocol format
            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder='little') + msg_pack
            self.writer.write(full_message)
            await self.writer.drain()

            print(f"Sent: {message_dict}")

            # Read response with timeout
            try:
                response_data = await asyncio.wait_for(self.reader.read(4096), timeout=5.0)
                if response_data:
                    # Parse response
                    if len(response_data) > 12:
                        identifier = response_data[:8]
                        length = int.from_bytes(response_data[8:12], byteorder='little')
                        msg_data = response_data[12:12+length]
                        response = msgpack.unpackb(msg_data, raw=False, strict_map_key=False)
                        print(f"Received: {response}")
                else:
                    print("Connection closed by server")
                    self.writer = None
                    self.reader = None
            except asyncio.TimeoutError:
                print("Response timeout")

        except Exception as e:
            print(f"Error sending message: {e}")
            # Mark connection as lost
            self.writer = None
            self.reader = None

async def test_bssci_communication():
    # Use SSL by default, connecting to port 3001 (external access)
    client = BSScITestClient(host="0.0.0.0", port=3001, use_ssl=True)

    print("Testing BSSCI Base Station Communication")
    print("=" * 50)

    try:
        # Connect once at the beginning
        await client.connect()

        # Test 1: Connection message
        print("\n1. Sending connection message...")
        connection_msg = {
            "command": "con",
            "opId": 1001,
            "bsEui": 0x1234567890ABCDEF,
            "snBsUuid": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
        }
        await client.send_message(connection_msg)

        await asyncio.sleep(1)

        # Test 2: Ping message
        print("\n2. Sending ping message...")
        ping_msg = {
            "command": "ping",
            "opId": 1002
        }
        await client.send_message(ping_msg)

        await asyncio.sleep(1)

        # Test 3: Status response
        print("\n3. Sending status response...")
        status_msg = {
            "command": "statusRsp",
            "opId": 1003,
            "dutyCycle": 0.15,
            "time": 1704067200,  # Unix timestamp
            "uptime": 86400      # 24 hours in seconds
        }
        await client.send_message(status_msg)

        await asyncio.sleep(1)

        # Test 4: Uplink data message
        print("\n4. Sending uplink data message...")
        ul_data_msg = {
            "command": "ulData",
            "opId": 1004,
            "epEui": 0x74731D0000000001,
            "rxTime": 1704067200000000,
            "snr": 12.5,
            "rssi": -85.2,
            "packetCnt": 42,
            "payload": [0x01, 0x02, 0x03, 0x04, 0x05]
        }
        await client.send_message(ul_data_msg)

        print("\nTest completed successfully!")

    except Exception as e:
        print(f"Test failed: {e}")
    finally:
        # Always disconnect at the end
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_bssci_communication())