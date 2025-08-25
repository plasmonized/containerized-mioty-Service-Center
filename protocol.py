from typing import Any

import msgpack


def decode_messages(data: bytes) -> list[dict[str, Any]]:
    messages = []

    # Check if data is too short for a valid message
    if len(data) < 12:
        return messages

    while len(data) > 12:
        identifier = data[:8]
        if identifier != IDENTIFIER:
            print(f"Invalid identifier: {identifier}")
            # Try to find next valid identifier
            next_pos = data.find(IDENTIFIER, 1)
            if next_pos > 0:
                data = data[next_pos:]
                continue
            else:
                break

        try:
            unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
            length = int.from_bytes(data[8 : 8 + 4], byteorder="little")

            # Validate length is reasonable
            if length > 1024 * 1024:  # 1MB max message size
                print(f"[ERROR] Message length {length} too large, skipping")
                break

            if length + 12 > len(data):
                break

            payload = data[12 : 12 + length]
            unpacker.feed(payload)
            data = data[12 + length :]

            for msg in unpacker:
                # Ensure we only append dictionaries
                if isinstance(msg, dict):
                    messages.append(msg)
                else:
                    print(f"[WARN] Skipping non-dict message: {type(msg)}")

        except msgpack.exceptions.ExtraData:
            print(f"[WARN] Extra data in msgpack payload, continuing")
            continue
        except Exception as e:
            print(f"[ERROR] Error decoding message: {e}")
            # Skip this message and try to continue with remaining data
            break

    return messages


def encode_message(data: dict[str, Any]) -> bytes:
    encoded_message = bytes(msgpack.packb(data))
    return encoded_message