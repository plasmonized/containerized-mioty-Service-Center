
#!/usr/bin/env python3

import os
import json
import ssl
import asyncio
from datetime import datetime

def check_certificates():
    """Check SSL certificate configuration"""
    print("🔐 CHECKING SSL CERTIFICATES")
    print("-" * 50)
    
    cert_files = {
        'Service Center Certificate': 'certs/service_center_cert.pem',
        'Service Center Key': 'certs/service_center_key.pem', 
        'CA Certificate': 'certs/ca_cert.pem',
        'Client Certificate': 'certs/client_cert.pem',
        'Client Key': 'certs/client_key.pem'
    }
    
    all_good = True
    for name, path in cert_files.items():
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    content = f.read()
                    if 'BEGIN CERTIFICATE' in content or 'BEGIN PRIVATE KEY' in content:
                        print(f"✅ {name}: Found at {path}")
                    else:
                        print(f"❌ {name}: File exists but doesn't look like a certificate/key")
                        all_good = False
            except Exception as e:
                print(f"❌ {name}: Error reading {path} - {e}")
                all_good = False
        else:
            print(f"⚠️  {name}: Not found at {path}")
            if 'client' not in name.lower():  # Client certs are optional
                all_good = False
    
    return all_good

def check_configuration():
    """Check BSSCI configuration"""
    print("\n🔧 CHECKING BSSCI CONFIGURATION")
    print("-" * 50)
    
    try:
        import bssci_config
        print(f"✅ Configuration file loaded")
        print(f"   Listen Host: {bssci_config.LISTEN_HOST}")
        print(f"   Listen Port: {bssci_config.LISTEN_PORT}")
        print(f"   MQTT Broker: {bssci_config.MQTT_BROKER}:{bssci_config.MQTT_PORT}")
        
        # Check if we can bind to the port
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((bssci_config.LISTEN_HOST, bssci_config.LISTEN_PORT))
            s.close()
            print(f"✅ Port {bssci_config.LISTEN_PORT} is available")
        except OSError as e:
            if "already in use" in str(e).lower():
                print(f"⚠️  Port {bssci_config.LISTEN_PORT} is already in use (server might be running)")
            else:
                print(f"❌ Cannot bind to port {bssci_config.LISTEN_PORT}: {e}")
        
        return True
    except ImportError as e:
        print(f"❌ Cannot import bssci_config: {e}")
        return False
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

def check_endpoints():
    """Check endpoints configuration"""
    print("\n📡 CHECKING ENDPOINTS CONFIGURATION")
    print("-" * 50)
    
    try:
        with open('endpoints.json', 'r') as f:
            endpoints = json.load(f)
        
        if not endpoints:
            print("⚠️  No endpoints configured")
            return False
        
        print(f"✅ Found {len(endpoints)} configured endpoints:")
        for i, endpoint in enumerate(endpoints, 1):
            eui = endpoint.get('eui', 'unknown')
            short_addr = endpoint.get('shortAddr', 'unknown')
            print(f"   {i:2d}. EUI: {eui}, Short Addr: {short_addr}")
            
            # Basic validation
            if len(eui) != 16:
                print(f"      ⚠️  EUI length should be 16 characters, got {len(eui)}")
            if len(short_addr) != 4:
                print(f"      ⚠️  Short address length should be 4 characters, got {len(short_addr)}")
        
        return True
    except FileNotFoundError:
        print("❌ endpoints.json not found")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ endpoints.json is not valid JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading endpoints: {e}")
        return False

async def check_server_connectivity():
    """Check if server can be reached"""
    print("\n🌐 CHECKING SERVER CONNECTIVITY")
    print("-" * 50)
    
    try:
        import bssci_config
        host = bssci_config.LISTEN_HOST
        port = bssci_config.LISTEN_PORT
    except:
        host, port = "localhost", 16017
    
    # Test TCP connection
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=3.0
        )
        writer.close()
        await writer.wait_closed()
        print(f"✅ TCP connection to {host}:{port} successful")
        return True
    except asyncio.TimeoutError:
        print(f"❌ Connection to {host}:{port} timed out")
        return False
    except ConnectionRefusedError:
        print(f"❌ Connection to {host}:{port} refused (server not running?)")
        return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def check_mqtt_config():
    """Check MQTT configuration"""
    print("\n📨 CHECKING MQTT CONFIGURATION") 
    print("-" * 50)
    
    try:
        import bssci_config
        print(f"✅ MQTT Configuration:")
        print(f"   Broker: {bssci_config.MQTT_BROKER}:{bssci_config.MQTT_PORT}")
        print(f"   Topic Prefix: {getattr(bssci_config, 'MQTT_TOPIC_PREFIX', 'bssci/')}")
        
        if hasattr(bssci_config, 'MQTT_USERNAME'):
            print(f"   Username: {bssci_config.MQTT_USERNAME}")
        else:
            print(f"   Authentication: None")
        
        return True
    except Exception as e:
        print(f"❌ MQTT configuration error: {e}")
        return False

async def main():
    """Run all configuration checks"""
    print("🔍 BSSCI CONFIGURATION CHECKER")
    print("=" * 80)
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    checks = [
        ("SSL Certificates", check_certificates()),
        ("BSSCI Configuration", check_configuration()),
        ("Endpoints Configuration", check_endpoints()),
        ("MQTT Configuration", check_mqtt_config()),
        ("Server Connectivity", await check_server_connectivity())
    ]
    
    print(f"\n📊 CONFIGURATION CHECK RESULTS")
    print("=" * 80)
    
    passed = 0
    total = len(checks)
    
    for check_name, result in checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {check_name}")
        if result:
            passed += 1
    
    success_rate = (passed / total * 100) if total > 0 else 0
    print(f"\n📈 SUMMARY:")
    print(f"   Checks Passed: {passed}/{total}")
    print(f"   Success Rate: {success_rate:.1f}%")
    
    if success_rate == 100:
        print("\n🎉 All checks passed! System should be ready for testing.")
        print("💡 Run: python test_bssci_local_complete.py")
    elif success_rate >= 75:
        print("\n⚠️  Most checks passed. Minor issues may affect functionality.")
    else:
        print("\n❌ Several issues detected. Please fix configuration before testing.")
    
    print(f"\n🚀 TO START THE SERVER:")
    print(f"   python main.py")
    print(f"\n🧪 TO RUN TESTS:")
    print(f"   python test_bssci_local_complete.py")

if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
    
    asyncio.run(main())
