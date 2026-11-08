#!/usr/bin/env bash
# Post-build checks on the APK. Each one guards a failure that still produces a file of the right
# size, so "the build exited 0" does not catch it:
#   - db missing from assets/  -> app installs, then dies on first launch importing the corpus
#   - classes.dex missing      -> "app not installed" / instant crash
#   - versionCode not bumped   -> installs over nothing, or INSTALL_FAILED_UPDATE_INCOMPATIBLE
#   - signature not verifiable -> installs fine, updates fail later
set -euo pipefail
cd "$(dirname "$0")/.."

APK=app/build/poetry.apk
EXPECT_CODE="${1:-}"
[ -f "$APK" ] || { echo "no $APK"; exit 1; }
ls -l "$APK"

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/opt/android-sdk}}"
BT="${BT:-$(ls -d "$SDK"/build-tools/* 2>/dev/null | sort -V | tail -1)}"
[ -n "$BT" ] || { echo "no build-tools found under $SDK"; exit 1; }

# Pick an aapt that actually runs. Newest is not safest: build-tools 37.0.0-rc2 on this phone's
# proot box is a binary whose loader dependencies are absent, so it dies with "required file not
# found" while the 36.0.0 copy next to it works fine. Probe with a real call instead of trusting
# sort order -- a bad probe is worse than no probe, since the script would then report PASS
# without ever having read the version out of the APK.
AAPT=''
for cand in "$(command -v aapt || true)" $(ls -d "$SDK"/build-tools/*/aapt 2>/dev/null | sort -V -r); do
  [ -n "$cand" ] && [ -x "$cand" ] || continue
  if "$cand" dump badging "$APK" >/dev/null 2>&1; then AAPT="$cand"; break; fi
done
[ -n "$AAPT" ] || { echo 'no working aapt (tried PATH and every build-tools copy)'; exit 1; }
echo "using $AAPT"

# The db is stored already deflated and build.sh zips it with `zip -X` (no extra fields), so the
# archive member size must equal the .gz on disk -- a silently recompressed or truncated asset
# would change that number.
unzip -l "$APK" | grep -q 'assets/poetry.db.gz' || { echo 'assets/poetry.db.gz missing from apk'; exit 1; }
unzip -l "$APK" | grep -q ' classes.dex' || { echo 'classes.dex missing from apk'; exit 1; }
INSIDE=$(unzip -l "$APK" | awk '/assets\/poetry.db.gz/{print $1}')
ONDISK=$(stat -c %s out/poetry_lite.db.gz)
[ "$INSIDE" = "$ONDISK" ] || { echo "db size in apk $INSIDE != $ONDISK on disk"; exit 1; }
echo "db asset: $INSIDE bytes (matches out/poetry_lite.db.gz)"

"$BT/apksigner" verify "$APK"
"$BT/apksigner" verify --print-certs "$APK" | head -2

# Read the version back out of the built APK rather than trusting the build log.
BADGE=$("$AAPT" dump badging "$APK" | head -1)
echo "$BADGE"
CODE=$(sed -n "s/.*versionCode='\([0-9]*\)'.*/\1/p" <<<"$BADGE")
NAME=$(sed -n "s/.*versionName='\([^']*\)'.*/\1/p" <<<"$BADGE")
echo "apk reports versionName=$NAME versionCode=$CODE"
[ -n "$CODE" ] || { echo 'could not read versionCode from the apk'; exit 1; }
if [ -n "$EXPECT_CODE" ] && [ "$CODE" != "$EXPECT_CODE" ]; then
  echo "apk versionCode $CODE != expected $EXPECT_CODE"; exit 1
fi
# An APK claiming version 1 can never be installed over a real one; this is what the old
# hardcoded `--version-code 1` in build.sh would have produced.
[ "$CODE" -ge 2 ] || { echo "versionCode $CODE looks like a placeholder"; exit 1; }
echo "apk checks: PASS"