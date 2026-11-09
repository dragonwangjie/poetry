#!/bin/bash
# Build the Poetry APK without Gradle: aapt2 + javac + d8 + zipalign + apksigner
set -u
# Everything is resolved from this script's own location, not from a hardcoded /root/poetry:
# a clone anywhere on disk must build. ROOT is the repo root (app/ lives inside it).
SRC="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SRC")"
# Toolchain paths are resolved, not hardcoded, so the same script builds on the phone's proot
# box AND on GitHub Actions, where the SDK lives under $ANDROID_HOME instead of /opt/android-sdk.
# aapt2: prefer one from PATH (that is what local builds have always used), fall back to the
# build-tools copy for CI images that do not ship a standalone aapt2.
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/opt/android-sdk}}"
[ -d "$SDK" ] || SDK=/opt/android-sdk
BT="${BT:-$(ls -d "$SDK"/build-tools/* 2>/dev/null | sort -V | tail -1)}"
[ -n "$BT" ] && [ -d "$BT" ] || { echo "no build-tools under $SDK -- set ANDROID_HOME"; exit 1; }
AAPT2="${AAPT2:-$(command -v aapt2 || echo "$BT/aapt2")}"
PLATFORM="${PLATFORM:-$SDK/platforms/android-34/android.jar}"
[ -f "$PLATFORM" ] || { echo "missing $PLATFORM -- run: sdkmanager 'platforms;android-34'"; exit 1; }
OUT=$SRC/build
GZ=$ROOT/out/poetry_lite.db.gz
KS=$SRC/release.keystore
# No in-repo fallback on purpose: the literal used to live here (and in README), so anyone
# who could read the repo could sign as us the moment a keystore leaked too. Set the env
# var; CI supplies it from POETRY_KS_PASS, locally: POETRY_KS_PASS="$(cat ...)" ./build.sh
KS_PASS="${POETRY_KS_PASS:?POETRY_KS_PASS must be set -- signing password, not stored in git}"

rm -rf "$OUT"
mkdir -p "$OUT/obj" "$OUT/dex" "$OUT/gen" "$OUT/apk"

echo "== [1/7] compile resources"
$AAPT2 compile --dir "$SRC/res" -o "$OUT/res.zip" || exit 1

echo "== [2/7] link resources"
# The version numbers come from AndroidManifest.xml -- that is the file release bumps -- and are
# passed explicitly. build.sh used to hardcode "--version-code 1 --version-name 1.0" here, which
# read like it decided the version while the manifest actually won; an APK that silently claims
# version 1 cannot be installed as an upgrade over the real one, so make the source of truth
# explicit instead of relying on which flag aapt2 happens to prefer.
VC=$(sed -n 's/.*android:versionCode="\([0-9]*\)".*/\1/p' "$SRC/AndroidManifest.xml" | head -1)
VN=$(sed -n 's/.*android:versionName="\([^"]*\)".*/\1/p' "$SRC/AndroidManifest.xml" | head -1)
[ -n "$VC" ] && [ -n "$VN" ] || { echo "cannot read versionCode/versionName from AndroidManifest.xml"; exit 1; }
echo "   version: $VN ($VC)"
$AAPT2 link -o "$OUT/apk/base.apk" \
  -I "$PLATFORM" \
  --manifest "$SRC/AndroidManifest.xml" \
  --java "$OUT/gen" \
  --min-sdk-version 24 --target-sdk-version 34 \
  --version-code "$VC" --version-name "$VN" \
  "$OUT/res.zip" || exit 1

echo "== [3/7] javac"
find "$SRC/src" "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
javac -nowarn -encoding UTF-8 -source 8 -target 8 \
  -bootclasspath "$PLATFORM" \
  -classpath "$PLATFORM" \
  -d "$OUT/obj" @"$OUT/sources.txt" 2>&1 | grep -v 'bootstrap class path\|deprecat\|^Note:' || true
CLASSES=$(find "$OUT/obj" -name '*.class' | wc -l)
echo "   compiled classes: $CLASSES"
[ "$CLASSES" -gt 0 ] || exit 1

echo "== [4/7] d8 -> dex"
find "$OUT/obj" -name '*.class' > "$OUT/classes.txt"
"$BT/d8" --release --lib "$PLATFORM" --min-api 24 \
  --output "$OUT/dex" $(cat "$OUT/classes.txt") || exit 1
ls -la "$OUT/dex"

