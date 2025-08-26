
import aiohttp
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ServiceCenterHTTPClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"Content-Type": "application/json"}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def send_sensor_uplink(self, sensor_eui: str, bssci_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send sensor uplink data to service center"""
        try:
            url = f"{self.base_url}/api/bssci/uplink/{sensor_eui}"
            
            logger.info(f"📤 HTTP UPLINK TRANSMISSION")
            logger.info(f"   Target URL: {url}")
            logger.info(f"   Sensor EUI: {sensor_eui}")
            logger.info(f"   Data: SNR={bssci_data.get('snr', 'N/A'):.1f}dB, RSSI={bssci_data.get('rssi', 'N/A'):.1f}dBm")
            
            if not self.session:
                raise RuntimeError("HTTP session not initialized")
            
            async with self.session.post(url, json=bssci_data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ Uplink sent successfully for {sensor_eui}: {result.get('message', 'OK')}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"❌ HTTP {response.status}: {error_text}")
                    return None
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ HTTP client error sending uplink for {sensor_eui}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error sending uplink for {sensor_eui}: {e}")
            return None
    
    async def send_base_station_status(self, base_station_eui: str, status_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send base station status to service center"""
        try:
            url = f"{self.base_url}/api/bssci/base-station-status/{base_station_eui}"
            
            logger.info(f"📤 HTTP BASE STATION STATUS TRANSMISSION")
            logger.info(f"   Target URL: {url}")
            logger.info(f"   Base Station EUI: {base_station_eui}")
            logger.info(f"   Status: CPU={status_data.get('cpuLoad', 'N/A'):.1%}, Memory={status_data.get('memLoad', 'N/A'):.1%}")
            
            if not self.session:
                raise RuntimeError("HTTP session not initialized")
            
            async with self.session.post(url, json=status_data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ Base station status sent successfully for {base_station_eui}: {result.get('message', 'OK')}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"❌ HTTP {response.status}: {error_text}")
                    return None
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ HTTP client error sending base station status for {base_station_eui}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error sending base station status for {base_station_eui}: {e}")
            return None
    
    async def send_batch(self, uplinks: List[Dict[str, Any]] = None, base_station_statuses: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Send batch data to service center for efficiency"""
        try:
            url = f"{self.base_url}/api/bssci/batch"
            
            batch_data = {
                "uplinks": uplinks or [],
                "baseStationStatuses": base_station_statuses or []
            }
            
            logger.info(f"📤 HTTP BATCH TRANSMISSION")
            logger.info(f"   Target URL: {url}")
            logger.info(f"   Uplinks: {len(batch_data['uplinks'])}")
            logger.info(f"   Base Station Statuses: {len(batch_data['baseStationStatuses'])}")
            
            if not self.session:
                raise RuntimeError("HTTP session not initialized")
            
            async with self.session.post(url, json=batch_data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ Batch data sent successfully: {result.get('message', 'OK')}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"❌ HTTP {response.status}: {error_text}")
                    return None
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ HTTP client error sending batch data: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error sending batch data: {e}")
            return None
