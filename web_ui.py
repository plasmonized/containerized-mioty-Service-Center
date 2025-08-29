import json
import logging
import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from typing import List, Dict, Any
import bssci_config

app = Flask(__name__)
app.secret_key = 'bssci-ui-secret-key'

# Global variables for log storage and configuration
log_entries: List[Dict[str, Any]] = []
max_log_entries = 1000

# Custom log handler to capture all logs
# Consolidated WebUILogHandler - single definition to avoid duplicates

class WebUILogHandler(logging.Handler):
    def emit(self, record):
        global log_entries

        # Filter out noisy web request logs to reduce clutter
        if record.name == 'werkzeug' and any(x in record.getMessage() for x in [
            'GET /api/', 'GET /logs', 'GET /sensors', 'GET /config', 'GET /', 'GET /static/'
        ]):
            return  # Skip web request logs

        # Avoid duplicate handlers by checking if this exact message was just logged
        current_time = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        message = record.getMessage()

        # Check if this exact message was logged in the last second (duplicate detection)
        if log_entries:
            last_entry = log_entries[-1]
            time_diff = abs(record.created - datetime.strptime(last_entry['timestamp'], '%Y-%m-%d %H:%M:%S.%f').timestamp())
            if (time_diff < 1.0 and  # Within 1 second
                last_entry['message'] == message and
                last_entry['logger'] == record.name):
                return  # Skip duplicate message

        log_entry = {
            'timestamp': current_time,
            'level': record.levelname,
            'logger': record.name,
            'message': message
        }
        log_entries.append(log_entry)

        # Keep only the last max_log_entries
        if len(log_entries) > max_log_entries:
            log_entries = log_entries[-max_log_entries:]

# Add our custom handler to the root logger (only once)
if not any(isinstance(h, WebUILogHandler) for h in logging.getLogger().handlers):
    web_handler = WebUILogHandler()
    logging.getLogger().addHandler(web_handler)
    logging.getLogger().setLevel(logging.DEBUG)

    # Specifically capture important logs
    logging.getLogger('TLSServer').setLevel(logging.DEBUG)
    logging.getLogger('mqtt_interface').setLevel(logging.DEBUG)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sensors')
def sensors():
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except FileNotFoundError:
        sensors = []
        logging.warning(f"Sensor config file not found: {bssci_config.SENSOR_CONFIG_FILE}")
    except json.JSONDecodeError:
        sensors = []
        logging.error(f"Error decoding JSON from sensor config file: {bssci_config.SENSOR_CONFIG_FILE}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while reading sensor config: {e}")
        sensors = []
    return render_template('sensors.html', sensors=sensors)

