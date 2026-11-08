package com.poetry.app;

import android.animation.ObjectAnimator;
import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import android.view.animation.DecelerateInterpolator;

/**
 * 飞花令 dial: the 令字 may sit in 任意位置 or 第1..第7字, drawn as 8 wedges around a hollow
 * centre (that hole hosts the 开始/停止/认输 buttons).
 *
 * The wedge band rotates and the top pointer never moves, so choosing a position reads as a
 * wheel spin landing the chosen wedge under the pointer (spinTo). Wedge i sits at i*45deg
 * clockwise from the pointer, so the band angle centring wedge i is exactly -i*45deg.
 *
 * Labels stay upright at every wedge (clock-face style), and the hub is wide enough for three
 * round buttons: 开始 / 停止 side by side with 认输 below.
 */
public class DialView extends View {

    public static final int SLOTS = 8;              // 0 = 任意, 1..7 = 第1..7字
    private static final float STEP = 360f / SLOTS;

    public interface Listener { void onSlotPicked(int slot); }

    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint sep = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint label = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint hub = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint rim = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF oval = new RectF();
    private final Path pointer = new Path();

    private String[] labels = {"任意", "第1字", "第2字", "第3字", "第4字", "第5字", "第6字", "第7字"};
    private float angle = 0f;                       // wedge-band rotation, degrees
    private int selected = 0;
    private float density = 1f;
    private Listener listener;
    private ObjectAnimator spin;

    public DialView(Context c, AttributeSet a) {
        super(c, a);
        density = getResources().getDisplayMetrics().density;
        sep.setStyle(Paint.Style.STROKE);
        sep.setStrokeWidth(1.2f * density);
        sep.setColor(0x33FFFFFF);
        rim.setStyle(Paint.Style.STROKE);
        rim.setStrokeWidth(1.6f * density);
        rim.setColor(0x22000000);
        hub.setStyle(Paint.Style.FILL);
        label.setTextAlign(Paint.Align.CENTER);
        label.setFakeBoldText(true);
    }

    public void setListener(Listener l) { listener = l; }

    /** Animated through ObjectAnimator, hence a bean-style setter. */
    public void setAngle(float a) { angle = a; invalidate(); }
    public float getAngle() { return angle; }

    public void setLabels(String[] l) {
        if (l != null && l.length == SLOTS) { labels = l; invalidate(); }
    }

    /** Land the wedge under the pointer with no animation (first layout, restore). */
    public void selectQuiet(int slot) {
        selected = clamp(slot);
        angle = -selected * STEP;
        invalidate();
    }

    public int getSelected() { return selected; }

    /** Spin clockwise about three turns, decelerating onto `slot`. */
    public void spinTo(int slot) {
        selected = clamp(slot);
        float want = -selected * STEP;
        float diff = ((want - angle) % 360f + 360f) % 360f;
        if (spin != null && spin.isRunning()) spin.cancel();
        spin = ObjectAnimator.ofFloat(this, "angle", angle + 3f * 360f + diff);
        spin.setDuration(850);
        spin.setInterpolator(new DecelerateInterpolator(1.7f));
        spin.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            public void onAnimationUpdate(ValueAnimator v) { invalidate(); }
        });
        spin.start();
    }

    private static int clamp(int i) { return i < 0 ? 0 : (i >= SLOTS ? SLOTS - 1 : i); }

    /** Ring radius, leaving headroom at the top for the pointer triangle. */
    private float outerR() { return Math.min(getWidth(), getHeight()) / 2f - 22f * density; }

    /**
     * Hub radius. 0.70 rather than a slimmer ring: the hole has to hold three round buttons
     * (开始 / 停止 side by side, 认输 beneath), and onTouchEvent uses the same number so the
     * dead zone matches what is drawn.
     */
    private float innerR() { return outerR() * 0.70f; }

    /** 0-based index into a poem line that this slot demands; null = 任意位置. */
    public static Integer posOf(int slot) { return slot <= 0 ? null : Integer.valueOf(slot - 1); }

    /** Inverse of posOf, so a stored rule can re-seat the dial. */
    public static int slotOf(Integer pos) { return pos == null ? 0 : clamp(pos.intValue() + 1); }

    @Override
    protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight();
        float cx = w / 2f, cy = h / 2f;
        float outer = outerR();
        float inner = innerR();
        oval.set(cx - outer, cy - outer, cx + outer, cy + outer);

        for (int i = 0; i < SLOTS; i++) {
            float start = angle - 90f - STEP / 2f + i * STEP;
            boolean on = i == selected;
            fill.setColor(on ? (i == 0 ? 0xFF8B3A2B : 0xFFB4553F) : 0xFFF1E7D3);
            c.drawArc(oval, start, STEP, true, fill);
        }
        c.drawArc(oval, 0, 360, false, rim);

        // punch the hub: the hole is where the centre buttons live
        hub.setColor(0xFFFBF7EF);
        c.drawCircle(cx, cy, inner, hub);
        c.drawCircle(cx, cy, inner, rim);

        // Wedges are painted with absolute arc angles, so the text was never tilted: drawing it
        // straight (no canvas rotation) keeps every label upright, clock-face style. Rotating by
        // the wedge angle here was the original bug -- it turned 第5/6/7字 upside down.
        label.setTextSize((outer - inner) * 0.44f);
        float mid = (inner + outer) / 2f;
        for (int i = 0; i < SLOTS; i++) {
            float band = angle + i * STEP;                       // 0 = under the pointer
            boolean on = i == selected;
            label.setColor(on ? 0xFFFFFFFF : 0xFF6B5B45);
            float rad = (float) Math.toRadians(band - 90f);
            float tx = cx + mid * (float) Math.cos(rad);
            float ty = cy + mid * (float) Math.sin(rad);
            c.drawText(labels[i], tx, ty + label.getTextSize() * 0.36f, label);
        }

        pointer.moveTo(cx, cy - outer + 2f * density);
        pointer.lineTo(cx - 7f * density, cy - outer - 12f * density);
        pointer.lineTo(cx + 7f * density, cy - outer - 12f * density);
        pointer.close();
        fill.setColor(0xFF8B3A2B);
        c.drawPath(pointer, fill);
    }

    /**
     * Wedge i occupies [angle-22.5+i*45, angle+22.5+i*45] in canvas degrees (0 = east, growing
     * clockwise); the pointer sits at -90. A touch `deg` clockwise from the top is canvas angle
     * deg-90, so the hit wedge is round((deg-angle)/45), which is why `angle` is SUBTRACTED.
     */
    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (e.getAction() != MotionEvent.ACTION_DOWN) return true;
        float cx = getWidth() / 2f, cy = getHeight() / 2f;
        float outer = outerR(), inner = innerR();
        float dx = e.getX() - cx, dy = e.getY() - cy;
        float dist = (float) Math.sqrt(dx * dx + dy * dy);
        if (dist < inner || dist > outer * 1.12f) return false;             // hub = buttons
        double deg = Math.toDegrees(Math.atan2(dy, dx)) + 90d;              // 0 = up, cw +
        double rel = ((deg - angle) % 360d + 360d) % 360d;
        int hit = (int) (Math.floor(rel / STEP + 0.5d) % SLOTS);
        spinTo(hit);
        if (listener != null) listener.onSlotPicked(hit);
        return true;
    }
}