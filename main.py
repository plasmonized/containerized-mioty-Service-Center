import asyncio
import logging
import os
from aiohttp import web

from bssci_config import SENSOR_CONFIG_FILE, LISTEN_HOST, LISTEN_PORT, MQTT_BROKER, MQTT_PORT
from mqtt_interface import MQTTClient
from TLSServer import TLSServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def health_check(request):
    """Health check endpoint for Replit Deployments"""
    return web.json_response({
        "status": "healthy",
        "service": "BSSCI Service Center",
        "tls_port": LISTEN_PORT
    })

async def start_health_server():
    """Start HTTP server for health checks on port 80 in deployments"""
    if os.getenv("REPL_DEPLOYMENT"):
        app = web.Application()
        app.router.add_get('/health', health_check)
        app.router.add_get('/', health_check)  # Root path for deployment health check
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 80)
        await site.start()
        logger.info("Health check server started on port 80")

async def main() -> None:
    logger.info("Starting BSSCI Service Center...")
    logger.info(f"TLS Server will listen on {LISTEN_HOST}:{LISTEN_PORT}")
    logger.info(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    logger.info(f"Sensor config file: {SENSOR_CONFIG_FILE}")
    
    mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    
    logger.info("Initializing TLS Server...")
    server = TLSServer(SENSOR_CONFIG_FILE, mqtt_out_queue, mqtt_in_queue)
    
    logger.info("Initializing MQTT Client...")
    mqtt_server = MQTTClient(mqtt_out_queue, mqtt_in_queue)
    
    logger.info("Starting services...")
    
    # Start health check server for deployments
    await start_health_server()
    
    await asyncio.gather(mqtt_server.start(), server.start_server())


if __name__ == "__main__":
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())
