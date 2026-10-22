// ציור אירועים בתא: חגים, פס אירועים רב-יומיים, אירועי יום

// פונקציה להמרת שם צבע ל-RGBA
function getColorRGBA(color) {
    const colorMap = {
        'cyan': '0, 255, 255, 0.4',
        'yellow': '255, 255, 0, 0.4',
        'orange': '255, 165, 0, 0.4',
        'green': '0, 128, 0, 0.4'
    };
    return colorMap[color] || '0, 0, 0, 0';
}

function getMultiDaySegmentRole(dateStr, event, weekDates) {
    const prev = addDaysToDateStr(dateStr, -1);
    const next = addDaysToDateStr(dateStr, 1);
    const continuesFromPrev = weekDates.includes(prev)
        && isDateInRange(prev, event.gregorian_date, event.end_date);
    const continuesToNext = weekDates.includes(next)
        && isDateInRange(next, event.gregorian_date, event.end_date);

    if (!continuesFromPrev && continuesToNext) {
        return 'start';
    }
    if (continuesFromPrev && continuesToNext) {
        return 'middle';
    }
    if (continuesFromPrev && !continuesToNext) {
        return 'end';
    }
    return 'single';
}

function assignMultiDayLanes(multiDayEvents, weekDates) {
    const relevant = multiDayEvents
        .filter((event) => weekDates.some((date) => (
            isDateInRange(date, event.gregorian_date, event.end_date)
        )))
        .sort((a, b) => {
            if (a.gregorian_date !== b.gregorian_date) {
                return a.gregorian_date < b.gregorian_date ? -1 : 1;
            }
            return getEventDurationDays(b) - getEventDurationDays(a);
        });

    const laneEnds = [];
    const eventLanes = new Map();

    for (const event of relevant) {
        const daysInWeek = weekDates.filter((date) => (
            isDateInRange(date, event.gregorian_date, event.end_date)
        ));
        if (daysInWeek.length === 0) {
            continue;
        }

        const startInWeek = daysInWeek[0];
        const endInWeek = daysInWeek[daysInWeek.length - 1];
        let lane = 0;
        while (lane < laneEnds.length && laneEnds[lane] >= startInWeek) {
            lane += 1;
        }

        if (lane === laneEnds.length) {
            laneEnds.push(endInWeek);
        } else {
            laneEnds[lane] = endInWeek;
        }
        eventLanes.set(eventInstanceKey(event), lane);
    }

    return { eventLanes, laneCount: laneEnds.length };
}

