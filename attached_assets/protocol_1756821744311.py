"""Protocol utilities for mioty BSSCI message encoding and decoding."""

import logging
from typing import Any, Dict, List

import msgpack

logger = logging.getLogger(__name__)

IDENTIFIER = bytes("MIOTYB01", "utf-8")


def decode_messages(data: bytes) -> List[Dict[str, Any]]:
    """
    Decode multiple BSSCI messages from byte data.

    Args:
        data: Raw byte data containing one or more BSSCI messages

    Returns:
        List of decoded message dictionaries
    """
    messages = []
    while len(data) > 12:
        try:
            unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
            length = int.from_bytes(data[8:12], byteorder="little")

            if length + 12 > len(data):
                logger.warning(
                    f"Incomplete message: expected {length + 12} bytes, "
                    f"got {len(data)}"
                )
                break

            unpacker.feed(data[12 : 12 + length])
            data = data[12 + length :]

            for msg in unpacker:
                messages.append(msg)

        except (
            msgpack.exceptions.ExtraData,
            msgpack.exceptions.FormatError,
            ValueError,
        ) as e:
            logger.error(f"Error decoding message: {e}")
            break
        except Exception as e:
            logger.error(f"Unexpected error decoding message: {e}")
            break

    return messages


def decode_message(data: bytes) -> Dict[str, Any]:
    """
    Decode a single message from bytes.

    Args:
        data: Raw byte data containing a single message

    Returns:
        Decoded message dictionary, empty dict if decoding fails
    """
    try:
        unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
        unpacker.feed(data)

        for msg in unpacker:
            return msg

        logger.warning("No message found in provided data")
        return {}

    except (
        msgpack.exceptions.ExtraData,
        msgpack.exceptions.FormatError,
        ValueError,
    ) as e:
        logger.error(f"Error decoding single message: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error decoding single message: {e}")
        return {}


def encode_message(data: Dict[str, Any]) -> bytes:
    """
    Encode a message dictionary to MessagePack bytes.

    Args:
        data: Message dictionary to encode

    Returns:
        Encoded message as bytes

    Raises:
        ValueError: If encoding fails
    """
    try:
        encoded_message = msgpack.packb(data)
        if encoded_message is None:
            raise ValueError("msgpack.packb returned None")
        return encoded_message
    except (
        msgpack.exceptions.ExtraData,
        msgpack.exceptions.FormatError,
        ValueError,
    ) as e:
        logger.error(f"Error encoding message: {e}")
        raise ValueError(f"Failed to encode message: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error encoding message: {e}")
        raise ValueError(f"Unexpected encoding error: {e}") from e


def validate_message_format(data: bytes) -> bool:
    """
    Validate that data starts with proper BSSCI identifier.

    Args:
        data: Raw byte data to validate

    Returns:
        True if data has valid BSSCI header, False otherwise
    """
    if len(data) < 12:
        return False

    return data[:8] == IDENTIFIER


def extract_message_length(data: bytes) -> int:
    """
    Extract message length from BSSCI header.

    Args:
        data: Raw byte data with BSSCI header

    Returns:
        Message length in bytes

    Raises:
        ValueError: If data is too short or invalid
    """
    if len(data) < 12:
        raise ValueError("Data too short to contain BSSCI header")

    if data[:8] != IDENTIFIER:
        raise ValueError("Invalid BSSCI identifier")

    return int.from_bytes(data[8:12], byteorder="little")
