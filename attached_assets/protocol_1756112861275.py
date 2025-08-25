import msgpack

def decode_messages(data):
    messages = []
    while (len(data)>12):
        try:
            unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
            identifier = data[:8]
            length = int.from_bytes(data[8:8+4],byteorder='little')
            if length+8>len(data):
                break
            unpacker.feed(data[12:12+length])
            data = data[12+length:]
            for msg in unpacker:
                messages.append(msg)
        except Exception as e:
            print(f"[ERROR] Fehler beim Dekodieren der Nachricht: {e}")
    return messages


def encode_message(data):
    return msgpack.packb(data)
