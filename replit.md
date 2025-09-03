# BSSCI Service Center

## Overview

The BSSCI Service Center is a comprehensive IoT device management system that provides secure communication between mioty sensors, base stations, and MQTT brokers. It implements the BSSCI (Base Station Service Center Interface) protocol for managing mioty sensor networks, featuring real-time sensor lifecycle management, automated message deduplication, and a web-based management interface.

The system acts as a central hub that receives sensor data from base stations via TLS connections, processes and deduplicates messages, and forwards them to MQTT brokers for integration with external systems. It also provides bidirectional communication for sensor configuration and management commands.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Components

**TLS Server Architecture**: The system implements a custom TLS server that handles secure BSSCI protocol communications with base stations. It maintains persistent connections with multiple base stations simultaneously and manages sensor attach/detach operations through a message-based protocol using MessagePack serialization.

**MQTT Interface**: A dedicated MQTT client handles bidirectional communication with external systems. It publishes sensor data and status information to MQTT topics while subscribing to configuration and command topics. The interface uses a queue-based architecture for reliable message handling.

**Web Management Interface**: A Flask-based web application provides real-time monitoring and management capabilities. The interface runs on a separate thread and communicates with the core TLS server through shared data structures and queue systems.

**Message Processing Pipeline**: The system implements a sophisticated message deduplication system that buffers incoming sensor messages for a configurable delay period, selecting the best quality message (highest SNR) when duplicates are received from multiple base stations.

**Auto-Detach System**: An automated sensor lifecycle management system monitors sensor activity and automatically detaches inactive sensors after configurable timeout periods, with warning notifications sent before detachment.

### Data Flow Architecture

**Sensor Registration Flow**: Sensors are configured in JSON format with EUI, network keys, and addressing information. The TLS server reads this configuration and sends attach requests to connected base stations, tracking pending operations and their responses.

**Message Routing**: Incoming sensor data flows from base stations through the TLS server, gets processed by the deduplication system, and is then queued for MQTT publication. Status information and commands flow in the reverse direction.

**Queue-Based Communication**: The system uses asyncio queues for inter-component communication, with separate queues for MQTT outbound messages, MQTT inbound messages, and internal coordination.

### Configuration Management

**Environment-Based Configuration**: All system settings are managed through environment variables with sensible defaults, including TLS certificates, MQTT broker settings, timing parameters, and feature toggles.

**Dynamic Sensor Configuration**: Sensor endpoints are configured through a JSON file that can be modified at runtime, with the web interface providing tools for adding, editing, and removing sensor configurations.

**Certificate Management**: The system supports custom SSL/TLS certificates for secure base station communication, with certificate generation and management capabilities built into the web interface.

## External Dependencies

**MQTT Broker Integration**: Requires connection to an external MQTT broker for data publishing and command reception. Supports username/password authentication and configurable topic structures.

**SSL/TLS Infrastructure**: Depends on certificate authority infrastructure for securing base station communications. Requires CA certificates, server certificates, and private keys.

**MessagePack Protocol**: Uses MessagePack for efficient binary serialization of BSSCI protocol messages between the service center and base stations.

**Flask Web Framework**: The management interface is built on Flask with Bootstrap for responsive UI design and real-time updates through JavaScript polling.

**Docker Deployment**: Includes Docker containerization with support for both development and production deployment configurations, including volume mounting for persistent configuration and certificate storage.

**Base Station Hardware**: Designed to work with mioty-compatible base stations that implement the BSSCI protocol for sensor network management and data collection.