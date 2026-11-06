package com.poetry.app;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Random;
import java.util.zip.GZIPInputStream;

/** Read-only data access over the bundled poetry SQLite database. */
public class PoemDb {
    public static final String ASSET_DB = "poetry.db.gz";
    public static final int DB_VERSION = 13;

    private static PoemDb sInstance;
    private SQLiteDatabase db;
    private final Context ctx;
    private final HashMap<String, int[]> postingCache = new HashMap<String, int[]>();
    private final HashMap<String, String> s2t = new HashMap<String, String>();
    private final HashMap<String, List<String>> tOfS = new HashMap<String, List<String>>();
    private final Random rnd = new Random();

    public static synchronized PoemDb get(Context c) {
        if (sInstance == null) sInstance = new PoemDb(c.getApplicationContext());
        return sInstance;
    }

    private PoemDb(Context c) { ctx = c; }

    public interface Progress { void onProgress(int percent); }

    public static class Line {
        public int id, poemId;
        public String text, title, author, source, rhythmic;
    }

    public static class Poem {
        public int id, lineCount;
        public String title, author, authorId, body, source, form, rhythmic, prologue, tags;
        public String trans, note, intro, titlePy, py;
    }

    public static class Author {
        public int id, poemCount;
        public String name, dynasty, shortBio, bio;
    }

    private File dbFile() { return new File(ctx.getFilesDir(), "poetry.db"); }

    private static String readSmall(File f) {
        try {
            InputStream in = new java.io.FileInputStream(f);
            byte[] b = new byte[64];
            int n = in.read(b);
            in.close();
            return n <= 0 ? "" : new String(b, 0, n, "UTF-8").trim();
        } catch (Exception e) {
            return "";
        }
    }

    public boolean isReady() {
        File f = dbFile();
        return f.exists() && f.length() > 1000000
                && readSmall(new File(ctx.getFilesDir(), "poetry.ver")).equals(String.valueOf(DB_VERSION));
    }

    /** Decompress the bundled asset into internal storage. Must run off the main thread. */
    public synchronized void install(Progress p) throws Exception {
        if (isReady()) {
            if (p != null) p.onProgress(100);
            return;
        }
        File tmp = new File(ctx.getFilesDir(), "poetry.db.tmp");
        InputStream in = new GZIPInputStream(ctx.getAssets().open(ASSET_DB), 1 << 16);
        OutputStream out = new FileOutputStream(tmp);
        byte[] buf = new byte[1 << 16];
        long written = 0;
        long expect = 100L * 1024 * 1024;
        int n;
        int lastPct = -1;
        while ((n = in.read(buf)) > 0) {
            out.write(buf, 0, n);
            written += n;
            int pct = (int) Math.min(99, written * 100 / expect);
            if (p != null && pct != lastPct) {
                lastPct = pct;
                p.onProgress(pct);
            }
        }
        out.flush();
        out.close();
        in.close();
        File f = dbFile();
        if (f.exists()) f.delete();
        if (!tmp.renameTo(f)) throw new Exception("rename failed");
        OutputStream vo = new FileOutputStream(new File(ctx.getFilesDir(), "poetry.ver"));
        vo.write(String.valueOf(DB_VERSION).getBytes("UTF-8"));
        vo.close();
        if (p != null) p.onProgress(100);
    }

    public synchronized SQLiteDatabase open() {
        if (db != null && db.isOpen()) return db;
        db = SQLiteDatabase.openDatabase(dbFile().getAbsolutePath(), null,
                SQLiteDatabase.OPEN_READONLY | SQLiteDatabase.NO_LOCALIZED_COLLATORS);
        Cursor c = db.rawQuery("SELECT t,s FROM t2s_map", null);
        while (c.moveToNext()) {
            String t = c.getString(0);
            String s = c.getString(1);
            s2t.put(t, s);
            List<String> l = tOfS.get(s);
            if (l == null) {
                l = new ArrayList<String>();
                tOfS.put(s, l);
            }
            l.add(t);
        }
        c.close();
        return db;
    }

    static int[] decode(byte[] blob) {
        if (blob == null) return new int[0];
        int[] tmp = new int[Math.max(8, blob.length)];
        int count = 0;
        int shift = 0;
        long x = 0;
        long prev = 0;
        for (int i = 0; i < blob.length; i++) {
            int b = blob[i] & 0xff;
            x |= (long) (b & 0x7f) << shift;
            if ((b & 0x80) != 0) {
                shift += 7;
            } else {
                prev += x;
                if (count == tmp.length) {
                    int[] g = new int[tmp.length * 2];
                    System.arraycopy(tmp, 0, g, 0, count);
                    tmp = g;
                }
                tmp[count++] = (int) prev;
                x = 0;
                shift = 0;
            }
        }
        int[] out = new int[count];
        System.arraycopy(tmp, 0, out, 0, count);
        return out;
    }

