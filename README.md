# mioty BSSCI Service Center

A comprehensive implementation of the mioty Base Station Service Center Interface (BSSCI) protocol v1.0.0.0 with web-based management interface and MQTT integration.

## Table of Contents

- [Overview](#overview)
- [BSSCI Protocol Understanding](#bssci-protocol-understanding)
- [Architecture & Data Flow](#architecture--data-flow)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Web Interface](#web-interface)
- [MQTT Integration](#mqtt-integration)
- [Programming Guide](#programming-guide)
- [API Documentation](#api-documentation)
- [Troubleshooting](#troubleshooting)
- [Advanced Features](#advanced-features)
- [License](#license)
- [Contributing](#contributing)
- [Support the Project](#support-the-project)

## Overview

This service center acts as a bridge between mioty base stations and MQTT brokers, providing:

- **TLS-secured communication** with base stations following BSSCI v1.0.0.0
- **Real-time sensor data processing** with deduplication
- **MQTT publishing** of sensor data and base station status  
- **Web-based management interface** for monitoring and configuration
- **Dynamic sensor registration** via MQTT
- **Multi-base station support** with intelligent routing

## BSSCI Protocol Understanding

### What is BSSCI?

The Base Station Service Center Interface (BSSCI) is a standardized protocol for communication between mioty base stations and service centers. It defines:

1. **Connection Management**: Secure TLS handshake and authentication
2. **Sensor Registration**: Dynamic attachment/detachment of sensors
3. **Data Exchange**: Uplink data forwarding and downlink message routing
4. **Status Monitoring**: Base station health and performance metrics
5. **Message Acknowledgment**: Reliable delivery confirmation

### Protocol Flow

```
[Sensor] --mioty--> [Base Station] --BSSCI/TLS--> [Service Center] --MQTT--> [Your Application]
```

#### Key BSSCI Message Types

- **con/conCmp**: Connection establishment
- **attPrpReq/attPrpRsp**: Sensor attachment requests/responses
- **ulData/ulDataCmp**: Uplink data messages
- **statusReq/statusRsp**: Base station status queries
- **ping/pingCmp**: Keep-alive messages

### Message Structure

All BSSCI messages use MessagePack encoding with this structure:
```
[8-byte identifier "MIOTYB01"] + [4-byte length] + [MessagePack payload]
```

## Architecture & Data Flow

### System Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Base Station  │◄──►│  Service Center  │◄──►│  MQTT Broker    │
│                 │TLS │                  │    │                 │
│  - Sensor Mgmt  │    │ - TLS Server     │    │ - Data Topics   │
│  - Data Collect │    │ - MQTT Client    │    │ - Config Topics │
│  - Status Rep.  │    │ - Web Interface  │    │ - Status Topics │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                         ┌──────▼──────┐
                         │ Web Browser │
                         │ Management  │
                         └─────────────┘
```

### Data Flow Details

#### 1. Sensor Data Flow
```
Sensor → Base Station → Service Center → MQTT → Your Application
```

1. **Sensor Transmission**: Sensor sends data via mioty radio
2. **Base Station Reception**: Base station receives and forwards via BSSCI
3. **Service Center Processing**: 
   - Validates message
   - Performs deduplication (multiple base stations)
   - Selects best signal quality path
   - Formats for MQTT
4. **MQTT Publishing**: Data published to `bssci/ep/{sensor_eui}/ul`
5. **Application Consumption**: Your application subscribes and processes

#### 2. Configuration Flow
```
Your Application → MQTT → Service Center → Base Station → Sensor
```

1. **Configuration Request**: Publish to `bssci/ep/{sensor_eui}/config`
2. **Service Center Processing**: Validates and stores configuration
3. **Base Station Update**: Sends attachment request to base station
4. **Sensor Registration**: Base station registers sensor with network key

#### 3. Status Monitoring Flow
```
Base Station → Service Center → MQTT → Your Application
```

1. **Status Request**: Service center queries base station every 30 seconds
2. **Status Response**: Base station reports CPU, memory, uptime
3. **MQTT Publishing**: Status published to `bssci/bs/{basestation_eui}`
4. **Application Monitoring**: Subscribe for base station health monitoring

## Installation & Setup

### Prerequisites

- Python 3.8+
- TLS certificates for base station authentication
- MQTT broker access
- mioty base stations configured for BSSCI

### Quick Start

1. **Clone and Setup**:
   ```bash
   git clone <repository>
   cd mioty_BSSCI
   pip install -r requirements.txt
   ```

2. **Generate Certificates**:
   ```bash
   # Create CA certificate
   openssl genrsa -out certs/ca_key.pem 4096
   openssl req -x509 -new -key certs/ca_key.pem -sha256 -days 3650 -out certs/ca_cert.pem

   # Create service center certificate
   openssl genrsa -out certs/service_center_key.pem 2048
   openssl req -new -key certs/service_center_key.pem -out certs/service_center.csr
   openssl x509 -req -in certs/service_center.csr \
     -CA certs/ca_cert.pem -CAkey certs/ca_key.pem -CAcreateserial \
     -out certs/service_center_cert.pem -days 825 -sha256
   ```

3. **Configure Settings**:
   Edit `bssci_config.py` with your MQTT broker details and certificate paths.

4. **Start Service**:
   ```bash
   python web_main.py
   ```

5. **Access Web Interface**:
   Open `http://localhost:5000` for management interface.

## Configuration

### Main Configuration (`bssci_config.py`)

```python
# TLS Server Settings
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16018

# Certificate Paths
CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem" 
CA_FILE = "certs/ca_cert.pem"

# MQTT Broker Settings
MQTT_BROKER = "your-broker.com"
MQTT_PORT = 1883
MQTT_USERNAME = "username"
MQTT_PASSWORD = "password"
BASE_TOPIC = "bssci/"

# Operational Settings
STATUS_INTERVAL = 30  # Base station status query interval (seconds)
DEDUPLICATION_DELAY = 2  # Message deduplication window (seconds)
```

### Sensor Configuration (`endpoints.json`)

```json
[
  {
    "eui": "fca84a0300001234",
    "nwKey": "0011223344556677889AABBCCDDEEFF00",
    "shortAddr": "1234",
    "bidi": false
  }
]
```

## Usage

### Starting the Service

#### With Web Interface (Recommended)
```bash
python web_main.py
```
- Starts both BSSCI service and web management interface
- Web UI available at `http://localhost:5000`
- Integrated logging and monitoring

#### Service Only
```bash
python main.py  
```
- Starts only BSSCI service without web interface
- Console logging only

### Base Station Configuration

Configure your mioty base stations with:
- **Service Center IP**: Your server IP address
- **Port**: 16018 (or configured port)
- **TLS Certificate**: Install generated CA certificate
- **Client Certificate**: Configure base station client certificate

## Web Interface

### Dashboard Features

- **Service Status**: Real-time service health monitoring
- **Base Stations**: Connected base station status and statistics
- **Sensors**: Sensor registration status and configuration
- **Logs**: Real-time system logs with filtering
- **Configuration**: Sensor management and bulk operations

### Key Monitoring Metrics

- Connected base stations count
- Registered sensors count  
- Message throughput statistics
- Deduplication effectiveness
- MQTT broker connectivity status

## MQTT Integration

### Topic Structure

#### Sensor Data Topics
```
bssci/ep/{sensor_eui}/ul
```

**Payload Structure:**
```json
{
  "bs_eui": "70b3d59cd0000022",
  "rxTime": 1755708639613188798,
  "snr": 22.88,
  "rssi": -71.39,
  "cnt": 4830,
  "data": [2, 83, 1, 97, 6, 34, 3, 30, 2, 121]
}
```

#### Base Station Status Topics
```
bssci/bs/{basestation_eui}
```

**Payload Structure:**
```json
{
  "code": 0,
  "memLoad": 0.33,
  "cpuLoad": 0.23,
  "dutyCycle": 0.0,
  "time": 1755706414392137804,
  "uptime": 1566
}
```

#### Configuration Topics
```
bssci/ep/{sensor_eui}/config
```

**Payload Structure:**
```json
{
  "nwKey": "0011223344556677889AABBCCDDEEFF00",
  "shortAddr": "1234", 
  "bidi": false
}
```

### Message Deduplication

The service center implements intelligent deduplication:

1. **Multi-Path Reception**: Same sensor message received via multiple base stations
2. **Signal Quality Analysis**: Compares SNR values to select best path
3. **Delayed Publishing**: 2-second window to collect all copies
4. **Best Signal Selection**: Publishes message from base station with highest SNR
5. **Statistics Tracking**: Monitors duplication rates and effectiveness

## Programming Guide

### For Application Developers

#### Consuming Sensor Data

```python
import paho.mqtt.client as mqtt
import json

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # Subscribe to all sensor uplink data
    client.subscribe("bssci/ep/+/ul")

def on_message(client, userdata, msg):
    topic_parts = msg.topic.split('/')
    sensor_eui = topic_parts[2]

    data = json.loads(msg.payload.decode())

    print(f"Sensor {sensor_eui}:")
    print(f"  Base Station: {data['bs_eui']}")
    print(f"  Signal: SNR={data['snr']:.1f}dB, RSSI={data['rssi']:.1f}dBm")
    print(f"  Data: {data['data']}")
    print(f"  Timestamp: {data['rxTime']}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("your-mqtt-broker.com", 1883, 60)
client.loop_forever()
```

#### Dynamic Sensor Configuration

```python
def configure_sensor(client, sensor_eui, network_key, short_addr, bidirectional=False):
    config = {
        "nwKey": network_key,
        "shortAddr": short_addr,
        "bidi": bidirectional
    }

    topic = f"bssci/ep/{sensor_eui}/config"
    payload = json.dumps(config)

    client.publish(topic, payload)
    print(f"Configuration sent for sensor {sensor_eui}")

# Example usage
configure_sensor(client, "fca84a0300001234", "0011223344556677889AABBCCDDEEFF00", "1234")
```

#### Monitoring Base Station Health

```python
def on_base_station_status(client, userdata, msg):
    topic_parts = msg.topic.split('/')
    bs_eui = topic_parts[2]

    status = json.loads(msg.payload.decode())

    # Check for high resource usage
    if status['cpuLoad'] > 0.8:
        print(f"WARNING: Base station {bs_eui} high CPU usage: {status['cpuLoad']:.1%}")

    if status['memLoad'] > 0.9:
        print(f"WARNING: Base station {bs_eui} high memory usage: {status['memLoad']:.1%}")

    # Monitor uptime
    uptime_hours = status['uptime'] / 3600
    print(f"Base station {bs_eui} uptime: {uptime_hours:.1f} hours")

# Subscribe to base station status
client.subscribe("bssci/bs/+")
```

### Data Processing Considerations

#### Timestamp Handling

```python
from datetime import datetime

def parse_mioty_timestamp(timestamp_ns):
    """Convert mioty nanosecond timestamp to datetime"""
    timestamp_seconds = timestamp_ns / 1_000_000_000
    return datetime.fromtimestamp(timestamp_seconds)

# Usage
rx_datetime = parse_mioty_timestamp(data['rxTime'])
print(f"Message received at: {rx_datetime}")
```

#### Data Payload Interpretation

Sensor data arrives as byte arrays. Interpretation depends on your sensor:

```python
def parse_sensor_data(raw_data, sensor_type="temperature_humidity"):
    """Parse sensor-specific data format"""
    if sensor_type == "temperature_humidity":
        if len(raw_data) >= 4:
            temp = int.from_bytes(raw_data[0:2], byteorder='little', signed=True) / 100
            humidity = int.from_bytes(raw_data[2:4], byteorder='little') / 100
            return {"temperature": temp, "humidity": humidity}

    elif sensor_type == "gps_tracker":
        if len(raw_data) >= 8:
            lat = int.from_bytes(raw_data[0:4], byteorder='little', signed=True) / 1000000
            lon = int.from_bytes(raw_data[4:8], byteorder='little', signed=True) / 1000000
            return {"latitude": lat, "longitude": lon}

    return {"raw_data": raw_data}
```

### Quality Metrics

#### Signal Quality Assessment

```python
def assess_signal_quality(snr, rssi):
    """Assess signal quality from SNR and RSSI values"""
    if snr > 10 and rssi > -80:
        return "excellent"
    elif snr > 5 and rssi > -90:
        return "good"
    elif snr > 0 and rssi > -100:
        return "fair"
    else:
        return "poor"

quality = assess_signal_quality(data['snr'], data['rssi'])
print(f"Signal quality: {quality}")
```

## API Documentation

### Web API Endpoints

#### Service Status
```
GET /api/bssci/status
```
Returns service health and connection status.

#### Base Stations
```
GET /api/base-stations
```
Returns list of connected base stations with status.

#### Sensors
```
GET /api/sensors
GET /api/sensors/{eui}
POST /api/sensors (bulk configuration)
DELETE /api/sensors/clear
```

#### Logs
```
GET /api/logs?level=INFO&lines=100
```
Returns recent log entries with filtering.

## Troubleshooting

### Common Issues

#### Base Station Not Connecting

1. **Certificate Issues**:
   - Verify CA certificate installed on base station
   - Check certificate validity dates
   - Ensure certificate CN matches configuration

2. **Network Issues**:
   - Check firewall rules for port 16018
   - Verify base station can reach service center IP
   - Test TLS connectivity with openssl

3. **Configuration Issues**:
   - Verify base station BSSCI configuration
   - Check service center listening address
   - Review certificate paths in config

#### Sensors Not Registering

1. **Configuration Issues**:
   - Verify EUI format (16 hex characters)
   - Check network key length (32 hex characters)
   - Validate short address format (4 hex characters)

2. **Base Station Issues**:
   - Ensure base station is connected
   - Check base station sensor capacity
   - Verify base station firmware supports BSSCI

#### MQTT Issues

1. **Connection Problems**:
   - Verify broker credentials
   - Check network connectivity to broker
   - Review broker authentication settings

2. **Message Issues**:
   - Check topic permissions
   - Verify message format
   - Review broker message limits

### Debugging Tools

#### Log Analysis
```bash
# Filter logs by level
grep "ERROR" logs/bssci.log

# Monitor real-time logs  
tail -f logs/bssci.log

# Search for specific sensor
grep "fca84a0300001234" logs/bssci.log
```

#### MQTT Testing
```bash
# Subscribe to all topics
mosquitto_sub -h broker-host -t "bssci/#" -v

# Test configuration publishing
mosquitto_pub -h broker-host -t "bssci/ep/fca84a0300001234/config" \
  -m '{"nwKey":"0011223344556677889AABBCCDDEEFF00","shortAddr":"1234","bidi":false}'
```

## Advanced Features

### Message Deduplication

The service center implements sophisticated deduplication:

- **Multi-base station support**: Handles same message from multiple base stations
- **Signal quality optimization**: Selects best signal path based on SNR
- **Configurable delay**: Adjustable deduplication window
- **Statistics tracking**: Monitors duplicate rates and efficiency

### Preferred Downlink Path

Automatically tracks best base station for each sensor:

- **Signal quality tracking**: Monitors SNR for each sensor-base station pair
- **Dynamic path selection**: Updates preferred path based on signal quality
- **Persistent storage**: Saves preferred paths to configuration

### High Availability Features

- **Automatic reconnection**: Handles base station disconnections gracefully  
- **Queue persistence**: Maintains message queues during network issues
- **Health monitoring**: Continuous service health checks
- **Graceful degradation**: Continues operation with partial connectivity

### Performance Optimization

- **Asynchronous processing**: Non-blocking message handling
- **Connection pooling**: Efficient base station connection management
- **Memory management**: Automatic cleanup of old data
- **Batch operations**: Efficient bulk sensor configuration

---

## 📄 License

This project is licensed under a **Non-Commercial License**. 

### What you CAN do:
- ✅ Use for personal projects
- ✅ Use for educational purposes  
- ✅ Use for research
- ✅ Modify and distribute (non-commercially)
- ✅ Study the code

### What you CANNOT do:
- ❌ Use in commercial products or services
- ❌ Sell the software or derivatives
- ❌ Use to generate revenue

### Commercial Use
For commercial licensing, enterprise support, or custom development, please open an issue on GitHub or contact us through the repository.

**Full license terms**: See [LICENSE](LICENSE) file

---

## 🤝 Contributing

Contributions are welcome! By contributing, you agree that your contributions will be licensed under the same non-commercial terms.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

## ⭐ Support the Project

If this project helps you, please:
- Give it a star on GitHub ⭐
- Share it with others who might find it useful
- Report bugs and suggest improvements
- Consider contributing code or documentation

---

For questions or support, please check the troubleshooting section or create an issue in the repository.