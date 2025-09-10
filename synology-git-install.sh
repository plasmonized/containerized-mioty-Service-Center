#!/bin/bash
# Synology Git Installation Script
# Komplette Installation der Git-Version auf Synology

echo "🏠 SYNOLOGY GIT-VERSION INSTALLATION"
echo "====================================="

# Prüfe ob wir auf Synology laufen
if [ ! -d "/volume1" ] && [ ! -d "/volume2" ]; then
    echo "⚠️  Warning: Dieses Script ist für Synology optimiert"
    echo "   Wenn du nicht auf Synology bist, verwende docker-git-update.sh"
    read -p "Trotzdem fortfahren? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Stoppe bestehenden Container
echo "🛑 Stoppe bestehenden Container..."
docker-compose down 2>/dev/null || true

# Backup der aktuellen Konfiguration
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
echo "📦 Erstelle Backup: $BACKUP_DIR"
mkdir -p $BACKUP_DIR
cp docker-compose.yml $BACKUP_DIR/ 2>/dev/null || true
cp docker-compose.synology.yml $BACKUP_DIR/ 2>/dev/null || true
cp docker-entrypoint.sh $BACKUP_DIR/ 2>/dev/null || true

# Setze korrekte Permissions
echo "🔧 Setze Synology-Permissions..."
sudo chown -R 1000:1000 . 2>/dev/null || chown -R 1000:1000 . 2>/dev/null || true

# Bereinige Git-Locks
echo "🔧 Bereinige Git-Locks..."
rm -f .git/index.lock .git/refs/heads/*.lock .git/refs/remotes/origin/*.lock 2>/dev/null || true

# Git safe directory setzen
git config --global --add safe.directory $(pwd) 2>/dev/null || true

# Setze Git-Konfiguration falls nicht vorhanden
if [ -z "$(git config user.name 2>/dev/null)" ]; then
    echo "📝 Setze Git-Konfiguration..."
    git config user.name "BSSCI Synology Service"
    git config user.email "bssci@synology.local"
fi

# Kopiere die neuen Git-optimierten Dateien
echo "📋 Installiere Git-optimierte Konfiguration..."

# 1. Docker Compose Konfiguration
if [ -f "docker-compose.synology-git.yml" ]; then
    cp docker-compose.synology-git.yml docker-compose.yml
    echo "✅ Git-optimierte docker-compose.yml installiert"
else
    echo "❌ docker-compose.synology-git.yml nicht gefunden!"
    exit 1
fi

# 2. Docker Entrypoint
if [ -f "docker-entrypoint-synology-git.sh" ]; then
    cp docker-entrypoint-synology-git.sh docker-entrypoint.sh
    chmod +x docker-entrypoint.sh
    echo "✅ Git-optimierter docker-entrypoint.sh installiert"
else
    echo "❌ docker-entrypoint-synology-git.sh nicht gefunden!"
    exit 1
fi

# 3. Dockerfile anpassen für Git
echo "🔧 Passe Dockerfile für Git an..."
if ! grep -q "git" Dockerfile; then
    # Backup original Dockerfile
    cp Dockerfile $BACKUP_DIR/
    
    # Add git to system dependencies
    sed -i 's/openssl \\/openssl \\\n    git \\/' Dockerfile
    echo "✅ Git zur Dockerfile hinzugefügt"
fi

# Setze Umgebungsvariablen
echo "📝 Setze Git-Umgebungsvariablen..."
cat >> .env << EOF

# Git Configuration for Synology
GIT_AUTHOR_NAME=BSSCI Synology Service  
GIT_AUTHOR_EMAIL=bssci@synology.local
GIT_COMMITTER_NAME=BSSCI Synology Service
GIT_COMMITTER_EMAIL=bssci@synology.local
EOF

# Build und starte Container mit Git-Support
echo "🐳 Baue und starte Git-optimierten Container..."
docker-compose build --no-cache
docker-compose up -d

# Prüfe Container Status
echo "📊 Prüfe Container Status..."
sleep 5
docker-compose ps

# Teste Git-Funktionalität im Container
echo "🧪 Teste Git-Funktionalität..."
if docker exec bssci-service-center git --version >/dev/null 2>&1; then
    echo "✅ Git ist im Container verfügbar"
    
    if docker exec bssci-service-center git status >/dev/null 2>&1; then
        echo "✅ Git-Repository ist zugänglich"
    else
        echo "⚠️  Git-Repository benötigt möglicherweise manuelle Konfiguration"
    fi
else
    echo "❌ Git ist nicht im Container verfügbar"
fi

# Zeige Logs
echo "📋 Container Logs (letzte 10 Zeilen):"
docker-compose logs --tail=10

echo ""
echo "🎉 SYNOLOGY GIT-INSTALLATION ABGESCHLOSSEN!"
echo "==========================================="
echo ""
echo "✅ Was wurde installiert:"
echo "   - Git-optimierte docker-compose.yml"
echo "   - Synology-spezifischer Entrypoint mit Git-Support"
echo "   - Git-Umgebungsvariablen konfiguriert"
echo "   - Dockerfile für Git erweitert"
echo ""
echo "🔍 Nächste Schritte:"
echo "   - Überprüfe Container: docker-compose ps"
echo "   - Teste Web-UI: http://localhost:5056"
echo "   - Teste Git im Container: docker exec bssci-service-center git status"
echo ""
echo "📦 Backup gespeichert in: $BACKUP_DIR"
echo "   (Bei Problemen: docker-compose down && cp $BACKUP_DIR/* . && docker-compose up -d)"