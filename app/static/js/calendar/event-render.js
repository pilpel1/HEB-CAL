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
        eventLanes.set(event.id, lane);
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
    const title = escapeHtml(event.title ?? '');

    return `<div class="${classes.join(' ')}" data-event-id="${event.id}" title="${label}" style="${style}">${timeHtml}<span class="event-title">${title}</span></div>`;
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

/**
 * בטלפון הכותרת עד שתי שורות. "+N" רק על מה שבאמת חורג מגובה התא.
 * פס רב-יומי נשאר שלם כדי שההמשך בתאים השכנים לא יישבר.
 */
function fitCellChips(cell) {
    cell.querySelectorAll('.cell-more').forEach((el) => el.remove());
    const chips = cellChipNodes(cell);
    chips.forEach((el) => el.classList.remove('is-chip-hidden'));
    cell.classList.remove('is-crowded');

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
    const hideable = chips.filter((el) => !el.closest('.multi-day-rail'));
    if (!content || hideable.length === 0) {
        return;
    }

    const overflows = () => cellContentBottom(cell) > limit + 1;
    if (!overflows()) {
        return;
    }

    let hidden = 0;
    for (let i = hideable.length - 1; i >= 0; i -= 1) {
        hideable[i].classList.add('is-chip-hidden');
        hidden += 1;
        const badge = makeMoreBadge(hidden);
        content.appendChild(badge);
        if (!overflows()) {
            return;
        }
        badge.remove();
    }
    if (hidden > 0) {
        content.appendChild(makeMoreBadge(hidden));
    }
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

        const lane = eventLanes.get(event.id);
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
