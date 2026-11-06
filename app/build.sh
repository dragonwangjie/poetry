#!/bin/bash
# Build the Poetry APK without Gradle: aapt2 + javac + d8 + zipalign + apksigner
set -u
BT=/opt/android-sdk/build-tools/36.0.0
AAPT2=/usr/bin/aapt2
PLATFORM=/opt/android-sdk/platforms/android-34/android.jar
SRC=/root/poetry/app
OUT=$SRC/build
GZ=/root/poetry/out/poetry_lite.db.gz
KS=$SRC/release.keystore
KS_PASS=poetry123

rm -rf "$OUT"
mkdir -p "$OUT/obj" "$OUT/dex" "$OUT/gen" "$OUT/apk"

echo "== [1/7] compile resources"
$AAPT2 compile --dir "$SRC/res" -o "$OUT/res.zip" || exit 1

echo "== [2/7] link resources"
$AAPT2 link -o "$OUT/apk/base.apk" \
  -I "$PLATFORM" \
  --manifest "$SRC/AndroidManifest.xml" \
  --java "$OUT/gen" \
  --min-sdk-version 24 --target-sdk-version 34 \
  --version-code 1 --version-name 1.0 \
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
DB=/root/poetry/out/poetry_lite.db
# A killed gzip leaves a truncated .gz that is NEWER than the db, so mtime alone cannot
# be trusted: compare the decompressed size instead.
need=1
if [ -f "$GZ" ] && [ /root/poetry/out/poetry_lite.db -nt "$GZ" ]; then need=1
elif [ -f "$GZ" ]; then
  got=$(gzip -dc "$GZ" 2>/dev/null | wc -c)
  [ "$got" = "$(stat -c %s "$DB")" ] && need=0 || echo "   stale/truncated gz ($got != $(stat -c %s "$DB")), recompressing"
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
if [ ! -f "$KS" ]; then
  keytool -genkeypair -v -keystore "$KS" -storepass "$KS_PASS" -keypass "$KS_PASS" \
    -alias poetry -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Poetry, OU=Dev, O=Poetry, L=City, S=State, C=CN" >/dev/null 2>&1 || exit 1
fi
java -jar "$BT/lib/apksigner.jar" sign --ks "$KS" --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
  --out "$OUT/poetry.apk" "$OUT/apk/poetry.aligned.apk" || exit 1
java -jar "$BT/lib/apksigner.jar" verify --print-certs "$OUT/poetry.apk" | head -3
ls -la "$OUT/poetry.apk"
echo "APK: $OUT/poetry.apk"