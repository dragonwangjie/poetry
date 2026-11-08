#!/usr/bin/env python3
"""On-device assertions for 飞花令, driven through adb + uiautomator.

FeihuaActivity is not exported, so the only way in is tapping the 主页 button; the dial, its
hand and the countdown badge are self-drawn and invisible to uiautomator. What this can assert
is the *consequence* of the hand landing: the counter states 「X」第N字, and every 出句 dealt
afterwards must genuinely carry X at position N. That cross-check is the reason this file
exists -- nothing else here would notice the hand stopping on the wrong wedge.

Two environment traps handled here:
  * MIUI falls back to Dozing between adb calls, and a dump taken then contains only systemui;
    wake() runs before the first grab and again if a dump comes back without our package.
  * `adb shell uiautomator dump` reports success even when it wrote nothing usable, so every
    grab is checked for our package name rather than for a zero exit code.
"""
import re
import subprocess
import sys
import time

PKG = 'com.poetry.app'
fails = []


def sh(cmd):
    return subprocess.run(['adb', 'shell'] + cmd, capture_output=True, text=True,
                          timeout=60).stdout


def bad(msg):
    fails.append(msg)


def wake():
    """Ensure the screen is ON. Never keyevent 26: POWER is a toggle, and sending it while the
    screen is lit puts the phone to sleep -- which stalled a spin mid-sweep (no frames, no
    settle) and made the game look broken when the harness itself was the culprit."""
    state = sh(['dumpsys', 'power'])
    if 'mWakefulness=Awake' not in state:
        sh(['input', 'keyevent', '224'])          # WAKEUP: wakes, never sleeps
        time.sleep(2)
    sh(['input', 'swipe', '540', '2100', '540', '700', '300'])   # MIUI needs the swipe-up;
    sh(['wm', 'dismiss-keyguard'])                               # dismiss-keyguard alone leaves it up
    time.sleep(1)


def grab(label, tries=2):
    """Return the rendered text nodes, or [] if the screen would not give them up."""
    for _ in range(tries):
        sh(['rm', '-f', '/sdcard/%s.xml' % label])
        sh(['uiautomator', 'dump', '/sdcard/%s.xml' % label])
        xml = subprocess.run(['adb', 'exec-out', 'cat', '/sdcard/%s.xml' % label],
                             capture_output=True, text=True, timeout=60).stdout
        if PKG in xml:
            return re.findall(r'text="([^"]*)"', xml), xml
        wake()
    bad('屏幕抓取里没有 %s（屏睡了或应用退到后台）' % PKG)
    return [], ''


def tap(nodes_xml, label):
    """Tap the centre of the node whose text is exactly `label`."""
    for m in re.finditer(r'text="%s"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' % re.escape(label),
                         nodes_xml):
        x1, y1, x2, y2 = map(int, m.groups())
        if x2 > x1 and y2 > y1:
            sh(['input', 'tap', str((x1 + x2) // 2), str((y1 + y2) // 2)])
            return True
    bad('页面上找不到「%s」按钮' % label)
    return False


def keepawake(on):
    """MIUI freezes a backgrounded/screen-off app: no animation frames, no posted Runnables, so a
    spin started then never settles. Hold the screen on for the duration of the test."""
    if on:
        sh(['svc', 'power', 'stayon', 'true'])
        sh(['settings', 'put', 'system', 'screen_off_timeout', '600000'])
    else:
        sh(['svc', 'power', 'stayon', 'false'])
        sh(['settings', 'put', 'system', 'screen_off_timeout', '60000'])


# ------------------------------------------------------------------ enter the game
keepawake(True)
wake()
sh(['am', 'force-stop', PKG])
sh(['am', 'start', '-n', PKG + '/.MainActivity'])
time.sleep(4)
texts, xml = grab('fh_enter')
if '飞花令' not in texts:
    bad('主页上没有「飞花令」入口')
tap(xml, '飞花令')
time.sleep(3)
texts, hub_xml = grab('fh_hub')

mfocus = re.search(r'mCurrentFocus=Window\{\S+ u0 (\S+)', sh(['dumpsys', 'window']))
if 'FeihuaActivity' not in (mfocus.group(1) if mfocus else ''):
    bad('点「飞花令」后焦点不在 FeihuaActivity')

if '开始' not in texts:
    bad('中枢缺「开始」')
if '认输' not in texts:
    bad('中枢缺「认输」')
if '停止' in texts:
    bad('「停止」按钮应已移除')
# the 出句者/答句者 boxes are gone; as EditTexts their hints used to show up as their own nodes
for gone in ('系统', '我'):
    if gone in texts:
        bad('「%s」输入框应已移除' % gone)

# ---------------------------------------------------------------- press 开始 and read
tap(hub_xml, '开始')
# The 5s sweep ends with beginPlay(), which puts the label back to 开始 on both paths (dealt, and
# empty-pool-with-a-note) -- so that is the signal to read the screen. Do NOT wait on 剩余: that
# text is already present from the initial load, which once made this grab the screen ~1s after
# 开始 and report "no 出句" for a spin that was simply still running.
slept = 0
texts = []
deadline = time.time() + 30
while time.time() < deadline:
    time.sleep(1)
    texts, _ = grab('fh_after', tries=1)
    if 'Awake' not in sh(['dumpsys', 'power']):
        slept += 1
        sh(['input', 'keyevent', '224'])
    if '开始' in texts or any(t.startswith('出句者 出') for t in texts):
        break
joined = '\n'.join(texts)

m = re.search(r'「(.+?)」第(\d)字|「(.+?)」需在任意位置', joined)
ch = pos = None
if not m:
    bad('没读到位置规则（期望「X」第N字 或「X」需在任意位置）: %s' % joined[:120])
else:
    ch = m.group(1) or m.group(3)
    pos = int(m.group(2)) - 1 if m.group(2) else None

# a 出句 line is the text node immediately before its "出句者 出" attribution
dealt = [texts[i - 1] for i, t in enumerate(texts)
         if t.startswith('出句者 出') and i > 0 and texts[i - 1].strip()]
if not dealt:
    bad('按了开始却没有出句（表针落点之后没有开局）'
        + ('——但测试期间屏幕睡了 %d 次，可能是环境冻结了进程' % slept if slept else ''))
for line in dealt:
    if ch and ch not in line:
        bad('出句 %r 不含令字 %r' % (line, ch))
    elif pos is not None and line.index(ch) != pos:
        bad('出句 %r 的「%s」在第%d字，规则要求第%d字' % (line, ch, line.index(ch) + 1, pos + 1))

left = re.search(r'剩余\s*(\d+)\s*句', joined)
if not left:
    bad('没读到剩余句数')
elif int(left.group(1)) <= 0:
    bad('剩余句数为 0，落点位置的池子是空的')
if not re.search(r'出句者\s*\d+\s*:\s*\d+\s*答句者', joined):
    bad('没读到比分')

print('   landed %s@%s · 出句 %s · 剩余 %s' % (
    ch or '?', ('任意' if pos is None else pos + 1), dealt[:1] or '-', left.group(1) if left else '?'))
for f in fails:
    print('  FAIL ' + f)
if fails:
    # without this a failure only says "no 出句" and tells you nothing about what was on screen
    print('  screen was: %s' % ' | '.join(t for t in texts if t.strip())[:300])
keepawake(False)
print('feihua device checks: %s' % ('ALL PASS' if not fails else 'FAIL'))
sys.exit(1 if fails else 0)