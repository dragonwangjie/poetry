package com.poetry.app;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.text.TextPaint;
import android.view.View;
/**
 * Hanzi text with a pinyin ruby above each character.
 *
 * Each character owns one column, as wide as the wider of glyph and ruby. Starting from the
 * requested glyph size the text is shrunk towards a floor until it fits the available width,
 * so a verse line is displayed complete and centered instead of being clipped; only text that
 * still cannot fit at the floor size wraps into additional centered rows.
 */
public class PinyinText extends View {
    /** Characters that carry a ruby. The syllable stream must follow this same rule. */
    public static boolean han(char ch) {
        return (ch >= 0x3400 && ch <= 0x4DBF)       // CJK extension A
                || (ch >= 0x4E00 && ch <= 0x9FFF)   // CJK unified ideographs
                || (ch >= 0xF900 && ch <= 0xFAFF);  // compatibility ideographs
    }
    private final TextPaint hanPaint = new TextPaint(Paint.ANTI_ALIAS_FLAG);
    private final TextPaint rubyPaint = new TextPaint(Paint.ANTI_ALIAS_FLAG);
    private final float density = getResources().getDisplayMetrics().density;
    private String text = "";
    private String[] py = new String[0];
    private float wantSp = 22f;
    private float rubyWantSp = 11f;
    private float minSp = 12.5f;
    private float hanSp;
    private float rubySp;
    private float hanPx;
    private float rubyPx;
    private int rowGapPx = (int) (8 * density);
    private int colGapPx = (int) (2 * density);
    private float[] colW = new float[0];
    private String[] chars = new String[0];
    private String[] rubies = new String[0];
    private int rowHeight;
    private int rows = 1;
    private boolean rubyOn = true;
    private boolean bold;
    private boolean dirty = true;
    private int lastAvail = -1;

    public PinyinText(Context c) {
        super(c);
        rubyPaint.setAlpha(0xB0);
    }
    public void setBold(boolean b) {
        bold = b;
        dirty = true;
        relayout();
    }
    public void setPinyinVisible(boolean on) {
        rubyOn = on;
        dirty = true;
        relayout();
    }
    public void setColors(int hanColor, int rubyColor) {
        hanPaint.setColor(hanColor);
        rubyPaint.setColor(rubyColor);
        invalidate();
    }
    /**
     * @param hanSp  requested glyph size, sp
     * @param rubySp requested ruby size, sp (also scaled down with the glyphs)
     * @param minSp  smallest glyph size allowed so the line can still fit on one row
     */
    public void setTextSize(float hanSp, float rubySp, float minSp) {
        this.wantSp = hanSp;
        this.rubyWantSp = rubySp;
        this.minSp = Math.min(minSp, hanSp);
        this.dirty = true;
        relayout();
    }
    /** @param pinyin readings separated by spaces, one per {@link #han} character of {@code src}. */
    public void setContent(String src, String pinyin) {
        text = src == null ? "" : src;
        py = pinyin == null || pinyin.trim().length() == 0
                ? new String[0] : pinyin.trim().split("\\s+");
        dirty = true;
        relayout();
    }
    private void relayout() {
        invalidate();
        requestLayout();
    }
    private void fonts(float sp) {
        hanSp = sp;
        rubySp = Math.min(rubyWantSp, Math.max(7f, sp * 0.5f));
        hanPx = sp * density;
        rubyPx = rubySp * density;
        hanPaint.setTypeface(Typeface.create("sans-serif", bold ? Typeface.BOLD : Typeface.NORMAL));
        hanPaint.setTextSize(hanPx);
        rubyPaint.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        rubyPaint.setTextSize(rubyPx);
    }
    /** Lay out one column per character at the current sizes; returns the one-row width. */
    private float columns() {
        int n = text.length();
        if (colW.length != n) {
            colW = new float[n];
            chars = new String[n];
            rubies = new String[n];
        }
        int k = 0;
        float total = 0f;
        for (int i = 0; i < n; i++) {
            char ch = text.charAt(i);
            String s = String.valueOf(ch);
            chars[i] = s;
            String r = "";
            if (rubyOn && han(ch) && k < py.length) r = py[k++];
            rubies[i] = r;
            float w = hanPaint.measureText(s);
            if (r.length() > 0) {
                float rw = rubyPaint.measureText(r);
                if (rw > w) w = rw;
            }
            colW[i] = w + colGapPx;
            total += colW[i];
        }
        int hanH = (int) Math.ceil(hanPaint.descent() - hanPaint.ascent());
        int rubyH = rubyOn ? (int) Math.ceil(rubyPaint.descent() - rubyPaint.ascent()) : 0;
        rowHeight = hanH + rubyH + (int) (2 * density);
        return total;
    }
    /** Shrink the glyph size until the whole string fits {@code avail}, but never below minSp. */
    private void fitTo(int avail) {
        fonts(wantSp);
        if (avail <= 1 || text.length() == 0) {
            columns();
            return;
        }
        for (int i = 0; i < 8; i++) {
            float w = columns();
            if (w <= avail || hanSp <= minSp + 0.01f) break;
            float next = hanSp * (avail / w);
            if (next < minSp) next = minSp;
            if (next > hanSp - 0.05f) next = hanSp - 0.5f;
            if (next < minSp) next = minSp;
            fonts(next);
            if (hanSp <= minSp + 0.01f) break;
        }
        columns();
    }
    private int countRows(int avail) {
        if (avail <= 0 || colW.length == 0) return 1;
        int r = 1;
        float line = 0f;
        for (int i = 0; i < colW.length; i++) {
            if (line > 0 && line + colW[i] > avail) {
                r++;
                line = colW[i];
            } else {
                line += colW[i];
            }
        }
        return r;
    }
    @Override
    protected void onMeasure(int widthSpec, int heightSpec) {
        int w = MeasureSpec.getSize(widthSpec);
        int avail = w - getPaddingLeft() - getPaddingRight();
        if (dirty || avail != lastAvail) {
            fitTo(avail);
            lastAvail = avail;
            dirty = false;
        }
        rows = countRows(avail);
        int h = rows * rowHeight + (rows - 1) * rowGapPx + getPaddingTop() + getPaddingBottom();
        setMeasuredDimension(w, h);
    }
    @Override
    protected void onDraw(Canvas canvas) {
        if (colW.length == 0) return;
        int avail = getWidth() - getPaddingLeft() - getPaddingRight();
        int start = 0;
        float line = 0f;
        int row = 0;
        for (int i = 0; i <= colW.length; i++) {
            boolean brk = i == colW.length;
            if (!brk && i > start && line + colW[i] > avail) brk = true;
            if (!brk) {
                line += colW[i];
                continue;
            }
            float rowW = 0f;
            for (int j = start; j < i; j++) rowW += colW[j];
            float x = getPaddingLeft() + Math.max(0f, (avail - rowW) / 2f);
            float top = getPaddingTop() + row * (float) (rowHeight + rowGapPx);
            float rubyBase = top - rubyPaint.ascent();
            float hanBase = top + (rubyOn ? rubyPx + 2 * density : 0f) - hanPaint.ascent();
            for (int j = start; j < i; j++) {
                float cx = x + colW[j] / 2f;
                if (rubies[j].length() > 0) canvas.drawText(rubies[j], cx, rubyBase, rubyPaint);
                canvas.drawText(chars[j], cx, hanBase, hanPaint);
                x += colW[j];
            }
            row++;
            start = i;
            line = 0f;
            if (i < colW.length) line += colW[i];
        }
    }
}