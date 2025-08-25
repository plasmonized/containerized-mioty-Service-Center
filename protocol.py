from typing import Any

import msgpack


def decode_messages(data: bytes) -> list[dict[str, Any]]:
    messages = []
    while len(data) > 12:
        try:
            unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
            length = int.from_bytes(data[8 : 8 + 4], byteorder="little")
            if length + 12 > len(data):
                break
            unpacker.feed(data[12 : 12 + length])
            data = data[12 + length :]
            for msg in unpacker:
                # Ensure we only append dictionaries
                if isinstance(msg, dict):
                    messages.append(msg)
                else:
                    print(f"[WARN] Skipping non-dict message: {type(msg)}")
        except Exception as e:
            print(f"[ERROR] Error decoding message: {e}")
            # Skip this message and try to continue with remaining data
            break
    return messages


def encode_message(data: dict[str, Any]) -> bytes:
    encoded_message = bytes(msgpack.packb(data))
    return encoded_message