    public List<String> variants(String one) {
        List<String> out = new ArrayList<String>();
        if (one == null || one.length() == 0) return out;
        String base = String.valueOf(one.charAt(0));
        addIf(out, base);
        String s = s2t.get(base);
        if (s != null) addIf(out, s);
        List<String> trads = tOfS.get(base);
        if (trads != null) for (String t : trads) addIf(out, t);
        if (s != null) {
            List<String> t2 = tOfS.get(s);
            if (t2 != null) for (String t : t2) addIf(out, t);
        }
        return out;
    }

    private static void addIf(List<String> l, String v) {
        if (v != null && v.length() == 1 && !l.contains(v)) l.add(v);
    }

    /** pos==null -> any position; pos>=0 -> that index; pos<0 -> counted from the end. */
    public int[] postings(String ch, Integer pos) {
        String key = ch + "#" + pos;
        int[] cached = postingCache.get(key);
        if (cached != null) return cached;
        Cursor c;
        if (pos == null) {
            c = db.rawQuery("SELECT ids FROM char_index WHERE ch=?", new String[]{ch});
        } else {
            c = db.rawQuery("SELECT ids FROM char_pos WHERE ch=? AND pos=?",
                    new String[]{ch, String.valueOf(pos)});
        }
        int[] r = c.moveToFirst() ? decode(c.getBlob(0)) : new int[0];
        c.close();
        if (postingCache.size() < 400) postingCache.put(key, r);
        return r;
    }

    public int[] findLines(String one, Integer pos) {
        List<String> vs = variants(one);
        if (pos != null) {
            for (String v : vs) {
                int[] p = postings(v, pos);
                if (p.length > 0) return p;
            }
        }
        for (String v : vs) {
            int[] p = postings(v, null);
            if (p.length > 0) return p;
        }
        return new int[0];
    }

    public static int[] intersect(int[] a, int[] b) {
        int[] tmp = new int[Math.min(a.length, b.length)];
        int i = 0;
        int j = 0;
        int n = 0;
        while (i < a.length && j < b.length) {
            if (a[i] == b[j]) {
                tmp[n++] = a[i];
                i++;
                j++;
            } else if (a[i] < b[j]) {
                i++;
            } else {
                j++;
            }
        }
        int[] out = new int[n];
        System.arraycopy(tmp, 0, out, 0, n);
        return out;
    }

    public List<Line> linesByIds(int[] ids, int from, int count) {
        List<Line> ordered = new ArrayList<Line>();
        if (ids == null || from >= ids.length) return ordered;
        int to = Math.min(ids.length, from + count);
        StringBuilder sb = new StringBuilder("SELECT l.id,l.poem_id,l.text,p.title_s,p.source,p.rhythmic,a.name_s"
                + " FROM line l JOIN poem p ON p.id=l.poem_id JOIN author a ON a.id=p.author_id WHERE l.id IN(");
        for (int i = from; i < to; i++) sb.append(i > from ? "," : "").append(ids[i]);
        sb.append(")");
        Cursor c = db.rawQuery(sb.toString(), null);
        HashMap<Integer, Line> byId = new HashMap<Integer, Line>();
        while (c.moveToNext()) {
            Line l = new Line();
            l.id = c.getInt(0);
            l.poemId = c.getInt(1);
            l.text = c.getString(2);
            l.title = c.getString(3);
            l.source = c.getString(4);
            l.rhythmic = c.getString(5);
            l.author = c.getString(6);
            byId.put(l.id, l);
        }
        c.close();
        for (int i = from; i < to; i++) {
            Line l = byId.get(ids[i]);
            if (l != null) ordered.add(l);
        }
        return ordered;
    }

    public Line lineById(int id) {
        Cursor c = db.rawQuery("SELECT l.id,l.poem_id,l.text,p.title_s,p.source,p.rhythmic,a.name_s"
                        + " FROM line l JOIN poem p ON p.id=l.poem_id JOIN author a ON a.id=p.author_id WHERE l.id=?",
                new String[]{String.valueOf(id)});
        Line l = null;
        if (c.moveToFirst()) {
            l = new Line();
            l.id = c.getInt(0);
            l.poemId = c.getInt(1);
            l.text = c.getString(2);
            l.title = c.getString(3);
            l.source = c.getString(4);
            l.rhythmic = c.getString(5);
            l.author = c.getString(6);
        }
        c.close();
        return l;
    }

    public int randomId(int[] pool, java.util.Set<Integer> used) {
        if (pool.length == 0) return -1;
        for (int t = 0; t < 80; t++) {
            int id = pool[rnd.nextInt(pool.length)];
            if (used == null || !used.contains(id)) return id;
        }
        if (used == null) return pool[0];
        for (int id : pool) if (!used.contains(id)) return id;
        return -1;
    }

