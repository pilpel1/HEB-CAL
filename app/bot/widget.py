"""ווידג'ט HTML לטלגרם (Bot API 10.4 sendWidget) - סיכום היום לקריאה בלבד.

המגבלה הרשמית: עד 4096 בתים אחרי zlib level 9. כאן שומרים מרווח ל-4000.
אם השליחה נכשלת (API ישן / סביבה בלי ווידג'טים) - נופלים לטקסט רגיל.
"""
from __future__ import annotations

import html
import json
import zlib
from datetime import date

# מרווח מתחת ל-4096 הרשמי של טלגרם
WIDGET_ZLIB_MAX = 4000


def widget_zlib_size(html_source: str) -> int:
    raw = html_source.encode("utf-8")
    return len(zlib.compress(raw, 9))


def widget_fits(html_source: str, *, limit: int | None = None) -> bool:
    cap = WIDGET_ZLIB_MAX if limit is None else limit
    if "\x00" in html_source:
        return False
    if len(html_source.encode("utf-8")) > 32768:
        return False
    return widget_zlib_size(html_source) <= cap


def build_today_digest_widget_html(
    day: date,
    lines: list[str],
    *,
    heading: str = "סיכום היום",
) -> str:
    """HTML עצמאי עם TelegramWidget + כפתור רענון (widget_query).

    ``lines`` הן שורות כבר מעוצבות (למשל מ-format_digest_event), בלי תגי HTML.
    """
    safe_heading = html.escape(heading, quote=False)
    items = []
    for line in lines:
        text = (line or "").strip()
        if not text:
            continue
        items.append(f"<li>{html.escape(text, quote=False)}</li>")
    if not items:
        items.append("<li>אין אירועים היום</li>")
    body = "\n".join(items)
    day_iso = day.isoformat()
    # RTL עברי; chat_data מחזיק את התאריך לרענון
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="utf-8">
<style>
body{{margin:8px 12px;font-family:system-ui,sans-serif}}
h3{{margin:0 0 8px;font-size:1.05em}}
ul{{margin:0;padding-inline-start:1.1em}}
li{{margin:0.2em 0}}
button{{margin-top:10px}}
</style>
</head>
<body>
<h3>{safe_heading}</h3>
<p id="d" dir="ltr" style="margin:0 0 6px;opacity:.7;font-size:.85em">{html.escape(day_iso)}</p>
<ul id="list">{body}</ul>
<button type="button" id="ref">רענון</button>
<script>
(function(){{
  var W=window.TelegramWidget;
  function paint(state){{
    try{{
      var s=typeof state==='string'?JSON.parse(state||'{{}}'):(state||{{}});
      if(s.day){{var d=document.getElementById('d');if(d)d.textContent=s.day;}}
      if(Array.isArray(s.lines)){{
        var ul=document.getElementById('list');
        if(ul){{
          ul.innerHTML='';
          s.lines.forEach(function(line){{
            var li=document.createElement('li');
            li.textContent=line;
            ul.appendChild(li);
          }});
          if(!s.lines.length){{
            var empty=document.createElement('li');
            empty.textContent='אין אירועים היום';
            ul.appendChild(empty);
          }}
        }}
      }}
    }}catch(e){{}}
  }}
  if(W){{
    W.onEvent('chatDataChanged',function(){{paint(W.chatData);}});
    paint(W.chatData);
    var btn=document.getElementById('ref');
    if(btn){{
      btn.onclick=function(){{
        if(typeof W.request==='function'){{
          W.request('refresh').catch(function(){{}});
        }}
      }};
    }}
  }}
}})();
</script>
</body>
</html>
"""


def today_digest_widget_payload(
    day: date,
    event_lines: list[str],
    *,
    heading: str = "סיכום היום",
) -> dict:
    """מחזיר מילון לשליחה ב-sendWidget, או מעלה ValueError אם גדול מדי."""
    html_source = build_today_digest_widget_html(day, event_lines, heading=heading)
    if not widget_fits(html_source):
        raise ValueError("widget html exceeds zlib cap")
    chat_data = json.dumps(
        {"day": day.isoformat(), "lines": list(event_lines)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "html": html_source,
        "chat_data": chat_data,
        "allow_queries": True,
        "caption": heading,
    }
