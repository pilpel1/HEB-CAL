"""רשימת אירועים: קיפול «אירועים חוזרים» והעדפות."""
from pathlib import Path

LIST = (Path(__file__).resolve().parent.parent / "app/templates/events_list.html").read_text(
    encoding="utf-8"
)


def test_events_list_partitions_recurring_and_persists_prefs():
    assert "hebCal.eventsListPrefs" in LIST
    assert "recurringOpen" in LIST
    assert "אירועים חוזרים" in LIST
    assert "eventIsRecurringMaster" in LIST
    assert "partitionEventsList" in LIST
    assert "currentRecurringEvents" in LIST
    assert "currentOneOffEvents" in LIST
    assert "events-recurring-details" in LIST
    assert "events-recurring-count" in LIST
