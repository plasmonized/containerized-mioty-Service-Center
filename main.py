import asyncio
import json
from bssci_config import SENSOR_CONFIG_FILE
from mqtt_interface import MQTTClient
from TLSServer import TLSServer

async def main():
    mqtt_in_queue = asyncio.Queue()
    mqtt_out_queue = asyncio.Queue()
    server = TLSServer(SENSOR_CONFIG_FILE,mqtt_in_queue,mqtt_out_queue)
    mqtt_server = MQTTClient(mqtt_in_queue,mqtt_out_queue)
    await asyncio.gather(
                mqtt_server.start(),
                server.start_server()
            )

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