@app.route('/api/sensors', methods=['GET'])
def get_sensors():
    try:
        # Try async service first
        tls_server = None
        try:
            from web_main import get_tls_server
            tls_server = get_tls_server()
            if tls_server:
                if hasattr(tls_server, 'reload_sensor_config'):
                    tls_server.reload_sensor_config()
                if hasattr(tls_server, 'get_sensor_registration_status'):
                    return jsonify(tls_server.get_sensor_registration_status())
        except Exception as async_e:
            logging.debug(f"Async service not available: {async_e}")

        # Try sync service if async not available
        if not tls_server:
            try:
                import sync_main
                if hasattr(sync_main, 'tls_server_instance') and sync_main.tls_server_instance:
                    tls_server = sync_main.tls_server_instance
                    if hasattr(tls_server, 'sensor_config'):
                        # For sync version, build registration status from sensor config
                        sensor_status = {}
                        connected_stations = getattr(tls_server, 'connected_base_stations', {})
                        base_station_list = list(set(connected_stations.values()))  # Remove duplicates

                        for sensor in tls_server.sensor_config:
                            eui = sensor['eui'].lower()
                            sensor_status[eui] = {
                                'eui': sensor['eui'],
                                'nwKey': sensor['nwKey'],
                                'shortAddr': sensor['shortAddr'],
                                'bidi': sensor['bidi'],
                                'registered': len(connected_stations) > 0,
                                'registration_info': {
                                    'status': 'registered' if len(connected_stations) > 0 else 'not_registered',
                                    'base_stations': base_station_list,
                                    'total_registrations': len(base_station_list)
                                },
                                'base_stations': base_station_list,
                                'total_registrations': len(base_station_list)
                            }
                        return jsonify(sensor_status)
            except Exception as sync_e:
                logging.debug(f"Sync service not available: {sync_e}")

        # Fallback to file only
        try:
            with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    sensors = json.loads(content)
                else:
                    sensors = []

            # Convert to registration status format
            sensor_status = {}
            for sensor in sensors:
                eui = sensor['eui'].lower()
                sensor_status[eui] = {
                    'eui': sensor['eui'],
                    'nwKey': sensor['nwKey'],
                    'shortAddr': sensor['shortAddr'],
                    'bidi': sensor['bidi'],
                    'registered': False,
                    'registration_info': {},
                    'base_stations': [],
                    'total_registrations': 0
                }
            return jsonify(sensor_status)
        except FileNotFoundError:
            logging.warning(f"Sensor config file not found: {bssci_config.SENSOR_CONFIG_FILE}")
            return jsonify({})
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from sensor config file: {bssci_config.SENSOR_CONFIG_FILE}")
            return jsonify({})
        except Exception as file_e:
            logging.error(f"Failed to read sensor config file: {file_e}")
            return jsonify({})

    except Exception as e:
        logging.error(f"Error getting sensors: {e}")
        return jsonify({'error': 'Failed to load sensors', 'message': str(e)}), 500

