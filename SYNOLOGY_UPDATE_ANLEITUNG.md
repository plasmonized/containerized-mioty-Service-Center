# 🔧 SYNOLOGY DOCKER UPDATE ANLEITUNG

## Problem behoben: "Permission denied: backup_20250909_155221"

### ✅ LÖSUNG 1: Direkte Befehle (SSH)

```bash
# 1. In Container-Verzeichnis wechseln
cd /path/to/your/bssci-service-center

# 2. Berechtigungen korrigieren
sudo chown -R 1000:1000 . 

# 3. Backup-Verzeichnis erstellen
sudo mkdir -p backup_$(date +%Y%m%d_%H%M%S)
sudo chown 1000:1000 backup_*

# 4. Docker Update
docker-compose down
docker-compose pull  
docker-compose up -d --force-recreate
```

### ✅ LÖSUNG 2: Update-Script verwenden

```bash
# Script ausführbar machen
chmod +x synology_update.sh

# Update durchführen
./synology_update.sh
```

### ✅ LÖSUNG 3: Synology UI

1. **Container Manager öffnen**
2. **Container stoppen**
3. **Terminal öffnen → SSH aktivieren**
4. **SSH einloggen und Befehle ausführen:**
   ```bash
   sudo chown -R 1000:1000 /volume1/docker/bssci-service-center/
   ```
5. **Container über UI neu starten**

## ⚙️ Permanente Fixes in docker-compose.yml

Die folgenden Änderungen wurden bereits vorgenommen:

```yaml
services:
  bssci-service-center:
    # Synology-spezifische Berechtigungskorrekturen
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    privileged: false
    cap_drop:
      - ALL
    cap_add:
      - CHOWN          # Für Backup-Erstellung
      - DAC_OVERRIDE   # Für Dateizugriff
```

## 🎯 Teste das Update

Nach dem Update prüfen:

```bash
# Container Status
docker-compose ps

# Logs prüfen  
docker-compose logs --tail=20

# Web Interface testen
curl http://localhost:5056/api/service/status
```

Das System läuft jetzt stabil und ist bereit für Updates!