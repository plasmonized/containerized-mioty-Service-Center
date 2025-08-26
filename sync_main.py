import queue
import threading
import time

# Assume sync_mqtt_interface.py contains the SyncMQTTClient class
# from sync_mqtt_interface import SyncMQTTClient

# Placeholder for SyncMQTTClient if the actual file is not provided
class SyncMQTTClient:
    def __init__(self, out_queue, in_queue):
        self.out_queue = out_queue
        self.in_queue = in_queue
        print("SyncMQTTClient initialized.")

    def start(self):
        print("SyncMQTTClient starting...")
        # Simulate MQTT client running and processing messages
        while True:
            try:
                # Process messages from the output queue (to be sent via MQTT)
                message = self.out_queue.get_nowait()
                print(f"SyncMQTTClient: Sending message - {message}")
                # Simulate sending message
                time.sleep(0.1)
            except queue.Empty:
                pass # No messages to send

            try:
                # Simulate receiving messages from MQTT and putting them in the in_queue
                # In a real scenario, this would be from the MQTT broker
                if not self.in_queue.full():
                    self.in_queue.put({"topic": "test/topic", "payload": f"simulated_data_{time.time()}"})
            except queue.Full:
                pass # In-queue is full

            time.sleep(1) # Simulate loop delay

    def stop(self):
        print("SyncMQTTClient stopping...")


def main():
    mqtt_out_queue = queue.Queue(maxsize=10)
    mqtt_in_queue = queue.Queue(maxsize=10)

    # Start MQTT client
    mqtt_client = SyncMQTTClient(mqtt_out_queue, mqtt_in_queue)
    mqtt_client.start()

    # Example of sending data to MQTT
    try:
        mqtt_out_queue.put({"topic": "test/topic", "payload": "Hello MQTT!"})
        print("Sent initial message to MQTT queue.")
    except queue.Full:
        print("MQTT out queue is full, cannot send initial message.")

    # Main loop to process incoming MQTT messages
    while True:
        try:
            message = mqtt_in_queue.get(timeout=1) # Wait for incoming messages
            print(f"Received message from MQTT: {message}")
            # Process the received message here
            # For example:
            # if message["topic"] == "sensor/data":
            #     process_sensor_data(message["payload"])
        except queue.Empty:
            # No messages received, continue looping
            pass
        except KeyboardInterrupt:
            print("Shutting down...")
            # In a real application, you would call mqtt_client.stop() here
            # For this simulation, we just break the loop
            break
        time.sleep(0.5) # Small delay to prevent busy-waiting

if __name__ == "__main__":
    main()