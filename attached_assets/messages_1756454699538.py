from typing import Any


def build_connection_response(opID: int, snscuuid_arr: list[int]) -> dict[str, object]:
    return {
        "command": "conRsp",
        "scEui": 8391082416558637055,
        "opId": opID,
        "snResume": False,
        "snScUuid": snscuuid_arr,
    }


def build_attach_request(sensor: dict[str, Any], opID: int) -> dict[str, object]:
    return {
        "command": "attPrp",
        "opId": opID,
        "epEui": int.from_bytes(bytes.fromhex(sensor["eui"]), "big"),
        "bidi": sensor["bidi"],
        "nwkSnKey": list(bytes.fromhex(sensor["nwKey"])),
        "shAddr": int.from_bytes(bytes.fromhex(sensor["shortAddr"]), "big"),
        "lastPacketCnt": 0,
        "dualChan": True,
        "repetition": False,
        "wideCarrOff": False,
        "longBlkDist": False,
    }


def build_attach_complete(opID: int) -> dict[str, object]:
    return {"command": "attPrpCmp", "opId": opID}


def build_detach_request(eui: str, opID: int) -> dict[str, object]:
    return {"command": "detachReq", "eui": eui, "opId": opID}


def build_ping_response(opID: int) -> dict[str, object]:
    return {"command": "pingRsp", "opId": opID}


def build_status_request(opID: int) -> dict[str, object]:
    return {"command": "status", "opId": opID}


def build_status_complete(opID: int) -> dict[str, object]:
    return {"command": "statusCmp", "opId": opID}


def build_ul_response(opID: int) -> dict[str, object]:
    return {"command": "ulDataRsp", "opId": opID}