    /** Prefer 5/7-character lines when generating AI answers (classic verse shapes). */
    public int randomNiceId(int[] pool, java.util.Set<Integer> used) {
        for (int t = 0; t < 40; t++) {
            int id = pool[rnd.nextInt(pool.length)];
            if (used != null && used.contains(id)) continue;
            Cursor c = db.rawQuery("SELECT len FROM line WHERE id=?", new String[]{String.valueOf(id)});
            int len = c.moveToFirst() ? c.getInt(0) : 0;
            c.close();
            if (len == 5 || len == 7) return id;
        }
        return randomId(pool, used);
    }

    public List<Author> searchAuthors(String q, String dynasty, int limit, int offset) {
        List<Author> out = new ArrayList<Author>();
        StringBuilder sql = new StringBuilder(
                "SELECT id,name_s,dynasty,poem_count,short_bio,bio_s FROM author WHERE poem_count>0");
        List<String> args = new ArrayList<String>();
        if (dynasty != null && dynasty.length() > 0) {
            sql.append(" AND dynasty=?");
            args.add(dynasty);
        }
        if (q != null && q.trim().length() > 0) {
            sql.append(" AND name_s LIKE ?");
            args.add("%" + normalize(q.trim()) + "%");
        }
        sql.append(" ORDER BY poem_count DESC, id ASC LIMIT ? OFFSET ?");
        args.add(String.valueOf(limit));
        args.add(String.valueOf(offset));
        Cursor c = db.rawQuery(sql.toString(), args.toArray(new String[args.size()]));
        while (c.moveToNext()) {
            Author a = new Author();
            a.id = c.getInt(0);
            a.name = c.getString(1);
            a.dynasty = c.getString(2);
            a.poemCount = c.getInt(3);
            a.shortBio = c.getString(4);
            a.bio = c.getString(5);
            out.add(a);
        }
        c.close();
        return out;
    }

    public Author authorById(int id) {
        Cursor c = db.rawQuery("SELECT id,name_s,dynasty,poem_count,short_bio,bio_s FROM author WHERE id=?",
                new String[]{String.valueOf(id)});
        Author a = null;
        if (c.moveToFirst()) {
            a = new Author();
            a.id = c.getInt(0);
            a.name = c.getString(1);
            a.dynasty = c.getString(2);
            a.poemCount = c.getInt(3);
            a.shortBio = c.getString(4);
            a.bio = c.getString(5);
        }
        c.close();
        return a;
    }

    public List<Poem> poemsOfAuthor(int authorId, String q, int limit, int offset) {
        List<Poem> out = new ArrayList<Poem>();
        StringBuilder sql = new StringBuilder(
                "SELECT id,title_s,line_count,source,form,rhythmic FROM poem WHERE author_id=?");
        List<String> args = new ArrayList<String>();
        args.add(String.valueOf(authorId));
        if (q != null && q.trim().length() > 0) {
            sql.append(" AND title_s LIKE ?");
            args.add("%" + q.trim() + "%");
        }
        sql.append(" ORDER BY id LIMIT ? OFFSET ?");
        args.add(String.valueOf(limit));
        args.add(String.valueOf(offset));
        Cursor c = db.rawQuery(sql.toString(), args.toArray(new String[args.size()]));
        while (c.moveToNext()) {
            Poem p = new Poem();
            p.id = c.getInt(0);
            p.title = c.getString(1);
            p.lineCount = c.getInt(2);
            p.source = c.getString(3);
            p.form = c.getString(4);
            p.rhythmic = c.getString(5);
            out.add(p);
        }
        c.close();
        return out;
    }

    public Poem poemById(int id) {
        Cursor c = db.rawQuery("SELECT p.id,p.title_s,p.body,p.source,p.form,p.rhythmic,p.prologue,p.tags,"
                + "p.line_count,a.name_s,a.id,p.trans,p.note,p.intro,p.title_py,p.py"
                + " FROM poem p JOIN author a ON a.id=p.author_id"
                + " WHERE p.id=?", new String[]{String.valueOf(id)});
        Poem p = null;
        if (c.moveToFirst()) {
            p = new Poem();
            p.id = c.getInt(0);
            p.title = c.getString(1);
            p.body = c.getString(2);
            p.source = c.getString(3);
            p.form = c.getString(4);
            p.rhythmic = c.getString(5);
            p.prologue = c.getString(6);
            p.tags = c.getString(7);
            p.lineCount = c.getInt(8);
            p.author = c.getString(9);
            p.authorId = String.valueOf(c.getInt(10));
            p.trans = c.getString(11);
            p.note = c.getString(12);
            p.intro = c.getString(13);
            p.titlePy = c.getString(14);
            p.py = c.getString(15);
        }
        c.close();
        return p;
    }

