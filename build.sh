#!/usr/bin/env bash
# Builds "Claude Usage.app". `./build.sh install` also copies it into /Applications.
#
# PyInstaller, not a shell launcher around the uv venv: macOS gives ⌘-Tab and
# the Dock the identity of the process it actually started, and a framework
# CPython re-execs itself through its own Python.app — so any wrapper that
# ends in `exec python` shows up as Python, with Python's icon, whatever the
# bundle around it says.
set -euo pipefail
cd "$(dirname "$0")"

# Regenerate the icon with: swift tools/make-icon.swift
test -f macos/ClaudeUsage.icns

uv run --with pyinstaller --with PySide6-Essentials \
    pyinstaller --noconfirm --clean --windowed \
    --name "Claude Usage" \
    --icon "$PWD/macos/ClaudeUsage.icns" \
    --osx-bundle-identifier com.giacorri.claudeusage \
    --collect-submodules claude_usage \
    --distpath build --workpath build/pyi --specpath build \
    main.py

APP="build/Claude Usage.app"
# PyInstaller writes its own Info.plist; overwrite the few keys we care about
# rather than hand it the whole file, so its bootloader keys survive.
# LSUIElement: this is a menu-bar app. Without it the OSD — a frameless
# always-on-top panel — drags a Dock icon and a ⌘-Tab entry behind it for a
# window you never switch to.
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'Claude Usage'" \
    -c "Set :CFBundleDisplayName 'Claude Usage'" \
    -c "Set :NSHighResolutionCapable true" \
    -c "Add :LSUIElement bool true" \
    "$APP/Contents/Info.plist" >/dev/null

# Ad-hoc signature: a stable identity, so macOS keeps what it granted the
# previous build instead of treating every rebuild as a new app.
codesign --force --deep --sign - "$APP" 2>/dev/null

echo "built $PWD/$APP"

if [[ "${1:-}" == "install" ]]; then
    pkill -f "claude_usage" 2>/dev/null || true
    pkill -f "Claude Usage" 2>/dev/null || true
    rm -rf "/Applications/Claude Usage.app"
    cp -R "$APP" /Applications/
    echo "installed /Applications/Claude Usage.app"

    # Start at login. A LaunchAgent rather than a Login Item: it needs no
    # System Events automation prompt, and it is a file this repo can rewrite.
    AGENT="$HOME/Library/LaunchAgents/com.giacorri.claudeusage.plist"
    mkdir -p "$(dirname "$AGENT")"
    cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.giacorri.claudeusage</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/Claude Usage.app/Contents/MacOS/Claude Usage</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
PLIST
    launchctl bootout "gui/$UID/com.giacorri.claudeusage" 2>/dev/null || true
    launchctl bootstrap "gui/$UID" "$AGENT"
    echo "login agent loaded: $AGENT"
fi
