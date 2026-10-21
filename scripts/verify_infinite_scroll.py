"""בדיקת דפדפן headless ללוח האינסופי (Playwright + Chromium).

לא חלק מ-pytest (דורש דפדפן ושרת רץ). הרצה:

    python -m flask --app app run --port 5000   # בטרמינל נפרד
    python scripts/verify_infinite_scroll.py --base-url http://127.0.0.1:5000

בודק:
  1. רענון ×N — נוחתים על "היום", ממורכז, בלי תזוזת גלילה אחרי החשיפה.
  2. גלילה מהירה/איטית למעלה ולמטה (wheel + scrollTop תכנותי) —
     התאריך שבמרכז המסך מונוטוני (אין קפיצה אחורה), אין שורות/תאים ריקים במסך.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# נטען לפני כל סקריפט של הדף — דוגם כל פריים מה-"מסך" מנקודת מבט המשתמש.
SAMPLER_JS = r"""
(() => {
  const S = (window.__samples = []);
  const t0 = performance.now();

  function scroller() {
    const stream = document.getElementById('calendar-stream');
    if (stream && stream.scrollHeight > stream.clientHeight + 1
        && getComputedStyle(stream).overflowY !== 'visible') {
      return stream;
    }
    return document.scrollingElement;
  }
  window.__scroller = scroller;

  function viewportBox() {
    const sc = scroller();
    const r = sc === document.scrollingElement
      ? { top: 0, bottom: innerHeight }
      : sc.getBoundingClientRect();
    let top = r.top;
    for (const sel of ['.calendar-sticky-chrome', '.weekday-header']) {
      const el = document.querySelector(sel);
      if (el) {
        const er = el.getBoundingClientRect();
        if (er.bottom > top && er.top < r.bottom) top = Math.max(top, er.bottom);
      }
    }
    return { top, bottom: Math.min(r.bottom, innerHeight) };
  }
  window.__viewportBox = viewportBox;

  function probeDate() {
    const box = viewportBox();
    const y = (box.top + box.bottom) / 2;
    const el = document.elementFromPoint(innerWidth / 2, y);
    const td = el && el.closest && el.closest('td[data-date]');
    return td ? td.dataset.date : null;
  }
  window.__probeDate = probeDate;

  function emptyVisible() {
    const box = viewportBox();
    let empty = 0;
    const tds = document.querySelectorAll('#calendar-weeks td');
    for (const td of tds) {
      const r = td.getBoundingClientRect();
      if (r.bottom <= box.top + 1 || r.top >= box.bottom - 1) continue;
      if (!td.hasAttribute('data-date')) empty += 1;
    }
    const table = document.querySelector('#calendar-weeks');
    let gap = 0;
    if (table && table.rows.length) {
      const tr = table.getBoundingClientRect();
      if (tr.top > box.top + 2) gap += tr.top - box.top;
      if (tr.bottom < box.bottom - 2) gap += box.bottom - tr.bottom;
    }
    return { empty, gap: Math.round(gap) };
  }

  function booting() {
    return Boolean(document.querySelector('.infinite-calendar.is-booting'));
  }

  function tick() {
    if (document.getElementById('calendar-weeks')) {
      const sc = scroller();
      const ev = emptyVisible();
      const todayCell = document.querySelector('#calendar-weeks td.current-day');
      S.push({
        todayTop: todayCell ? Math.round(todayCell.getBoundingClientRect().top) : null,
        t: Math.round(performance.now() - t0),
        booting: booting(),
        st: Math.round(sc.scrollTop),
        date: booting() ? null : probeDate(),
        empty: ev.empty,
        gap: ev.gap,
        rows: document.querySelectorAll('#calendar-weeks tr').length,
      });
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
"""

GREGORIAN_MONTHS_HE = [
    "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
]

TODAY_GEOMETRY_JS = r"""
() => {
  const today = document.querySelector('#calendar-weeks td.current-day');
  if (!today) return null;
  const box = window.__viewportBox();
  const r = today.getBoundingClientRect();
  const tall = r.height > box.bottom - box.top;
  return {
    date: today.dataset.date,
    cellCenter: (r.top + r.bottom) / 2,
    viewCenter: (box.top + box.bottom) / 2,
    cellHeight: r.height,
    // תא גבוה מהמסך (הרבה אירועים בטלפון) — אי אפשר למרכז; מצופה שיתחיל בראש התוכן
    tallerThanView: tall,
    inView: tall
      ? Math.abs(r.top - box.top) <= 2
      : r.top >= box.top - 1 && r.bottom <= box.bottom + 1,
  };
}
"""


def seed_events(base_url: str, today: dt.date) -> None:
    """אירועים סביב היום (כולל מרובי-ימים) — שורות בגבהים שונים, כמו בשימוש אמיתי."""
    samples = [
        (-3, 5, "חופשה בצפון", "green", None),
        (-1, 0, "חתונה", "cyan", "19:00"),
        (0, 0, "רופא שיניים", "yellow", "08:15"),
        (0, 0, "יום הולדת", None, "12:30"),
        (1, 5, "כנס עבודה", "orange", None),
        (-21, 0, "פגישה", None, "10:00"),
        (15, 0, "מסיבה", None, None),
        (-60, 3, "טיול", "green", None),
        (45, 0, "ביקור הורים", "cyan", "18:00"),
    ]
    for offset, length, title, color, time in samples:
        start = today + dt.timedelta(days=offset)
        payload = {
            "title": f"{title} (בדיקה)",
            "gregorian_date": start.isoformat(),
            "hebrew_date": "בדיקה",
            "time": time,
            "color": color,
            "end_date": (start + dt.timedelta(days=length)).isoformat() if length else None,
        }
        request = urllib.request.Request(
            base_url + "/api/events",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(request).close()


def wait_ready(page: Page, timeout_ms: int = 15000) -> None:
    page.wait_for_function(
        "() => document.querySelector('.infinite-calendar') "
        "&& !document.querySelector('.infinite-calendar.is-booting')",
        timeout=timeout_ms,
    )


def check_refresh(page: Page, base_url: str, rounds: int, expected_today: str) -> list[str]:
    errors: list[str] = []
    for i in range(rounds):
        if i == 0:
            page.goto(base_url + "/")
        else:
            # גוללים קודם למקום אחר כדי לבדוק שהרענון לא משחזר את המיקום הישן
            page.mouse.move(page.viewport_size["width"] / 2, page.viewport_size["height"] * 0.6)
            for _ in range(8):
                page.mouse.wheel(0, -900)
                page.wait_for_timeout(30)
            page.reload()
        wait_ready(page)
        page.wait_for_timeout(1500)
        geo = page.evaluate(TODAY_GEOMETRY_JS)
        samples = page.evaluate("window.__samples")
        visible = [s for s in samples if not s["booting"]]
        # מה שהמשתמש רואה: מיקום תא "היום" על המסך (scrollTop עצמו משתנה בכוונה כשמוסיפים שבועות למעלה)
        tops = {s["todayTop"] for s in visible if s["todayTop"] is not None}
        dates = {s["date"] for s in visible}
        moved = max(tops) - min(tops) if tops else 0
        status = "OK"
        if not geo or geo["date"] != expected_today:
            status = "FAIL"
            errors.append(f"refresh {i + 1}: today cell missing ({geo})")
        elif not geo["inView"] or (
            not geo["tallerThanView"] and abs(geo["cellCenter"] - geo["viewCenter"]) > geo["cellHeight"]
        ):
            status = "FAIL"
            errors.append(f"refresh {i + 1}: today not centered ({geo})")
        if moved > 2:
            status = "FAIL"
            errors.append(
                f"refresh {i + 1}: today moved on screen after reveal ({moved}px, dates {sorted(d for d in dates if d)})"
            )
        print(
            f"  refresh {i + 1}: {status} today={geo and geo['date']} "
            f"offset={geo and round(geo['cellCenter'] - geo['viewCenter'])}px "
            f"today-moved-after-reveal={moved}px probe-dates={sorted(d for d in dates if d)}"
        )
    return errors


def _run_scroll(page: Page, mode: str, direction: int, step: int, frames: int) -> list[dict]:
    page.evaluate("window.__samples.length = 0")
    if mode.startswith("gesture"):
        # גלילה דרך צינור הגלילה האמיתי של Chrome (עם אנימציה), לא קפיצות scrollTop.
        # touch לא נתמך ב-headless (גם בדף ריק לא גולל), לכן רק mouse.
        speed = 1500 if step <= 600 else 8000
        cdp = page.context.new_cdp_session(page)
        for _ in range(frames):
            cdp.send(
                "Input.synthesizeScrollGesture",
                {
                    "x": page.viewport_size["width"] / 2,
                    "y": page.viewport_size["height"] * 0.6,
                    # ב-CDP חיובי = גלילה למעלה
                    "yDistance": -direction * step,
                    "speed": speed,
                    "gestureSourceType": "mouse",
                    "preventFling": False,
                },
            )
        cdp.detach()
    elif mode == "wheel":
        page.mouse.move(page.viewport_size["width"] / 2, page.viewport_size["height"] * 0.6)
        for _ in range(frames):
            page.mouse.wheel(0, direction * step)
            page.wait_for_timeout(16)
    else:
        page.evaluate(
            """([dir, step, frames]) => new Promise((resolve) => {
                let n = 0;
                const f = () => {
                  window.__scroller().scrollTop += dir * step;
                  if (++n >= frames) return resolve();
                  requestAnimationFrame(f);
                };
                requestAnimationFrame(f);
            })""",
            [direction, step, frames],
        )
    page.wait_for_timeout(700)
    return page.evaluate("window.__samples")


def check_scroll(
    page: Page,
    label: str,
    mode: str,
    direction: int,
    step: int,
    frames: int,
    stress: bool = False,
) -> list[str]:
    errors: list[str] = []
    samples = _run_scroll(page, mode, direction, step, frames)
    dates = [s["date"] for s in samples if s["date"]]
    backwards = []
    for prev, cur in zip(dates, dates[1:]):
        if (cur < prev) if direction > 0 else (cur > prev):
            backwards.append((prev, cur))
    empty_frames = [s for s in samples if s["empty"] or s["gap"]]
    first, last = (dates[0], dates[-1]) if dates else (None, None)
    span_days = (
        abs((dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days) if dates else 0
    )
    max_rows = max((s["rows"] for s in samples), default=0)
    # stress: ~120k px/s — מהיר מכל גלילה אנושית; שם נדרש רק "בלי קפיצה אחורה"
    ok = not backwards and (stress or not empty_frames) and span_days > 0
    print(
        f"  {label}: {'OK' if ok else 'FAIL'} {first} -> {last} ({span_days} days), "
        f"jump-backs={len(backwards)}, frames-with-empty-cells={len(empty_frames)}, "
        f"max-rows-in-DOM={max_rows}"
    )
    if backwards:
        errors.append(f"{label}: {len(backwards)} jump-backs, e.g. {backwards[:3]}")
    if empty_frames and not stress:
        worst = max(empty_frames, key=lambda s: (s["empty"], s["gap"]))
        errors.append(f"{label}: {len(empty_frames)} frames with empty cells/gaps, worst {worst}")
    if span_days == 0:
        errors.append(f"{label}: did not scroll at all")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--refreshes", type=int, default=5)
    parser.add_argument("--fake-today", help="YYYY-MM-DD — מקבע את Date בדפדפן (שעון רץ)")
    parser.add_argument("--artifacts", default="", help="תיקייה לצילומי מסך/וידאו")
    parser.add_argument(
        "--smooth",
        action="store_true",
        help="Chromium מלא עם smooth scrolling של גלגלת (קרוב יותר ל-Chrome בדסקטופ)",
    )
    parser.add_argument(
        "--seed-events",
        action="store_true",
        help="מוסיף אירועי בדיקה סביב היום דרך ה-API (רק מול DB זמני!)",
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--color-scheme", choices=["light", "dark"], default=None)
    args = parser.parse_args()

    artifacts = Path(args.artifacts) if args.artifacts else None
    if artifacts:
        artifacts.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    with sync_playwright() as p:
        if args.smooth:
            browser = p.chromium.launch(
                channel="chromium",
                args=["--enable-smooth-scrolling"],
            )
        else:
            browser = p.chromium.launch()
        size = {"width": args.width, "height": args.height}
        context_kwargs = {
            "viewport": size,
            "locale": "he-IL",
            "record_video_dir": str(artifacts / "video") if artifacts else None,
            "record_video_size": size,
        }
        if args.color_scheme:
            context_kwargs["color_scheme"] = args.color_scheme
        context = browser.new_context(**context_kwargs)
        context.add_init_script(SAMPLER_JS)
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        if args.fake_today:
            fake = dt.datetime.fromisoformat(args.fake_today + "T10:00:00")
            page.clock.set_fixed_time(fake)
            expected_today = args.fake_today
        else:
            expected_today = dt.date.today().isoformat()

        if args.seed_events:
            seed_events(args.base_url, dt.date.fromisoformat(expected_today))

        print(f"[refresh] today={expected_today}")
        errors += check_refresh(page, args.base_url, args.refreshes, expected_today)
        if artifacts:
            page.screenshot(path=str(artifacts / "after_refresh_today_centered.png"))

        print("[scroll]")
        plan = [
            ("slow gesture up", "gesture-mouse", -1, 500, 6),
            ("fast gesture up", "gesture-mouse", -1, 2500, 8),
            ("fast gesture down", "gesture-mouse", 1, 2500, 8),
            ("slow wheel up", "wheel", -1, 120, 90),
            ("slow wheel down", "wheel", 1, 120, 90),
            ("fast wheel up", "wheel", -1, 900, 120),
            ("fast wheel down", "wheel", 1, 900, 240),
            ("fast programmatic up", "programmatic", -1, 700, 240),
            ("fast programmatic down", "programmatic", 1, 700, 240),
            ("stress programmatic down", "programmatic", 1, 2000, 150),
            ("stress programmatic up", "programmatic", -1, 2000, 300),
        ]
        for label, mode, direction, step, frames in plan:
            stress = label.startswith("stress")
            errors += check_scroll(page, label, mode, direction, step, frames, stress)
            if artifacts:
                page.screenshot(path=str(artifacts / f"after_{label.replace(' ', '_')}.png"))

        print("[jump to date]")
        today_date = dt.date.fromisoformat(expected_today)
        near = (today_date.replace(day=1) + dt.timedelta(days=40)).replace(day=1)
        for target in (near, dt.date(today_date.year + 4, 3, 1), dt.date(today_date.year - 7, 11, 1)):
            page.click("#jumpToDateBtn")
            page.select_option("#monthSelect", str(target.month - 1))
            page.select_option("#yearSelect", str(target.year))
            page.click("text=אישור")
            page.wait_for_timeout(1500)
            first = page.evaluate(
                """(d) => {
                    const cell = document.querySelector(`#calendar-weeks td[data-date="${d}"]`);
                    if (!cell) return null;
                    const box = window.__viewportBox();
                    const r = cell.getBoundingClientRect();
                    return { top: r.top - box.top, label: document.getElementById('current-month').textContent };
                }""",
                target.isoformat(),
            )
            month_name = GREGORIAN_MONTHS_HE[target.month - 1]
            ok = bool(
                first
                and abs(first["top"]) <= 2
                and first["label"].startswith(f"{month_name} {target.year}")
            )
            print(f"  jump to {target}: {'OK' if ok else 'FAIL'} {first}")
            if not ok:
                errors.append(f"jump to {target}: {first}")

        print("[today button]")
        page.get_by_role("button", name="היום").click()
        page.wait_for_timeout(1500)
        geo = page.evaluate(TODAY_GEOMETRY_JS)
        ok = bool(geo and geo["inView"] and geo["date"] == expected_today)
        print(f"  today button: {'OK' if ok else 'FAIL'} {geo}")
        if not ok:
            errors.append(f"today button: {geo}")
        if artifacts:
            page.screenshot(path=str(artifacts / "after_today_button.png"))

        context.close()
        browser.close()

    print()
    if errors:
        print("FAILURES:")
        for e in errors:
            print("  -", e)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
