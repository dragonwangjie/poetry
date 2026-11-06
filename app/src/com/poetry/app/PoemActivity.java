package com.poetry.app;
import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.util.ArrayList;
import java.util.List;
/** Full text of one poem: every 分句 on its own centered row, hanzi with pinyin ruby. */
public class PoemActivity extends Activity {
    private static final int BG = 0xFFFBF7EF;
    private static final int INK = 0xFF26221C;
    private static final int RUBY = 0xFF9A8A6E;
    private static final int CARD = 0xFFFFFFFF;
    private static final int LINE = 0xFFEBE2D2;
    /** Clause marks that end a displayed row. */
    private static final String BREAK = "，。！？；：,!?;:\n";
    private PoemDb db;
    private final List<PinyinText> rubyViews = new ArrayList<PinyinText>();
    private boolean pinyinOn = true;
    private LinearLayout body;
    private TextView pyToggle;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        db = PoemDb.get(this);
        db.open();
        int id = getIntent().getIntExtra("poem_id", -1);
        final PoemDb.Poem p = db.poemById(id);
        if (p == null) {
            Toast.makeText(this, "未找到该作品", Toast.LENGTH_SHORT).show();
            finish();
            return;
        }
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(BG);
        body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(18), dp(16), dp(18), dp(26));
        sv.addView(body);
        setContentView(sv);

        addToolbar();
        addTitle(p);
        addMeta(p);
        addPrologue(p);
        addBody(p);
        addTags(p);
        addCard("译文", p.trans, 16f, 0xFF3A362E, 1.62f);
        addCard("注释", p.note, 14f, 0xFF5C5344, 1.5f);
        addCard("简介", p.intro, 14f, 0xFF5C5344, 1.5f);
        addActions(p);
    }

    /** Pinyin on/off, right-aligned above the title. */
    private void addToolbar() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.END);
        pyToggle = new TextView(this);
        pyToggle.setTextSize(12f);
        pyToggle.setTextColor(0xFF8B6A45);
        pyToggle.setText(pinyinOn ? "拼音：开" : "拼音：关");
        pyToggle.setPadding(dp(12), dp(6), dp(12), dp(6));
        pyToggle.setBackgroundResource(android.R.drawable.btn_default);
        pyToggle.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                pinyinOn = !pinyinOn;
                pyToggle.setText(pinyinOn ? "拼音：开" : "拼音：关");
                for (PinyinText t : rubyViews) t.setPinyinVisible(pinyinOn);
            }
        });
        row.addView(pyToggle);
        body.addView(row);
    }

    private void addTitle(PoemDb.Poem p) {
        String title = p.title == null || p.title.length() == 0 ? "（无题）" : p.title;
        PinyinText t = new PinyinText(this);
        t.setBold(true);
        t.setTextSize(26f, 12f, 14f);
        t.setColors(INK, RUBY);
        t.setPinyinVisible(pinyinOn);
        t.setContent(title, p.titlePy);
        t.setPadding(0, dp(10), 0, dp(2));
        body.addView(t);
        rubyViews.add(t);
        View rule = new View(this);
        rule.setBackgroundColor(LINE);
        LinearLayout.LayoutParams rl = new LinearLayout.LayoutParams(dp(46), dp(2));
        rl.gravity = Gravity.CENTER_HORIZONTAL;
        rl.topMargin = dp(10);
        rule.setLayoutParams(rl);
        body.addView(rule);
    }

    private void addMeta(PoemDb.Poem p) {
        StringBuilder ms = new StringBuilder();
        ms.append(p.author == null ? "" : p.author);
        if (p.source != null && p.source.length() > 0) ms.append(" · ").append(p.source);
        if (p.rhythmic != null && p.rhythmic.length() > 0)
            // 天净沙 is a 曲牌, not a 词牌: labelling every rhythmic 词牌 is wrong for 元曲.
            ms.append(" · ").append("曲".equals(p.form) ? "曲牌" : "词牌")
              .append("「").append(p.rhythmic).append("」");
        TextView meta = new TextView(this);
        meta.setTextSize(13f);
        meta.setTextColor(0xFF8A7B66);
        meta.setGravity(Gravity.CENTER_HORIZONTAL);
        meta.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        meta.setText(ms);
        meta.setPadding(0, dp(12), 0, dp(16));
        body.addView(meta);
    }

    private void addPrologue(PoemDb.Poem p) {
        if (p.prologue == null || p.prologue.trim().length() == 0) return;
        TextView pr = new TextView(this);
        pr.setTextSize(13.5f);
        pr.setTextColor(0xFF6A5F4E);
        pr.setLineSpacing(0, 1.45f);
        pr.setTypeface(Typeface.create("serif", Typeface.NORMAL));
        pr.setText("序：" + p.prologue.trim());
        pr.setPadding(dp(10), dp(10), dp(10), dp(10));
        pr.setBackground(card(0xFFF6F1E6, 0xFFF6F1E6));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(16);
        pr.setLayoutParams(lp);
        body.addView(pr);
    }

    /** One row per 分句 so a verse never shares a line with the next and never gets clipped. */
    private void addBody(PoemDb.Poem p) {
        String[] lines = (p.body == null ? "" : p.body).split("\n");
        String[] pys = (p.py == null || p.py.trim().length() == 0)
                ? new String[0] : p.py.trim().split("\n");
        int k = 0;
        for (String raw : lines) {
            String line = raw.trim();
            if (line.length() == 0) continue;
            String py = k < pys.length ? pys[k] : "";
            k++;
            for (int[] seg : splitClauses(line)) {
                String text = line.substring(seg[0], seg[1]).trim();
                if (text.length() == 0) continue;
                String syl = sylRange(py, seg[0], seg[1], line);
                PinyinText t = new PinyinText(this);
                int n = hanCount(text);
                float want = n > 20 ? 19f : 24f;
                float min = n > 20 ? 10.5f : 13f;
                t.setTextSize(want, Math.min(12f, want * 0.5f), min);
                t.setColors(INK, RUBY);
                t.setPinyinVisible(pinyinOn);
                t.setContent(text, syl);
                t.setPadding(0, dp(6), 0, dp(6));
                body.addView(t);
                rubyViews.add(t);
            }
        }
    }
    /** Clause ranges [from,to) of {@code line}, breaking on {@link #BREAK}. */
    static List<int[]> splitClauses(String line) {
        ArrayList<int[]> out = new ArrayList<int[]>();
        int start = 0;
        int hanInClause = 0;
        for (int i = 0; i < line.length(); i++) {
            char ch = line.charAt(i);
            if (PinyinText.han(ch)) hanInClause++;
            if (BREAK.indexOf(ch) < 0) continue;
            // Only break where there is something to show; keep tiny fragments attached.
            if (hanInClause == 0) continue;
            out.add(new int[]{start, i + 1});
            start = i + 1;
            hanInClause = 0;
        }
        if (start < line.length()) {
            String rest = line.substring(start).trim();
            if (rest.length() > 0) out.add(new int[]{start, line.length()});
        }
        if (out.isEmpty() && line.trim().length() > 0) {
            out.add(new int[]{0, line.length()});
        }
        return out;
    }
    /** Pick the syllables belonging to [from,to) by counting han characters on both sides. */
    private static String sylRange(String pinyin, int from, int to, String line) {
        if (pinyin == null || pinyin.trim().length() == 0) return "";
        String[] syl = pinyin.trim().split("\\s+");
        int a = 0;
        int b = 0;
        for (int i = 0; i < to; i++) {
            if (!PinyinText.han(line.charAt(i))) continue;
            if (i < from) a++;
            b++;
        }
        if (a >= syl.length) return "";
        StringBuilder sb = new StringBuilder();
        int end = Math.min(b, syl.length);
        for (int i = a; i < end; i++) {
            if (i > a) sb.append(' ');
            sb.append(syl[i]);
        }
        return sb.toString();
    }
    private static int hanCount(String s) {
        int n = 0;
        for (int i = 0; i < s.length(); i++) {
            if (PinyinText.han(s.charAt(i))) n++;
        }
        return n;
    }

    private void addTags(PoemDb.Poem p) {
        if (p.tags == null || p.tags.length() < 3) return;
        TextView tg = new TextView(this);
        tg.setTextSize(12f);
        tg.setTextColor(0xFFA79C88);
        tg.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        tg.setText(p.tags.replace("[", "").replace("]", "").replace("\"", "").replace(",", "  "));
        tg.setPadding(dp(2), dp(16), 0, 0);
        body.addView(tg);
    }

    /** Labelled card for 译文 / 注释 / 简介. */
    private void addCard(String label, String content, float size, int color, float spacing) {
        if (content == null || content.trim().length() == 0) return;
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setBackground(card(CARD, LINE));
        box.setPadding(dp(14), dp(12), dp(14), dp(14));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(14);
        box.setLayoutParams(lp);

        TextView head = new TextView(this);
        head.setTextSize(13f);
        head.setTextColor(0xFF8B3A2B);
        head.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        head.setText(label);
        head.setPadding(0, 0, 0, dp(8));
        box.addView(head);

        View sep = new View(this);
        sep.setBackgroundColor(LINE);
        box.addView(sep, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(1)));

        TextView txt = new TextView(this);
        txt.setTextSize(size);
        txt.setTextColor(color);
        txt.setLineSpacing(0, spacing);
        txt.setTypeface(Typeface.create("serif", Typeface.NORMAL));
        txt.setText(content.trim());
        txt.setPadding(0, dp(9), 0, 0);
        box.addView(txt);
        body.addView(box);
    }

    private void addActions(final PoemDb.Poem p) {
        LinearLayout acts = new LinearLayout(this);
        acts.setOrientation(LinearLayout.HORIZONTAL);
        acts.setPadding(0, dp(22), 0, 0);
        TextView copy = action("复制全文");
        copy.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                cm.setPrimaryClip(ClipData.newPlainText("poem", p.title + "\n" + p.author + "\n" + p.body));
                Toast.makeText(PoemActivity.this, "已复制", Toast.LENGTH_SHORT).show();
            }
        });
        acts.addView(copy);
        TextView toAuthor = action("看TA的全部作品");
        toAuthor.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                Intent it = new Intent(PoemActivity.this, AuthorActivity.class);
                it.putExtra("author_id", Integer.parseInt(p.authorId));
                startActivity(it);
            }
        });
        acts.addView(toAuthor);
        body.addView(acts);
    }

    private GradientDrawable card(int fill, int stroke) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(fill);
        d.setCornerRadius(dp(10));
        d.setStroke(Math.max(1, dp(1)), stroke);
        return d;
    }
    private TextView action(String label) {
        TextView t = new TextView(this);
        t.setTextSize(14f);
        t.setTextColor(0xFF8B3A2B);
        t.setText(label);
        t.setPadding(dp(14), dp(8), dp(14), dp(8));
        t.setBackgroundResource(android.R.drawable.btn_default);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.rightMargin = dp(10);
        t.setLayoutParams(lp);
        return t;
    }
    private int dp(int v) {
        return Math.round(getResources().getDisplayMetrics().density * v);
    }
}