function escapeHtml(text) {
    return String(text ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

const REPEAT_ICON_SVG = '<svg class="event-repeat-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/></svg>';

function eventInstanceKey(event) {
    if (event && event.occurrence_date) {
        return `${event.id}@${event.occurrence_date}`;
    }
    return String(event && event.id);
}

function repeatIconHtml(event) {
    if (!event || !event.recurrence_freq) {
        return '';
    }
    return REPEAT_ICON_SVG;
}

function compareEventsByTime(a, b) {
    const ta = a.time || '99:99';
    const tb = b.time || '99:99';
    if (ta !== tb) {
        return ta < tb ? -1 : 1;
    }
    return (Number(a.id) || 0) - (Number(b.id) || 0);
}

function eventTimeLabel(event) {
    if (event.time) {
        return `${event.time} - ${event.title ?? ''}`;
    }
    return String(event.title ?? '');
}

function buildEventItemHtml(event, extraClasses = []) {
    const classes = ['event-item', ...extraClasses];
    if (!event.color) {
        classes.push('event-uncolored');
    }

    const style = event.color
        ? `background-color: rgba(${getColorRGBA(event.color)})`
        : '';
    const label = escapeHtml(eventTimeLabel(event));
    const timeHtml = event.time
        ? `<span class="event-time">${escapeHtml(event.time)}</span><span class="event-sep"> - </span>`
        : '';
    const title = `${repeatIconHtml(event)}${escapeHtml(event.title ?? '')}`;
    const occurrence = escapeHtml(event.occurrence_date || event.gregorian_date || '');
    const recurring = event.recurrence_freq ? '1' : '0';

    return `<div class="${classes.join(' ')}" data-event-id="${event.id}" data-occurrence-date="${occurrence}" data-recurring="${recurring}" title="${label}" style="${style}">${timeHtml}<span class="event-title">${title}</span></div>`;
}

function jewishEventHtml(event) {
    const name = String(event.name ?? '');
    const safeType = ['parasha', 'holiday', 'fast'].includes(event.type) ? event.type : 'holiday';
    const color = event.color ? ` style="color: ${event.color}"` : '';
    if (safeType === 'parasha') {
        const prefix = 'פרשת ';
        const hasPrefix = name.startsWith(prefix);
        const shortName = hasPrefix ? name.slice(prefix.length) : name;
        const prefixHtml = hasPrefix ? '<span class="parasha-prefix">פרשת </span>' : '';
        return `<div class="parasha"${color} title="${escapeHtml(name)}">${prefixHtml}<span class="parasha-name">${escapeHtml(shortName)}</span></div>`;
    }
    return `<div class="${safeType}"${color} title="${escapeHtml(name)}">${escapeHtml(name)}</div>`;
}

function cellChipNodes(cell) {
    return [
        ...cell.querySelectorAll('.multi-day-rail .event-item'),
        ...cell.querySelectorAll('.jewish-events-container > div'),
        ...cell.querySelectorAll('.day-content .event-item'),
    ];
}

function makeMoreBadge(hidden) {
    const badge = document.createElement('div');
    badge.className = 'cell-more';
    badge.textContent = `+${hidden}`;
    badge.title = 'כל האירועים';
    badge.setAttribute('role', 'button');
    return badge;
}

/** גובה תיבת התוכן של התא לפי הצפיפות. border-collapse אוכל px אחד מה-height של השורה. */
function cellContentLimit(cell) {
    const raw = getComputedStyle(document.documentElement)
        .getPropertyValue('--week-row-height')
        .trim();
    const cssH = parseFloat(raw);
    if (!Number.isFinite(cssH) || cssH <= 0) {
        return cell.clientHeight;
    }
    const borderTop = parseFloat(getComputedStyle(cell).borderTopWidth) || 0;
    return cssH - borderTop;
}

/** תחתית התוכן הנראה, ביחס לתיבת התוכן של ה-td. */
function cellContentBottom(cell) {
    const box = cell.getBoundingClientRect();
    const borderTop = parseFloat(getComputedStyle(cell).borderTopWidth) || 0;
    const origin = box.top + borderTop;
    let bottom = 0;
    cell.querySelectorAll('.dates-container, .cell-content > *').forEach((el) => {
        if (el.offsetHeight === 0) {
            return;
        }
        bottom = Math.max(bottom, el.getBoundingClientRect().bottom - origin);
    });
    return bottom;
}

function resetChipFit(cell) {
    cell.querySelectorAll('.cell-more').forEach((el) => el.remove());
    cellChipNodes(cell).forEach((el) => {
        el.classList.remove('is-chip-hidden', 'is-one-line');
    });
    cell.classList.remove('is-crowded');
}

/** משאיר את keep הראשונים. אם נשארו מוסתרים — מוסיף "+N". */
function applyChipPrefix(content, hideable, keep) {
    content.querySelectorAll('.cell-more').forEach((el) => el.remove());
    hideable.forEach((el, index) => {
        el.classList.toggle('is-chip-hidden', index >= keep);
    });
    const hidden = hideable.length - keep;
    if (hidden > 0) {
        content.appendChild(makeMoreBadge(hidden));
    }
}

/**
 * בטלפון הכותרת עד שתי שורות, וכמה שיותר צ'יפים כאלה נכנסים לגובה.
 * "+N" רק על מה שלא נכנס. אם אף צ'יפ בשתי שורות לא נכנס יחד עם שורת "+N",
 * הצ'יפ הראשון יורד לשורה אחת עם אליפסיס — ואז "+N". אף פעם לא "+N" לבד.
 * פס רב-יומי נשאר שלם כדי שההמשך בתאים השכנים לא יישבר.
 */
function fitCellChips(cell) {
    resetChipFit(cell);

    if (!cell.isConnected) {
        return;
    }
    if (typeof isCompactCalendar !== 'function' || !isCompactCalendar()) {
        return;
    }

    const limit = cellContentLimit(cell);
    if (limit <= 0) {
        return;
    }
    const content = cell.querySelector('.cell-content');
    const hideable = cellChipNodes(cell).filter((el) => !el.closest('.multi-day-rail'));
    if (!content || hideable.length === 0) {
        return;
    }

    const overflows = () => cellContentBottom(cell) > limit + 1;
    if (!overflows() || hideable.length === 1) {
        return;
    }

    for (let keep = hideable.length - 1; keep >= 1; keep -= 1) {
        applyChipPrefix(content, hideable, keep);
        if (!overflows()) {
            return;
        }
    }

    const first = hideable[0];
    if (first.querySelector('.event-title')) {
        first.classList.add('is-one-line');
    }
    applyChipPrefix(content, hideable, 1);
}

function fitWeekRowChips(row) {
    if (!row) {
        return;
    }
    row.querySelectorAll('td[data-date]').forEach((cell) => fitCellChips(cell));
}

function fitRenderedWeekChips() {
    const body = typeof infiniteCalendar !== 'undefined' && infiniteCalendar.body;
    if (!body) {
        return;
    }
    for (const row of body.rows) {
        fitWeekRowChips(row);
    }
    if (infiniteCalendar.stream) {
        infiniteCalendar.chipFitWidth = infiniteCalendar.stream.clientWidth;
    }
}

function trimCellChips(cell) {
    fitCellChips(cell);
}

function renderMultiDayRail(cell, date, multiDayEvents, eventLanes, weekDates) {
    const rail = cell.querySelector('.multi-day-rail');
    if (!rail) {
        return;
    }

    const laneHtml = new Map();

    for (const event of multiDayEvents) {
        if (!isDateInRange(date, event.gregorian_date, event.end_date)) {
            continue;
        }

        const lane = eventLanes.get(eventInstanceKey(event));
        if (lane === undefined) {
            continue;
        }

        const role = getMultiDaySegmentRole(date, event, weekDates);
        laneHtml.set(lane, buildEventItemHtml(event, [
            'event-multi',
            `event-multi-${role}`,
        ]));
    }

    if (laneHtml.size === 0) {
        rail.innerHTML = '';
        return;
    }

    const maxLaneToday = Math.max(...laneHtml.keys());
    const lanes = [];
    for (let lane = 0; lane <= maxLaneToday; lane += 1) {
        lanes.push(
            laneHtml.get(lane)
            || '<div class="event-lane-spacer" aria-hidden="true"></div>'
        );
    }

    rail.innerHTML = lanes.join('');
}

function paintCellEvents(cell, date, jewishByDate, multiDayEvents, singleDayEvents, eventLanes, weekDates) {
    const jewishEvents = jewishByDate[date] || [];
    const jewishContainer = cell.querySelector('.jewish-events-container');
    if (jewishEvents.length > 0) {
        const sortedEvents = [...jewishEvents].sort((a, b) => {
            const order = { parasha: 1, holiday: 2, fast: 3 };
            return (order[a.type] || 9) - (order[b.type] || 9);
        });
        jewishContainer.innerHTML = sortedEvents.map(jewishEventHtml).join('');
    } else {
        jewishContainer.innerHTML = '';
    }

    renderMultiDayRail(cell, date, multiDayEvents, eventLanes, weekDates);

    const dayEvents = singleDayEvents
        .filter((event) => isDateInRange(date, event.gregorian_date, event.end_date))
        .sort(compareEventsByTime);
    const contentContainer = cell.querySelector('.day-content');
    contentContainer.innerHTML = dayEvents.length > 0
        ? dayEvents.map((event) => buildEventItemHtml(event)).join('')
        : '';

    trimCellChips(cell);
}
