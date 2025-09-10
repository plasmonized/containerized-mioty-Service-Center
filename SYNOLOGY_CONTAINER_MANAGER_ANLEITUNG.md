# Synology Container Manager - Git Version Installation

## 🏠 Installation über Container Manager GUI

### Schritt 1: Dateien vorbereiten

1. **Docker Compose ersetzen:**
   - Lösche die alte `docker-compose.yml`
   - Benenne `docker-compose.synology-git.yml` um zu `docker-compose.yml`

2. **Docker Entrypoint ersetzen:**
   - Lösche die alte `docker-entrypoint.sh` 
   - Benenne `docker-entrypoint-synology-git.sh` um zu `docker-entrypoint.sh`

3. **Umgebungsvariablen hinzufügen:**
   Füge diese Zeilen zu deiner `.env` Datei hinzu:
   ```
   # Git Configuration for Synology
   GIT_AUTHOR_NAME=plasmonized
   GIT_AUTHOR_EMAIL=58008926+plasmonized@users.noreply.github.com
   GIT_COMMITTER_NAME=plasmonized
   GIT_COMMITTER_EMAIL=58008926+plasmonized@users.noreply.github.com
   ```

### Schritt 2: Container Manager

1. **Öffne Container Manager**
2. **Gehe zu "Projekt"**
3. **Wähle dein BSSCI Projekt**
4. **Klicke "Stoppen"** (falls läuft)
5. **Klicke "Löschen"** (Container, nicht Projekt)
6. **Klicke "Erstellen"**
7. **Warte bis Build abgeschlossen**
8. **Klicke "Starten"**

### Schritt 3: Überprüfung

1. **Container Status prüfen:**
   - Container sollte "Ausgeführt" zeigen
   - Keine Fehler in den Logs

2. **Git-Test im Container:**
   - Gehe zu Container → "Details" → "Terminal"
   - Führe aus: `git --version`
   - Führe aus: `git status`

3. **Web-UI testen:**
   - Öffne: `http://[SYNOLOGY-IP]:5056`

## ✅ Fertig!

Dein Container läuft jetzt mit Git-Support und alle Backup/Update-Probleme sind behoben.