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
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'Claude Usage'" \
    -c "Set :CFBundleDisplayName 'Claude Usage'" \
    -c "Set :NSHighResolutionCapable true" \
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
fi
