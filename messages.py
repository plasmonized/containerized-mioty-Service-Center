def build_connection_response(opID,snscuuid_arr):
    return {
        "command": "conRsp",
        "scEui": 8391082416558637055,
        "opId": opID,
        "snResume": False,
        "snScUuid":snscuuid_arr
    }

def build_attach_request(sensor,opID):
    return {
        "command": "attPrp",
        "opId":opID,
        "epEui": int.from_bytes(bytes.fromhex(sensor["eui"]), "big"),
        "bidi": sensor["bidi"],
        "nwkSnKey": list(bytes.fromhex(sensor["nwKey"])),
        "shAddr": int.from_bytes(bytes.fromhex(sensor["shortAddr"]), "big"),
        "lastPacketCnt":0,
        "dualChan": True,
        "repetition": False,
        "wideCarrOff": False,
        "longBlkDist": False
    }

def build_attach_complete(opID):
    return {
        "command": "attPrpCmp",
        "opId": opID
    }

def build_detach_request(eui,opID):
    return {
        "command": "detachReq",
        "eui": eui
    }

def build_ping_response(opID):
    return {
        "command": "pingRsp",
        "opId": opID
    }

def build_status_request(opID):
    return {
        "command": "status",
        "opId": opID
    }

def build_status_complete(opID):
    return {
        "command": "statusCmp",
        "opId": opID
    }

def build_ul_response(opID):
    return {
        "command": "ulDataRsp",
        "opId": opID
    }

