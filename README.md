# mioty BSSCI Service Center

Eine umfassende Implementierung des mioty Base Station Service Center Interface (BSSCI) Protokolls v1.0.0.0 mit webbasierter Verwaltungsoberfläche und MQTT-Integration.

## Danksagung

Dieses Projekt basiert auf der ursprünglichen Codebasis von [IronMate/mioty_BSSCI](https://github.com/IronMate/mioty_BSSCI). Vielen Dank an **Ironmate** für die Bereitstellung der grundlegenden BSSCI-Implementierung, die als Fundament für diese erweiterte Version dient.

## Inhaltsverzeichnis

- [Überblick](#überblick)
- [BSSCI Protokoll Verständnis](#bssci-protokoll-verständnis)
- [Architektur & Datenfluss](#architektur--datenfluss)
- [Installation & Setup](#installation--setup)
- [Konfiguration](#konfiguration)
- [Verwendung](#verwendung)
- [Web Interface](#web-interface)
- [MQTT Integration](#mqtt-integration)
- [Sensoren-Management](#sensoren-management)
- [Auto-Detach Funktionalität](#auto-detach-funktionalität)
- [MQTT Kommando-Interface](#mqtt-kommando-interface)
- [Docker Deployment](#docker-deployment)
- [API Dokumentation](#api-dokumentation)
- [Fehlerbehebung](#fehlerbehebung)
- [Erweiterte Features](#erweiterte-features)
- [Lizenz](#lizenz)
- [Beitragen](#beitragen)
- [Projekt unterstützen](#projekt-unterstützen)

## Überblick

Dieses Service Center fungiert als Brücke zwischen mioty Basisstationen und MQTT-Brokern und bietet:

- **TLS-gesicherte Kommunikation** mit Basisstationen nach BSSCI v1.0.0.0
- **Echtzeit-Sensordatenverarbeitung** mit Deduplizierung
- **MQTT-Veröffentlichung** von Sensordaten und Basisstationsstatus  
- **Webbasierte Verwaltungsoberfläche** für Monitoring und Konfiguration
- **Dynamische Sensorregistrierung** über MQTT
- **Multi-Basisstations-Unterstützung** mit intelligentem Routing
- **Automatisches Sensor-Detachment** nach Inaktivität
- **MQTT-Kommandoschnittstelle** für Sensor-Management
- **Docker-Container Support** mit Synology NAS Kompatibilität

## BSSCI Protokoll Verständnis

### Was ist BSSCI?

Das Base Station Service Center Interface (BSSCI) ist ein standardisiertes Protokoll für die Kommunikation zwischen mioty Basisstationen und Service Centern. Es definiert:

1. **Verbindungsmanagement**: Sichere TLS-Handshake und Authentifizierung
2. **Sensorregistrierung**: Dynamisches Anhängen/Abhängen von Sensoren
3. **Datenaustausch**: Uplink-Datenweiterleitung und Downlink-Nachrichtenrouting
4. **Statusüberwachung**: Basisstationsgesundheit und Leistungsmetriken
5. **Nachrichtenbestätigung**: Zuverlässige Zustellungsbestätigung

### Protokollfluss

```
[Sensor] --mioty--> [Basisstation] --BSSCI/TLS--> [Service Center] --MQTT--> [Ihre Anwendung]
```

#### Wichtige BSSCI Nachrichtentypen

- **con/conCmp**: Verbindungsaufbau
- **attPrpReq/attPrpRsp**: Sensor-Anhängungsanfragen/-antworten
- **ulData/ulDataCmp**: Uplink-Datennachrichten
- **statusReq/statusRsp**: Basisstationsstatus-Abfragen
- **ping/pingCmp**: Keep-Alive-Nachrichten
- **detachReq/detachRsp**: Sensor-Abkopplungsanfragen/-antworten

### Nachrichtenstruktur

Alle BSSCI-Nachrichten verwenden MessagePack-Kodierung mit dieser Struktur:
```
[8-Byte Identifikator "MIOTYB01"] + [4-Byte Länge] + [MessagePack Nutzlast]
```

## Architektur & Datenfluss

### Systemkomponenten

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Basisstation  │◄──►│  Service Center  │◄──►│  MQTT Broker    │
│                 │TLS │                  │    │                 │
│  - Sensor Mgmt  │    │ - TLS Server     │    │ - Data Topics   │
│  - Data Collect │    │ - MQTT Client    │    │ - Config Topics │
│  - Status Rep.  │    │ - Web Interface  │    │ - Command Topics│
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                         ┌──────▼──────┐
                         │ Web Browser │
                         │ Management  │
                         └─────────────┘
```

## Installation & Setup

### Voraussetzungen

- Python 3.8+
- TLS-Zertifikate für Basisstations-Authentifizierung
- MQTT-Broker-Zugang
- mioty Basisstationen konfiguriert für BSSCI

### Schnellstart

1. **Klonen und Setup**:
   ```bash
   git clone <repository>
   cd mioty_BSSCI
   pip install -r requirements.txt
   ```

2. **Zertifikate generieren**:
   ```bash
   # CA-Zertifikat erstellen
   openssl genrsa -out certs/ca_key.pem 4096
   openssl req -x509 -new -key certs/ca_key.pem -sha256 -days 3650 -out certs/ca_cert.pem

   # Service Center Zertifikat erstellen
   openssl genrsa -out certs/service_center_key.pem 2048
   openssl req -new -key certs/service_center_key.pem -out certs/service_center.csr
   openssl x509 -req -in certs/service_center.csr \
     -CA certs/ca_cert.pem -CAkey certs/ca_key.pem -CAcreateserial \
     -out certs/service_center_cert.pem -days 825 -sha256
   ```

3. **Einstellungen konfigurieren**:
   Bearbeiten Sie `bssci_config.py` mit Ihren MQTT-Broker-Details und Zertifikatspfaden.

4. **Service starten**:
   ```bash
   python web_main.py
   ```

5. **Web Interface aufrufen**:
   Öffnen Sie `http://localhost:5000` für die Verwaltungsoberfläche.

## Konfiguration

### Hauptkonfiguration (`bssci_config.py`)

```python
# TLS Server Einstellungen
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 16018

# Zertifikatspfade
CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem" 
CA_FILE = "certs/ca_cert.pem"

# MQTT Broker Einstellungen
MQTT_BROKER = "your-broker.com"
MQTT_PORT = 1883
MQTT_USERNAME = "your-username"
MQTT_PASSWORD = "your-password"
BASE_TOPIC = "bssci/"

# Betriebseinstellungen
STATUS_INTERVAL = 30  # Basisstationsstatus-Abfrageintervall (Sekunden)
DEDUPLICATION_DELAY = 2  # Nachrichten-Deduplizierungsfenster (Sekunden)
AUTO_DETACH_HOURS = 48  # Auto-Detach nach Stunden ohne Aktivität
```

### Sensorkonfiguration (`endpoints.json`)

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

## Verwendung

### Service starten

#### Mit Web Interface (Empfohlen)
```bash
python web_main.py
```
- Startet sowohl BSSCI-Service als auch Web-Verwaltungsoberfläche
- Web UI verfügbar unter `http://localhost:5000`
- Integrierte Protokollierung und Überwachung

#### Nur Service
```bash
python main.py  
```
- Startet nur BSSCI-Service ohne Web-Interface
- Nur Konsolen-Protokollierung

### Basisstations-Konfiguration

Konfigurieren Sie Ihre mioty Basisstationen mit:
- **Service Center IP**: Ihre Server-IP-Adresse
- **Port**: 16018 (oder konfigurierter Port)
- **TLS-Zertifikat**: Installieren Sie generiertes CA-Zertifikat
- **Client-Zertifikat**: Konfigurieren Sie Basisstations-Client-Zertifikat

## Web Interface

### Dashboard-Features

- **Service-Status**: Echtzeit-Service-Gesundheitsüberwachung
- **Basisstationen**: Status und Statistiken verbundener Basisstationen
- **Sensoren**: Sensorregistrierungsstatus und Konfiguration
- **Protokolle**: Echtzeit-Systemprotokolle mit Filterung
- **Konfiguration**: Sensorverwaltung und Massenoperationen

### Sensoren-Management im Web Interface

#### Einzelne Sensoren verwalten

1. **Sensor hinzufügen**:
   - Navigieren Sie zum "Sensoren" Tab
   - Klicken Sie "Sensor hinzufügen"
   - Geben Sie EUI, Netzwerkschlüssel und Short Address ein
   - Klicken Sie "Speichern"

2. **Sensor löschen (mit automatischem Detach)**:
   - Finden Sie den Sensor in der Liste
   - Klicken Sie den "Löschen" Button
   - **AUTOMATISCH**: Detach-Request wird an alle verbundenen Basisstationen gesendet
   - Sensor wird aus der Konfiguration entfernt

3. **Alle Sensoren löschen (Bulk Detach)**:
   - Klicken Sie "Alle löschen" in der Sensorliste
   - **AUTOMATISCH**: Bulk-Detach-Requests werden an alle Basisstationen gesendet
   - Alle Sensoren werden aus der Konfiguration entfernt

#### Manuelle Detach-Buttons

Das Web Interface bietet dedizierte Detach-Buttons für präzise Kontrolle:

- **Einzelner Sensor Detach**: Button neben jedem Sensor für manuelles Detachment
- **Bulk Detach**: Button zum Detachen aller registrierten Sensoren
- **Status-Anzeige**: Zeigt Registrierungsstatus und letzten Detach-Zeitpunkt

## Auto-Detach Funktionalität

### Automatisches Sensor-Detachment

Das System implementiert intelligentes Auto-Detach für inaktive Sensoren:

#### Konfiguration
```python
# In bssci_config.py
AUTO_DETACH_HOURS = 48  # Sensoren nach 48h Inaktivität detachen
```

#### Funktionsweise

1. **Überwachung**: System prüft alle 30 Minuten die Sensoraktivität
2. **Inaktivitätserkennung**: Sensoren ohne Daten für 48+ Stunden werden identifiziert
3. **Automatisches Detachment**: Detach-Requests werden automatisch gesendet
4. **Protokollierung**: Alle Auto-Detach-Aktionen werden protokolliert
5. **Status-Update**: Sensoren werden als "auto_detached" markiert

#### Protokoll-Beispiel
```
🕐 AUTO-DETACH: Found 2 inactive sensors
   Auto-detaching inactive sensor: FCA84A0300001234
   Auto-detaching inactive sensor: FCA84A0300005678
✅ AUTO-DETACH: Detach request sent for FCA84A0300001234
✅ AUTO-DETACH: Detach request sent for FCA84A0300005678
```

## MQTT Integration

### Topic-Struktur

#### Sensordaten-Topics
```
bssci/ep/{sensor_eui}/ul
```

**Nutzlast-Struktur:**
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

#### Basisstationsstatus-Topics
```
bssci/bs/{basestation_eui}
```

**Nutzlast-Struktur:**
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

#### Konfigurations-Topics
```
bssci/ep/{sensor_eui}/config
```

**Nutzlast-Struktur:**
```json
{
  "nwKey": "0011223344556677889AABBCCDDEEFF00",
  "shortAddr": "1234", 
  "bidi": false
}
```

## MQTT Kommando-Interface

### Kommando-Topics

Das System bietet ein vollständiges MQTT-Kommando-Interface für Sensor-Management:

#### Kommando-Topic
```
bssci/ep/{sensor_eui}/cmd
```

#### Verfügbare Kommandos

##### 1. Sensor Detach
```json
{
  "command": "detach"
}
```

##### 2. Sensor Status
```json
{
  "command": "status"
}
```

##### 3. Sensor Re-attach
```json
{
  "command": "attach"
}
```

#### Kommando-Antwort-Topic
```
bssci/ep/{sensor_eui}/cmd/response
```

**Antwort-Nutzlast:**
```json
{
  "command": "detach",
  "status": "success",
  "sensor_eui": "0123456789ABCDEF",
  "timestamp": "2024-01-20 14:30:25.123",
  "message": "Detach request sent to 2 base stations"
}
```

### Praktische MQTT-Kommando-Beispiele

#### Sensor über MQTT detachen
```bash
# Mit mosquitto_pub
mosquitto_pub -h your-broker.com -t "bssci/ep/fca84a0300001234/cmd" \
  -m '{"command": "detach"}'

# Antwort abonnieren
mosquitto_sub -h your-broker.com -t "bssci/ep/fca84a0300001234/cmd/response"
```

#### Python-Beispiel für MQTT-Kommandos
```python
import paho.mqtt.client as mqtt
import json

def send_detach_command(client, sensor_eui):
    command = {"command": "detach"}
    topic = f"bssci/ep/{sensor_eui}/cmd"
    client.publish(topic, json.dumps(command))

def on_command_response(client, userdata, msg):
    response = json.loads(msg.payload.decode())
    print(f"Command response: {response}")

# Setup
client = mqtt.Client()
client.on_message = on_command_response
client.connect("your-broker.com", 1883, 60)
client.subscribe("bssci/ep/+/cmd/response")

# Sensor detachen
send_detach_command(client, "fca84a0300001234")
```

## Docker Deployment

### Schnellstart mit Docker

#### Entwicklungsumgebung
```bash
# Service bauen und starten
docker-compose up --build

# Im Hintergrund ausführen
docker-compose up -d --build
```

#### Produktionsumgebung
```bash
# Produktionskonfiguration verwenden
docker-compose -f docker-compose.prod.yml up -d --build
```

### Synology NAS Deployment

Spezieller Support für Synology NAS-Systeme:

```bash
# Synology-spezifische Konfiguration
docker-compose -f docker-compose.synology.yml up -d --build
```

#### Synology-spezifische Features
- **Berechtigungsmanagement**: Automatische Korrektur von Docker-Volume-Berechtigungen
- **SELinux-Kompatibilität**: Volume-Mounts mit `:z` Flag für SELinux-Systeme
- **Startup-Skripte**: Spezielle Skripte für Synology Docker-Umgebung

### Docker-Volumes

Die folgenden Verzeichnisse sind als Volumes gemountet:

- `./certs` - SSL-Zertifikate (nur-lesen)
- `./endpoints.json` - Sensorkonfiguration (lesen/schreiben)
- `./bssci_config.py` - Service-Konfiguration (lesen/schreiben)
- `./logs` - Anwendungsprotokolle (schreiben)

### Container-Management

```bash
# Protokolle anzeigen
docker-compose logs -f

# Service stoppen
docker-compose down

# Service neu starten
docker-compose restart

# Aktualisieren und neu starten
docker-compose pull && docker-compose up -d

# Alles entfernen (einschließlich Volumes)
docker-compose down -v
```

## API Dokumentation

### Web API Endpunkte

#### Service-Status
```
GET /api/bssci/status
```
Gibt Service-Gesundheit und Verbindungsstatus zurück.

#### Basisstationen
```
GET /api/base-stations
```
Gibt Liste verbundener Basisstationen mit Status zurück.

#### Sensoren
```
GET /api/sensors
GET /api/sensors/{eui}
POST /api/sensors (Massenkonfiguration)
DELETE /api/sensors/clear (Alle löschen mit Bulk-Detach)
DELETE /api/sensors/unregister/{sensor_eui} (Einzelnen Sensor detachen)
POST /api/sensors/unregister-all (Alle Sensoren detachen)
```

#### Neue Sensor-Management Endpunkte

##### Sensor unregistrieren (detachen)
```bash
# Einzelnen Sensor detachen
curl -X DELETE http://localhost:5000/api/sensors/unregister/fca84a0300001234

# Alle Sensoren detachen
curl -X POST http://localhost:5000/api/sensors/unregister-all
```

#### Protokolle
```
GET /api/logs?level=INFO&lines=100
```
Gibt aktuelle Protokolleinträge mit Filterung zurück.

## Fehlerbehebung

### Häufige Probleme

#### Basisstation verbindet sich nicht

1. **Zertifikatsprobleme**:
   - CA-Zertifikat auf Basisstation installiert überprüfen
   - Zertifikatsgültigkeitsdaten prüfen
   - Sicherstellen, dass Zertifikat-CN mit Konfiguration übereinstimmt

2. **Netzwerkprobleme**:
   - Firewall-Regeln für Port 16018 prüfen
   - Überprüfen, ob Basisstation Service Center IP erreichen kann
   - TLS-Verbindung mit openssl testen

#### Sensoren registrieren sich nicht

1. **Konfigurationsprobleme**:
   - EUI-Format überprüfen (16 Hex-Zeichen)
   - Netzwerkschlüssellänge prüfen (32 Hex-Zeichen)
   - Short Address Format validieren (4 Hex-Zeichen)

2. **Auto-Detach Probleme**:
   - Prüfen Sie die AUTO_DETACH_HOURS Konfiguration
   - Überwachen Sie die Auto-Detach-Protokolle
   - Verifizieren Sie Sensor-Aktivitätszeitstempel

#### MQTT-Probleme

1. **Verbindungsprobleme**:
   - Broker-Anmeldedaten überprüfen
   - Netzwerkverbindung zum Broker prüfen
   - Broker-Authentifizierungseinstellungen überprüfen

2. **Kommando-Interface Probleme**:
   - Topic-Berechtigungen prüfen
   - Nachrichtenformat verifizieren
   - Broker-Nachrichtenlimits überprüfen

### Debugging-Tools

#### Protokollanalyse
```bash
# Protokolle nach Level filtern
grep "ERROR" logs/bssci.log

# Echtzeit-Protokolle überwachen
tail -f logs/bssci.log

# Nach spezifischem Sensor suchen
grep "fca84a0300001234" logs/bssci.log

# Auto-Detach-Ereignisse
grep "AUTO-DETACH" logs/bssci.log
```

#### MQTT-Tests
```bash
# Alle Topics abonnieren
mosquitto_sub -h broker-host -t "bssci/#" -v

# Kommando-Antworten überwachen
mosquitto_sub -h broker-host -t "bssci/ep/+/cmd/response"

# Detach-Kommando senden
mosquitto_pub -h broker-host -t "bssci/ep/fca84a0300001234/cmd" \
  -m '{"command":"detach"}'
```

## Erweiterte Features

### Nachrichten-Deduplizierung

Das Service Center implementiert ausgeklügelte Deduplizierung:

- **Multi-Basisstations-Unterstützung**: Behandelt dieselbe Nachricht von mehreren Basisstationen
- **Signalqualitätsoptimierung**: Wählt besten Signalpfad bas
on SNR
- **Konfigurierbare Verzögerung**: Einstellbares Deduplizierungsfenster
- **Statistik-Verfolgung**: Überwacht Duplikatraten und Effizienz

### Bevorzugter Downlink-Pfad

Verfolgt automatisch beste Basisstation für jeden Sensor:

- **Signalqualitäts-Verfolgung**: Überwacht SNR für jedes Sensor-Basisstations-Paar
- **Dynamische Pfadauswahl**: Aktualisiert bevorzugten Pfad basierend auf Signalqualität
- **Persistente Speicherung**: Speichert bevorzugte Pfade in Konfiguration

### Hochverfügbarkeits-Features

- **Automatische Wiederverbindung**: Behandelt Basisstations-Verbindungsabbrüche elegant  
- **Warteschlangen-Persistenz**: Behält Nachrichtenwarteschlangen während Netzwerkproblemen bei
- **Gesundheitsüberwachung**: Kontinuierliche Service-Gesundheitsprüfungen
- **Graceful Degradation**: Fortsetzung des Betriebs mit partieller Verbindung

### Leistungsoptimierung

- **Asynchrone Verarbeitung**: Nicht-blockierende Nachrichtenbehandlung
- **Verbindungspooling**: Effizientes Basisstations-Verbindungsmanagement
- **Speicherverwaltung**: Automatische Bereinigung alter Daten
- **Batch-Operationen**: Effiziente Massen-Sensorkonfiguration

---

## 📄 Lizenz

Dieses Projekt steht unter einer **Nicht-kommerziellen Lizenz**. 

### Was Sie TUN können:
- ✅ Für persönliche Projekte verwenden
- ✅ Für Bildungszwecke verwenden  
- ✅ Für Forschung verwenden
- ✅ Modifizieren und verteilen (nicht-kommerziell)
- ✅ Den Code studieren

### Was Sie NICHT tun können:
- ❌ In kommerziellen Produkten oder Dienstleistungen verwenden
- ❌ Die Software oder Derivate verkaufen
- ❌ Zur Umsatzgenerierung verwenden

### Kommerzielle Nutzung
Für kommerzielle Lizenzierung, Unternehmensunterstützung oder benutzerdefinierte Entwicklung öffnen Sie bitte ein Issue auf GitHub oder kontaktieren Sie uns über das Repository.

**Vollständige Lizenzbedingungen**: Siehe [LICENSE](LICENSE) Datei

---

## 🤝 Beitragen

Beiträge sind willkommen! Durch das Beitragen stimmen Sie zu, dass Ihre Beiträge unter denselben nicht-kommerziellen Bedingungen lizenziert werden.

1. Repository forken
2. Feature-Branch erstellen
3. Ihre Änderungen vornehmen
4. Gründlich testen
5. Pull Request einreichen

---

## ⭐ Projekt unterstützen

Wenn Ihnen dieses Projekt hilft, bitte:
- Geben Sie ihm einen Stern auf GitHub ⭐
- Teilen Sie es mit anderen, die es nützlich finden könnten
- Melden Sie Bugs und schlagen Sie Verbesserungen vor
- Erwägen Sie, Code oder Dokumentation beizutragen

---

Für Fragen oder Support überprüfen Sie bitte den Fehlerbehebungsbereich oder erstellen Sie ein Issue im Repository.