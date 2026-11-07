package com.poetry.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputFilter;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;

/**
 * 飞花令. 令字 box, 出句者/答句者 name boxes, a dial that fixes where the 令字 must sit
 * (任意位置 or 第1..第7字) with 开始/停止 and 认输 in its hub, and the round log pinned to the
 * bottom where every line carries its 出处.
 *
 * The 出句者 is dealt by the machine: each round it draws a random line holding the 令字 at the
 * dial's position, never repeating one already played. The 答句者 types their line and it is
 * validated against the corpus (exact text, position, unused).
 */
public class FeihuaActivity extends Activity {

    private PoemDb db;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Random rnd = new Random();

    private String ch = "月";
    private int[] pool = new int[0];
    private final Set<Integer> used = new HashSet<Integer>();
    private final List<Entry> log = new ArrayList<Entry>();

    private DialView dial;
    private EditText charInput;
    private EditText askerName;
    private EditText answerName;
    private EditText answerInput;
    private TextView counter;
    private Button startBtn;
    private ListView logList;
    private BaseAdapter logAdapter;

    private int askerScore = 0;
    private int answerScore = 0;
    private boolean running = false;
    private boolean awaitingAnswer = false;

    static class Entry {
        String who, text, title, author, note;
        boolean fail;
        Entry(String who, String text, String title, String author, boolean fail, String note) {
            this.who = who; this.text = text; this.title = title;
            this.author = author; this.fail = fail; this.note = note;
        }
    }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        db = PoemDb.get(this);
        db.open();
        buildUi();
        setChar("月");
    }

    // ------------------------------------------------------------------ UI

    private void buildUi() {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundColor(0xFFFBF7EF);

        outer.addView(head());
        outer.addView(charRow());
        outer.addView(nameRow());
        outer.addView(dialBlock());
        outer.addView(answerRow());

        counter = tv(13f, 0xFF2B2B2B, "");
        counter.setPadding(dp(16), 0, dp(16), dp(6));
        outer.addView(counter);

        // ⑤ the log takes the remaining height and scrolls once rounds overflow it.
        logList = new ListView(this);
        logList.setCacheColorHint(0xFFFBF7EF);
        logList.setStackFromBottom(true);
        logAdapter = new BaseAdapter() {
            public int getCount() { return log.size(); }
            public Object getItem(int i) { return log.get(i); }
            public long getItemId(int i) { return i; }

            public View getView(int i, View cv, ViewGroup parent) {
                Entry e = log.get(i);
                LinearLayout row = new LinearLayout(FeihuaActivity.this);
                row.setOrientation(LinearLayout.VERTICAL);
                row.setPadding(dp(16), dp(9), dp(16), dp(9));

                TextView l1 = tv(18f, e.fail ? 0xFFB00020 : 0xFF2B2B2B,
                        e.text.length() > 0 ? e.text : e.note);
                l1.setTypeface(Typeface.create("serif", Typeface.NORMAL));
                row.addView(l1);

                if (e.text.length() > 0) {
                    row.addView(tv(12f, 0xFF9A8F7E, e.who + "　—— " + e.author + "《" + e.title + "》"));
                } else if (!e.fail) {
                    row.addView(tv(12f, 0xFF9A8F7E, e.who));
                }
                return row;
            }
        };
        logList.setAdapter(logAdapter);
        logList.setOnItemClickListener(new android.widget.AdapterView.OnItemClickListener() {
            public void onItemClick(android.widget.AdapterView<?> p, View v, int i, long id) {
                PoemDb.Line l = db.matchLine(log.get(i).text);
                if (l != null) {
                    Intent it = new Intent(FeihuaActivity.this, PoemActivity.class);
                    it.putExtra("poem_id", l.poemId);
                    startActivity(it);
                }
            }
        });
        outer.addView(logList, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(outer);
    }

    private View head() {
        LinearLayout h = new LinearLayout(this);
        h.setOrientation(LinearLayout.HORIZONTAL);
        h.setGravity(android.view.Gravity.CENTER_VERTICAL);
        h.setPadding(dp(16), dp(10), dp(16), dp(2));
        h.addView(tv(22f, 0xFF8B3A2B, "飞花令"));
        TextView tip = tv(11f, 0xFF8A8A8A, "轮盘定令字位置 · 点诗句看全诗");
        tip.setPadding(dp(10), dp(4), 0, 0);
        h.addView(tip);
        return h;
    }

    private View charRow() {
        LinearLayout r = row(dp(4), dp(6));
        r.addView(tv(13f, 0xFF6B5B45, "令字"));
        charInput = edit("月", 1);
        charInput.setTextSize(19f);
        charInput.setTypeface(Typeface.create("serif", Typeface.BOLD));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(56), ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(dp(8), 0, dp(6), 0);
        r.addView(charInput, lp);
        r.addView(btn("定字", new View.OnClickListener() {
            public void onClick(View v) { setChar(charInput.getText().toString().trim()); }
        }));
        r.addView(btn("换字", new View.OnClickListener() {
            public void onClick(View v) { randomChar(); }
        }));
        return r;
    }

    private View nameRow() {
        LinearLayout r = row(dp(2), dp(6));
        r.addView(tv(13f, 0xFF6B5B45, "出句者"));
        askerName = edit("系统", 8);
        LinearLayout.LayoutParams a = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        a.setMargins(dp(6), 0, dp(10), 0);
        r.addView(askerName, a);
        r.addView(tv(13f, 0xFF6B5B45, "答句者"));
        answerName = edit("我", 8);
        LinearLayout.LayoutParams n = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        n.setMargins(dp(6), 0, 0, 0);
        r.addView(answerName, n);
        return r;
    }

    private View dialBlock() {
        FrameLayout box = new FrameLayout(this);
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(236));
        blp.setMargins(0, dp(2), 0, dp(2));
        box.setLayoutParams(blp);

        dial = new DialView(this, null);
        box.addView(dial, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        dial.setListener(new DialView.Listener() {
            public void onSlotPicked(int slot) { rebuild(); }
        });

        // ③ centre controls float in the dial's hole; DialView.onTouchEvent ignores that area.
        LinearLayout hub = new LinearLayout(this);
        hub.setOrientation(LinearLayout.VERTICAL);
        hub.setGravity(android.view.Gravity.CENTER);
        box.addView(hub, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        startBtn = btn("开始", new View.OnClickListener() {
            public void onClick(View v) { toggle(); }
        });
        hub.addView(startBtn);
        Button quit = btn("认输", new View.OnClickListener() {
            public void onClick(View v) { giveUp(); }
        });
        quit.setTextColor(0xFF8B3A2B);
        hub.addView(quit);
        return box;
    }

    private View answerRow() {
        LinearLayout r = row(dp(4), dp(6));
        answerInput = edit("答句：输入含令字的完整诗句", 40);
        r.addView(answerInput, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        r.addView(btn("答句", new View.OnClickListener() {
            public void onClick(View v) { submit(); }
        }));
        r.addView(btn("提示", new View.OnClickListener() {
            public void onClick(View v) { hint(); }
        }));
        return r;
    }

    private LinearLayout row(int padTop, int padBottom) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(android.view.Gravity.CENTER_VERTICAL);
        l.setPadding(dp(16), padTop, dp(16), padBottom);
        return l;
    }

    private TextView tv(float sp, int color, String text) {
        TextView t = new TextView(this);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setText(text);
        return t;
    }

    private EditText edit(String hint, int maxLen) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setMaxLines(1);
        e.setSingleLine(true);
        e.setTextSize(14f);
        e.setFilters(new InputFilter[]{new InputFilter.LengthFilter(maxLen)});
        return e;
    }

    private Button btn(String label, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextSize(12f);
        b.setAllCaps(false);
        b.setMinHeight(0);
        b.setPadding(dp(14), dp(4), dp(14), dp(4));
        b.setOnClickListener(l);
        return b;
    }

    // ---------------------------------------------------------------- rules

    private Integer rule() { return DialView.posOf(dial == null ? 0 : dial.getSelected()); }

    private String ruleText() {
        Integer p = rule();
        return p == null ? "任意位置" : "第" + (p.intValue() + 1) + "字";
    }

    private void randomChar() {
        new Thread(new Runnable() {
            public void run() {
                final List<String[]> cs = db.hotChars(60);
                ui.post(new Runnable() {
                    public void run() {
                        if (cs.isEmpty()) return;
                        setChar(cs.get(rnd.nextInt(Math.min(cs.size(), 40)))[0]);
                    }
                });
            }
        }).start();
    }

    private void setChar(String c) {
        if (c == null || c.length() == 0) return;
        ch = String.valueOf(c.charAt(0));
        if (charInput != null) {
            charInput.setText(ch);
            charInput.setSelection(ch.length());
        }
        rebuild();
    }

    private void rebuild() {
        pool = new int[0];
        used.clear();
        log.clear();
        askerScore = 0;
        answerScore = 0;
        running = false;
        awaitingAnswer = false;
        startBtn.setText("开始");
        counter.setText("加载中…");
        if (logAdapter != null) logAdapter.notifyDataSetChanged();
        final String c = ch;
        final Integer p = rule();
        new Thread(new Runnable() {
            public void run() {
                final int[] ids = db.findLines(c, p);
                ui.post(new Runnable() {
                    public void run() {
                        pool = ids;
                        score();
                        if (ids.length == 0) {
                            log.add(new Entry("提示", "", "", "", true,
                                    "库中没有「" + ch + "」在" + ruleText() + "的句子，换个令字或转一下轮盘"));
                            logAdapter.notifyDataSetChanged();
                        } else {
                            answerInput.setHint("答句：「" + ch + "」需在" + ruleText());
                        }
                    }
                });
            }
        }).start();
    }

    // ----------------------------------------------------------------- game

    private void toggle() {
        if (running) {
            running = false;
            startBtn.setText("继续");
            note("已暂停");
            return;
        }
        if (pool.length == 0) { note("池子空了，换令字或位置再开始"); rebuild(); return; }
        running = true;
        startBtn.setText("停止");
        if (!awaitingAnswer) ask();
    }

    /** ④ deal the 出句: random unused line that satisfies the dial's position rule. */
    private void ask() {
        new Thread(new Runnable() {
            public void run() {
                final int id = db.randomNiceId(pool, used);
                if (id < 0) {
                    ui.post(new Runnable() {
                        public void run() {
                            running = false;
                            awaitingAnswer = false;
                            startBtn.setText("开始");
                            log.add(new Entry(asker(), "", "", "", true,
                                    "出句者无句可出，" + answerName() + " 赢了！"));
                            logAdapter.notifyDataSetChanged();
                            scrollDown();
                            score();
                        }
                    });
                    return;
                }
                used.add(id);
                final PoemDb.Line l = db.lineById(id);
                askerScore++;
                ui.post(new Runnable() {
                    public void run() {
                        awaitingAnswer = true;
                        log.add(new Entry(asker() + " 出", l.text, l.title, l.author, false, null));
                        logAdapter.notifyDataSetChanged();
                        scrollDown();
                        score();
                    }
                });
            }
        }).start();
    }

    private void submit() {
        final String raw = answerInput.getText().toString().trim();
        if (raw.length() == 0) return;
        if (!awaitingAnswer) { note("先按「开始」让出句者出句"); return; }
        answerInput.setText("");
        new Thread(new Runnable() {
            public void run() {
                PoemDb.Line l = db.matchLine(raw);
                if (l == null) { reject(raw, "查无此句（需与原诗完全一致，可先按「提示」）"); return; }
                Integer p = rule();
                if (p != null && (p.intValue() >= l.text.length()
                        || l.text.charAt(p.intValue()) != norm1(ch))) {
                    reject(l.text, "「" + ch + "」不在" + ruleText());
                    return;
                }
                if (used.contains(l.id)) { reject(l.text, "这句已经用过了"); return; }
                used.add(l.id);
                answerScore++;
                awaitingAnswer = false;
                ui.post(new Runnable() {
                    public void run() {
                        log.add(new Entry(answerName() + " 答", l.text, l.title, l.author, false, null));
                        logAdapter.notifyDataSetChanged();
                        scrollDown();
                        score();
                    }
                });
                if (running) ask();
            }
        }).start();
    }

    /** Keep the verse in the box for correction; a rejection scores nothing. */
    private void reject(final String text, final String why) {
        ui.post(new Runnable() {
            public void run() {
                askerScore++;
                log.add(new Entry(answerName() + " 答", text, "", "", true, why));
                logAdapter.notifyDataSetChanged();
                scrollDown();
                score();
                answerInput.setText(text);
                answerInput.setSelection(text.length());
            }
        });
    }

    /** Offer one legal line without consuming it, so the hint earns no point. */
    private void hint() {
        new Thread(new Runnable() {
            public void run() {
                final int id = db.randomNiceId(pool, used);
                if (id < 0) { note("没有可提示的句子了"); return; }
                final PoemDb.Line l = db.lineById(id);
                ui.post(new Runnable() {
                    public void run() {
                        answerInput.setText(l.text);
                        answerInput.setSelection(l.text.length());
                        note("提示：" + l.text + "　—— " + l.author + "《" + l.title + "》");
                    }
                });
            }
        }).start();
    }

    private void giveUp() {
        running = false;
        awaitingAnswer = false;
        startBtn.setText("开始");
        log.add(new Entry(answerName(), "", "", "", true, "答句者认输，出句者胜"));
        logAdapter.notifyDataSetChanged();
        scrollDown();
        score();
    }

    private void note(String s) {
        ui.post(new Runnable() {
            public void run() {
                log.add(new Entry("提示", s, "", "", false, null));
                logAdapter.notifyDataSetChanged();
                scrollDown();
            }
        });
    }

    private void score() {
        int left = Math.max(0, pool.length - used.size());
        counter.setText("「" + ch + "」" + ruleText() + "  剩余 " + left + " 句　"
                + asker() + " " + askerScore + " : " + answerScore + " " + answerName());
    }

    private void scrollDown() {
        if (!log.isEmpty()) logList.setSelection(log.size() - 1);
    }

    private String asker() { return orDefault(askerName.getText().toString(), "出句者"); }

    private String answerName() { return orDefault(answerName.getText().toString(), "答句者"); }

    private String orDefault(String s, String d) {
        String t = s.trim();
        return t.length() == 0 ? d : t;
    }

    private char norm1(String c) {
        String v = db.normalize(c);
        return v != null && v.length() > 0 ? v.charAt(0) : c.charAt(0);
    }

    private int dp(int v) {
        return Math.round(getResources().getDisplayMetrics().density * v);
    }
}