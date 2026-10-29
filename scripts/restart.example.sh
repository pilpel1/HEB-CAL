#!/bin/sh
# נשאר לתאימות עם עותקים ישנים של ההוראות.
# הסקריפט הוא scripts/restart.sh (כתובת ופורט מ-HEB_CAL_BIND_HOST / HEB_CAL_PORT).
exec "$(CDPATH= cd -- "$(dirname "$0")" && pwd)/restart.sh" "$@"
