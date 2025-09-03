
**Version: V1.20 - Fully Functional Checkpoint**
*Date: January 2025*
*Status: ✅ All systems operational - Base stations connecting, sensors registering successfully*

## Overview

The BSSCI Service Center is a comprehensive IoT device management system that provides secure communication between mioty sensors, base stations, and MQTT brokers. It implements the BSSCI (Base Station Service Center Interface) protocol with advanced features for sensor lifecycle management, automatic detachment, and real-time monitoring.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Core Features](#core-features)
3. [Installation & Setup](#installation--setup)
4. [Configuration](#configuration)
5. [Sensor Management](#sensor-management)
6. [Auto-Detach System](#auto-detach-system)
7. [MQTT Integration](#mqtt-integration)
8. [Web Interface](#web-interface)
9. [API Reference](#api-reference)
10. [Troubleshooting](#troubleshooting)
11. [Advanced Features](#advanced-features)

## System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Base Station  │◄──►│  Service Center  │◄──►│  MQTT Broker    │
│                 │TLS │                  │    │                 │
│  - Sensor Mgmt  │    │ - TLS Server     │    │ - Data Topics   │
│  - Data Collect │    │ - MQTT Client    │    │ - Config Topics │
│  - Status Rep.  │    │ - Web Interface  │    │ - Status Topics │
│                 │    │ - Auto-Detach    │    │ - Commands      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                         ┌──────▼──────┐
                         │ Web Browser │
                         │ Management  │
                         └─────────────┘
```

### Key Components

- **TLS Server**: Secure communication with base stations using BSSCI protocol
- **MQTT Interface**: Bidirectional communication with external systems
- **Web UI**: Real-time management and monitoring dashboard
- **Auto-Detach System**: Automated sensor lifecycle management
- **Certificate Management**: SSL/TLS security infrastructure

## Core Features

### Sensor Lifecycle Management

- **Automatic Registration**: Sensors are automatically registered when base stations connect
- **Manual Detachment**: Individual sensor detachment via web UI
- **Bulk Operations**: Clear all sensors with automatic detachment
- **Remote Commands**: MQTT-based sensor control (attach, detach, status)
- **Auto-Detach**: Automatic removal of inactive sensors after configurable timeout

### Real-Time Monitoring

- **Live Dashboard**: Real-time sensor status and base station monitoring
- **Activity Tracking**: Monitor sensor communication and detect inactivity
- **Warning System**: Proactive alerts before auto-detachment
- **Signal Quality**: Track preferred downlink paths based on SNR
- **Comprehensive Logging**: Detailed system logs with timezone support

### Data Processing

- **Message Deduplication**: Intelligent filtering of duplicate messages from multiple base stations
- **Signal Optimization**: Automatic selection of best signal path
- **Queue Management**: Asynchronous message processing with monitoring
- **Performance Metrics**: Real-time statistics and monitoring

## Installation & Setup

### Prerequisites

- Python 3.12+
- SSL certificates for TLS communication
- MQTT broker access
- Network connectivity to base stations

### Quick Start

1. **Clone and Setup**:
   ```bash
   git clone <repository-url>
   cd bssci-service-center
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Generate Certificates** (if needed):
   ```bash
   mkdir certs
   # Use web UI certificate management or manual generation
   ```

4. **Start the Service**:
   ```bash
   python web_main.py
   ```

5. **Access Web Interface**:
   Open http://localhost:5000 in your browser

## Configuration

### Environment Variables (.env)

```bash
# TLS Server Configuration
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8000
CERT_FILE=certs/service_center_cert.pem
KEY_FILE=certs/service_center_key.pem
CA_FILE=certs/ca_cert.pem

# MQTT Configuration
MQTT_BROKER=your-mqtt-broker.com
MQTT_PORT=1883
MQTT_USERNAME=your-username
MQTT_PASSWORD=your-password
BASE_TOPIC=mioty

# Auto-detach Configuration
AUTO_DETACH_ENABLED=true
AUTO_DETACH_TIMEOUT=259200          # 72 hours in seconds
AUTO_DETACH_WARNING_TIMEOUT=129600  # 36 hours in seconds
AUTO_DETACH_CHECK_INTERVAL=3600     # Check every hour

# Application Configuration
SENSOR_CONFIG_FILE=endpoints.json
STATUS_INTERVAL=300
DEDUPLICATION_DELAY=2.0
```

### Main Configuration (bssci_config.py)

The system uses a Python configuration file for core settings:

```python
# Network Configuration
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16018

# SSL/TLS Certificates
CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem" 
CA_FILE = "certs/ca_cert.pem"

# Auto-detach Settings (configurable via web UI)
AUTO_DETACH_ENABLED = True
AUTO_DETACH_TIMEOUT = 72 * 3600      # 72 hours
AUTO_DETACH_WARNING_TIMEOUT = 36 * 3600  # 36 hours
AUTO_DETACH_CHECK_INTERVAL = 3600    # 1 hour
```

## Sensor Management

### Adding Sensors

#### Via Web Interface
1. Navigate to "Manage Sensors" in the web UI
2. Click "Add New Sensor"
3. Fill in required fields:
   - **EUI**: 16-character hexadecimal identifier
   - **Network Key**: 32-character hexadecimal key
   - **Short Address**: 4-character hexadecimal address
   - **Bidirectional**: Enable/disable bidirectional communication

#### Via MQTT Configuration
Publish to topic: `{BASE_TOPIC}/ep/{EUI}/config`
```json
{
  "nwKey": "0011223344556677889AABBCCDDEEFF00",
  "shortAddr": "1234",
  "bidi": false
}
```

### Sensor Status Indicators

The web interface displays comprehensive sensor status:

- **🟢 Active**: Sensor recently communicated (within warning threshold)
- **🟡 Warning**: Sensor inactive for 36+ hours (configurable)
- **🔴 Auto-Detach Pending**: Sensor inactive for 72+ hours (configurable)
- **⚫ Auto-Detached**: Sensor automatically detached due to inactivity
- **🔗 Registered**: Sensor successfully registered to base station(s)

### Manual Detachment

#### Single Sensor Detachment
- Click the "Detach" button next to any sensor in the web interface
- Sensor is detached from all connected base stations
- Status is updated immediately

#### Bulk Detachment
- Click "Clear All" in the sensors management page
- All sensors are detached from all base stations
- Configuration is cleared
- Operation is logged and confirmed

## Auto-Detach System

The auto-detach system provides automated sensor lifecycle management based on communication activity.

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AUTO_DETACH_ENABLED` | `true` | Enable/disable auto-detach functionality |
| `AUTO_DETACH_TIMEOUT` | `259200` | Seconds (72 hours) before auto-detach |
| `AUTO_DETACH_WARNING_TIMEOUT` | `129600` | Seconds (36 hours) before warning |
| `AUTO_DETACH_CHECK_INTERVAL` | `3600` | Seconds (1 hour) between checks |

### Auto-Detach Process

1. **Activity Monitoring**: System tracks last communication from each sensor
2. **Warning Phase** (after 36 hours):
   - Warning status displayed in web interface
   - MQTT warning notification sent to `ep/{EUI}/warning`
   - Sensor status shows hours until detachment
3. **Auto-Detach Phase** (after 72 hours):
   - Sensor automatically detached from all base stations
   - MQTT notification sent to `ep/{EUI}/status`
   - Sensor removed from registration tracking
   - Status updated in web interface

### Warning Information

When sensors enter warning state, the following information is available:

```json
{
  "action": "inactivity_warning",
  "sensor_eui": "FCA84A0300001234",
  "inactive_hours": 36.5,
  "hours_until_detach": 35.5,
  "warning_threshold_hours": 36,
  "detach_threshold_hours": 72,
  "timestamp": 1703123456.789
}
```

## MQTT Integration

### Topic Structure

The system uses a hierarchical MQTT topic structure:

```
{BASE_TOPIC}/
├── ep/{EUI}/
│   ├── ul              # Uplink data from sensors
│   ├── dl              # Downlink data to sensors  
│   ├── config          # Sensor configuration
│   ├── status          # Sensor status updates
│   ├── warning         # Inactivity warnings
│   ├── response        # Command responses
│   └── error           # Error notifications
├── bs/{EUI}/           # Base station status
├── config/             # System configuration
└── health_check        # Connection health monitoring
```

### Remote Commands

Send commands to sensors via MQTT topic `EP/{EUI}/cmd/`:

#### Detach Command
```bash
mosquitto_pub -h broker -t "EP/FCA84A0300001234/cmd/" -m "detach"
```

#### Attach Command  
```bash
mosquitto_pub -h broker -t "EP/FCA84A0300001234/cmd/" -m "attach"
```

#### Status Request
```bash
mosquitto_pub -h broker -t "EP/FCA84A0300001234/cmd/" -m "status"
```

### Command Responses

Commands receive responses on topic `EP/{EUI}/response`:

```json
{
  "command": "detach",
  "status": "received",
  "timestamp": 1703123456.789
}
```

### Auto-Detach Notifications

#### Warning Notification (`ep/{EUI}/warning`)
```json
{
  "action": "inactivity_warning",
  "sensor_eui": "FCA84A0300001234", 
  "inactive_hours": 36.5,
  "hours_until_detach": 35.5,
  "timestamp": 1703123456.789
}
```

#### Auto-Detach Notification (`ep/{EUI}/status`)
```json
{
  "action": "auto_detached",
  "sensor_eui": "FCA84A0300001234",
  "reason": "inactivity", 
  "inactive_hours": 72.3,
  "threshold_hours": 72,
  "timestamp": 1703123456.789
}
```

## Web Interface

### Dashboard Overview

The main dashboard provides real-time system status:

- **Service Status**: Overall system health and connectivity
- **Base Station Monitor**: Connected and connecting base stations
- **Sensor Summary**: Total sensors, registrations, and activity status
- **Quick Actions**: Direct access to management functions

### Sensor Management Interface

#### Sensor List View
- **Status Indicators**: Visual status for each sensor (active, warning, detached)
- **Registration Info**: Shows which base stations each sensor is connected to
- **Activity Tracking**: Hours since last communication
- **Signal Quality**: Preferred downlink path with SNR information
- **Action Buttons**: Detach individual sensors or bulk operations

#### Sensor Details
- **Configuration**: EUI, network key, short address, bidirectional setting
- **Registration History**: Timeline of registrations and detachments  
- **Communication Stats**: Message counts, signal quality metrics
- **Warning Status**: Current warning state and time until auto-detach

### Configuration Management

#### General Settings
- Network configuration (host, port)
- MQTT broker settings
- SSL certificate management
- System intervals and timeouts

#### Auto-Detach Settings
- Enable/disable auto-detach functionality
- Configure warning and detach timeouts
- Set monitoring check intervals
- Real-time parameter updates

### Certificate Management

#### SSL Certificate Operations
- **Generate**: Create new self-signed certificates
- **Upload**: Upload existing certificate files
- **Download**: Backup current certificates
- **Status Check**: Verify certificate validity and expiration

#### Certificate Files Required
- `ca_cert.pem`: Certificate Authority certificate
- `service_center_cert.pem`: Service center certificate
- `service_center_key.pem`: Service center private key

## API Reference

### Sensor Operations

#### Get All Sensors
```http
GET /api/sensors
```

Returns complete sensor status including registration, activity, and warning information.

#### Add/Update Sensor
```http
POST /api/sensors
Content-Type: application/json

{
  "eui": "FCA84A0300001234",
  "nwKey": "0011223344556677889AABBCCDDEEFF00", 
  "shortAddr": "1234",
  "bidi": false
}
```

#### Delete Sensor
```http
DELETE /api/sensors/{eui}
```

#### Detach Single Sensor
```http
POST /api/sensors/{eui}/detach
```

Detaches the sensor from all connected base stations.

#### Clear All Sensors
```http
POST /api/sensors/clear
```

Performs bulk detachment and clears all sensor configurations.

### System Status

#### Service Status
```http
GET /api/bssci/status
```

Returns comprehensive system status including:
- Service running state
- Base station connections
- Sensor registration statistics
- MQTT connectivity
- TLS server status

#### Base Station Status
```http
GET /api/base_stations
```

Returns detailed information about connected and connecting base stations.

### Configuration Management

#### Get Configuration
```http
GET /config
```

#### Update Configuration  
```http
POST /api/config
Content-Type: application/json

{
  "MQTT_BROKER": "your-broker.com",
  "AUTO_DETACH_ENABLED": true,
  "AUTO_DETACH_TIMEOUT": 259200,
  "AUTO_DETACH_WARNING_TIMEOUT": 129600
}
```

## Advanced Features

### Message Deduplication

The system implements sophisticated message deduplication for multi-base station deployments:

#### How It Works
1. **Message Reception**: Same sensor message received from multiple base stations
2. **Quality Comparison**: SNR values compared between base stations  
3. **Best Path Selection**: Message with highest SNR is selected for publication
4. **Preferred Path Update**: System learns optimal routing for each sensor
5. **Duplicate Filtering**: Lower quality duplicates are discarded

#### Configuration
- **Deduplication Delay**: `DEDUPLICATION_DELAY = 2.0` seconds
- **Buffer Management**: Automatic cleanup of processed messages
- **Statistics Tracking**: Real-time duplicate rate monitoring

#### Statistics Available
- Total messages received
- Duplicate messages filtered  
- Messages published
- Duplication rate percentage

### Preferred Downlink Path Management

The system automatically tracks the best communication path for each sensor:

#### Signal Quality Tracking
- **SNR Monitoring**: Tracks Signal-to-Noise Ratio for each sensor-base station pair
- **Dynamic Updates**: Continuously updates preferred path based on signal quality
- **Path Persistence**: Stores preferred paths in sensor configuration
- **Multi-Base Station Support**: Handles sensors communicating through multiple base stations

#### Path Selection Algorithm
1. Message received with SNR measurement
2. Compare with current preferred path SNR
3. Update preferred path if new SNR is better
4. Save configuration with updated preferred path
5. Use preferred path for future downlink messages

### Queue Management System

#### Asynchronous Queue Architecture
- **MQTT Output Queue**: Messages to be published to MQTT broker
- **MQTT Input Queue**: Configuration and command messages from MQTT
- **Queue Monitoring**: Real-time queue size monitoring and statistics
- **Health Checking**: Automatic detection and recovery from queue issues

#### Queue Statistics
- Queue sizes and utilization
- Message processing rates
- Error rates and recovery statistics
- Performance metrics and bottleneck detection

### Security Features

#### SSL/TLS Security
- **Mutual Authentication**: Base stations must present valid certificates
- **Certificate Validation**: Full chain validation with CA verification
- **Secure Channels**: All communication encrypted with TLS 1.2+
- **Certificate Management**: Web-based certificate upload, generation, and backup

#### Access Control
- **Web Interface Security**: Session-based access control
- **API Protection**: Request validation and sanitization
- **Certificate-Based Auth**: Base station authentication via client certificates
- **MQTT Security**: Username/password authentication for MQTT broker

## Troubleshooting

### Common Issues

#### Base Station Connection Issues

**Problem**: Base stations cannot connect to TLS server

**Solutions**:
1. **Certificate Issues**:
   ```bash
   # Check certificate validity
   openssl x509 -in certs/service_center_cert.pem -text -noout
   
   # Verify CA certificate
   openssl verify -CAfile certs/ca_cert.pem certs/service_center_cert.pem
   ```

2. **Network Connectivity**:
   ```bash
   # Check if port is accessible
   telnet <service-center-ip> 16018
   
   # Verify firewall settings
   netstat -tlnp | grep 16018
   ```

3. **SSL Configuration**:
   - Ensure base station has correct CA certificate
   - Verify base station client certificate is signed by same CA
   - Check certificate expiration dates

#### MQTT Connectivity Issues

**Problem**: MQTT broker connection failures

**Solutions**:
1. **Authentication Issues**:
   - Verify MQTT_USERNAME and MQTT_PASSWORD in configuration
   - Check broker access control lists (ACLs)
   - Test credentials with mosquitto_pub/sub

2. **Network Issues**:
   ```bash
   # Test MQTT connectivity
   mosquitto_pub -h <broker-host> -p <port> -u <username> -P <password> -t "test" -m "hello"
   ```

3. **Topic Permissions**:
   - Ensure user has publish/subscribe permissions for all required topics
   - Check broker topic filter configurations

#### Sensor Registration Problems

**Problem**: Sensors not registering properly

**Solutions**:
1. **Configuration Validation**:
   - Verify EUI format (16 hex characters)
   - Check network key format (32 hex characters)  
   - Validate short address (4 hex characters)
   - Ensure sensor configuration is saved in endpoints.json

2. **Base Station Issues**:
   - Verify base station is connected to service center
   - Check base station sensor capacity
   - Review base station logs for errors

3. **Protocol Issues**:
   - Monitor TLS server logs for BSSCI protocol errors
   - Verify BSSCI protocol version compatibility
   - Check for network timeout issues

#### Auto-Detach Issues

**Problem**: Sensors being detached unexpectedly

**Solutions**:
1. **Timeout Configuration**:
   - Review AUTO_DETACH_TIMEOUT setting (default 72 hours)
   - Check AUTO_DETACH_WARNING_TIMEOUT (default 36 hours)
   - Verify sensor communication frequency

2. **Activity Tracking**:
   - Monitor sensor last-seen timestamps in web interface
   - Check for network issues preventing sensor communication
   - Verify sensor transmission schedules

3. **Disable Auto-Detach**:
   ```python
   # In bssci_config.py or via web interface
   AUTO_DETACH_ENABLED = False
   ```

### Debugging Tools

#### Log Analysis
```bash
# View real-time logs
tail -f logs/bssci_service.log

# Filter by log level
grep "ERROR" logs/bssci_service.log

# Search for specific sensor
grep "FCA84A0300001234" logs/bssci_service.log

# Monitor auto-detach activity
grep "AUTO-DETACH" logs/bssci_service.log
```

#### MQTT Debugging
```bash
# Monitor all MQTT traffic
mosquitto_sub -h <broker> -u <user> -P <pass> -t "#" -v

# Test sensor commands
mosquitto_pub -h <broker> -u <user> -P <pass> -t "EP/FCA84A0300001234/cmd/" -m "status"

# Monitor specific sensor
mosquitto_sub -h <broker> -u <user> -P <pass> -t "mioty/ep/FCA84A0300001234/#" -v
```

#### Web Interface Debugging
- Use browser developer tools to monitor API calls
- Check network tab for failed requests
- Review console for JavaScript errors
- Monitor WebSocket connections if applicable

### Performance Monitoring

#### System Metrics
- Monitor CPU and memory usage
- Check network bandwidth utilization
- Review disk space for log files
- Track message processing rates

#### Queue Monitoring
```bash
# Monitor queue sizes via web interface
curl http://localhost:5000/api/bssci/status | jq '.queue_statistics'
```

#### Base Station Load
- Monitor base station connection counts
- Track sensor registration distribution
- Review base station CPU/memory from status reports
- Analyze duty cycle and uptime statistics

## Data Flow Details

### Sensor Data Flow
```
Sensor → Base Station → Service Center → MQTT → Your Application
```

1. **Sensor Transmission**: Sensor sends data via mioty radio protocol
2. **Base Station Reception**: Base station receives and processes sensor data
3. **TLS Forwarding**: Base station forwards data to service center via secure TLS
4. **Deduplication**: Service center processes and deduplicates messages
5. **MQTT Publication**: Deduplicated data published to MQTT broker
6. **Application Consumption**: Your application receives data from MQTT topics

### Configuration Flow  
```
Web UI/MQTT → Service Center → Base Station → Sensor
```

1. **Configuration Input**: Via web interface or MQTT topic
2. **Validation**: Service center validates configuration parameters
3. **Storage**: Configuration saved to endpoints.json
4. **Propagation**: Attach requests sent to connected base stations
5. **Registration**: Base stations register sensors with provided configuration
6. **Confirmation**: Registration status reported back to service center

### Command Flow
```
MQTT/Web UI → Service Center → Base Station → Sensor
```

1. **Command Reception**: Commands received via MQTT or web interface
2. **Processing**: Service center processes and validates commands
3. **Execution**: Appropriate BSSCI protocol messages sent to base stations
4. **Response**: Base stations respond with execution status
5. **Notification**: Status updates sent via MQTT and web interface

## Deployment Options

### Development Mode
```bash
python web_main.py
```
- Includes web interface on port 5000
- Detailed logging and debugging
- Auto-reload on configuration changes

### Production Mode  
```bash
python main.py
```
- Service only (no web interface)
- Optimized logging
- Production-ready performance

### Docker Deployment
```bash
docker-compose up -d --build
```
- Containerized deployment
- Automatic certificate generation
- Volume persistence for configuration and logs

## Monitoring and Alerting

### Log Monitoring
- **Structured Logging**: JSON-formatted logs with timezone support
- **Log Levels**: DEBUG, INFO, WARNING, ERROR with appropriate filtering
- **Component Identification**: Clear logger names for each system component
- **Performance Metrics**: Message processing times and queue statistics

### Health Checks
- **Service Health**: Regular health check endpoints
- **Component Status**: Individual component status monitoring  
- **Connection Monitoring**: Base station and MQTT broker connectivity
- **Auto-Recovery**: Automatic reconnection and error recovery

### Alerting Integration
- **MQTT Notifications**: Real-time alerts via MQTT topics
- **Web Interface Alerts**: Visual notifications in management interface
- **Log-Based Monitoring**: Integration with log monitoring systems
- **Custom Alerting**: Extensible notification system for integration

## Integration Examples

### Python Application Integration
```python
import paho.mqtt.client as mqtt
import json

def on_message(client, userdata, message):
    topic = message.topic
    payload = json.loads(message.payload.decode())
    
    if "/ul" in topic:
        # Handle sensor data
        sensor_eui = topic.split('/')[2]
        sensor_data = payload['data']
        print(f"Data from {sensor_eui}: {sensor_data}")
    
    elif "/warning" in topic:
        # Handle inactivity warnings
        sensor_eui = payload['sensor_eui'] 
        hours_inactive = payload['inactive_hours']
        print(f"Warning: Sensor {sensor_eui} inactive for {hours_inactive} hours")
    
    elif "/status" in topic and payload.get('action') == 'auto_detached':
        # Handle auto-detach notifications
        sensor_eui = payload['sensor_eui']
        print(f"Alert: Sensor {sensor_eui} was auto-detached due to inactivity")

client = mqtt.Client()
client.on_message = on_message
client.connect("broker-host", 1883, 60)
client.subscribe("mioty/ep/+/ul")        # Sensor data
client.subscribe("mioty/ep/+/warning")   # Inactivity warnings  
client.subscribe("mioty/ep/+/status")    # Status updates
client.loop_forever()
```

### Remote Sensor Management
```python
import paho.mqtt.publish as publish

def detach_sensor(sensor_eui):
    """Remotely detach a sensor"""
    topic = f"EP/{sensor_eui}/cmd/"
    payload = "detach"
    publish.single(topic, payload, hostname="broker-host")

def attach_sensor(sensor_eui):
    """Remotely attach a sensor"""
    topic = f"EP/{sensor_eui}/cmd/"
    payload = "attach" 
    publish.single(topic, payload, hostname="broker-host")

def get_sensor_status(sensor_eui):
    """Request sensor status"""
    topic = f"EP/{sensor_eui}/cmd/"
    payload = "status"
    publish.single(topic, payload, hostname="broker-host")
```

## Best Practices

### Configuration Management
- **Regular Backups**: Backup endpoints.json and certificates regularly
- **Version Control**: Track configuration changes with version control
- **Validation**: Always validate configuration before applying
- **Testing**: Test configuration changes in development environment first

### Security
- **Certificate Rotation**: Regularly update SSL certificates
- **Access Control**: Limit access to management interfaces
- **Audit Logging**: Monitor all configuration and operational changes
- **Network Security**: Use firewalls and VPNs for production deployments

### Performance Optimization
- **Queue Monitoring**: Monitor queue sizes and processing rates
- **Resource Usage**: Track CPU, memory, and network utilization  
- **Base Station Distribution**: Balance sensor load across base stations
- **Database Optimization**: Regular cleanup of old logs and data

### Operational Procedures
- **Health Monitoring**: Implement comprehensive health checking
- **Alert Management**: Set up appropriate alerting for critical issues
- **Backup Procedures**: Regular backup of configuration and certificates
- **Disaster Recovery**: Documented procedures for service recovery

## License

This project is licensed under the terms specified in the LICENSE file.

## Support

For technical support and questions:
- Check the troubleshooting section above
- Review system logs for error details
- Use the web interface diagnostic tools
- Monitor MQTT topics for real-time system status

---

*BSSCI Service Center - Professional IoT Device Management Platform*
