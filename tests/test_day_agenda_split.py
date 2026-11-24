"""פאנל יום בטלפון: גובה חופשי בלי מגנט לאמצע."""
from pathlib import Path

AGENDA = (Path(__file__).resolve().parent.parent / "app/static/js/calendar/day-agenda.js").read_text(
    encoding="utf-8"
)


def test_snap_keeps_mid_share_and_latches_only_edges():
    assert "const points = [0, 0.2, 0.5, 1]" not in AGENDA
    assert "latch" in AGENDA
    assert "0.025" in AGENDA
    assert "return clamped" in AGENDA
    assert "heb-cal-agenda-split" in AGENDA
    assert "heb-cal-agenda-split-prev" in AGENDA
    # מקלדת: צעדים קטנים, Home/End לקצוות
    assert "current + 0.05" in AGENDA
    assert "current - 0.05" in AGENDA
    assert "event.key === 'Home'" in AGENDA
    assert "event.key === 'End'" in AGENDA
    assert "order = [0, 0.2, 0.5, 1]" not in AGENDA
