package com.poetry.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

/** Browse authors, and search everything -- poet names, poem titles, poem text. */
public class MainActivity extends Activity {

    /** Rows a search costs before the list stops growing: authors paginate, poems do not. */
    private static final int AUTHOR_PAGE = 60;
    private static final int POEM_CAP = 12;

    /** One list row: a PoemDb.Author, a PoemDb.VerseHit, or a String section header. */
    private final List<Object> items = new ArrayList<Object>();
    /** The two sources keep their own lists so the slower one cannot reorder the page. */
    private final List<Object> authorRows = new ArrayList<Object>();
    private final List<Object> poemRows = new ArrayList<Object>();
    private PoemDb adb;
    private BaseAdapter adapter;
    private ListView list;
    private TextView status;
    private ProgressBar progress;
    private LinearLayout root;
    private String dynasty = "";
    private String query = "";
    private int offset = 0;
    private boolean loading = false;
    private boolean poemsDone = true;
    /** Stop asking for author pages once a short page says there are no more. */
    private boolean authorsExhausted = false;
    /** Guards against a slow query for an older keystroke landing after a newer one. */
    private int seq = 0;
    private final Runnable pendingReload = new Runnable() {
        public void run() { reload(); }
    };
    private final Handler ui = new Handler(Looper.getMainLooper());
    private static final String[] DYNASTIES = {"全部", "唐", "宋", "魏晋", "南北朝", "五代", "元", "明", "清", "先秦", "汉"};

