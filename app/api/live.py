"""זרם SSE לשינויי אירועים. GET כמו שאר ה-API — אותה עוגיית session."""
from . import api
from app.live_sync import live_sync_response


@api.route("/events/stream")
def events_stream():
    return live_sync_response()
