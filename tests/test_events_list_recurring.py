"""רשימת אירועים: מקטעים מתקפלים, הצג עוד, והעדפות."""
from pathlib import Path

LIST = (Path(__file__).resolve().parent.parent / "app/templates/events_list.html").read_text(
    encoding="utf-8"
)


def test_events_list_partitions_sections_chunks_and_persists_prefs():
    assert "hebCal.eventsListPrefs" in LIST
    assert "sectionOpen" in LIST
    assert "sectionVisible" in LIST
    assert "אירועים חוזרים" in LIST
    assert "אירועים שעברו" in LIST
    assert "הצג עוד" in LIST
    assert "eventIsRecurringMaster" in LIST
    assert "partitionEventsList" in LIST
    assert "events-section-details" in LIST
    assert "events-show-more-btn" in LIST
    assert "past: false" in LIST or "past:false" in LIST.replace(" ", "")
    # תאימות להעדפות ישנות
    assert "recurringOpen" in LIST
