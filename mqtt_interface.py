import asyncio
import json

from aiomqtt import Client

from bssci_config import BASE_TOPIC, MQTT_BROKER


class MQTTClient:
    def __init__(
        self,
        mqtt_out_queue: asyncio.Queue[dict[str, str]],
        mqtt_in_queue: asyncio.Queue[dict[str, str]],
    ):
        self.broker_host = MQTT_BROKER
        if BASE_TOPIC[-1] == "/":
            self.base_topic = BASE_TOPIC[:-1]
        else:
            self.base_topic = BASE_TOPIC
        self.config_topic = self.base_topic + "/ep/+/config"
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue

    async def start(self) -> None:
        async with Client(self.broker_host) as client:
            await asyncio.gather(
                self._handle_incoming(client), self._handle_outgoing(client)
            )

    async def _handle_incoming(self, client: Client) -> None:
        await client.subscribe(self.config_topic)
        async for message in client.messages:
            eui = str(message.topic).split("/")[len(self.base_topic.split("/")) + 1]
            payload = message.payload
            if isinstance(payload, (bytes, bytearray)):
                config = json.loads(payload.decode())
            elif isinstance(payload, str):
                config = json.loads(payload)
            else:
                raise TypeError(f"Unsupported payload type: {type(payload)}")
            config["eui"] = eui
            # print("Konfig erhalten:", config)
            await self.mqtt_in_queue.put(config)

    async def _handle_outgoing(self, client: Client) -> None:
        print(type(client))
        while True:
            msg = await self.mqtt_out_queue.get()
            # print(f"{self.base_topic}/{msg['topic']}:\n\t{msg['payload']}")
            await client.publish(f"{self.base_topic}/{msg['topic']}", msg["payload"])


if __name__ == "__main__":
    import sys

    async def send_mqtt(mqtt_out_queue: asyncio.Queue[dict[str, str]]) -> None:
        eui = "0123456789abcdef"
        data_dict = {
            "rxTime": 1751819907443066821,
            "snr": 23.673797607421875,
            "rssi": -72.2540283203125,
            "cnt": 3749,
            "data": [
                2,
                193,
                1,
                125,
                1,
                225,
                2,
                236,
                1,
                48,
                3,
                121,
                3,
                65,
                7,
                218,
                2,
                120,
                5,
                93,
                5,
            ],
        }
        while True:
            await mqtt_out_queue.put(
                {"topic": f"ep/{eui}/ul", "payload": json.dumps(data_dict)}
            )
            await asyncio.sleep(5)

    async def main() -> None:
        mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        mqtt_server = MQTTClient(mqtt_out_queue, mqtt_in_queue)
        await asyncio.gather(mqtt_server.start(), send_mqtt(mqtt_out_queue))

    if sys.platform.startswith("win"):
        policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if policy_cls is not None:
            asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())
    while 1:
        pass
