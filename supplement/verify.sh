#!/bin/bash
# One command to verify the app after a build:
#   bash supplement/verify.sh            offline suites + install + on-device assertions
#   SKIP_DEVICE=1 bash supplement/verify.sh   offline suites only
# Exits non-zero if anything failed or the device run could not read the screen.
# pipefail matters here: `suite | tail -1 || status=1` would otherwise read tail's exit
# code and report green for a failing suite.
set -u -o pipefail
run_suite() {  # run_suite <label> <command...>
  local label="$1"; shift
  local out rc
  out=$("$@" 2>&1); rc=$?
  echo "== $label"
  echo "$out" | tail -1
  [ $rc -eq 0 ] || { echo "   (exit $rc)"; echo "$out" | tail -6; status=1; }
}
cd "$(dirname "$0")"
DB=${DB:-/tmp/inapk13.db}
APK=${APK:-../app/build/poetry.apk}   # relative: verify.sh has already cd'd to its own dir
status=0

if [ ! -f "$DB" ]; then
  echo "== extracting db from $APK"
  python3 - "$APK" "$DB" <<'PY' || exit 1
import sys, zipfile, gzip
data = gzip.decompress(zipfile.ZipFile(sys.argv[1]).read('assets/poetry.db.gz'))
open(sys.argv[2], 'wb').write(data)
print(len(data), 'bytes')
PY
fi

run_suite "test_parse (corpus parser)" timeout 300 python3 test_parse.py
run_suite "test_anno (annotations against the shipped db)" timeout 300 python3 test_anno.py "$DB"
run_suite "test_title_search (ranking rules, SQL from PoemDb.java)" timeout 500 python3 test_title_search.py "$DB"
# The dial is self-drawn, so uiautomator never sees its wedges; these guard the angle maths and
# the strict position lookup instead. POETRY_SRC stays default => checks run against real sources.
run_suite "test_feihua (dial geometry + 令字 rules, mirrors DialView.java)" timeout 300 python3 test_feihua.py "$DB"

if [ "${SKIP_DEVICE:-0}" = 1 ]; then
  echo "== device assertions: skipped (SKIP_DEVICE=1)"
  echo "verify: $([ $status -eq 0 ] && echo ALL GREEN || echo SOMETHING FAILED)"
  exit $status
fi

echo "== install $APK"
cp "$APK" /sdcard/Download/poetry.apk || exit 1
adb install -r /sdcard/Download/poetry.apk 2>&1 | tail -1

run_suite "device assertions (rendered text via uiautomator)" timeout 1200 bash test_ui_device.sh
# 飞花令 needs the screen awake and drives a real 5s spin, so it lives here and not in the
# pre-commit hook. It re-installs nothing; it just enters via 主页 and presses 开始.
run_suite "feihua device checks (spin lands, 出句 honours the landed position)" timeout 900 python3 test_feihua_device.py

echo "verify: $([ $status -eq 0 ] && echo ALL GREEN || echo SOMETHING FAILED)"
exit $status