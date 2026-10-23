"""ניתוב פקודות וכפתורים. בלי רשת — מחזיר טקסט ומקלדת."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from app.bot import directory, household, query as lists, store, ui
from app.bot.parse import InputError, explain_payload_error, parse_user_date, parse_user_time
from app.bot.session import ensure_bot_schema, load_session, save_session
from app.bot.textutil import clean_line, esc
from app.database import get_db, get_event
from app.reminders.schedule import reminder_timezone
from app.services.event_payload import DESCRIPTION_MAX, TITLE_MAX, EventPayloadError
from app.services.shifts import ShiftError

log = logging.getLogger("hebcal.bot")

_CB = re.compile(r"^[A-Za-z0-9:_-]{1,64}$")
_EV = re.compile(r"^ev:(\d{1,12})(?::(\d{8}))?$")
_ED_ID = re.compile(r"^ed:(\d{1,12})$")
_FIND_MAX = 80


def local_today(now: datetime | None = None) -> date:
    tz = reminder_timezone()
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    return current.astimezone(tz).date()


def parse_command(text: str) -> tuple[str, str] | None:
    raw = text.strip()
    if not raw.startswith("/"):
        return None
    first, _, rest = raw.partition(" ")
    name = first[1:]
    if "@" in name:
        name = name.split("@", 1)[0]
    name = name.lower()
    if not re.fullmatch(r"[a-z0-9_]+", name):
        return None
    return name, rest.strip()


def parse_update(update: dict) -> dict | None:
    if not isinstance(update, dict):
        return None
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        message = callback.get("message") or {}
        chat = (message.get("chat") or {}).get("id")
        if isinstance(chat, bool) or chat is None:
            return None
        data = callback.get("data")
        if not isinstance(data, str):
            data = ""
        return {
            "chat_id": chat,
            "kind": "callback",
            "text": "",
            "data": data.strip(),
            "callback_id": callback.get("id"),
            "edit_id": message.get("message_id"),
        }
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = (message.get("chat") or {}).get("id")
    if isinstance(chat, bool) or chat is None:
        return None
    text = message.get("text")
    if not isinstance(text, str):
        text = ""
    return {
        "chat_id": chat,
        "kind": "message",
        "text": text,
        "data": "",
        "callback_id": None,
        "edit_id": None,
    }


def _blank_session() -> dict:
    return {
        "flow": None,
        "draft": {},
        "list": {"kind": "today", "page": 0, "person_id": None, "query": ""},
        "filter": "all",
        "household_id": None,
        "open_id": None,
        "open_day": None,
        "link_page": 0,
        "who_page": 0,
        "workers_page": 0,
    }


def _session(raw: dict) -> dict:
    base = _blank_session()
    if not isinstance(raw, dict):
        return base
    base.update(raw)
    if base.get("filter") not in {"all", "ev", "sh"}:
        base["filter"] = "all"
    if not isinstance(base.get("draft"), dict):
        base["draft"] = {}
    listing = base.get("list")
    if not isinstance(listing, dict):
        base["list"] = _blank_session()["list"]
    else:
        merged = _blank_session()["list"]
        merged.update(listing)
        base["list"] = merged
    return base


def _prefix_int(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    rest = data[len(prefix) :]
    if not rest.isdigit():
        return None
    return int(rest)


def _take_title(text: str) -> str:
    title = clean_line(text)
    if not title:
        raise InputError("חסרה כותרת.")
    if len(title) > TITLE_MAX:
        raise InputError("הכותרת ארוכה מדי.")
    return title


def _take_description(text: str) -> str:
    if clean_line(text) == "בלי":
        return ""
    description = (text or "").strip()
    if len(description) > DESCRIPTION_MAX:
        raise InputError("התיאור ארוך מדי.")
    return description


def _with_error(text: str, error: str) -> str:
    if not error:
        return text
    return esc(error) + "\n\n" + text


class Bot:
    def __init__(self, chat_id, today: date, session: dict):
        self.chat_id = chat_id
        self.today = today
        self.session = session
        self.toast = ""
        self.house_note = ""
        self.reload_people()
        self.resolve_household()

    def reload_people(self) -> None:
        from app.reminders.repository import list_people

        self.people = list_people()
        self.by_id = {person["id"]: person for person in self.people}
        cid = str(self.chat_id)
        self.linked = [
            person for person in self.people if (person.get("telegram_chat_id") or "") == cid
        ]

    def resolve_household(self) -> None:
        self.homes = household.list_households()
        hid = self.session.get("household_id")
        current = next((item for item in self.homes if item["id"] == hid), None)
        if hid is None:
            if len(self.homes) == 1:
                self.session["household_id"] = self.homes[0]["id"]
                current = self.homes[0]
            else:
                current = None
        elif current is None:
            if len(self.homes) == 1:
                self.session["household_id"] = self.homes[0]["id"]
                self.house_note = "הבית שסומן לא קיים. עברנו לבית שנשאר."
                current = self.homes[0]
            else:
                self.house_note = "הבית שסומן כבר לא קיים."
                current = None
        self.household = current

    def refresh_household(self) -> None:
        hid = self.session.get("household_id")
        self.homes = household.list_households()
        self.household = next((item for item in self.homes if item["id"] == hid), None)

    def shifts_on(self) -> bool | None:
        if self.household is None:
            return None
        return bool(self.household.get("shifts_enabled"))

    def out(self, text: str, markup: dict) -> dict:
        return {"text": text, "markup": markup, "toast": self.toast}

    def _clear_flow(self) -> None:
        self.session["flow"] = None
        self.session["draft"] = {}

    def go_home(self, *, cancelled: bool = False, note: str = "") -> dict:
        had = bool(self.session.get("flow"))
        self._clear_flow()
        if cancelled and had and not note:
            note = "בוטל."
        text, markup = ui.home_screen(self.chat_id, self.linked, note=note)
        return self.out(text, markup)

    def run(self, parsed: dict) -> dict:
        if parsed["kind"] == "callback":
            data = parsed["data"]
            if not data or not _CB.fullmatch(data):
                self.toast = "הכפתור לא מוכר"
                return self.go_home()
            return self.on_callback(data)
        text = parsed["text"]
        if text.strip().startswith("/"):
            command = parse_command(text)
            if command is None:
                return self.go_home(note="אין פקודה כזאת.")
            return self.on_command(*command)
        if text.strip():
            return self.on_text(text)
        return self._nudge()

    def on_command(self, name: str, arg: str) -> dict:
        if name in {"start", "menu", "help"}:
            return self.go_home(cancelled=True)
        if name == "today":
            return self.show_list("today", clear_flow=True)
        if name == "week":
            return self.show_list("week", clear_flow=True)
        if name == "add":
            return self.start_add()
        if name == "find":
            if arg:
                return self._run_find(arg, clear_flow=True)
            self._clear_flow()
            self.session["flow"] = "find"
            return self.out(*ui.find_screen())
        if name == "settings":
            had = bool(self.session.get("flow"))
            self._clear_flow()
            note = "הטיוטה בוטלה." if had else ""
            return self.settings(note=note)
        self._clear_flow()
        return self.go_home(note="אין פקודה כזאת.")

    def on_callback(self, data: str) -> dict:
        if data in {"home", "cancel"}:
            return self.go_home(cancelled=(data == "cancel" or bool(self.session.get("flow"))))
        if data == "today":
            return self.show_list("today", clear_flow=True)
        if data == "week":
            return self.show_list("week", clear_flow=True)
        if data == "soon":
            return self.show_list("soon", clear_flow=True)
        if data == "shifts":
            self.session["list"]["shift_sunday"] = ""
            return self.show_list("shifts", clear_flow=True)
        if data.startswith("sw:"):
            return self._open_shift_week(data[3:])
        if data == "who":
            self._clear_flow()
            return self.out(*ui.person_picker(self.people, self.session.get("who_page") or 0))
        if data == "find":
            self._clear_flow()
            self.session["flow"] = "find"
            return self.out(*ui.find_screen())
        if data == "add":
            return self.start_add()
        if data == "set":
            had = bool(self.session.get("flow"))
            self._clear_flow()
            return self.settings(note="הטיוטה בוטלה." if had else "")
        if data.startswith("pg:"):
            return self._page(data)
        if data.startswith("flt:"):
            mode = data.split(":", 1)[1]
            if mode not in {"all", "ev", "sh"}:
                self.toast = "הכפתור לא מוכר"
                return self.go_home()
            self.session["filter"] = mode
            kind = self.session["list"].get("kind") or "today"
            return self.show_list(kind, page=0)
        if data == "back:list":
            return self._back_list()
        if data == "back:add":
            return self._back_add()
        if data == "back:edit":
            return self._edit_menu()
        if data == "back:ev":
            self._clear_flow()
            return self._reopen()
        who_page = _prefix_int(data, "whop:")
        if who_page is not None:
            self.session["who_page"] = who_page
            return self.out(*ui.person_picker(self.people, who_page))
        who_id = _prefix_int(data, "who:")
        if who_id is not None:
            self.session["who_page"] = 0
            return self.show_list("person", person_id=who_id, clear_flow=True)
        event_match = _EV.fullmatch(data)
        if event_match:
            focus = ui.parse_ymd(event_match.group(2) or "")
            return self._open(int(event_match.group(1)), focus)
        delete_id = _prefix_int(data, "rmy:")
        if delete_id is not None:
            return self._do_delete(delete_id)
        ask_delete = _prefix_int(data, "rm:")
        if ask_delete is not None:
            return self._ask_delete(ask_delete)
        if data.startswith("ed"):
            return self._on_edit(data)
        if data.startswith("add:"):
            return self._on_add(data)
        if data.startswith("sh:"):
            return self._on_shift(data)
        if data.startswith("set"):
            return self._on_settings(data)
        self.toast = "הכפתור לא מוכר"
        return self.go_home()

    def on_text(self, text: str) -> dict:
        flow = self.session.get("flow")
        try:
            if flow == "title":
                self.session["draft"]["title"] = _take_title(text)
                self.session["draft"]["gregorian_date"] = self.today.isoformat()
                self.session["draft"]["time"] = None
                self.session["draft"]["description"] = ""
                self.session["draft"]["end_date"] = None
                self.session["flow"] = "add"
                return self._add_confirm()
            if flow == "date":
                day = parse_user_date(text, self.today)
                self.session["draft"]["gregorian_date"] = day.isoformat()
                self.session["flow"] = "add"
                return self._add_confirm()
            if flow == "time":
                self.session["draft"]["time"] = parse_user_time(text)
                self.session["flow"] = "add"
                return self._add_confirm()
            if flow == "desc":
                self.session["draft"]["description"] = _take_description(text)
                self.session["flow"] = "add"
                return self._add_confirm()
            if flow == "end":
                if clean_line(text) == "בלי":
                    self.session["draft"]["end_date"] = None
                else:
                    note = self._apply_end(parse_user_date(text, self.today))
                    if note:
                        self.session["flow"] = "add"
                        return self._add_confirm(note)
                self.session["flow"] = "add"
                return self._add_confirm()
            if flow == "edit_title":
                self.session["draft"]["title"] = _take_title(text)
                self.session["flow"] = "edit"
                return self._edit_menu(saved=ui.field_saved("title"))
            if flow == "edit_date_text":
                day = parse_user_date(text, self.today)
                self.session["draft"]["gregorian_date"] = day.isoformat()
                return self._after_edit_date()
            if flow == "edit_time":
                self.session["draft"]["time"] = parse_user_time(text)
                self.session["flow"] = "edit"
                return self._edit_menu(saved=ui.field_saved("time"))
            if flow == "edit_desc":
                self.session["draft"]["description"] = _take_description(text)
                self.session["flow"] = "edit"
                return self._edit_menu(saved=ui.field_saved("desc"))
            if flow == "edit_end":
                if clean_line(text) == "בלי":
                    self.session["draft"]["end_date"] = None
                else:
                    note = self._apply_end(parse_user_date(text, self.today))
                    if note and "לפני" in note:
                        text_screen, markup = ui.edit_end_screen(self.session["draft"])
                        return self.out(_with_error(text_screen, note), markup)
                    if note:
                        self.session["flow"] = "edit"
                        return self._edit_menu(note)
                self.session["flow"] = "edit"
                return self._edit_menu(saved=ui.field_saved("end"))
            if flow == "find":
                return self._run_find(text)
            if flow == "link_name":
                return self._create_person(text)
            if flow == "shift_date":
                day = parse_user_date(text, self.today)
                self.session["draft"]["gregorian_date"] = day.isoformat()
                self.session["flow"] = "shift"
                return self._shift_confirm()
            if flow == "edit_date":
                day = parse_user_date(text, self.today)
                self.session["draft"]["gregorian_date"] = day.isoformat()
                return self._after_edit_date()
        except InputError as exc:
            return self._repeat_flow(str(exc))
        if flow:
            return self._repeat_flow("לחצו על אחד הכפתורים.")
        return self.go_home(note="בחרו כפתור.")

    def _nudge(self) -> dict:
        if self.session.get("flow"):
            return self._repeat_flow("לא קיבלתי טקסט.")
        return self.go_home(note="בחרו כפתור.")

    def _repeat_flow(self, error: str) -> dict:
        flow = self.session.get("flow")
        if flow == "title":
            text, markup = ui.add_title_screen()
        elif flow == "date":
            text, markup = ui.add_date_screen(self.today)
        elif flow == "time":
            text, markup = ui.add_time_text_screen()
        elif flow == "desc":
            text, markup = ui.add_desc_screen()
        elif flow == "end":
            text, markup = ui.add_end_screen(self.session.get("draft") or {}, self.today)
        elif flow == "edit_title":
            text, markup = ui.edit_title_screen()
        elif flow == "edit_date":
            text, markup = ui.edit_date_screen(
                self.session.get("draft") or {},
                self.today,
                shift=bool((self.session.get("draft") or {}).get("is_shift")),
            )
        elif flow == "edit_date_text":
            text, markup = ui.edit_date_text_screen()
        elif flow == "edit_time":
            text, markup = ui.edit_time_text_screen()
        elif flow == "edit_desc":
            text, markup = ui.edit_desc_screen()
        elif flow == "edit_end":
            text, markup = ui.edit_end_screen(self.session.get("draft") or {})
        elif flow == "find":
            text, markup = ui.find_screen(error=error)
            return self.out(text, markup)
        elif flow == "link_name":
            text, markup = ui.link_name_screen(error=error)
            return self.out(text, markup)
        elif flow == "shift_date":
            text, markup = ui.shift_date_text_screen(self.today)
        elif flow == "add":
            return self._add_confirm(error)
        elif flow == "edit":
            return self._edit_menu(error)
        elif flow == "shift":
            return self._shift_confirm(error)
        else:
            return self.go_home(note=error)
        return self.out(_with_error(text, error), markup)

    def start_add(self) -> dict:
        self.session["flow"] = "title"
        self.session["draft"] = {
            "gregorian_date": self.today.isoformat(),
            "time": None,
            "description": "",
            "end_date": None,
        }
        return self.out(*ui.add_title_screen())

    def _add_confirm(self, error: str = "") -> dict:
        self.session["flow"] = "add"
        return self.out(*ui.add_confirm_screen(self.session.get("draft") or {}, self.today, error=error))

    def _back_add(self) -> dict:
        if (self.session.get("draft") or {}).get("title"):
            return self._add_confirm()
        return self.start_add()

    def _apply_end(self, day: date) -> str | None:
        draft = self.session["draft"]
        start_raw = (draft.get("gregorian_date") or self.today.isoformat())[:10]
        start = date.fromisoformat(start_raw)
        if day < start:
            raise InputError("תאריך הסיום לפני ההתחלה.")
        if day == start:
            draft["end_date"] = None
            return "נשאר יום אחד."
        draft["end_date"] = day.isoformat()
        return None

    def _on_add(self, data: str) -> dict:
        draft = self.session.setdefault("draft", {})
        if data == "add:ok":
            return self._save_add()
        if not draft.get("title") and data != "add:ok":
            return self._repeat_flow("קודם כותבים שם.") if self.session.get("flow") == "title" else self.start_add()
        if data == "add:d:0":
            draft["gregorian_date"] = self.today.isoformat()
            return self._add_confirm()
        if data == "add:d:1":
            draft["gregorian_date"] = (self.today + timedelta(days=1)).isoformat()
            return self._add_confirm()
        if data == "add:d:x":
            self.session["flow"] = "date"
            return self.out(*ui.add_date_screen(self.today))
        if data == "add:time":
            self.session["flow"] = "add"
            return self.out(*ui.add_time_screen(draft))
        if data == "add:all":
            draft["time"] = None
            return self._add_confirm()
        if data == "add:hm:x":
            self.session["flow"] = "time"
            return self.out(*ui.add_time_text_screen())
        if data.startswith("add:hm:"):
            stamp = data.split(":")[-1]
            if len(stamp) == 4 and stamp.isdigit():
                draft["time"] = f"{stamp[:2]}:{stamp[2:]}"
                return self._add_confirm()
        if data == "add:desc":
            self.session["flow"] = "desc"
            return self.out(*ui.add_desc_screen())
        if data == "add:desc0":
            draft["description"] = ""
            return self._add_confirm()
        if data == "add:end":
            self.session["flow"] = "end"
            return self.out(*ui.add_end_screen(draft, self.today))
        if data == "add:end0":
            draft["end_date"] = None
            return self._add_confirm()
        if data == "add:end1":
            start = date.fromisoformat((draft.get("gregorian_date") or self.today.isoformat())[:10])
            draft["end_date"] = (start + timedelta(days=1)).isoformat()
            return self._add_confirm()
        self.toast = "הכפתור לא מוכר"
        return self._add_confirm()

    def _save_add(self) -> dict:
        try:
            event = store.create_user_event(self.session.get("draft") or {})
        except (EventPayloadError, InputError) as exc:
            message = explain_payload_error(exc) if isinstance(exc, EventPayloadError) else str(exc)
            return self._add_confirm(message)
        self._clear_flow()
        self.toast = "נשמר"
        self.session["open_id"] = event["id"]
        self.session["open_day"] = (event.get("gregorian_date") or "")[:10]
        text, markup = ui.event_screen(event, self.by_id, _focus(self.session.get("open_day")))
        return self.out("נשמר.\n\n" + text, markup)

    def show_list(
        self,
        kind: str,
        page: int = 0,
        *,
        person_id: int | None = None,
        query: str | None = None,
        clear_flow: bool = False,
        note: str = "",
    ) -> dict:
        if clear_flow and self.session.get("flow"):
            extra = "הטיוטה בוטלה."
            note = f"{note}\n{extra}".strip() if note else extra
            self._clear_flow()
        listing = self.session["list"]
        if kind == "person" and person_id is None:
            person_id = listing.get("person_id")
        if kind == "find" and query is None:
            query = listing.get("query") or ""
        if kind == "shifts":
            state = self.shifts_on()
            if state is None:
                return self.settings(note="קודם בוחרים בית. יש יותר מבית אחד.")
            if not state:
                if note:
                    text, markup = ui.shifts_off_screen()
                    return self.out(_with_error(text, note), markup)
                return self.out(*ui.shifts_off_screen())
            return self._shifts_board(note)
        if kind == "person" and not person_id:
            return self.out(*ui.person_picker(self.people, self.session.get("who_page") or 0))
        if kind == "find" and not clean_line(query or ""):
            self.session["flow"] = "find"
            return self.out(*ui.find_screen())
        person = self.by_id.get(person_id) if person_id else None
        if kind == "person" and person is None:
            self.toast = "האדם לא נמצא"
            return self.out(*ui.person_picker(self.people, 0))
        rows = lists.collect_list(
            kind,
            self.today,
            mode=self.session.get("filter") or "all",
            person_id=person_id,
            query=query,
        )
        bounds = lists.range_for(kind, self.today)
        start, end = bounds if bounds else (None, None)
        page, _pages = lists.clamp_page(len(rows), page)
        listing.update(
            {
                "kind": kind,
                "page": page,
                "person_id": person_id,
                "query": query or "",
            }
        )
        text, markup = ui.list_screen(
            kind=kind,
            rows=rows,
            page=page,
            today=self.today,
            mode=self.session.get("filter") or "all",
            people=self.by_id,
            person_name=person.get("name") if person else None,
            query=query,
            start=start,
            end=end,
            note=note,
        )
        return self.out(text, markup)

    def _shifts_board(self, note: str) -> dict:
        anchor = lists.shift_anchor(self.session["list"].get("shift_sunday"), self.today)
        self.session["list"].update(
            {
                "kind": "shifts",
                "page": 0,
                "person_id": None,
                "query": "",
                "shift_sunday": anchor.isoformat(),
            }
        )
        end = anchor + timedelta(days=6)
        rows = [row for row in lists.events_between(anchor, end) if row.get("is_shift")]
        text, markup = ui.shifts_board(rows, self.by_id, self.today, anchor)
        if note:
            text = esc(note).rstrip() + "\n\n" + text
        return self.out(text, markup)

    def _open_shift_week(self, stamp: str) -> dict:
        day = ui.parse_ymd(stamp)
        if day is None:
            self.toast = "הכפתור לא מוכר"
            return self.go_home()
        self.session["list"]["shift_sunday"] = lists.shift_anchor(day, day).isoformat()
        return self.show_list("shifts")

    def _page(self, data: str) -> dict:
        try:
            page = int(data.split(":", 1)[1])
        except (IndexError, ValueError):
            page = 0
        kind = self.session["list"].get("kind") or "today"
        return self.show_list(kind, page=page)

    def _back_list(self) -> dict:
        kind = self.session["list"].get("kind") or "today"
        page = self.session["list"].get("page") or 0
        return self.show_list(kind, page=page)

    def _run_find(self, text: str, *, clear_flow: bool = False) -> dict:
        if clear_flow:
            self._clear_flow()
        term = clean_line(text)
        if not term:
            self.session["flow"] = "find"
            return self.out(*ui.find_screen(error="כתבו מילה."))
        if len(term) > _FIND_MAX:
            self.session["flow"] = "find"
            return self.out(*ui.find_screen(error="החיפוש ארוך מדי."))
        self.session["flow"] = None
        return self.show_list("find", page=0, query=term)

    def _open(self, event_id: int, focus: date | None) -> dict:
        event = get_event(event_id)
        if event is None:
            self.toast = "האירוע נמחק"
            return self.out(*ui.missing_event_screen())
        self.session["open_id"] = event_id
        shown = focus or _focus(event.get("gregorian_date"))
        self.session["open_day"] = shown.isoformat() if shown else None
        return self.out(*ui.event_screen(event, self.by_id, shown))

    def _reopen(self) -> dict:
        event_id = self.session.get("open_id")
        if not event_id:
            return self._back_list()
        return self._open(int(event_id), _focus(self.session.get("open_day")))

    def _ask_delete(self, event_id: int) -> dict:
        event = get_event(event_id)
        if event is None:
            self.toast = "האירוע נמחק"
            return self.out(*ui.missing_event_screen())
        if event.get("gcal_source_id"):
            self.toast = "לעריכה ביומן גוגל"
            return self._open(event_id, _focus(event.get("gregorian_date")))
        self.session["open_id"] = event_id
        return self.out(*ui.delete_screen(event))

    def _do_delete(self, event_id: int) -> dict:
        event = get_event(event_id)
        if event is not None and event.get("gcal_source_id"):
            self.toast = "לעריכה ביומן גוגל"
            return self._open(event_id, _focus(event.get("gregorian_date")))
        if event is None or not store.remove_event(event_id):
            self.toast = "כבר נמחק"
            return self.out(*ui.missing_event_screen())
        self._clear_flow()
        self.toast = "נמחק"
        text, markup = ui.deleted_note_screen(ui.visible_name(event))
        return self.out(text, markup)

    def _on_edit(self, data: str) -> dict:
        if data == "ed:ok":
            return self._save_edit(force=False)
        if data == "ed:force":
            return self._save_edit(force=True)
        if data == "edf:title":
            self.session["flow"] = "edit_title"
            return self.out(*ui.edit_title_screen())
        if data == "edf:date":
            self.session["flow"] = "edit_date"
            return self.out(*ui.edit_date_screen(self.session.get("draft") or {}, self.today))
        if data == "edf:time":
            self.session["flow"] = "edit"
            return self.out(*ui.edit_time_screen(self.session.get("draft") or {}))
        if data == "edf:desc":
            self.session["flow"] = "edit_desc"
            return self.out(*ui.edit_desc_screen())
        if data == "edf:end":
            self.session["flow"] = "edit_end"
            return self.out(*ui.edit_end_screen(self.session.get("draft") or {}))
        if data == "ed:d:0":
            self.session["draft"]["gregorian_date"] = self.today.isoformat()
            return self._after_edit_date()
        if data == "ed:d:1":
            self.session["draft"]["gregorian_date"] = (self.today + timedelta(days=1)).isoformat()
            return self._after_edit_date()
        if data == "ed:d:x":
            self.session["flow"] = "edit_date_text"
            return self.out(*ui.edit_date_text_screen())
        if data == "ed:all":
            self.session["draft"]["time"] = None
            self.session["flow"] = "edit"
            return self._edit_menu(saved=ui.field_saved("time"))
        if data == "ed:hm:x":
            self.session["flow"] = "edit_time"
            return self.out(*ui.edit_time_text_screen())
        if data.startswith("ed:hm:"):
            stamp = data.split(":")[-1]
            if len(stamp) == 4 and stamp.isdigit():
                self.session["draft"]["time"] = f"{stamp[:2]}:{stamp[2:]}"
                self.session["flow"] = "edit"
                return self._edit_menu(saved=ui.field_saved("time"))
        if data == "ed:desc0":
            self.session["draft"]["description"] = ""
            self.session["flow"] = "edit"
            return self._edit_menu(saved=ui.field_saved("desc"))
        if data == "ed:end0":
            self.session["draft"]["end_date"] = None
            self.session["flow"] = "edit"
            return self._edit_menu(saved=ui.field_saved("end"))
        if data == "ed:end1":
            start = date.fromisoformat(
                (self.session["draft"].get("gregorian_date") or self.today.isoformat())[:10]
            )
            self.session["draft"]["end_date"] = (start + timedelta(days=1)).isoformat()
            self.session["flow"] = "edit"
            return self._edit_menu(saved=ui.field_saved("end"))
        match = _ED_ID.fullmatch(data)
        if match:
            return self._begin_edit(int(match.group(1)))
        self.toast = "הכפתור לא מוכר"
        return self.go_home()

    def _begin_edit(self, event_id: int) -> dict:
        event = get_event(event_id)
        if event is None:
            self.toast = "האירוע נמחק"
            return self.out(*ui.missing_event_screen())
        if event.get("gcal_source_id"):
            self.toast = "לעריכה ביומן גוגל"
            return self._open(event_id, _focus(event.get("gregorian_date")))
        self.session["draft"] = store.snapshot(event)
        self.session["open_id"] = event_id
        if event.get("is_shift"):
            self.session["flow"] = "edit_date"
            return self.out(
                *ui.edit_date_screen(self.session["draft"], self.today, shift=True)
            )
        self.session["flow"] = "edit"
        return self._edit_menu()

    def _edit_menu(self, error: str = "", saved: str = "") -> dict:
        draft = self.session.get("draft") or {}
        if not draft.get("event_id"):
            return self._reopen()
        if draft.get("is_shift"):
            self.session["flow"] = "edit_date"
            text, markup = ui.edit_date_screen(draft, self.today, shift=True)
            return self.out(_with_error(text, error or saved), markup)
        self.session["flow"] = "edit"
        return self.out(*ui.edit_menu_screen(draft, error=error, saved=saved))

    def _after_edit_date(self) -> dict:
        draft = self.session.get("draft") or {}
        if draft.get("is_shift"):
            self.session["flow"] = "edit_date"
            return self.out(*ui.edit_date_screen(draft, self.today, shift=True))
        self.session["flow"] = "edit"
        return self._edit_menu(saved=ui.field_saved("date"))

    def _save_edit(self, *, force: bool) -> dict:
        draft = self.session.get("draft") or {}
        if not draft.get("event_id"):
            return self.go_home(note="אין אירוע פתוח.")
        if force:
            draft["force"] = True
        try:
            status, event = store.update_user_event(draft)
        except (EventPayloadError, InputError) as exc:
            message = explain_payload_error(exc) if isinstance(exc, EventPayloadError) else str(exc)
            return self._edit_menu(message)
        if status == "deleted":
            self._clear_flow()
            self.toast = "האירוע נמחק"
            return self.out(*ui.missing_event_screen())
        if status == "readonly":
            self._clear_flow()
            self.toast = "לעריכה ביומן גוגל"
            return self._open(int(draft["event_id"]), _focus(self.session.get("open_day")))
        if status == "conflict":
            self.toast = "האירוע השתנה"
            return self.out(*ui.conflict_screen(event or {}, draft))
        self._clear_flow()
        self.toast = "נשמר"
        self.session["open_id"] = event["id"]
        self.session["open_day"] = (event.get("gregorian_date") or "")[:10]
        text, markup = ui.event_screen(event, self.by_id, _focus(self.session.get("open_day")))
        return self.out("נשמר.\n\n" + text, markup)

    def settings(self, note: str = "") -> dict:
        if self.house_note and not note:
            note = self.house_note
        return self.out(
            *ui.settings_screen(
                self.chat_id,
                self.linked,
                self.household,
                self.homes,
                note=note,
            )
        )

    def _on_settings(self, data: str) -> dict:
        if data == "set:link":
            self.session["link_page"] = 0
            return self.out(*ui.link_picker(self.people, 0))
        if data == "set:new":
            self.session["flow"] = "link_name"
            return self.out(*ui.link_name_screen())
        if data == "set:workers":
            self.session["workers_page"] = 0
            return self.out(*ui.workers_screen(self.people, 0))
        if data == "set:sh:1":
            return self._confirm_shifts(True)
        if data == "set:sh:0":
            return self._confirm_shifts(False)
        if data == "set:shy:1":
            return self._apply_shifts(True)
        if data == "set:shy:0":
            return self._apply_shifts(False)
        page = _prefix_int(data, "set:lp:")
        if page is not None:
            self.session["link_page"] = page
            return self.out(*ui.link_picker(self.people, page))
        page = _prefix_int(data, "set:wp:")
        if page is not None:
            self.session["workers_page"] = page
            return self.out(*ui.workers_screen(self.people, page))
        picked = _prefix_int(data, "set:pick:")
        if picked is not None:
            return self._link_pick(picked)
        moved = _prefix_int(data, "set:move:")
        if moved is not None:
            return self._link_commit(moved, exclusive=True)
        shared = _prefix_int(data, "set:share:")
        if shared is not None:
            return self._link_commit(shared, exclusive=False)
        unlinked = _prefix_int(data, "set:ul:")
        if unlinked is not None:
            return self._unlink(unlinked)
        house_id = _prefix_int(data, "set:hh:")
        if house_id is not None:
            return self._pick_house(house_id)
        worker = _prefix_int(data, "set:ws:")
        if worker is not None:
            return self._flip_worker(worker)
        self.toast = "הכפתור לא מוכר"
        return self.settings()

    def _confirm_shifts(self, enabled: bool) -> dict:
        if self.household is None:
            return self.settings(note="קודם בוחרים בית.")
        return self.out(*ui.shift_toggle_screen(enabled, self.household.get("name") or "הבית"))

    def _apply_shifts(self, enabled: bool) -> dict:
        if self.household is None:
            return self.settings(note="קודם בוחרים בית.")
        try:
            household.set_household_shifts(self.household["id"], enabled)
        except LookupError:
            self.session["household_id"] = None
            self.resolve_household()
            return self.settings(note="הבית כבר לא קיים.")
        self.refresh_household()
        self.toast = "עודכן"
        state = "דלוקות" if enabled else "כבויות"
        return self.settings(note=f"משמרות {state}.")

    def _pick_house(self, household_id: int) -> dict:
        match = next((item for item in self.homes if item["id"] == household_id), None)
        if match is None:
            self.toast = "הבית לא נמצא"
            self.resolve_household()
            return self.settings()
        self.session["household_id"] = household_id
        self.household = match
        self.house_note = ""
        return self.settings()

    def _link_pick(self, person_id: int) -> dict:
        status = directory.link_status(person_id, self.chat_id)
        if status is None:
            self.toast = "האדם לא נמצא"
            return self.out(*ui.link_picker(self.people, self.session.get("link_page") or 0))
        if status["already"] and not status["others"]:
            return self.settings(note="כבר מחובר.")
        if status["others"] or status["replaces"]:
            return self.out(*ui.link_conflict_screen(status, self.chat_id))
        return self._link_commit(person_id, exclusive=False)

    def _link_commit(self, person_id: int, *, exclusive: bool) -> dict:
        person = directory.link_person(person_id, self.chat_id, exclusive=exclusive)
        if person is None:
            self.toast = "האדם לא נמצא"
            return self.out(*ui.link_picker(self.people, 0))
        self.reload_people()
        self._clear_flow()
        self.toast = "חובר"
        return self.settings(note=f"חובר אל {person['name']}.")

    def _unlink(self, person_id: int) -> dict:
        person = directory.unlink_person(person_id)
        self.reload_people()
        if person is None:
            self.toast = "האדם לא נמצא"
            return self.settings()
        self.toast = "נותק"
        return self.settings(note=f"{person['name']} נותק מהצ'אט.")

    def _create_person(self, text: str) -> dict:
        try:
            person = directory.add_linked_person(clean_line(text), self.chat_id)
        except ValueError as exc:
            return self.out(*ui.link_name_screen(error=str(exc)))
        self.reload_people()
        self._clear_flow()
        self.toast = "חובר"
        return self.settings(note=f"נוצר וחובר אל {person['name']}.")

    def _flip_worker(self, person_id: int) -> dict:
        person = self.by_id.get(person_id)
        if person is None:
            self.toast = "האדם לא נמצא"
            self.reload_people()
            return self.out(*ui.workers_screen(self.people, self.session.get("workers_page") or 0))
        updated = directory.set_works_shifts(person_id, not person.get("works_shifts"))
        self.reload_people()
        if updated is None:
            self.toast = "האדם לא נמצא"
        else:
            self.toast = "עודכן"
        return self.out(*ui.workers_screen(self.people, self.session.get("workers_page") or 0))

    def _on_shift(self, data: str) -> dict:
        if data == "sh:new":
            return self._start_shift()
        if data == "sh:back":
            return self._shift_confirm()
        person_id = _prefix_int(data, "sh:p:")
        if person_id is not None:
            return self._shift_person(person_id)
        if data in {"sh:l:m", "sh:l:e", "sh:l:n"}:
            key = data[-1]
            self.session["draft"]["label_key"] = key
            self.session["draft"]["label"] = ui.SHIFT_LABELS[key]
            if not self.session["draft"].get("gregorian_date"):
                self.session["draft"]["gregorian_date"] = self.today.isoformat()
            self.session["flow"] = "shift"
            return self._shift_confirm()
        if data == "sh:d:0":
            self.session["draft"]["gregorian_date"] = self.today.isoformat()
            return self._shift_confirm()
        if data == "sh:d:1":
            self.session["draft"]["gregorian_date"] = (self.today + timedelta(days=1)).isoformat()
            return self._shift_confirm()
        if data == "sh:d:x":
            self.session["flow"] = "shift_date"
            return self.out(*ui.shift_date_text_screen(self.today))
        if data == "sh:ok":
            return self._save_shift()
        self.toast = "הכפתור לא מוכר"
        return self.show_list("shifts")

    def _start_shift(self) -> dict:
        state = self.shifts_on()
        if state is None:
            return self.settings(note="קודם בוחרים בית.")
        if not state:
            return self.out(*ui.shifts_off_screen())
        workers = [person for person in self.people if person.get("works_shifts")]
        self.session["flow"] = "shift"
        self.session["draft"] = {"gregorian_date": self.today.isoformat()}
        if len(workers) == 1:
            return self._shift_person(workers[0]["id"])
        return self.out(*ui.shift_people_screen(workers))

    def _shift_person(self, person_id: int) -> dict:
        person = self.by_id.get(person_id)
        if person is None or not person.get("works_shifts"):
            self.toast = "האדם לא נמצא"
            return self._start_shift()
        self.session["draft"]["person_id"] = person_id
        self.session["flow"] = "shift"
        return self.out(*ui.shift_label_screen(person["name"]))

    def _shift_confirm(self, error: str = "") -> dict:
        draft = self.session.get("draft") or {}
        person = self.by_id.get(draft.get("person_id"))
        if person is None:
            return self._start_shift()
        self.session["flow"] = "shift"
        text, markup = ui.shift_confirm_screen(draft, self.today, person["name"], error=error)
        return self.out(text, markup)

    def _save_shift(self) -> dict:
        draft = self.session.get("draft") or {}
        try:
            event = store.create_shift(
                int(draft.get("person_id")),
                draft.get("label") or "",
                draft.get("gregorian_date") or "",
            )
        except ShiftError as exc:
            return self._shift_confirm(str(exc))
        except InputError as exc:
            return self._shift_confirm(str(exc))
        except EventPayloadError as exc:
            return self._shift_confirm(explain_payload_error(exc))
        except (TypeError, ValueError):
            return self._shift_confirm("חסרים פרטים למשמרת.")
        self._clear_flow()
        self.toast = "נשמר"
        self.session["open_id"] = event["id"]
        self.session["open_day"] = (event.get("gregorian_date") or "")[:10]
        text, markup = ui.event_screen(event, self.by_id, _focus(self.session.get("open_day")))
        return self.out("נשמר.\n\n" + text, markup)


def _focus(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def handle_update(update: dict, *, now: datetime | None = None) -> dict:
    """מחזיר הודעה אחת, או ``{"skip": True}`` אם אין צ'אט."""
    parsed = parse_update(update)
    if parsed is None:
        return {"skip": True}
    ensure_bot_schema(get_db())
    session = _session(load_session(parsed["chat_id"]))
    bot = Bot(parsed["chat_id"], local_today(now), session)
    try:
        result = bot.run(parsed)
    except Exception:
        log.exception("bot update failed for chat %s", parsed["chat_id"])
        result = {
            "text": "משהו השתבש. הנה התפריט.",
            "markup": ui.kb(ui.menu_rows()),
            "toast": "שגיאה",
        }
        bot = None
    if bot is not None:
        save_session(parsed["chat_id"], bot.session)
    result["chat_id"] = parsed["chat_id"]
    result["callback_id"] = parsed["callback_id"]
    result["edit_id"] = parsed["edit_id"] if parsed["kind"] == "callback" else None
    result.setdefault("toast", "")
    return result