echo "== [5/7] assemble apk"
cp "$OUT/apk/base.apk" "$OUT/apk/poetry.unsigned.apk"
mkdir -p "$OUT/stage/assets"
DB=$ROOT/out/poetry_lite.db
# A killed gzip leaves a truncated .gz that is NEWER than the db, so mtime alone cannot
# be trusted: compare the decompressed size instead.
# If the db is missing we are building from a fresh clone: out/poetry_lite.db.gz is
# versioned, so ship it as-is. gzip -t only validates the deflate stream, so also inflate
# it and open it as sqlite -- a truncated or wrong-schema db would otherwise surface as a
# 100-second silent extraction on the user's first launch.
if [ ! -f "$DB" ]; then
  [ -f "$GZ" ] || { echo "neither $DB nor $GZ exists -- run 'python3 build_db.py lite' first (README 重建路径)"; exit 1; }
  echo "   no uncompressed db -- packaging the versioned $GZ"
  gzip -t "$GZ" || { echo "gzip -t failed on $GZ"; exit 1; }
  python3 - "$GZ" <<'PY' || exit 1
import sqlite3, sys, gzip, tempfile, os
raw = gzip.decompress(open(sys.argv[1], 'rb').read())
p = os.path.join(tempfile.mkdtemp(), 'v.db')
open(p, 'wb').write(raw)
con = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
n = con.execute('select count(*) from poem').fetchone()[0]
assert con.execute('pragma integrity_check').fetchone()[0] == 'ok', 'integrity_check failed'
assert n > 79000, 'only %d poems in the db' % n
print('   db ok: %d poems, %d bytes inflated' % (n, len(raw)))
PY
  need=0
else
  need=1
  if [ -f "$GZ" ] && [ "$DB" -nt "$GZ" ]; then need=1
  elif [ -f "$GZ" ]; then
    got=$(gzip -dc "$GZ" 2>/dev/null | wc -c)
    [ "$got" = "$(stat -c %s "$DB")" ] && need=0 || echo "   stale/truncated gz ($got != $(stat -c %s "$DB")), recompressing"
  fi
fi
if [ "$need" = 1 ]; then
  echo "   gzipping database..."
  rm -f "$GZ"
  gzip -9 -c "$DB" > "$GZ" || exit 1
  gzip -t "$GZ" || { echo "gzip failed"; exit 1; }
  [ "$(gzip -dc "$GZ" | wc -c)" = "$(stat -c %s "$DB")" ] || { echo "gz size mismatch"; exit 1; }
fi
ln -sf "$GZ" "$OUT/stage/assets/poetry.db.gz"
cd "$OUT/stage" && zip -q -X -r "$OUT/apk/poetry.unsigned.apk" assets || exit 1
cd "$OUT/dex" && zip -q -X -j "$OUT/apk/poetry.unsigned.apk" classes.dex || exit 1
cd "$OUT"

echo "== [6/7] zipalign"
python3 "$SRC/zipalign.py" "$OUT/apk/poetry.unsigned.apk" "$OUT/apk/poetry.aligned.apk" || exit 1

echo "== [7/7] sign"
# The keystore is deliberately not versioned (build.sh carries the password in plaintext).
# Regenerating it silently would produce an APK that installs fine but CANNOT replace an
# already-installed app (INSTALL_FAILED_UPDATE_INCOMPATIBLE), so look for a backup first and
# shout if we really have to start a new signing identity.
if [ ! -f "$KS" ]; then
  for cand in "${POETRY_KS:-}" /root/backup/release.keystore /sdcard/Download/release.keystore; do
    if [ -n "$cand" ] && [ -f "$cand" ]; then
      cp "$cand" "$KS" || exit 1
      echo "   restored signing key from $cand"
      break
    fi
  done
fi
if [ ! -f "$KS" ]; then
  echo "   WARNING: no release.keystore anywhere -> generating a NEW signing key."
  echo "   This APK will NOT upgrade an existing install (uninstall first, or restore the"
  echo "   key from /root/backup/ or /sdcard/Download/ and re-run)."
  keytool -genkeypair -v -keystore "$KS" -storepass "$KS_PASS" -keypass "$KS_PASS" \
    -alias poetry -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Poetry, OU=Dev, O=Poetry, L=City, S=State, C=CN" >/dev/null 2>&1 || exit 1
fi
java -jar "$BT/lib/apksigner.jar" sign --ks "$KS" --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
  --out "$OUT/poetry.apk" "$OUT/apk/poetry.aligned.apk" || exit 1
java -jar "$BT/lib/apksigner.jar" verify --print-certs "$OUT/poetry.apk" | head -3
ls -la "$OUT/poetry.apk"
echo "APK: $OUT/poetry.apk"