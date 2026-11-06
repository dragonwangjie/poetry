#!/bin/bash
# On-device assertions against the installed apk: cold-start MainActivity with a query
# extra (adb cannot type Chinese into the box) and assert on the rendered text that
# uiautomator reads back.
#
# Two traps found the hard way:
#  1. force-stop must happen BEFORE am start. On a live task am start does not re-run
#     onCreate, so the query extra is ignored -- every case then read back the previous
#     query's screen and the whole suite silently asserted one stale page (7/7 FAIL with
#     identical text is the fingerprint).
#  2. This device dozes seconds after waking and KEYCODE_WAKEUP does nothing; only POWER
#     (26) wakes it and it toggles, so wake() checks mWakefulness first. If the screen
#     still cannot be read every case is SKIP and the run exits non-zero -- skipped is
#     deliberately not success, green always means the text was really asserted.
set -u
PKG=com.poetry.app
fails=0
skipped=0
ran=0

if ! adb get-state >/dev/null 2>&1; then
  echo "no device connected; device assertions cannot run"
  exit 2
fi
adb shell settings put global aod_display_enabled 0 >/dev/null 2>&1
adb shell settings put secure doze_always_on 0 >/dev/null 2>&1
adb shell am force-stop com.miui.aod >/dev/null 2>&1

wake() {
  st=$(adb shell dumpsys power 2>/dev/null | grep -m1 -oE 'mWakefulness=[A-Za-z]+')
  [ "$st" = "mWakefulness=Awake" ] || { adb shell input keyevent 26 >/dev/null 2>&1; sleep 1; }
  adb shell wm dismiss-keyguard >/dev/null 2>&1
  adb shell input swipe 640 2300 640 900 250 >/dev/null 2>&1
}

grab() {   # grab <query> -> /tmp/w.xml
  # Cold start every case (trap 1) and keep the window short: the device dozes again
  # seconds after waking, ~1s per adb round trip, and 3s covers cold start (~0.4s)
  # plus both query branches (~0.2s).
  for try in 1 2 3 4; do
    wake
    adb shell am force-stop $PKG >/dev/null 2>&1
    if [ -n "$1" ]; then
      adb shell am start -n $PKG/.MainActivity --es query "$1" >/dev/null 2>&1
    else
      adb shell am start -n $PKG/.MainActivity >/dev/null 2>&1
    fi
    sleep 3
    adb shell uiautomator dump /sdcard/w.xml >/dev/null 2>&1
    adb pull /sdcard/w.xml /tmp/w.xml >/dev/null 2>&1
    grep -q "$PKG" /tmp/w.xml 2>/dev/null && return 0
  done
  return 1
}

expect() {  # expect <query> <must-contain> [must-not-contain]
  local q="$1" want="$2" absent="${3:-}"
  ran=$((ran + 1))
  if ! grab "$q"; then
    echo "SKIP [$q]: app window unreachable (screen asleep or overlay owns it)"
    skipped=$((skipped + 1)); return
  fi
  local txt
  txt=$(tr '>' '\n' < /tmp/w.xml | grep -oE 'text="[^"]{1,46}"' | sed 's/text=//; s/"//g' | tr '\n' '|')
  local s=ok
  [[ "$txt" == *"$want"* ]] || { s=FAIL; fails=$((fails + 1)); }
  if [ -n "$absent" ] && [[ "$txt" == *"$absent"* ]]; then
    s="$s(LEAK:$absent)"; fails=$((fails + 1))
  fi
  echo "$s [$q] want«$want» -> ${txt:0:150}"
}

# A title that is not a line of any poem: only the title branch can find it.
expect 静夜思 '《静夜思》'
# A half-remembered line: the verse engine with its fuzzy/异文 fallback must still work.
expect 床前明月光 '静夜思'
# The corpus writes this title differently; the longestChunk retry has to bridge it.
expect '观书有感·其一' '观书有感二首·其一'
# 词牌: dozens of exact copies must not crowd 李煜 off the page.
expect 虞美人 '李煜'
# Exact title leads, and a poet whose name contains the same characters shares the screen.
expect 明月 '《明月》'
# One character is below both poem engines' floor -- say that instead of "0 首诗词".
expect 李 '搜诗词请至少输入两个字' '首诗词'
# Browse mode (empty box): the plain poet list, no section headers.
expect '' '位作者' '首诗词'

echo "device assertions: ran=$ran $([ $fails -eq 0 ] && [ $skipped -eq 0 ] && echo ALL PASS || echo "fails=$fails skipped=$skipped")"
# Skipped is never success: these checks exist to read the rendered text, and a run that
# could not read the screen proved nothing.
[ $fails -eq 0 ] && [ $skipped -eq 0 ]