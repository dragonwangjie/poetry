#!/usr/bin/env bash
# Make sure every tool app/build.sh actually calls is present AND runs, so a broken toolchain
# fails here instead of three steps later with a confusing mid-build error.
#
# Why not android-actions/setup-android: it failed run #1 with
#   Warning: Failed to find package 'tools'
#   Error: The process '.../cmdline-tools/16.0/bin/sdkmanager' failed with exit code 1
# because it installs the legacy `tools` package, which current cmdline-tools no longer publishes.
# The ubuntu runner image already ships an SDK, so only a missing platform needs adding.
#
# The checks mirror build.sh's real dependencies, not a generic SDK wishlist:
#   aapt2      from PATH if present, else $BT/aapt2
#   d8         $BT/d8
#   apksigner  java -jar $BT/lib/apksigner.jar
#   zipalign   NOT required -- build.sh uses its own app/zipalign.py
#   javac/python3/zip, and platforms/android-34/android.jar
set -euo pipefail
cd "$(dirname "$0")/.."

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$SDK" ] || [ ! -d "$SDK" ]; then
  # Probe instead of demanding an export: /usr/local/lib/android/sdk is the runner image location,
  # /opt/android-sdk is this project's own box (with ANDROID_HOME left unset).
  for cand in /usr/local/lib/android/sdk /opt/android-sdk "$HOME/Android/Sdk" /usr/lib/android-sdk; do
    if [ -d "$cand/build-tools" ] || [ -d "$cand/platforms" ]; then SDK="$cand"; break; fi
  done
fi
[ -n "${SDK:-}" ] && [ -d "$SDK" ] || { echo 'no Android SDK found (ANDROID_HOME unset, no candidate dir)'; exit 1; }
echo "SDK: $SDK"
echo "  build-tools: $(ls "$SDK"/build-tools 2>/dev/null | tr '\n' ' ')"
echo "  platforms:   $(ls "$SDK"/platforms 2>/dev/null | tr '\n' ' ')"

SDKMGR="$(command -v sdkmanager || ls "$SDK"/cmdline-tools/*/bin/sdkmanager 2>/dev/null | head -1 || true)"

install_pkg() {  # install_pkg <package>
  [ -n "$SDKMGR" ] || { echo "need $1 but there is no sdkmanager to fetch it"; exit 1; }
  echo "== installing $1 (licenses auto-accepted)"
  # `yes` answers the license prompts; sdkmanager otherwise blocks forever on a runner.
  if ! yes | "$SDKMGR" --sdk_root="$SDK" "$1" >/tmp/sdk.log 2>&1; then tail -25 /tmp/sdk.log; exit 1; fi
}

PLATFORM="$SDK/platforms/android-34/android.jar"
[ -f "$PLATFORM" ] || install_pkg "platforms;android-34"
[ -f "$PLATFORM" ] || { echo "still missing $PLATFORM"; exit 1; }

pick_bt() {  # newest build-tools whose d8 and apksigner actually execute
  # $1 = "strict" to also require its own aapt2 to run.
  local strict="${1:-}"
  for cand in $(ls -d "$SDK"/build-tools/*/ 2>/dev/null | sort -Vr); do
    local d="${cand%/}"
    [ -f "$d/lib/apksigner.jar" ] || continue
    java -jar "$d/lib/apksigner.jar" version >/dev/null 2>&1 || continue
    "$d/d8" --version >/dev/null 2>&1 || continue
    if [ "$strict" = strict ] && [ -x "$d/aapt2" ]; then "$d/aapt2" version >/dev/null 2>&1 || continue; fi
    echo "$d"
    return
  done
}
# Newest alone is not safe: on this project's own box build-tools/37.0.0-rc2/aapt2 exists but dies
# with "cannot execute: required file not found" (absent loader deps) while 36.0.0 beside it is
# fine, so candidates get probed by actually running them. Prefer a build-tools that carries a
# working aapt2 -- on the runner, PATH has no aapt2, so build.sh falls back to $BT/aapt2 -- and
# only settle for a PATH-provided aapt2 otherwise (that is how this box builds today).
PATH_AAPT2_OK=0
command -v aapt2 >/dev/null 2>&1 && aapt2 version >/dev/null 2>&1 && PATH_AAPT2_OK=1

BT_DIR=$(pick_bt strict || true)
if [ -z "$BT_DIR" ] && [ "$PATH_AAPT2_OK" = 1 ]; then
  BT_DIR=$(pick_bt || true)
  [ -n "$BT_DIR" ] && echo "  (using aapt2 from PATH, since no build-tools has a working one)"
fi
if [ -z "$BT_DIR" ]; then
  install_pkg "build-tools;35.0.0"
  BT_DIR=$(pick_bt strict || pick_bt || true)
fi
[ -n "$BT_DIR" ] || { echo 'no usable build-tools'; exit 1; }
echo "build-tools: $BT_DIR"

# aapt2 the way build.sh resolves it: PATH first, then the chosen build-tools.
if [ -z "${AAPT2:-}" ]; then
  if [ "$PATH_AAPT2_OK" = 1 ]; then AAPT2="$(command -v aapt2)"; else AAPT2="$BT_DIR/aapt2"; fi
fi
"$AAPT2" version >/dev/null 2>&1 || { echo "aapt2 ($AAPT2) will not run"; exit 1; }
echo "aapt2: $("$AAPT2" version 2>&1 | head -1)"

for t in javac java python3 zip; do
  command -v "$t" >/dev/null || { echo "missing $t"; exit 1; }
done
python3 -c 'import sqlite3' || { echo 'python3 without sqlite3'; exit 1; }

# Export for later steps; build.sh reads ANDROID_HOME and honours BT when already set.
if [ -n "${GITHUB_ENV:-}" ]; then
  { echo "ANDROID_HOME=$SDK"; echo "ANDROID_SDK_ROOT=$SDK"; echo "BT=$BT_DIR"; } >> "$GITHUB_ENV"
fi
echo "SDK ready: android-34 + $(basename "$BT_DIR") + $(basename "$AAPT2")"
