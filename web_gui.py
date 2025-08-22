
import asyncio
import json
import logging
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
import bssci_config
from TLSServer import TLSServer
from mqtt_interface import MQTTClient
import os

app = Flask(__name__)
app.secret_key = 'bssci_secret_key_2024'

# Global variables to store application state
tls_server = None
mqtt_client = None
mqtt_in_queue = None
mqtt_out_queue = None
log_messages = []
max_log_messages = 1000

class LogHandler(logging.Handler):
    def emit(self, record):
        global log_messages
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.name
        }
        log_messages.append(log_entry)
        if len(log_messages) > max_log_messages:
            log_messages.pop(0)

# Setup logging handler
log_handler = LogHandler()
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.INFO)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def status():
    connected_bs = []
    if tls_server and hasattr(tls_server, 'connected_base_stations'):
        for writer, bs_eui in tls_server.connected_base_stations.items():
            addr = writer.get_extra_info('peername') if writer else 'Unknown'
            connected_bs.append({
                'eui': bs_eui,
                'address': str(addr)
            })
    
    return render_template('index.html', base_stations=connected_bs)

@app.route('/api/status')
def api_status():
    connected_bs = []
    if tls_server and hasattr(tls_server, 'connected_base_stations'):
        for writer, bs_eui in tls_server.connected_base_stations.items():
            addr = writer.get_extra_info('peername') if writer else 'Unknown'
            connected_bs.append({
                'eui': bs_eui,
                'address': str(addr)
            })
    
    return jsonify({
        'connected_count': len(connected_bs),
        'base_stations': connected_bs,
        'mqtt_connected': True if mqtt_client else False
    })

@app.route('/sensors')
def sensors():
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except:
        sensors = []
    
    return render_template('sensors.html', sensors=sensors)

@app.route('/api/sensors')
def api_sensors():
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except:
        sensors = []
    
    return jsonify(sensors)

@app.route('/api/sensors/add', methods=['POST'])
def add_sensor():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Validate input
        required_fields = ['eui', 'nwKey', 'shortAddr']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Field {field} is required'}), 400
        
        # Clean and validate data
        eui = data['eui'].strip().upper()
        nw_key = data['nwKey'].strip().upper()
        short_addr = data['shortAddr'].strip().upper()
        
        # Validate lengths and format
        if len(eui) != 16:
            return jsonify({'error': 'EUI must be exactly 16 characters long'}), 400
        if len(nw_key) != 32:
            return jsonify({'error': 'Network Key must be exactly 32 characters long'}), 400
        if len(short_addr) != 4:
            return jsonify({'error': 'Short Address must be exactly 4 characters long'}), 400
        
        # Validate hex format
        try:
            int(eui, 16)
            int(nw_key, 16) 
            int(short_addr, 16)
        except ValueError:
            return jsonify({'error': 'All fields must contain only hexadecimal characters (0-9, A-F)'}), 400
    
    try:
        # Load existing sensors
        try:
            with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
                sensors = json.load(f)
        except:
            sensors = []
        
        # Check if sensor already exists
        for sensor in sensors:
            if sensor['eui'].lower() == data['eui'].lower():
                return jsonify({'error': 'Sensor with this EUI already exists'}), 400
        
        # Add new sensor
        new_sensor = {
            'eui': eui,
            'nwKey': nw_key,
            'shortAddr': short_addr,
            'bidi': data.get('bidi', False)
        }
        
        sensors.append(new_sensor)
        
        # Save to file
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump(sensors, f, indent=4)
        
        # Update TLS server config
        if tls_server:
            tls_server.sensor_config = sensors
            # Note: TLS server will automatically reload config on next connection
        
        logging.info(f"Sensor added successfully: {eui}")
        return jsonify({'success': True, 'message': 'Sensor erfolgreich hinzugefügt'})
    
    except Exception as e:
        logging.error(f"Error adding sensor: {e}")
        return jsonify({'error': f'Fehler beim Hinzufügen des Sensors: {str(e)}'}), 500

@app.route('/api/sensors/delete/<eui>', methods=['DELETE'])
def delete_sensor(eui):
    try:
        # Load existing sensors
        try:
            with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
                sensors = json.load(f)
        except:
            sensors = []
        
        # Remove sensor
        sensors = [s for s in sensors if s['eui'].lower() != eui.lower()]
        
        # Save to file
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump(sensors, f, indent=4)
        
        # Update TLS server config
        if tls_server:
            tls_server.sensor_config = sensors
        
        return jsonify({'success': True, 'message': 'Sensor deleted successfully'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/mqtt')
def mqtt():
    config = {
        'broker': bssci_config.MQTT_BROKER,
        'port': bssci_config.MQTT_PORT,
        'username': bssci_config.MQTT_USERNAME,
        'password': bssci_config.MQTT_PASSWORD,
        'base_topic': bssci_config.BASE_TOPIC
    }
    return render_template('mqtt.html', config=config)

@app.route('/api/mqtt/update', methods=['POST'])
def update_mqtt():
    data = request.json
    
    try:
        # Update config file
        config_content = f"""LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16017  # Internal container port

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

MQTT_BROKER = "{data['broker']}"
MQTT_PORT = {data['port']}
MQTT_USERNAME = "{data['username']}"
MQTT_PASSWORD = "{data['password']}"
BASE_TOPIC = "{data['base_topic']}"

SENSOR_CONFIG_FILE = "endpoints.json"
STATUS_INTERVAL = 60  # seconds
"""
        
        with open('bssci_config.py', 'w') as f:
            f.write(config_content)
        
        return jsonify({'success': True, 'message': 'MQTT configuration updated successfully. Please restart the application.'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logs')
def logs():
    return render_template('logs.html')

@app.route('/api/logs')
def api_logs():
    return jsonify(log_messages[-100:])  # Return last 100 log entries

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    global log_messages
    log_messages = []
    return jsonify({'success': True, 'message': 'Logs cleared successfully'})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

def start_web_gui(tls_srv, mqtt_cli, mqtt_in_q, mqtt_out_q):
    global tls_server, mqtt_client, mqtt_in_queue, mqtt_out_queue
    tls_server = tls_srv
    mqtt_client = mqtt_cli
    mqtt_in_queue = mqtt_in_q
    mqtt_out_queue = mqtt_out_q
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