    public List<String[]> hotChars(int limit) {
        List<String[]> out = new ArrayList<String[]>();
        Cursor c = db.rawQuery("SELECT ch,cnt FROM char_index WHERE length(ch)=1 AND cnt BETWEEN 150 AND 40000"
                + " ORDER BY cnt DESC LIMIT ?", new String[]{String.valueOf(limit)});
        while (c.moveToNext()) out.add(new String[]{c.getString(0), String.valueOf(c.getInt(1))});
        c.close();
        return out;
    }

    public String normalize(String s) {
        if (s == null) return null;
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            String v = s2t.get(String.valueOf(s.charAt(i)));
            sb.append(v != null ? v : s.charAt(i));
        }
        return sb.toString();
    }

    public static String stripPunct(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (Character.isWhitespace(c)) continue;
            if (!Character.isLetterOrDigit(c)) continue;
            sb.append(c);
        }
        return sb.toString();
    }

    /** Validate a user-supplied verse against the corpus (exact match after normalisation). */
    public Line matchLine(String raw) {
        String q = normalize(stripPunct(raw));
        if (q.length() == 0) return null;
        Cursor c = db.rawQuery("SELECT l.id,l.poem_id,l.text,p.title_s,p.source,p.rhythmic,a.name_s"
                + " FROM line l JOIN poem p ON p.id=l.poem_id JOIN author a ON a.id=p.author_id WHERE l.text=?"
                + " LIMIT 1", new String[]{q});
        Line l = null;
        if (c.moveToFirst()) {
            l = new Line();
            l.id = c.getInt(0);
            l.poemId = c.getInt(1);
            l.text = c.getString(2);
            l.title = c.getString(3);
            l.source = c.getString(4);
            l.rhythmic = c.getString(5);
            l.author = c.getString(6);
        }
        c.close();
        return l;
    }

    /** One result of a verse lookup: the matched clause(s) plus where they came from. */
    public static class VerseHit {
        public int poemId;
        public String text;
        public String title;
        public String author;
        /** 0 exact line, 1 clause inside a longer line, 2 same characters in order, 3 couplet, 4 near match. */
        public int kind;
        /** True when the match is in the poem's title (or its pinyin) rather than its text. */
        public boolean byTitle;
        /** The attributed author's dynasty, so a dynasty filter can be applied to hits. */
        public String dynasty;
        /** Surviving poems by the attributed author; orders same-text duplicates. */
        public int fame;
        /** poem.sig, see sameText. */
        public String sig;
    }
    /** A line row kept together with its coordinates so neighbours can be found. */
    private static class Row {
        int id, poemId, idx;
        String text;
        String stripped;
        int cov;
        int kind;
        /** How many poems by this line's author survives; breaks ties for sameText rows. */
        int fame;
        /** poem.sig -- fingerprint of the whole poem, see sameText. */
        String sig;
    }
    /**
     * Line rows joined to their author's output count. The corpus records the same
     * quatrain twice (白日依山尽 under 朱斌《登楼》 and 王之涣《登鹳雀楼》), so when two hits
     * score identically the reader means the famous poet's copy: 王之涣 has 7 poems,
     * 朱斌 1. LEFT JOIN keeps a line even if its poem row is missing.
     */
    private static final String LINE_SELECT = "SELECT l.id,l.poem_id,l.idx,l.text,"
            + "IFNULL(a.poem_count,0),IFNULL(p.sig,'')"
            + " FROM line l LEFT JOIN poem p ON p.id=l.poem_id"
            + " LEFT JOIN author a ON a.id=p.author_id WHERE l.id IN(";
    private static final String PUNCT = " \t\r\n，。！？；：、,.!?;:·…—-（）()「」『』“”‘’《》〈〉【】[]";
    /** Strip everything a reader would not type when recalling a verse. */
    static String collapse(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (PUNCT.indexOf(ch) >= 0) continue;
            sb.append(ch);
        }
        return sb.toString();
    }
    /** Union of the postings of a character and its traditional/simplified variants. */
    private int[] charLines(char ch) {
        List<String> vs = variants(String.valueOf(ch));
        int[] acc = new int[0];
        for (String v : vs) {
            int[] p = postings(v, null);
            if (p.length == 0) continue;
            acc = mergeSorted(acc, p);
        }
        return acc;
    }
    private static int[] mergeSorted(int[] a, int[] b) {
        if (a.length == 0) return b;
        if (b.length == 0) return a;
        int[] tmp = new int[a.length + b.length];
        int i = 0, j = 0, n = 0;
        while (i < a.length && j < b.length) {
            int v = a[i] <= b[j] ? a[i++] : b[j++];
            if (n == 0 || tmp[n - 1] != v) tmp[n++] = v;
        }
        while (i < a.length) {
            int v = a[i++];
            if (n == 0 || tmp[n - 1] != v) tmp[n++] = v;
        }
        while (j < b.length) {
            int v = b[j++];
            if (n == 0 || tmp[n - 1] != v) tmp[n++] = v;
        }
        int[] out = new int[n];
        System.arraycopy(tmp, 0, out, 0, n);
        return out;
    }
    private static int[] intersectSorted(int[] a, int[] b) {
        if (a.length == 0 || b.length == 0) return new int[0];
        int[] out = intersect(a, b);
        return out;
    }
    /** Load line rows for the given ids, stopping after {@code cap} rows. */
    private List<Row> rowsByIds(int[] ids, int cap) {
        List<Row> out = new ArrayList<Row>();
        if (ids == null || ids.length == 0) return out;
        int pos = 0;
        while (pos < ids.length && out.size() < cap) {
            int end = Math.min(ids.length, pos + 800);
            StringBuilder sb = new StringBuilder(LINE_SELECT);
            for (int i = pos; i < end; i++) sb.append(i > pos ? "," : "").append(ids[i]);
            sb.append(")");
            Cursor c = db.rawQuery(sb.toString(), null);
            while (c.moveToNext() && out.size() < cap) {
                Row r = new Row();
                r.id = c.getInt(0);
                r.poemId = c.getInt(1);
                r.idx = c.getInt(2);
                r.text = c.getString(3);
                r.stripped = collapse(r.text);
                r.fame = c.getInt(4);
                r.sig = c.getString(5);
                out.add(r);
            }
            c.close();
            pos = end;
        }
        return out;
    }
    private void fillPoem(VerseHit h, int poemId) {
        Cursor c = db.rawQuery("SELECT p.title_s,a.name_s,IFNULL(a.poem_count,0),IFNULL(p.sig,''),"
                + "IFNULL(a.dynasty,'')"
                + " FROM poem p JOIN author a ON a.id=p.author_id WHERE p.id=?",
                new String[]{String.valueOf(poemId)});
        if (c.moveToFirst()) {
            h.title = c.getString(0);
            h.author = c.getString(1);
            h.fame = c.getInt(2);
            h.sig = c.getString(3);
            h.dynasty = c.getString(4);
        }
        h.poemId = poemId;
        c.close();
    }
    /** Lines containing every distinct character of {@code clause} (falling back to all-but-one). */
    private List<Row> clauseLines(String clause, int cap) {
        ArrayList<Integer> chars = distinctCodes(clause);
        int[][] lists = new int[chars.size()][];
        int k = 0;
        for (int code : chars) {
            int[] p = charLines((char) code);
            if (p.length == 0) return new ArrayList<Row>();
            lists[k++] = p;
        }
        java.util.Arrays.sort(lists, new java.util.Comparator<int[]>() {
            public int compare(int[] x, int[] y) { return x.length - y.length; }
        });
        int[] cand = lists[0];
        for (int i = 1; i < lists.length && cand.length > 0; i++) {
            cand = intersectSorted(cand, lists[i]);
        }
        List<Row> rows = cand.length > 0 ? rowsByIds(cand, cap) : new ArrayList<Row>();
        if (!rows.isEmpty()) return rows;
        // Nothing holds every character: the corpus often differs by one glyph (床前看月光
        // vs the popular 床前明月光; 天涯若比隣 with a variant 隣 that t2s_map lacks).
        // Scan the union of the two rarest lists instead: when the intersection is empty
        // the wanted line can only live in one of them. Filter while scanning so a long
        // list cannot push the wanted line past a row cap.
        if (lists.length < 2) return rows;
        return scanNear(mergeSorted(lists[0], lists[1]), chars);
    }
    /** Lines that contain all but one of {@code chars}, scanning {@code anchor} in slices. */
    private List<Row> scanNear(int[] anchor, ArrayList<Integer> chars) {
        List<Row> near = new ArrayList<Row>();
        int need = chars.size();
        int scanned = 0;
        for (int pos = 0; pos < anchor.length && scanned < 60000 && near.size() < 400; pos += 800) {
            int end = Math.min(anchor.length, pos + 800);
            StringBuilder sb = new StringBuilder(LINE_SELECT);
            for (int i = pos; i < end; i++) sb.append(i > pos ? "," : "").append(anchor[i]);
            sb.append(")");
            scanned += end - pos;
            Cursor c = db.rawQuery(sb.toString(), null);
            while (c.moveToNext()) {
                String text = c.getString(3);
                String stripped = collapse(text);
                int cov = 0;
                for (int code : chars) {
                    if (stripped.indexOf(code) >= 0) cov++;
                }
                if (cov < need - 1) continue;
                Row r = new Row();
                r.id = c.getInt(0);
                r.poemId = c.getInt(1);
                r.idx = c.getInt(2);
                r.text = text;
                r.stripped = stripped;
                r.fame = c.getInt(4);
                r.sig = c.getString(5);
                near.add(r);
            }
            c.close();
        }
        return near;
    }
    static ArrayList<Integer> distinctCodes(String s) {
        ArrayList<Integer> out = new ArrayList<Integer>();
        for (int i = 0; i < s.length(); i++) {
            int code = s.charAt(i);
            if (!out.contains(code)) out.add(code);
        }
        return out;
    }
    private static boolean subsequence(String needle, String hay) {
        int j = 0;
        for (int i = 0; i < hay.length() && j < needle.length(); i++) {
            if (hay.charAt(i) == needle.charAt(j)) j++;
        }
        return j == needle.length();
    }
    /**
     * Poems whose title contains the query.
     *
     * The verse index answers "which poem contains this line", so a query that is only a
     * title returned nothing: 静夜思 is not a line of the poem named after it, and neither is
     * 登高 or 虞美人. Titles are short (79,831 rows, one LIKE scan measured at ~40ms) so this
     * needs no posting index. Matching title_s means the query may be typed in either script:
     * normalize() folds traditional input onto the simplified column.
     * Ranking: exact-title matches first (capped at half the page), then titles starting
     * with the query, then titles merely containing it. Within those, curated anthologies
     * (南唐二主词/花间集/...) lead, then annotated copies, then short titles -- 明月何皎皎
     * before 明月湖醉后蔷薇花歌. At most two cards per author: five identical 《虞美人》
     * 辛弃疾 cards tell the reader nothing, since the author page lists them all.
     */
    public List<VerseHit> searchTitles(String raw, int limit) {
        return searchTitles(raw, limit, "");
    }
    /** {@code dynasty} is a chip value (唐/宋/…); empty means no filter. */
    public List<VerseHit> searchTitles(String raw, int limit, String dynasty) {
        String dy = dynasty == null ? "" : dynasty.trim();
        String q = collapse(normalize(raw));
        if (q.length() < 2) return new ArrayList<VerseHit>();
        List<VerseHit> out = pickTitles(q, raw.trim(), limit, dy);
        if (out.size() >= 4) return out;
        // 观书有感·其一 matches neither title (the corpus has 观书有感二首·其一): every
        // full-string LIKE fails across the inserted 二首. The longest punctuation-free
        // chunk of the query does match, so retry with that before giving up.
        String best = longestChunk(normalize(raw));
        if (best.length() >= 2 && !best.equals(q)) {
            java.util.HashSet<Integer> ids = new java.util.HashSet<Integer>();
            for (VerseHit h : out) ids.add(h.poemId);
            for (VerseHit h : pickTitles(best, best, limit, dy)) {
                if (ids.add(h.poemId)) out.add(h);
            }
        }
        return out.size() > limit ? out.subList(0, limit) : out;
    }
    /** Longest run of non-punctuation characters (PUNCT) in {@code s}. */
    static String longestChunk(String s) {
        String best = "";
        int start = 0;
        for (int i = 0; i <= s.length(); i++) {
            if (i < s.length() && PUNCT.indexOf(s.charAt(i)) < 0) continue;
            if (i - start > best.length()) best = s.substring(start, i);
            start = i + 1;
        }
        return best;
    }
    /**
     * Exact-title rows followed by the looser ones, with both caps applied.
     *
     * The two tiers are separate queries on purpose. 词牌 names have hundreds of exact
     * copies (虞美人 alone has more than the 200-row window a single ranked query would
     * read), so one query ordered exact-first never reaches the 虞美人·春花秋月何时了 the
     * reader is actually after. Splitting them lets the exact tier be capped without
     * displacing the rest of the page.
     */
    private List<VerseHit> pickTitles(String q, String raw, int limit, String dynasty) {
        List<VerseHit> out = new ArrayList<VerseHit>();
        HashMap<String, Integer> byAuthor = new HashMap<String, Integer>();
        int exactCap = Math.max(2, limit / 2);
        for (int pass = 0; pass < 2; pass++) {
            List<VerseHit> tier = titleRows(q, raw, limit, pass == 0, dynasty);
            for (VerseHit h : tier) {
                if (pass == 0 ? out.size() >= exactCap : out.size() >= limit) break;
                Integer n = byAuthor.get(h.author);
                int authored = n == null ? 0 : n.intValue();
                if (authored >= 2) continue;
                byAuthor.put(h.author, Integer.valueOf(authored + 1));
                out.add(h);
            }
        }
        return out;
    }
    /**
     * Title rows in display order. {@code exactOnly} selects between title = query and
     * title LIKE %query% (with the exact rows excluded, so the two tiers never overlap).
     */
    private List<VerseHit> titleRows(String q, String raw, int limit, boolean exactOnly, String dynasty) {
        List<VerseHit> out = new ArrayList<VerseHit>();
        // The dynasty predicate (?='' OR dynasty=?) keeps one statement shape for both the
        // filtered and unfiltered case -- the empty chip value matches itself. Pushing the
        // filter into SQL matters: filtering Java-side would let a 宋 chip empty a page whose
        // title matches all happen to be 唐, instead of finding the 宋 ones further down.
        Cursor c = db.rawQuery("SELECT p.id,p.title_s,a.name_s,IFNULL(a.poem_count,0),IFNULL(p.sig,''),"
                + "IFNULL(a.dynasty,'')"
                + " FROM poem p JOIN author a ON a.id=p.author_id"
                + " WHERE (?='' OR IFNULL(a.dynasty,'')=?)"
                + (exactOnly ? " AND (p.title_s=? OR p.title=?)"
                             : " AND (p.title_s LIKE ? OR p.title LIKE ?)"
                               + " AND p.title_s<>? AND p.title<>?")
                + " ORDER BY"
                + " CASE WHEN p.source IN ('诗经','楚辞','南唐二主词','曹操诗集') THEN 0"
                + "      WHEN p.source IN ('花间集','纳兰性德','补录') THEN 1 ELSE 2 END,"
                + (exactOnly ? ""
                             : " CASE WHEN p.title_s LIKE ? OR p.title LIKE ? THEN 1 ELSE 2 END,")
                + " (CASE WHEN coalesce(p.trans,'')<>'' THEN 1 ELSE 0 END"
                + "  +CASE WHEN coalesce(p.note,'')<>'' THEN 1 ELSE 0 END"
                + "  +CASE WHEN coalesce(p.intro,'')<>'' THEN 1 ELSE 0 END) DESC,"
                + " CASE WHEN a.name_s IN ('无名氏','佚名') THEN 1 ELSE 0 END,"
                + " length(p.title_s), IFNULL(a.poem_count,0) DESC, p.id LIMIT ?",
                exactOnly
                        ? new String[]{dynasty, dynasty, q, raw,
                                       String.valueOf(Math.max(200, limit * 8))}
                        : new String[]{dynasty, dynasty, "%" + q + "%", "%" + raw + "%", q, raw,
                                       q + "%", raw + "%", String.valueOf(Math.max(200, limit * 8))});
        while (c.moveToNext()) {
            VerseHit h = new VerseHit();
            h.poemId = c.getInt(0);
            h.title = c.getString(1);
            h.author = c.getString(2);
            h.fame = c.getInt(3);
            h.sig = c.getString(4);
            h.dynasty = c.getString(5);
            h.text = h.title;
            h.byTitle = true;
            out.add(h);
        }
        c.close();
        return out;
    }
    /**
     * One search over both things a reader remembers: the title and the text.
     *
     * Title hits lead -- typing a title means that is the poem wanted -- then the verse hits
     * in the order searchVerses already ranked them. A poem found both ways is listed once.
     */
    public List<VerseHit> searchAll(String raw, int limit) {
        return searchAll(raw, limit, "");
    }
    /**
     * Same, restricted to one dynasty chip (empty = all). Title matches are filtered in SQL
     * (see titleRows); verse matches after the fact, over-fetching so a filter still fills
     * the page -- the verse engine ranks globally and knows nothing about dynasties.
     */
    public List<VerseHit> searchAll(String raw, int limit, String dynasty) {
        String dy = dynasty == null ? "" : dynasty.trim();
        List<VerseHit> out = new ArrayList<VerseHit>();
        java.util.HashSet<Integer> seen = new java.util.HashSet<Integer>();
        for (VerseHit h : searchTitles(raw, Math.min(limit, 8), dy)) {
            if (seen.add(h.poemId)) out.add(h);
        }
        List<VerseHit> verses = searchVerses(raw, dy.length() == 0 ? limit : limit * 6);
        for (VerseHit h : verses) {
            if (out.size() >= limit) break;
            if (dy.length() > 0 && !dy.equals(h.dynasty)) continue;
            if (seen.add(h.poemId)) out.add(h);
        }
        return out.size() > limit ? out.subList(0, limit) : out;
    }
    /**
     * Find the poem(s) a remembered verse belongs to.
     *
     * Short queries match a single line. Long ones (two clauses run together, e.g.
     * 欲穷千里目更上一层楼) are also tried as an adjacent line pair, which is what a
     * reader usually recalls. One character of difference is tolerated so recensions
     * and variant glyphs still resolve.
     */
    public List<VerseHit> searchVerses(String raw, int limit) {
        List<VerseHit> out = new ArrayList<VerseHit>();
        String q = collapse(normalize(raw));
        if (q.length() < 2) return out;
        if (q.length() >= 8) {
            adjacentHits(q, limit, out);
            if (!out.isEmpty()) return out;
        }
        List<Row> rows = clauseLines(q, 1200);
        for (Row r : rows) {
            r.cov = coverage(q, r.stripped);
            r.kind = kindOf(q, r.stripped);
        }
        ArrayList<Row> scored = new ArrayList<Row>(rows);
        java.util.Collections.sort(scored, new java.util.Comparator<Row>() {
            public int compare(Row x, Row y) {
                if (x.cov != y.cov) return y.cov - x.cov;
                if (x.kind != y.kind) return x.kind - y.kind;
                return x.stripped.length() - y.stripped.length();
            }
        });
        int need = distinctCodes(q).size();
        // Keyed by line text to keep one card per wording; insertion order is the ranking.
        // A repeat may replace the keeper only when the two hits are the same poem under
        // two authorships, and then only in favour of the more prolific author.
        java.util.LinkedHashMap<String, Row> best = new java.util.LinkedHashMap<String, Row>();
        for (Row r : scored) {
            if (r.cov < need - 1) continue;
            Row old = best.get(r.stripped);
            if (old == null || (sameText(old, r) && r.fame > old.fame)) best.put(r.stripped, r);
        }
        for (Row r : best.values()) {
            VerseHit h = new VerseHit();
            h.text = r.text;
            h.kind = r.kind;
            fillPoem(h, r.poemId);
            if (h.title == null) continue;
            out.add(h);
            if (out.size() >= limit) break;
        }
        return out;
    }
    /**
     * True when both hits sit in poems whose entire text is identical, i.e. one poem
     * recorded twice under two authorships (白日依山尽 as 朱斌《登楼》 and 王之涣《登鹳雀楼》).
     * Only there may fame decide, otherwise two different poems reusing one line would
     * be reordered by how prolific their authors happen to be.
     */
    private static boolean sameText(Row x, Row y) {
        return x.sig != null && x.sig.length() > 0 && x.sig.equals(y.sig);
    }
    private static boolean sameText(String x, String y) {
        return x != null && x.length() > 0 && x.equals(y);
    }
    static int coverage(String needle, String hay) {
        int cov = 0;
        ArrayList<Integer> chars = distinctCodes(needle);
        for (int code : chars) {
            if (hay.indexOf(code) >= 0) cov++;
        }
        return cov;
    }
    static int kindOf(String needle, String hay) {
        if (hay.equals(needle)) return 0;
        if (hay.indexOf(needle) >= 0) return 1;
        if (subsequence(needle, hay)) return 2;
        return 4;
    }
    /** Split a run-together quotation in half and look for the two halves on neighbour lines. */
    private void adjacentHits(String q, int limit, List<VerseHit> out) {
        int mid = q.length() / 2;
        // Keyed by couplet text, insertion order kept as the ranking. A wording recorded in
        // two poems keeps the copy by the more prolific author only when the two poems
        // have the very same text (a double attribution); otherwise the first hit stays
        // first, so sharing one line no longer lets a famous author outrank the source.
        java.util.LinkedHashMap<String, VerseHit> best = new java.util.LinkedHashMap<String, VerseHit>();
        for (int d = 0; d <= 3; d++) {
            int[] cuts = d == 0 ? new int[]{mid} : new int[]{mid - d, mid + d};
            for (int cut : cuts) {
                if (cut < 3 || cut > q.length() - 3) continue;
                List<Row> first = clauseLines(q.substring(0, cut), 900);
                List<Row> second = clauseLines(q.substring(cut), 900);
                if (first.isEmpty() || second.isEmpty()) continue;
                HashMap<Long, Row> nextIdx = new HashMap<Long, Row>();
                for (Row r : first) nextIdx.put(((long) r.poemId << 20) | (r.idx + 1), r);
                for (Row r : second) {
                    Row prev = nextIdx.get(((long) r.poemId << 20) | r.idx);
                    if (prev == null) continue;
                    String key = prev.stripped + "|" + r.stripped;
                    VerseHit old = best.get(key);
                    if (old != null && !(sameText(old.sig, r.sig) && r.fame > old.fame)) continue;
                    VerseHit h = new VerseHit();
                    h.text = prev.text + " / " + r.text;
                    h.kind = 3;
                    h.sig = r.sig;
                    h.fame = r.fame;
                    h.poemId = r.poemId;
                    best.put(key, h);
                }
            }
            if (!best.isEmpty()) break;
        }
        for (VerseHit h : best.values()) {
            fillPoem(h, h.poemId);
            if (h.title == null) continue;
            out.add(h);
            if (out.size() >= limit) return;
        }
    }
    public int count(String table) {
        Cursor c = db.rawQuery("SELECT COUNT(*) FROM " + table, null);
        int n = c.moveToFirst() ? c.getInt(0) : 0;
        c.close();
        return n;
    }
}