    private EditText search;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        adb = PoemDb.get(this);
        buildUi();
        if (adb.isReady()) {
            onDbReady();
        } else {
            installDb();
        }
        // Test entry point (the box itself needs a soft keyboard, which adb cannot type
        // Chinese into): adb shell am start -n com.poetry.app/.MainActivity --es query 静夜思
        String preset = getIntent().getStringExtra("query");
        if (preset != null && preset.trim().length() > 0 && adb.isReady()) {
            search.setText(preset);
        }
    }

    private void buildUi() {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundColor(0xFFFBF7EF);

        TextView title = new TextView(this);
        title.setText(R.string.app_name);
        title.setTextSize(20f);
        title.setTextColor(0xFF2B2B2B);
        title.setPadding(dp(16), dp(12), dp(16), dp(6));
        outer.addView(title);

        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.HORIZONTAL);
        top.setPadding(dp(12), 0, dp(12), dp(6));
        search = new EditText(this);
        search.setHint(R.string.search_hint);
        search.setTextSize(16f);
        search.setMaxLines(1);
        search.setSingleLine(true);
        search.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        search.setLayoutParams(lp);
        top.addView(search);
        // No separate 查诗词 screen: the one box below searches poets, titles and text at
        // once (see reload), which is what the reader wants -- they do not know which of the
        // three they are remembering.
        Button go = new Button(this);
        go.setText("飞花令");
        go.setAllCaps(false);
        go.setTextSize(13f);
        go.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (!adb.isReady()) {
                    toast("书库尚在解压，请稍候");
                    return;
                }
                startActivity(new Intent(MainActivity.this, FeihuaActivity.class));
            }
        });
        top.addView(go);
        outer.addView(top);

        HorizontalScrollView hsv = new HorizontalScrollView(this);
        hsv.setHorizontalScrollBarEnabled(false);
        LinearLayout chips = new LinearLayout(this);
        chips.setPadding(dp(12), 0, dp(12), dp(6));
        for (String d : DYNASTIES) {
            final String dd = "全部".equals(d) ? "" : d;
            Button b2 = new Button(this);
            b2.setText(d);
            b2.setAllCaps(false);
            b2.setTextSize(13f);
            b2.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) {
                    dynasty = dd;
                    // A pending debounced reload would re-run with the new dynasty anyway, but
                    // dropping it keeps the list from flickering twice in a row.
                    ui.removeCallbacks(pendingReload);
                    reload();
                }
            });
            chips.addView(b2);
        }
        hsv.addView(chips);
        outer.addView(hsv);

        status = new TextView(this);
        status.setTextSize(12f);
        status.setTextColor(0xFF8A8A8A);
        status.setPadding(dp(16), dp(2), dp(16), dp(2));
        outer.addView(status);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        outer.addView(progress);

        list = new ListView(this);
        list.setCacheColorHint(0xFFFBF7EF);
        adapter = new BaseAdapter() {
            public int getCount() { return items.size(); }
            public Object getItem(int i) { return items.get(i); }
            /** Rows mix three types with unrelated ids, so position is the only stable key. */
            public long getItemId(int i) { return i; }
            /** Section headers are not clickable. */
            public boolean areAllItemsEnabled() { return false; }
            public boolean isEnabled(int i) { return !(items.get(i) instanceof String); }

            public View getView(int i, View cv, ViewGroup parent) {
                Object row = items.get(i);
                if (row instanceof String) return header((String) row);
                if (row instanceof PoemDb.VerseHit) return poemRow((PoemDb.VerseHit) row);
                return authorRow((PoemDb.Author) row);
            }
        };
        list.setAdapter(adapter);
        list.setOnItemClickListener(new android.widget.AdapterView.OnItemClickListener() {
            public void onItemClick(android.widget.AdapterView<?> p, View v, int pos, long id) {
                Object row = items.get(pos);
                Intent it;
                if (row instanceof PoemDb.VerseHit) {
                    it = new Intent(MainActivity.this, PoemActivity.class);
                    it.putExtra("poem_id", ((PoemDb.VerseHit) row).poemId);
                } else {
                    it = new Intent(MainActivity.this, AuthorActivity.class);
                    it.putExtra("author_id", ((PoemDb.Author) row).id);
                }
                startActivity(it);
            }
        });
        list.setOnScrollListener(new android.widget.AbsListView.OnScrollListener() {
            public void onScroll(android.widget.AbsListView v, int first, int last, int total) {
                if (total > 0 && first + last >= total - 12) loadMore();
            }
            public void onScrollStateChanged(android.widget.AbsListView v, int s) { }
        });
        root = outer;
        outer.addView(list, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(outer);

        search.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            public void onTextChanged(CharSequence s, int a, int b, int c) { }
            public void afterTextChanged(Editable s) {
                query = s.toString();
                // Debounced: a title LIKE plus the posting-list verse engine is a few hundred
                // milliseconds, and every keystroke used to fire one of those.
                ui.removeCallbacks(pendingReload);
                ui.postDelayed(pendingReload, 220);
            }
        });
        search.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            public boolean onEditorAction(TextView v, int actionId, android.view.KeyEvent event) {
                ui.removeCallbacks(pendingReload);
                android.view.inputmethod.InputMethodManager imm =
                        (android.view.inputmethod.InputMethodManager)
                                getSystemService(INPUT_METHOD_SERVICE);
                if (imm != null) imm.hideSoftInputFromWindow(v.getWindowToken(), 0);
                reload();
                return true;
            }
        });
    }

    private View authorRow(PoemDb.Author a) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setPadding(dp(16), dp(12), dp(16), dp(12));
        TextView l1 = new TextView(this);
        l1.setTextSize(17f);
        l1.setTextColor(0xFF2B2B2B);
        l1.setText(a.name + "  ·  " + (a.dynasty == null || a.dynasty.length() == 0 ? "？" : a.dynasty)
                + "  ·  " + a.poemCount + " 首");
        row.addView(l1);
        String bio = a.shortBio != null && a.shortBio.length() > 0 ? a.shortBio : a.bio;
        if (bio != null && bio.length() > 0) {
            TextView l2 = new TextView(this);
            l2.setTextSize(12f);
            l2.setTextColor(0xFF8A8A8A);
            l2.setMaxLines(2);
            l2.setText(bio);
            row.addView(l2);
        }
        return row;
    }
    /**
     * A poem hit. The line that matched is the headline for a text hit (that is what the
     * reader typed) but the title is the headline for a title hit, and then repeating it as
     * 《静夜思》 静夜思 李白 would read wrong, so the attribution line drops the brackets.
     */
    private View poemRow(PoemDb.VerseHit h) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setPadding(dp(16), dp(12), dp(16), dp(12));
        TextView l1 = new TextView(this);
        l1.setTextSize(17f);
        l1.setTextColor(0xFF2B2B2B);
        l1.setMaxLines(2);
        l1.setText(h.byTitle ? "《" + h.title + "》" : h.text);
        row.addView(l1);
        TextView l2 = new TextView(this);
        l2.setTextSize(12f);
        l2.setTextColor(0xFF8B3A2B);
        l2.setMaxLines(1);
        l2.setText((h.byTitle ? "" : "《" + h.title + "》 ")
                + h.author + (h.dynasty == null || h.dynasty.length() == 0 ? "" : " · " + h.dynasty)
                + hitTag(h));
        row.addView(l2);
        return row;
    }
    /** Why this row matched, so a fuzzy hit is not mistaken for the exact thing. */
    private static String hitTag(PoemDb.VerseHit h) {
        if (h.byTitle) return "";
        switch (h.kind) {
            case 0: return "";
            case 1: return "  · 含此句";
            case 2: return "  · 字序相同";
            case 3: return "  · 相邻两句";
            default: return "  · 近似（原文或有异文）";
        }
    }
    private View header(String label) {
        TextView t = new TextView(this);
        t.setText(label);
        t.setTextSize(12f);
        t.setTextColor(0xFF8A7B66);
        t.setPadding(dp(16), dp(10), dp(16), dp(2));
        t.setTypeface(android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.BOLD));
        return t;
    }

    private void installDb() {
        status.setText("首次启动：解压内置书库（约 100MB），请稍候…");
        progress.setVisibility(View.VISIBLE);
        new Thread(new Runnable() {
            public void run() {
                try {
                    adb.install(new PoemDb.Progress() {
                        public void onProgress(final int pct) {
                            ui.post(new Runnable() {
                                public void run() { progress.setProgress(pct); }
                            });
                        }
                    });
                    ui.post(new Runnable() {
                        public void run() { onDbReady(); }
                    });
                } catch (final Exception e) {
                    ui.post(new Runnable() {
                        public void run() {
                            status.setText("解压失败：" + e.getMessage());
                            toast("解压失败 " + e);
                        }
                    });
                }
            }
        }).start();
    }

    private void onDbReady() {
        progress.setVisibility(View.GONE);
        adb.open();
        final int p = adb.count("poem");
        final int a = adb.count("author");
        final int l = adb.count("line");
        status.setText(a + " 位作者 · " + p + " 首 · " + l + " 句可检索");
        reload();
    }

    private void reload() {
        if (!adb.isReady()) return;
        final int mySeq = ++seq;
        authorRows.clear();
        poemRows.clear();
        offset = 0;
        loading = false;
        authorsExhausted = false;
        // Both poem engines ignore queries shorter than two characters, so do not pay for
        // them on a single keystroke like 李.
        poemsDone = query.trim().length() < 2;
        publish();
        loadMore();
        if (!poemsDone) loadPoems(mySeq);
    }
    /**
     * Compose the visible rows from the two sources in a fixed order: poets, then poems.
     *
     * Both are fetched asynchronously, so they are kept in separate lists and joined here --
     * whichever finishes first cannot reorder the page. Poets lead because the box sits on
     * the poet page and a short query (李白) usually means the person; for the case that
     * matters more -- a title or a half-remembered line -- no poet matches at all, so the
     * poems land at the top anyway.
     */
    private void publish() {
        items.clear();
        boolean both = !poemRows.isEmpty() && !authorRows.isEmpty()
                && query.trim().length() >= 2;
        // Headers only when the two groups are mixed on one screen; the plain browse list
        // (empty box) is all poets and would just gain noise.
        if (both) items.add("诗人");
        items.addAll(authorRows);
        if (!poemRows.isEmpty()) {
            if (both) items.add("诗词");
            items.addAll(poemRows);
        }
        adapter.notifyDataSetChanged();
        if (query.trim().length() == 0) return;
        if (!poemsDone) {
            status.setText("正在检索诗词…");
            return;
        }
        int poets = authorRows.size();
        // The poem engines (title LIKE, and the posting-list verse matcher) both need two
        // characters, so a single-character query legitimately has no poem results -- saying
        // "0 首诗词" would read as a bug rather than as a rule of the search.
        if (query.trim().length() < 2) {
            status.setText(poets + " 位诗人 · 搜诗词请至少输入两个字");
            return;
        }
        // Both counts are only meaningful once the poem pass has landed; reporting 0 首诗词
        // while it is still running reads as "nothing found" and the reader stops typing.
        int poems = poemRows.size();
        String tail = (poems == 0 && poets == 0) ? "：换个说法或少输几个字试试" : "";
        status.setText(poems + " 首诗词 · " + poets + " 位诗人" + tail);
    }
    private void loadPoems(final int mySeq) {
        new Thread(new Runnable() {
            public void run() {
                final List<PoemDb.VerseHit> found = adb.searchAll(query, POEM_CAP, dynasty);
                ui.post(new Runnable() {
                    public void run() {
                        if (mySeq != seq) return;   // a newer query already took over
                        poemRows.addAll(found);
                        poemsDone = true;
                        publish();
                    }
                });
            }
        }).start();
    }

    private synchronized void loadMore() {
        if (loading || authorsExhausted) return;
        loading = true;
        final int off = offset;
        final int mySeq = seq;
        new Thread(new Runnable() {
            public void run() {
                final List<PoemDb.Author> page = adb.searchAuthors(query, dynasty, AUTHOR_PAGE, off);
                ui.post(new Runnable() {
                    public void run() {
                        if (mySeq != seq) { loading = false; return; }
                        authorRows.addAll(page);
                        offset += page.size();
                        if (page.size() < AUTHOR_PAGE) authorsExhausted = true;
                        publish();
                        loading = false;
                    }
                });
            }
        }).start();
    }

    private int dp(int v) {
        return Math.round(getResources().getDisplayMetrics().density * v);
    }

    private void toast(String s) {
        Toast.makeText(this, s, Toast.LENGTH_SHORT).show();
    }
}