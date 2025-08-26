
#!/usr/bin/env python3
"""
Test script for HTTP client functionality
"""

import asyncio
import logging
from http_client import ServiceCenterHTTPClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_http_client():
    """Test the HTTP client with sample data"""
    
    # Test data
    sensor_eui = "FCA84A030000127B"
    base_station_eui = "70b3d59cd00009f6"
    
    sample_uplink = {
        "bs_eui": base_station_eui,
        "rxTime": 1751819907443066821,
        "snr": 8.5,
        "rssi": -75.2,
        "cnt": 123,
        "data": [0x48, 0x65, 0x6c, 0x6c, 0x6f]  # "Hello" in bytes
    }
    
    sample_status = {
        "code": 0,
        "cpuLoad": 0.22,
        "memLoad": 0.39,
        "dutyCycle": 0.05,
        "time": 1751819907443066821,
        "uptime": 1699555
    }
    
    logger.info("🚀 Testing HTTP client...")
    
    async with ServiceCenterHTTPClient("https://mioty-cloud.replit.app") as client:
        
        # Test sensor uplink
        logger.info("📡 Testing sensor uplink...")
        uplink_result = await client.send_sensor_uplink(sensor_eui, sample_uplink)
        
        # Test base station status
        logger.info("📊 Testing base station status...")
        status_result = await client.send_base_station_status(base_station_eui, sample_status)
        
        # Test batch sending
        logger.info("📦 Testing batch sending...")
        batch_uplinks = [
            {"sensorEui": sensor_eui, "data": sample_uplink}
        ]
        batch_statuses = [
            {"baseStationEui": base_station_eui, "data": sample_status}
        ]
        
        batch_result = await client.send_batch(batch_uplinks, batch_statuses)
        
        logger.info("✅ HTTP client test completed")
        return uplink_result, status_result, batch_result

if __name__ == "__main__":
    asyncio.run(test_http_client())
