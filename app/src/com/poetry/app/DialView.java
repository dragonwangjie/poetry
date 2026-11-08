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

import java.util.Random;

/**
 * 飞花令 dial, drawn like a clock: the 8 wedges (任意位置 + 第1..第7字) are FIXED around the rim
 * and a single hand (表针) sweeps round them. Pressing 开始 lets the hand run for 5s and settle
 * on a wedge at random; wherever it points when it stops IS the round's position rule.
 *
 * Hand angle convention: 0 = straight up at wedge 0, growing clockwise, so wedge i is centred at
 * exactly i*45deg and landing on it needs hand angle i*STEP plus whole turns.
 *
 * Tapping a wedge still works as a manual override (the hand animates onto it without the
 * countdown). The hollow centre hosts the round buttons; onTouchEvent returns false inside the
 * hub radius so those buttons receive their taps.
 */
public class DialView extends View {

    public static final int SLOTS = 8;              // 0 = 任意, 1..7 = 第1..7字
    private static final float STEP = 360f / SLOTS;
    public static final long SPIN_MS = 5000;        // 开始 = 5 秒倒计时后自动停止

    public interface Listener { void onSlotPicked(int slot); }

    /** Fired once a timed spin has decelerated and settled. */
    public interface SpinDone { void onSettled(int slot); }

    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint label = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint hub = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint rim = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint hand = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint badge = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint badgeText = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF oval = new RectF();

    private String[] labels = {"任意", "第1字", "第2字", "第3字", "第4字", "第5字", "第6字", "第7字"};
    private float handAngle = 0f;                   // degrees clockwise from 12 o'clock
    private int selected = 0;
    private int countdown = 0;                       // >0 while a timed spin runs
    private float density = 1f;
    private Listener listener;
    private SpinDone onDone;
    private ObjectAnimator anim;
    private final Random rnd = new Random();

    public DialView(Context c, AttributeSet a) {
        super(c, a);
        density = getResources().getDisplayMetrics().density;
        rim.setStyle(Paint.Style.STROKE);
        rim.setStrokeWidth(1.6f * density);
        rim.setColor(0x22000000);
        hub.setStyle(Paint.Style.FILL);
        hand.setStyle(Paint.Style.FILL);
        hand.setColor(0xFF8B3A2B);
        badge.setStyle(Paint.Style.FILL);
        badge.setColor(0xFF8B3A2B);
        label.setTextAlign(Paint.Align.CENTER);
        label.setFakeBoldText(true);
        badgeText.setTextAlign(Paint.Align.CENTER);
        badgeText.setFakeBoldText(true);
        badgeText.setColor(0xFFFFFFFF);
    }

    public void setListener(Listener l) { listener = l; }

    /** Driven by ObjectAnimator, hence a bean-style setter. */
    public void setAngle(float a) { handAngle = a; invalidate(); }
    public float getAngle() { return handAngle; }

    public void setLabels(String[] l) {
        if (l != null && l.length == SLOTS) { labels = l; invalidate(); }
    }

    public int getSelected() { return selected; }

    public boolean isSpinning() { return anim != null && anim.isRunning(); }

    /** Point at a wedge without animating (first layout, state restore). */
    public void selectQuiet(int slot) {
        selected = clamp(slot);
        handAngle = selected * STEP;
        countdown = 0;
        invalidate();
    }

    /**
     * 开始: run the hand for {@link #SPIN_MS}, decelerating, and let it land wherever it lands.
     * Four whole turns guarantees the sweep reads as a spin whatever the wedge it is heading for.
     */
    public void spinRandom(SpinDone done) {
        int target = rnd.nextInt(SLOTS);
        onDone = done;
        countdown = (int) Math.ceil(SPIN_MS / 1000.0);
        animateTo(target, SPIN_MS, 1.25f, 4);
    }

    /** Abandon a running spin without firing the settle callback (认输 mid-draw). */
    public void cancelSpin() {
        if (anim != null && anim.isRunning()) {
            onDone = null;
            anim.cancel();
        }
        countdown = 0;
        invalidate();
    }

    /** Manual override from a wedge tap: quick settle, no countdown. */
    public void spinTo(int slot) {
        onDone = null;
        countdown = 0;
        animateTo(clamp(slot), 600, 1.6f, 0);
    }

