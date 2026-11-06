package com.poetry.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;

/**
 * 飞花令: pick a char, alternate verses containing it between you and the machine.
 * Modes: any position, fixed position (1..n), tail char.
 */
public class FeihuaActivity extends Activity {

    private static final int MODE_ANY = 0;
    private static final int MODE_POS = 1;
    private static final int MODE_TAIL = 2;

    private PoemDb db;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Random rnd = new Random();

    private String ch = "月";
    private Integer pos = null;
    private int mode = MODE_ANY;
    private int[] pool = new int[0];
    private final Set<Integer> used = new HashSet<Integer>();
    private final List<Entry> log = new ArrayList<Entry>();
    private BaseAdapter logAdapter;
    private TextView counter;
    private TextView charView;
    private EditText input;
    private int humanScore = 0;
    private int aiScore = 0;
    private boolean aiTurn = false;

    static class Entry {
        boolean human;
        String text, title, author;
        boolean fail;
        String note;
        Entry(boolean h, String t, String ti, String a, boolean f, String n) {
            human = h; text = t; title = ti; author = a; fail = f; note = n;
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

    private void buildUi() {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundColor(0xFFFBF7EF);

        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(android.view.Gravity.CENTER_VERTICAL);
        head.setPadding(dp(16), dp(12), dp(16), dp(4));

        charView = new TextView(this);
        charView.setTextSize(34f);
        charView.setTextColor(0xFF8B3A2B);
        charView.setTypeface(Typeface.create("serif", Typeface.BOLD));
        charView.setText("月");
        head.addView(charView);

        LinearLayout side = new LinearLayout(this);
        side.setOrientation(LinearLayout.VERTICAL);
        side.setPadding(dp(12), 0, 0, 0);
        counter = new TextView(this);
        counter.setTextSize(13f);
        counter.setTextColor(0xFF2B2B2B);
        side.addView(counter);
        TextView rule = new TextView(this);
        rule.setTextSize(12f);
        rule.setTextColor(0xFF8A8A8A);
        rule.setText("点击诗句可看全诗");
        side.addView(rule);
        head.addView(side);
        outer.addView(head);

        HorizontalScrollView hsv = new HorizontalScrollView(this);
        hsv.setHorizontalScrollBarEnabled(false);
        LinearLayout hot = new LinearLayout(this);
        hot.setPadding(dp(12), dp(4), dp(12), dp(4));
        new Thread(new Runnable() {
            public void run() {
                final List<String[]> chars = db.hotChars(24);
                ui.post(new Runnable() {
                    public void run() {
                        hot.removeAllViews();
                        for (final String[] cs : chars) {
                            Button t = new Button(FeihuaActivity.this);
                            t.setText(cs[0]);
                            t.setTextSize(15f);
                            t.setAllCaps(false);
                            t.setOnClickListener(new View.OnClickListener() {
                                public void onClick(View v) { setChar(cs[0]); }
                            });
                            hot.addView(t);
                        }
                    }
                });
            }
        }).start();
        hsv.addView(hot);
        outer.addView(hsv);

        LinearLayout rules = new LinearLayout(this);
        rules.setOrientation(LinearLayout.HORIZONTAL);
        rules.setPadding(dp(12), 0, dp(12), dp(6));
        rules.addView(ruleBtn("不限位置", new View.OnClickListener() {
            public void onClick(View v) { mode = MODE_ANY; pos = null; rebuild(); }
        }));
        for (int i = 1; i <= 7; i++) {
            final int idx = i - 1;
            rules.addView(ruleBtn("第" + i + "字", new View.OnClickListener() {
                public void onClick(View v) { mode = MODE_POS; pos = idx; rebuild(); }
            }));
        }
        rules.addView(ruleBtn("末字", new View.OnClickListener() {
            public void onClick(View v) { mode = MODE_TAIL; pos = -1; rebuild(); }
        }));
        HorizontalScrollView hsv2 = new HorizontalScrollView(this);
        hsv2.setHorizontalScrollBarEnabled(false);
        hsv2.addView(rules);
        outer.addView(hsv2);

        LinearLayout inputRow = new LinearLayout(this);
        inputRow.setOrientation(LinearLayout.HORIZONTAL);
        inputRow.setPadding(dp(12), dp(4), dp(12), dp(6));
        input = new EditText(this);
        input.setHint("轮到你：说一句含这个字的诗");
        input.setMaxLines(1);
        input.setSingleLine(true);
        input.setTextSize(15f);
        inputRow.addView(input, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        Button send = new Button(this);
        send.setText("出句");
        send.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { submit(); }
        });
        inputRow.addView(send);
        Button ai = new Button(this);
        ai.setText("求助");
        ai.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { letAi(1); }
        });
        inputRow.addView(ai);
        Button reset = new Button(this);
        reset.setText("换字");
        reset.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { pickRandomChar(); }
        });
        inputRow.addView(reset);
        outer.addView(inputRow);

        ListView list = new ListView(this);
        list.setCacheColorHint(0xFFFBF7EF);
        logAdapter = new BaseAdapter() {
            public int getCount() { return log.size(); }
            public Object getItem(int i) { return log.get(i); }
            public long getItemId(int i) { return i; }

            public View getView(int i, View cv, ViewGroup parent) {
                Entry e = log.get(i);
                LinearLayout row = new LinearLayout(FeihuaActivity.this);
                row.setOrientation(LinearLayout.VERTICAL);
                row.setPadding(dp(16), dp(10), dp(16), dp(10));
                TextView l1 = new TextView(FeihuaActivity.this);
                l1.setTextSize(18f);
                l1.setTypeface(Typeface.create("serif", Typeface.NORMAL));
                l1.setTextColor(e.fail ? 0xFFB00020 : 0xFF2B2B2B);
                l1.setText((e.human ? "你  " : "AI  ") + e.text);
                row.addView(l1);
                TextView l2 = new TextView(FeihuaActivity.this);
                l2.setTextSize(12f);
                l2.setTextColor(0xFF9A8F7E);
                l2.setText(e.fail ? e.note : "—— " + e.author + "《" + e.title + "》");
                row.addView(l2);
                return row;
            }
        };
        list.setAdapter(logAdapter);
        list.setOnItemClickListener(new android.widget.AdapterView.OnItemClickListener() {
            public void onItemClick(android.widget.AdapterView<?> p, View v, int i, long id) {
                Entry e = log.get(i);
                PoemDb.Line l = db.matchLine(e.text);
                if (l != null) {
                    Intent it = new Intent(FeihuaActivity.this, PoemActivity.class);
                    it.putExtra("poem_id", l.poemId);
                    startActivity(it);
                }
            }
        });
        outer.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(outer);
    }

    private Button ruleBtn(String label, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextSize(12f);
        b.setAllCaps(false);
        b.setOnClickListener(l);
        return b;
    }

    private void pickRandomChar() {
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
        charView.setText(ch);
        rebuild();
    }

    private void rebuild() {
        pool = new int[0];
        used.clear();
        log.clear();
        humanScore = 0;
        aiScore = 0;
        counter.setText("加载中…");
        if (logAdapter != null) logAdapter.notifyDataSetChanged();
        final String c = ch;
        final Integer p = pos;
        new Thread(new Runnable() {
            public void run() {
                final int[] ids = db.findLines(c, p);
                ui.post(new Runnable() {
                    public void run() {
                        pool = ids;
                        String where = mode == MODE_ANY ? "任意位置" : (mode == MODE_TAIL ? "句末" : "第" + (pos + 1) + "字");
                        counter.setText("「" + ch + "」" + where + "  " + ids.length + " 句可用  你 0 : 0 AI");
                        if (ids.length == 0) {
                            log.add(new Entry(false, "", "", "", true, "库中没有含这个字的句子，换个字试试"));
                            logAdapter.notifyDataSetChanged();
                        } else {
                            input.setHint("轮到你：说一句含「" + ch + "」的诗");
                        }
                    }
                });
            }
        }).start();
    }

    private void submit() {
        String raw = input.getText().toString().trim();
        if (raw.length() == 0) return;
        input.setText("");
        final String text = raw;
        new Thread(new Runnable() {
            public void run() {
                PoemDb.Line l = db.matchLine(text);
                if (l == null) {
                    failTurn(true, text, "查无此句（需与原诗完全一致，可先「求助」看范例）");
                    return;
                }
                if (mode == MODE_POS && (pos >= l.text.length() || l.text.charAt(pos) != norm1(ch))) {
                    failTurn(true, l.text, "「" + ch + "」不在第" + (pos + 1) + "字");
                    return;
                }
                if (mode == MODE_TAIL && l.text.charAt(l.text.length() - 1) != norm1(ch)) {
                    failTurn(true, l.text, "「" + ch + "」不是句末字");
                    return;
                }
                if (used.contains(l.id)) {
                    failTurn(true, l.text, "这句已经用过了");
                    return;
                }
                used.add(l.id);
                humanScore++;
                ui.post(new Runnable() {
                    public void run() {
                        log.add(new Entry(true, l.text, l.title, l.author, false, null));
                        logAdapter.notifyDataSetChanged();
                    }
                });
                ui.post(new Runnable() {
                    public void run() { score(); }
                });
                letAi(1);
            }
        }).start();
    }

    private char norm1(String c) {
        String v = db.normalize(c);
        return v != null && v.length() > 0 ? v.charAt(0) : c.charAt(0);
    }

    private void failTurn(boolean human, String text, String note) {
        final Entry e = new Entry(human, text, "", "", true, note);
        ui.post(new Runnable() {
            public void run() {
                if (human) aiScore++;
                log.add(e);
                logAdapter.notifyDataSetChanged();
                score();
            }
        });
    }

    private void letAi(int times) {
        new Thread(new Runnable() {
            public void run() {
                for (int i = 0; i < times; i++) {
                    final int id = db.randomNiceId(pool, used);
                    if (id < 0) {
                        ui.post(new Runnable() {
                            public void run() {
                                log.add(new Entry(false, "", "", "", true, "AI 认输，你赢了！"));
                                logAdapter.notifyDataSetChanged();
                                score();
                            }
                        });
                        return;
                    }
                    used.add(id);
                    final PoemDb.Line l = db.lineById(id);
                    aiScore++;
                    ui.post(new Runnable() {
                        public void run() {
                            log.add(new Entry(false, l.text, l.title, l.author, false, null));
                            logAdapter.notifyDataSetChanged();
                            score();
                        }
                    });
                    try {
                        Thread.sleep(420);
                    } catch (InterruptedException e) {
                        return;
                    }
                }
            }
        }).start();
    }

    private void score() {
        String where = mode == MODE_ANY ? "任意位置" : (mode == MODE_TAIL ? "句末" : "第" + (pos + 1) + "字");
        counter.setText("「" + ch + "」" + where + "  剩余 " + Math.max(0, pool.length - used.size())
                + " 句  你 " + humanScore + " : " + aiScore + " AI");
    }

    private int dp(int v) {
        return Math.round(getResources().getDisplayMetrics().density * v);
    }
}