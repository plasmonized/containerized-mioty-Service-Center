import asyncio

from bssci_config import SENSOR_CONFIG_FILE
from mqtt_interface import MQTTClient
from TLSServer import TLSServer


async def main() -> None:
    mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    server = TLSServer(SENSOR_CONFIG_FILE, mqtt_in_queue, mqtt_out_queue)
    mqtt_server = MQTTClient(mqtt_in_queue, mqtt_out_queue)
    await asyncio.gather(mqtt_server.start(), server.start_server())


if __name__ == "__main__":
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())
