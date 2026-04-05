#!/bin/bash
# Install App Guardian as a LaunchAgent so it starts automatically on login.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.tomgranot.app-guardian"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/.config/app-guardian"

mkdir -p "$LOG_DIR"

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${SCRIPT_DIR}/run.sh</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launch.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launch-error.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST"
echo "✅  App Guardian will now start automatically on login."
echo ""
echo "To stop and uninstall:"
echo "  launchctl unload $PLIST"
echo "  rm $PLIST"
