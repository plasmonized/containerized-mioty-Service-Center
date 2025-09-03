"""Message builders for mioty BSSCI protocol."""

from typing import Any, Dict, List, Optional


def build_attach_request(sensor: Dict[str, Any], op_id: int) -> Dict[str, Any]:
    """
    Build an attach request message for a sensor.

    Args:
        sensor: Sensor configuration dictionary
        op_id: Operation ID for the request

    Returns:
        BSSCI attach request message
    """
    return {
        "msgType": "attPrpReq",
        "opID": op_id,
        "eui": sensor["eui"],
        "nwKey": sensor["nwKey"],
        "shortAddr": sensor["shortAddr"],
        "bidi": sensor.get("bidi", False),
    }


def build_attach_response(op_id: int, status: str = "success") -> Dict[str, Any]:
    """
    Build an attach response message.

    Args:
        op_id: Operation ID from the original request
        status: Status of the attach operation

    Returns:
        BSSCI attach response message
    """
    return {"msgType": "attPrpRsp", "opID": op_id, "status": status}


def build_detach_request(eui: str, op_id: int) -> Dict[str, Any]:
    """
    Build a detach request message for a sensor.

    Args:
        eui: Sensor EUI to detach
        op_id: Operation ID for the request

    Returns:
        BSSCI detach request message
    """
    return {"msgType": "detachReq", "opID": op_id, "eui": eui}


def build_detach_response(op_id: int, status: str = "success") -> Dict[str, Any]:
    """
    Build a detach response message.

    Args:
        op_id: Operation ID from the original request
        status: Status of the detach operation

    Returns:
        BSSCI detach response message
    """
    return {"msgType": "detachRsp", "opID": op_id, "status": status}


def build_connection_message(bs_eui: str, op_id: int) -> Dict[str, Any]:
    """
    Build a connection establishment message.

    Args:
        bs_eui: Base station EUI
        op_id: Operation ID for the connection

    Returns:
        BSSCI connection message
    """
    return {
        "msgType": "con",
        "opID": op_id,
        "bsEui": bs_eui,
        "protocolVersion": "1.0.0.0",
    }


def build_connection_complete(op_id: int) -> Dict[str, Any]:
    """
    Build a connection complete response message.

    Args:
        op_id: Operation ID from the original connection request

    Returns:
        BSSCI connection complete message
    """
    return {"msgType": "conCmp", "opID": op_id, "status": "success"}


def build_status_request(op_id: int) -> Dict[str, Any]:
    """
    Build a status request message.

    Args:
        op_id: Operation ID for the request

    Returns:
        BSSCI status request message
    """
    return {"msgType": "statusReq", "opID": op_id}


def build_status_response(
    op_id: int, status_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build a status response message.

    Args:
        op_id: Operation ID from the original request
        status_data: Optional status data to include

    Returns:
        BSSCI status response message
    """
    message = {"msgType": "statusRsp", "opID": op_id}

    if status_data:
        message.update(status_data)

    return message


def build_ping(op_id: int) -> Dict[str, Any]:
    """
    Build a ping message.

    Args:
        op_id: Operation ID for the ping

    Returns:
        BSSCI ping message
    """
    return {"msgType": "ping", "opID": op_id}


def build_ping_complete(op_id: int) -> Dict[str, Any]:
    """
    Build a ping complete response message.

    Args:
        op_id: Operation ID from the original ping

    Returns:
        BSSCI ping complete message
    """
    return {"msgType": "pingCmp", "opID": op_id}


def build_uplink_data(
    eui: str,
    data: List[int],
    op_id: int,
    rx_time: Optional[int] = None,
    snr: Optional[float] = None,
    rssi: Optional[float] = None,
    cnt: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build an uplink data message.

    Args:
        eui: Sensor EUI
        data: Payload data as list of integers
        op_id: Operation ID
        rx_time: Reception timestamp
        snr: Signal-to-noise ratio
        rssi: Received signal strength indicator
        cnt: Frame counter

    Returns:
        BSSCI uplink data message
    """
    message = {"msgType": "ulData", "opID": op_id, "eui": eui, "data": data}

    if rx_time is not None:
        message["rxTime"] = rx_time
    if snr is not None:
        message["snr"] = snr
    if rssi is not None:
        message["rssi"] = rssi
    if cnt is not None:
        message["cnt"] = cnt

    return message


def build_uplink_complete(op_id: int) -> Dict[str, Any]:
    """
    Build an uplink data complete acknowledgment message.

    Args:
        op_id: Operation ID from the original uplink data

    Returns:
        BSSCI uplink complete message
    """
    return {"msgType": "ulDataCmp", "opID": op_id}


def build_downlink_data(
    eui: str, data: List[int], op_id: int, port: int = 1
) -> Dict[str, Any]:
    """
    Build a downlink data message.

    Args:
        eui: Target sensor EUI
        data: Payload data as list of integers
        op_id: Operation ID
        port: Application port number

    Returns:
        BSSCI downlink data message
    """
    return {"msgType": "dlData", "opID": op_id, "eui": eui, "data": data, "port": port}


def build_downlink_complete(op_id: int, status: str = "success") -> Dict[str, Any]:
    """
    Build a downlink data complete response message.

    Args:
        op_id: Operation ID from the original downlink data
        status: Status of the downlink operation

    Returns:
        BSSCI downlink complete message
    """
    return {"msgType": "dlDataCmp", "opID": op_id, "status": status}
