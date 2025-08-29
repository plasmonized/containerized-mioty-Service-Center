
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
    except:
        sensors = []
    return render_template('sensors.html', sensors=sensors)

@app.route('/api/sensors', methods=['GET'])
def get_sensors():
    try:
        # Also reload TLS server config to sync
        try:
            from web_main import get_tls_server
            tls_server = get_tls_server()
            if tls_server:
                tls_server.reload_sensor_config()
                # Get registration status
                return jsonify(tls_server.get_sensor_registration_status())
        except:
            pass  # Fallback to file only
        
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
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
                    'registration_info': {}
                }
            return jsonify(sensor_status)
    except:
        return jsonify({})

@app.route('/api/sensors', methods=['POST'])
def add_sensor():
    data = request.json
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except:
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
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/<eui>', methods=['DELETE'])
def delete_sensor(eui):
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except:
        sensors = []
    
    sensors = [s for s in sensors if s['eui'].lower() != eui.lower()]
    
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump(sensors, f, indent=4)
        return jsonify({'success': True, 'message': 'Sensor deleted successfully'})
    except Exception as e:
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
        except:
            pass  # TLS server not available, that's okay
        
        return jsonify({'success': True, 'message': 'All sensors cleared successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/reload', methods=['POST'])
def reload_sensors():
    """Force reload sensor configuration in TLS server"""
    try:
        from web_main import get_tls_server
        tls_server = get_tls_server()
        if tls_server:
            tls_server.reload_sensor_config()
            return jsonify({'success': True, 'message': 'Sensor configuration reloaded successfully'})
        else:
            return jsonify({'success': False, 'message': 'TLS server not available'})
    except Exception as e:
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
        'STATUS_INTERVAL': bssci_config.STATUS_INTERVAL,
        
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
        with open('bssci_config.py', 'w') as f:
            f.write(config_content)
        return jsonify({'success': True, 'message': 'Configuration updated successfully. Restart required.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/logs')
def logs():
    return render_template('logs.html')

@app.route('/api/logs')
def get_logs():
    global log_entries
    
    # Get query parameters for filtering
    level_filter = request.args.get('level', 'all').upper()
    logger_filter = request.args.get('logger', 'all')
    limit = int(request.args.get('limit', 100))
    
    # Filter logs based on parameters
    filtered_logs = log_entries
    
    if level_filter != 'ALL':
        filtered_logs = [log for log in filtered_logs if log['level'] == level_filter]
    
    if logger_filter != 'all':
        filtered_logs = [log for log in filtered_logs if logger_filter.lower() in log['logger'].lower()]
    
    # Return the most recent logs (up to limit)
    recent_logs = filtered_logs[-limit:] if len(filtered_logs) > limit else filtered_logs
    
    return jsonify({
        'logs': recent_logs,
        'total_logs': len(log_entries),
        'filtered_logs': len(filtered_logs),
        'bssci_status': get_bssci_service_status()
    })

def get_bssci_service_status():
    """Get the status of the BSSCI service"""
    try:
        from web_main import get_tls_server, get_mqtt_client
        
        # TLS Server Status
        tls_server = get_tls_server()
        tls_status = {
            'active': tls_server is not None,
            'listening_port': bssci_config.LISTEN_PORT if tls_server else None,
            'connected_base_stations': 0,
            'total_sensors': 0,
            'registered_sensors': 0,
            'pending_requests': 0
        }
        
        if tls_server:
            bs_status = tls_server.get_base_station_status()
            sensor_status = tls_server.get_sensor_registration_status()
            
            tls_status.update({
                'connected_base_stations': bs_status['total_connected'],
                'total_sensors': len(sensor_status),
                'registered_sensors': len([s for s in sensor_status.values() if s['registered']]),
                'pending_requests': len(tls_server.pending_attach_requests)
            })
        
        # MQTT Status
        mqtt_client = get_mqtt_client()
        mqtt_status = {
            'active': mqtt_client is not None,
            'broker_host': bssci_config.MQTT_BROKER,
            'broker_port': bssci_config.MQTT_PORT,
            'username': bssci_config.MQTT_USERNAME,
            'base_topic': bssci_config.BASE_TOPIC,
            'connected': False,
            'out_queue_size': 0,
            'in_queue_size': 0
        }
        
        if mqtt_client:
            mqtt_status.update({
                'connected': True,  # Assume connected if client exists
                'out_queue_size': mqtt_client.mqtt_out_queue.qsize() if hasattr(mqtt_client, 'mqtt_out_queue') else 0,
                'in_queue_size': mqtt_client.mqtt_in_queue.qsize() if hasattr(mqtt_client, 'mqtt_in_queue') else 0
            })
        
        return {
            'running': tls_status['active'] and mqtt_status['active'],
            'tls_server': tls_status,
            'mqtt_broker': mqtt_status,
            'uptime_seconds': int(time.time() - (getattr(get_bssci_service_status, 'start_time', time.time()))),
            'last_updated': time.time()
        }
        
    except Exception as e:
        return {
            'running': False,
            'error': str(e),
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
    """Get status of connected base stations"""
    try:
        # Import here to avoid circular import
        from web_main import get_tls_server, get_mqtt_client
        tls_server = get_tls_server()
        
        if tls_server:
            status = tls_server.get_base_station_status()
            
            # Add additional status info
            status['last_updated'] = time.time()
            status['tls_server_running'] = True
            
            # Add MQTT status if available
            try:
                mqtt_client = get_mqtt_client()
                if mqtt_client:
                    status['mqtt_status'] = 'connected'
                else:
                    status['mqtt_status'] = 'disconnected'
            except:
                status['mqtt_status'] = 'unknown'
            
            return jsonify(status)
        else:
            return jsonify({
                "connected": [],
                "connecting": [],
                "total_connected": 0,
                "total_connecting": 0,
                "tls_server_running": False,
                "mqtt_status": "unknown",
                "error": "TLS server not initialized"
            })
    except Exception as e:
        return jsonify({
            "connected": [],
            "connecting": [],
            "total_connected": 0,
            "total_connecting": 0,
            "tls_server_running": False,
            "mqtt_status": "unknown",
            "error": str(e)
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
