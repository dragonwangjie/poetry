package com.poetry.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

/** One poet's collected works (作品集). */
public class AuthorActivity extends Activity {

    private PoemDb db;
    private int authorId;
    private final List<PoemDb.Poem> items = new ArrayList<PoemDb.Poem>();
    private BaseAdapter adapter;
    private TextView status;
    private TextView bioView;
    private ScrollView bioScroll;
    private String filter = "";
    private int offset = 0;
    private boolean loading = false;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        db = PoemDb.get(this);
        db.open();
        authorId = getIntent().getIntExtra("author_id", -1);
        final PoemDb.Author a = db.authorById(authorId);
        buildUi(a);
        reload();
    }

    private void buildUi(PoemDb.Author a) {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundColor(0xFFFBF7EF);

        TextView head = new TextView(this);
        head.setTextSize(19f);
        head.setTextColor(0xFF2B2B2B);
        head.setPadding(dp(16), dp(12), dp(16), dp(2));
        head.setText(a.name + "  ·  " + (a.dynasty == null || a.dynasty.length() == 0 ? "？" : a.dynasty));
        outer.addView(head);

        status = new TextView(this);
        status.setTextSize(12f);
        status.setTextColor(0xFF8A8A8A);
        status.setPadding(dp(16), 0, dp(16), dp(6));
        status.setText(a.poemCount + " 首");
        outer.addView(status);

        String bio = a.bio != null && a.bio.length() > 0 ? a.bio : a.shortBio;
        if (bio != null && bio.length() > 0) {
            bioScroll = new ScrollView(this);
            bioView = new TextView(this);
            bioView.setTextSize(12f);
            bioView.setTextColor(0xFF6A5F4E);
            bioView.setLineSpacing(0, 1.15f);
            bioView.setMaxLines(4);
            bioView.setText(ellipsize(bio));
            bioView.setPadding(dp(16), dp(6), dp(16), dp(6));
            bioView.setOnClickListener(new View.OnClickListener() {
                boolean more = false;
                public void onClick(View v) {
                    more = !more;
                    String full = db.authorById(authorId).bio;
                    if (full == null) full = "";
                    bioView.setMaxLines(more ? 200 : 4);
                    bioView.setText(more ? full : ellipsize(full));
                }
            });
            bioScroll.addView(bioView);
            LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            blp.weight = 0;
            outer.addView(bioScroll, blp);
        }

        EditText f = new EditText(this);
        f.setHint("在本家集中搜标题");
        f.setMaxLines(1);
        f.setSingleLine(true);
        f.setTextSize(14f);
        f.setPadding(dp(14), dp(6), dp(14), dp(6));
        outer.addView(f);
        f.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int x, int y, int z) { }
            public void onTextChanged(CharSequence s, int x, int y, int z) { }
            public void afterTextChanged(Editable s) {
                filter = s.toString();
                reload();
            }
        });

        ListView list = new ListView(this);
        list.setCacheColorHint(0xFFFBF7EF);
        adapter = new BaseAdapter() {
            public int getCount() { return items.size(); }
            public Object getItem(int i) { return items.get(i); }
            public long getItemId(int i) { return items.get(i).id; }

            public View getView(int i, View cv, ViewGroup parent) {
                PoemDb.Poem p = items.get(i);
                LinearLayout row = new LinearLayout(AuthorActivity.this);
                row.setOrientation(LinearLayout.VERTICAL);
                row.setPadding(dp(16), dp(11), dp(16), dp(11));
                TextView l1 = new TextView(AuthorActivity.this);
                l1.setTextSize(16f);
                l1.setTextColor(0xFF2B2B2B);
                l1.setText(p.title == null || p.title.length() == 0 ? "（无题）" : p.title);
                row.addView(l1);
                TextView l2 = new TextView(AuthorActivity.this);
                l2.setTextSize(12f);
                l2.setTextColor(0xFF9A8F7E);
                String meta = p.source + (p.rhythmic != null && p.rhythmic.length() > 0 ? " · " + p.rhythmic : "");
                l2.setText(meta);
                row.addView(l2);
                return row;
            }
        };
        list.setAdapter(adapter);
        list.setOnItemClickListener(new android.widget.AdapterView.OnItemClickListener() {
            public void onItemClick(android.widget.AdapterView<?> p, View v, int pos, long id) {
                Intent it = new Intent(AuthorActivity.this, PoemActivity.class);
                it.putExtra("poem_id", (int) id);
                startActivity(it);
            }
        });
        list.setOnScrollListener(new android.widget.AbsListView.OnScrollListener() {
            public void onScroll(android.widget.AbsListView v, int first, int last, int total) {
                if (total > 0 && first + last >= total - 12) loadMore();
            }
            public void onScrollStateChanged(android.widget.AbsListView v, int s) { }
        });
        outer.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(outer);
    }

    private static String ellipsize(String s) {
        return s.length() > 130 ? s.substring(0, 130) + "…" : s;
    }

    private void reload() {
        items.clear();
        offset = 0;
        adapter.notifyDataSetChanged();
        loadMore();
    }

    private synchronized void loadMore() {
        if (loading) return;
        loading = true;
        final int off = offset;
        final String ff = filter;
        new Thread(new Runnable() {
            public void run() {
                final List<PoemDb.Poem> page = db.poemsOfAuthor(authorId, ff, 80, off);
                ui.post(new Runnable() {
                    public void run() {
                        items.addAll(page);
                        offset += page.size();
                        adapter.notifyDataSetChanged();
                        status.setText("已载 " + items.size() + " / " + db.authorById(authorId).poemCount + " 首");
                        loading = false;
                    }
                });
            }
        }).start();
    }

    private int dp(int v) {
        return Math.round(getResources().getDisplayMetrics().density * v);
    }
}