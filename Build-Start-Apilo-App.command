#!/bin/bash

set -eu

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$PROJECT_DIR/Start Apilo.app"
CONTENTS_DIR="$APP_PATH/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
EXECUTABLE_PATH="$MACOS_DIR/start-apilo"
PLIST_PATH="$CONTENTS_DIR/Info.plist"
PKGINFO_PATH="$CONTENTS_DIR/PkgInfo"
SOURCE_ICON_PATH="$PROJECT_DIR/AppIcon.icns"
TARGET_ICON_PATH="$RESOURCES_DIR/AppIcon.icns"

mkdir -p "$MACOS_DIR"
mkdir -p "$RESOURCES_DIR"

cat >"$EXECUTABLE_PATH" <<'EOF'
#!/bin/bash

set -eu

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_DIR="$(cd "$APP_DIR/.." && pwd)"
RUNNER_PATH="$(mktemp /tmp/start-apilo-XXXXXX.command)"

cat >"$RUNNER_PATH" <<INNER
#!/bin/bash
/bin/bash "$PROJECT_DIR/Start-Apilo.command"
INNER

chmod +x "$RUNNER_PATH"
/usr/bin/open -a Terminal "$RUNNER_PATH"
EOF

chmod +x "$EXECUTABLE_PATH"

cat >"$PLIST_PATH" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>start-apilo</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>pl.weeball.apilo-panel.launcher</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Start Apilo</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
</dict>
</plist>
EOF

printf "APPL????" >"$PKGINFO_PATH"

if [ -f "$SOURCE_ICON_PATH" ]; then
  cp "$SOURCE_ICON_PATH" "$TARGET_ICON_PATH"
fi

xattr -d com.apple.quarantine "$APP_PATH" 2>/dev/null || true

echo "Gotowe:"
echo "$APP_PATH"