    /**
     * Sweep clockwise onto `slot`: `turns` whole revolutions first, then the remaining delta, so
     * the motion never reads as a rewind. delta is the clockwise gap from where the hand is now
     * to wedge slot, and the hand lands on exactly slot*STEP mod 360 either way.
     */
    private void animateTo(int slot, long ms, float factor, int turns) {
        selected = slot;
        float delta = ((slot * STEP - handAngle) % 360f + 360f) % 360f;
        float target = handAngle + turns * 360f + delta;
        if (anim != null && anim.isRunning()) anim.cancel();
        anim = ObjectAnimator.ofFloat(this, "angle", target);
        anim.setDuration(ms);
        anim.setInterpolator(new DecelerateInterpolator(factor));
        anim.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            public void onAnimationUpdate(ValueAnimator v) {
                if (countdown > 0) {
                    int secs = (int) Math.ceil(SPIN_MS * (1f - v.getAnimatedFraction()) / 1000.0);
                    if (secs >= 0) countdown = secs;
                }
                invalidate();
            }
        });
        anim.addListener(new android.animation.AnimatorListenerAdapter() {
            @Override public void onAnimationEnd(android.animation.Animator a) {
                countdown = 0;
                invalidate();
                if (onDone != null) { SpinDone cb = onDone; onDone = null; cb.onSettled(selected); }
            }
        });
        anim.start();
    }

    private static int clamp(int i) { return i < 0 ? 0 : (i >= SLOTS ? SLOTS - 1 : i); }

    /** Ring radius, leaving headroom at the top for the pointer triangle. */
    private float outerR() { return Math.min(getWidth(), getHeight()) / 2f - 22f * density; }

    /**
     * Hub radius. 0.70 keeps a hole big enough for the two stacked round buttons (开始 over
     * 认输); onTouchEvent uses the same accessor so the dead zone matches what is drawn.
     */
    private float innerR() { return outerR() * 0.70f; }

    /** 0-based index into a poem line that this slot demands; null = 任意位置. */
    public static Integer posOf(int slot) { return slot <= 0 ? null : Integer.valueOf(slot - 1); }

    /** Inverse of posOf, so a stored rule can re-seat the hand. */
    public static int slotOf(Integer pos) { return pos == null ? 0 : clamp(pos.intValue() + 1); }

    @Override
    protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight();
        float cx = w / 2f, cy = h / 2f;
        float outer = outerR();
        float inner = innerR();
        oval.set(cx - outer, cy - outer, cx + outer, cy + outer);

        // fixed face: wedge i centred at i*STEP clockwise from the top
        for (int i = 0; i < SLOTS; i++) {
            float start = -90f - STEP / 2f + i * STEP;
            boolean on = i == selected;
            fill.setColor(on ? (i == 0 ? 0xFF8B3A2B : 0xFFB4553F) : 0xFFF1E7D3);
            c.drawArc(oval, start, STEP, true, fill);
        }
        c.drawArc(oval, 0, 360, false, rim);

        hub.setColor(0xFFFBF7EF);
        c.drawCircle(cx, cy, inner, hub);
        c.drawCircle(cx, cy, inner, rim);

        // Wedges are painted with absolute arc angles, so text is never tilted: drawing it
        // straight keeps every label upright. Rotating by the wedge angle flipped 第5/6/7字.
        label.setTextSize((outer - inner) * 0.44f);
        float mid = (inner + outer) / 2f;
        for (int i = 0; i < SLOTS; i++) {
            boolean on = i == selected;
            label.setColor(on ? 0xFFFFFFFF : 0xFF6B5B45);
            float rad = (float) Math.toRadians(i * STEP - 90f);
            float tx = cx + mid * (float) Math.cos(rad);
            float ty = cy + mid * (float) Math.sin(rad);
            c.drawText(labels[i], tx, ty + label.getTextSize() * 0.36f, label);
        }

        drawHand(c, cx, cy, outer, inner);

        // top pointer: a fixed marker where the hand is read
        Path p = new Path();
        p.moveTo(cx, cy - outer + 2f * density);
        p.lineTo(cx - 7f * density, cy - outer - 12f * density);
        p.lineTo(cx + 7f * density, cy - outer - 12f * density);
        p.close();
        fill.setColor(0xFF2B2B2B);
        c.drawPath(p, fill);
    }

    /** The sweeping hand, plus the seconds badge riding on it while the countdown runs. */
    private void drawHand(Canvas c, float cx, float cy, float outer, float inner) {
        float rad = (float) Math.toRadians(handAngle - 90f);
        float tipx = cx + (outer - 4f * density) * (float) Math.cos(rad);
        float tipy = cy + (outer - 4f * density) * (float) Math.sin(rad);
        float perp = rad + (float) Math.PI / 2f;
        float bw = 5f * density;
        Path p = new Path();
        p.moveTo(tipx, tipy);
        p.lineTo(cx + bw * (float) Math.cos(perp), cy + bw * (float) Math.sin(perp));
        p.lineTo(cx - bw * (float) Math.cos(perp), cy - bw * (float) Math.sin(perp));
        p.close();
        c.drawPath(p, hand);
        c.drawCircle(cx, cy, 6f * density, hand);

        if (countdown > 0) {
            float br = 13f * density;
            float bx = cx + (outer - 26f * density) * (float) Math.cos(rad);
            float by = cy + (outer - 26f * density) * (float) Math.sin(rad);
            c.drawCircle(bx, by, br, badge);
            badgeText.setTextSize(15f * density);
            c.drawText(String.valueOf(countdown), bx, by + badgeText.getTextSize() * 0.36f, badgeText);
        }
    }

    /**
     * The face is fixed, so the wedge under a touch is simply round(deg/45) where deg is measured
     * clockwise from the top. Inside the hub the touch is refused so the round buttons get it.
     */
    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (e.getAction() != MotionEvent.ACTION_DOWN) return true;
        if (isSpinning()) return true;                 // ignore taps mid-spin
        float cx = getWidth() / 2f, cy = getHeight() / 2f;
        float outer = outerR(), inner = innerR();
        float dx = e.getX() - cx, dy = e.getY() - cy;
        float dist = (float) Math.sqrt(dx * dx + dy * dy);
        if (dist < inner || dist > outer * 1.12f) return false;
        double deg = Math.toDegrees(Math.atan2(dx, -dy));                 // 0 = up, cw +
        int hit = (int) (Math.floor(((deg % 360d + 360d) % 360d) / STEP + 0.5d) % SLOTS);
        spinTo(hit);
        if (listener != null) listener.onSlotPicked(hit);
        return true;
    }
}