@app.route('/api/sensors', methods=['POST'])
def add_sensor():
    data = request.json
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except FileNotFoundError:
        sensors = []
        logging.warning(f"Sensor config file not found: {bssci_config.SENSOR_CONFIG_FILE}")
    except json.JSONDecodeError:
        sensors = []
        logging.error(f"Error decoding JSON from sensor config file: {bssci_config.SENSOR_CONFIG_FILE}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while reading sensor config: {e}")
        sensors = []

    # Check if sensor already exists
    for sensor in sensors:
        if sensor['eui'].lower() == data['eui'].lower():
            # Update existing sensor
            sensor.update(data)
            break
    else:
        # Add new sensor
        sensors.append(data)

    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump(sensors, f, indent=4)
        return jsonify({'success': True, 'message': 'Sensor saved successfully'})
    except Exception as e:
        logging.error(f"Failed to write sensor config file: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/<eui>', methods=['DELETE'])
def delete_sensor(eui):
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except FileNotFoundError:
        sensors = []
        logging.warning(f"Sensor config file not found: {bssci_config.SENSOR_CONFIG_FILE}")
    except json.JSONDecodeError:
        sensors = []
        logging.error(f"Error decoding JSON from sensor config file: {bssci_config.SENSOR_CONFIG_FILE}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while reading sensor config: {e}")
        sensors = []

    sensors = [s for s in sensors if s['eui'].lower() != eui.lower()]

    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump(sensors, f, indent=4)
        return jsonify({'success': True, 'message': 'Sensor deleted successfully'})
    except Exception as e:
        logging.error(f"Failed to write sensor config file: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/clear', methods=['POST'])
def clear_all_sensors():
    """Clear all sensor configurations"""
    try:
        # Clear the file
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump([], f, indent=4)

        # Also clear from TLS server if available
        try:
            from web_main import get_tls_server
            tls_server = get_tls_server()
            if tls_server:
                tls_server.clear_all_sensors()
        except Exception as e:
            logging.warning(f"Could not clear sensors from TLS server: {e}")

        return jsonify({'success': True, 'message': 'All sensors cleared successfully'})
    except Exception as e:
        logging.error(f"Failed to clear all sensors: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/reload', methods=['POST'])
def reload_sensors():
    """Force reload sensor configuration in TLS server"""
    try:
        from web_main import get_tls_server
        tls_server = get_tls_server()
        if tls_server:
            if hasattr(tls_server, 'reload_sensor_config'):
                tls_server.reload_sensor_config()
                return jsonify({'success': True, 'message': 'Sensor configuration reloaded successfully'})
            else:
                return jsonify({'success': False, 'message': 'TLS server does not support reload_sensor_config'})
        else:
            return jsonify({'success': False, 'message': 'TLS server not available'})
    except Exception as e:
        logging.error(f"Error reloading sensors: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/config')
def config():
    config_data = {
        'LISTEN_HOST': bssci_config.LISTEN_HOST,
        'LISTEN_PORT': bssci_config.LISTEN_PORT,
        'MQTT_BROKER': bssci_config.MQTT_BROKER,
        'MQTT_PORT': bssci_config.MQTT_PORT,
        'MQTT_USERNAME': bssci_config.MQTT_USERNAME,
        'MQTT_PASSWORD': bssci_config.MQTT_PASSWORD,
        'BASE_TOPIC': bssci_config.BASE_TOPIC,
        'STATUS_INTERVAL': bssci_config.STATUS_INTERVAL
    }
    return render_template('config.html', config=config_data)

@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.json
    config_content = f'''LISTEN_HOST = "{data['LISTEN_HOST']}"
LISTEN_PORT = {data['LISTEN_PORT']}

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

MQTT_BROKER = "{data['MQTT_BROKER']}"
MQTT_PORT = {data['MQTT_PORT']}
MQTT_USERNAME = "{data['MQTT_USERNAME']}"
MQTT_PASSWORD = "{data['MQTT_PASSWORD']}"
BASE_TOPIC = "{data['BASE_TOPIC']}"

SENSOR_CONFIG_FILE = "endpoints.json"
STATUS_INTERVAL = {data['STATUS_INTERVAL']}  # seconds


'''

    try:
        # Ensure the directory for endpoints.json exists and has correct permissions
        config_dir = os.path.dirname(bssci_config.SENSOR_CONFIG_FILE)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir)
            logging.info(f"Created configuration directory: {config_dir}")

        with open('bssci_config.py', 'w') as f:
            f.write(config_content)

        # Set permissions for endpoints.json (assuming it's in the same directory as bssci_config.py)
        # This is a common place for config files. Adjust if SENSOR_CONFIG_FILE is elsewhere.
        endpoints_path = bssci_config.SENSOR_CONFIG_FILE
        if os.path.exists(endpoints_path):
            # Set read/write permissions for the owner, read for group and others
            # Adjust mode as needed for your specific environment and security requirements
            os.chmod(endpoints_path, 0o644)
            logging.info(f"Set permissions for {endpoints_path} to 0o644")
        else:
             # If endpoints.json doesn't exist yet, the first write will create it.
             # We can set default permissions then, or rely on umask.
             # For now, let's assume it will be created by a subsequent operation.
             pass


        return jsonify({'success': True, 'message': 'Configuration updated successfully. Restart required.'})
    except Exception as e:
        logging.error(f"Failed to update configuration: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/logs')
def logs():
    return render_template('logs.html')

# Helper function to extract timestamp from log lines if they follow a specific format
def extract_timestamp(line):
    try:
        # Example format: 'YYYY-MM-DD HH:MM:SS.ms' or 'YYYY-MM-DD HH:MM:SS'
        # This is a basic attempt and might need refinement based on actual log formats.
        parts = line.split(' ', 3) # Split into at least 4 parts: date, time, logger, message
        if len(parts) >= 2:
            timestamp_str = parts[0] + ' ' + parts[1]
            # Try to parse with milliseconds
            try:
                datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                return timestamp_str
            except ValueError:
                # Try to parse without milliseconds
                try:
                    datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    return timestamp_str
                except ValueError:
                    return None # Not a recognized timestamp format
        return None
    except Exception:
        return None # Return None if any error occurs during parsing

@app.route('/api/logs')
def get_logs():
    """Get recent log entries"""
    try:
        log_files = ['logs/bssci.log', 'logs/bssci_sync.log']
        logs = []

        for log_file in log_files:
            if not os.path.exists(log_file):
                continue

            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()

                # Get the last 50 lines from each file
                recent_lines = lines[-50:] if len(lines) > 50 else lines

                for line in recent_lines:
                    line = line.strip()
                    if line:
                        logs.append({
                            'message': line,
                            'timestamp': extract_timestamp(line),
                            'source': os.path.basename(log_file)
                        })
            except PermissionError:
                logging.warning(f"Permission denied reading {log_file}")
                continue
            except Exception as e:
                logging.error(f"Error reading {log_file}: {e}")
                continue

        # Sort by timestamp if available
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Limit to 100 most recent
        logs = logs[:100]

        if not logs:
            return jsonify({
                'logs': [{'message': 'No log files accessible or logs are empty', 'timestamp': '', 'source': 'system'}],
                'total': 1,
                'message': 'Log files may have permission issues'
            })

        return jsonify({
            'logs': logs,
            'total': len(logs)
        })
    except Exception as e:
        return jsonify({
            'error': f'Failed to read logs: {str(e)}',
            'logs': [{'message': f'Log access error: {str(e)}', 'timestamp': '', 'source': 'error'}],
            'total': 1
        }), 500

def get_bssci_service_status():
    """Get the status of the BSSCI service"""
    try:
        # Try to get async service instances first
        try:
            from web_main import get_tls_server, get_mqtt_client
            tls_server = get_tls_server()
            mqtt_client = get_mqtt_client()
            service_type = "async"
        except Exception as e:
            logging.debug(f"Could not get async service instances: {e}")
            tls_server = None
            mqtt_client = None
            service_type = "unknown"

        # Try to get sync service instances if async not available
        sync_tls_server = None
        sync_mqtt_client = None
        if not tls_server or not mqtt_client:
            try:
                import sync_main
                if hasattr(sync_main, 'tls_server_instance'):
                    sync_tls_server = sync_main.tls_server_instance
                if hasattr(sync_main, 'mqtt_client_instance'):
                    sync_mqtt_client = sync_main.mqtt_client_instance
                if sync_tls_server or sync_mqtt_client:
                    service_type = "sync"
            except Exception as e:
                logging.debug(f"Could not get sync service instances: {e}")
                pass

        # Use whichever service instances we found
        active_tls = tls_server or sync_tls_server
        active_mqtt = mqtt_client or sync_mqtt_client

        # TLS Server Status
        tls_status = {
            'active': active_tls is not None,
            'service_type': service_type,
            'listening_port': bssci_config.LISTEN_PORT if active_tls else None,
            'connected_base_stations': 0,
            'total_sensors': 0,
            'registered_sensors': 0,
            'pending_requests': 0
        }

        if active_tls:
            try:
                if hasattr(active_tls, 'get_base_station_status'):
                    bs_status = active_tls.get_base_station_status()
                    # Use specific keys from the returned status dictionary
                    tls_status['connected_base_stations'] = bs_status.get('connected_count', 0)
                else:
                    # For sync version, count connected base stations directly
                    tls_status['connected_base_stations'] = len(getattr(active_tls, 'connected_base_stations', {}))

                if hasattr(active_tls, 'get_sensor_registration_status'):
                    sensor_status = active_tls.get_sensor_registration_status()
                    tls_status.update({
                        'total_sensors': len(sensor_status),
                        'registered_sensors': len([s for s in sensor_status.values() if s.get('registered', False)])
                    })
                else:
                    # For sync version, use sensor config
                    sensor_config = getattr(active_tls, 'sensor_config', [])
                    tls_status.update({
                        'total_sensors': len(sensor_config),
                        'registered_sensors': len(sensor_config)  # Assume all configured sensors are registered in sync version
                    })

                if hasattr(active_tls, 'pending_attach_requests'):
                    tls_status['pending_requests'] = len(active_tls.pending_attach_requests)
            except Exception as e:
                logging.debug(f"Error getting TLS server details: {e}")

        # MQTT Status - Get actual connection state
        mqtt_connected = False
        mqtt_client_id = None
        if active_mqtt:
            if hasattr(active_mqtt, 'is_connected'):
                mqtt_connected = active_mqtt.is_connected()
            elif hasattr(active_mqtt, '_client') and hasattr(active_mqtt._client, 'is_connected'):
                mqtt_connected = active_mqtt._client.is_connected()
            elif hasattr(active_mqtt, 'connected'):
                mqtt_connected = active_mqtt.connected

            # Try to get client ID
            if hasattr(active_mqtt, '_client_id'):
                mqtt_client_id = active_mqtt._client_id
            elif hasattr(active_mqtt, 'client_id'):
                mqtt_client_id = active_mqtt.client_id

        mqtt_status = {
            'active': active_mqtt is not None,
            'connected': mqtt_connected,
            'broker_host': bssci_config.MQTT_BROKER if active_mqtt else None,
            'broker_port': bssci_config.MQTT_PORT if active_mqtt else None,
            'client_id': mqtt_client_id,
            'username': bssci_config.MQTT_USERNAME if active_mqtt else None
        }

        return {
            'running': tls_status['active'] and mqtt_status['active'],
            'service_type': service_type,
            'tls_server': tls_status,
            'mqtt_broker': mqtt_status,
            'uptime_seconds': int(time.time() - (getattr(get_bssci_service_status, 'start_time', time.time()))),
            'last_updated': time.time()
        }

    except Exception as e:
        logging.error(f"Error getting BSSCI service status: {e}")
        return {
            'running': False,
            'error': str(e),
            'service_type': 'error',
            'tls_server': {'active': False},
            'mqtt_broker': {'active': False}
        }

# Initialize start time for uptime calculation
if not hasattr(get_bssci_service_status, 'start_time'):
    get_bssci_service_status.start_time = time.time()

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    global log_entries
    log_entries = []
    return jsonify({'success': True, 'message': 'Logs cleared successfully'})

@app.route('/api/bssci/status')
def bssci_status():
    return jsonify(get_bssci_service_status())



@app.route('/api/base_stations')
def get_base_stations():
    """Get base station status"""
    try:
        # Try to get from async service first
        try:
            from web_main import get_tls_server
            tls_server = get_tls_server()
            if tls_server and hasattr(tls_server, 'get_base_station_status'):
                status = tls_server.get_base_station_status()
                return jsonify(status)
            elif tls_server and hasattr(tls_server, 'connected_base_stations'): # Fallback for older async versions
                 # Get unique base stations only
                connected_stations = list(set(tls_server.connected_base_stations.values()))
                connecting_stations = list(set(tls_server.connecting_base_stations.values()))
                return jsonify({
                    'connected': connected_stations,
                    'connecting': connecting_stations,
                    'connected_count': len(connected_stations),
                    'connecting_count': len(connecting_stations)
                })
        except Exception as e:
            logging.debug(f"Could not get base station status from async service: {e}")
            pass

        # Try to get from sync service
        try:
            import sync_main
            if hasattr(sync_main, 'tls_server_instance') and sync_main.tls_server_instance:
                if hasattr(sync_main.tls_server_instance, 'get_base_station_status'):
                    status = sync_main.tls_server_instance.get_base_station_status()
                    return jsonify(status)
                elif hasattr(sync_main.tls_server_instance, 'connected_base_stations'): # Fallback for older sync versions
                    connected_stations = list(set(sync_main.tls_server_instance.connected_base_stations.values()))
                    return jsonify({
                        'connected': connected_stations,
                        'connecting': [], # Sync version might not track connecting separately
                        'connected_count': len(connected_stations),
                        'connecting_count': 0
                    })
        except Exception as e:
            logging.debug(f"Could not get base station status from sync service: {e}")
            pass

        # If no services available or they don't provide the status
        logging.warning("No base station status available from any service.")
        return jsonify({
            'connected': [],
            'connecting': [],
            'connected_count': 0,
            'connecting_count': 0,
            'error': 'No base station status information available'
        })

    except Exception as e:
        logging.error(f"Error getting base station status: {e}")
        return jsonify({
            'connected': [],
            'connecting': [],
            'connected_count': 0,
            'connecting_count': 0,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)