// תפריט הקשר: קליק ימני, ובמגע לחיצה ארוכה (אין קליק ימני בטלפון)

function initCalendarContextMenu(calendarBody) {
    let menu = document.getElementById('calendarContextMenu');
    if (!menu) {
        menu = document.createElement('div');
        menu.id = 'calendarContextMenu';
        menu.className = 'calendar-context-menu';
        menu.setAttribute('role', 'menu');
        document.body.appendChild(menu);
    }

    let menuState = { dateStr: null, eventId: null };
    let press = null;
    let suppressClick = false;
    const LONG_PRESS_MS = 500;

    function hideMenu() {
        menu.classList.remove('is-open');
        menu.innerHTML = '';
        menuState = { dateStr: null, eventId: null };
    }

    function positionMenu(clientX, clientY) {
        menu.style.visibility = 'hidden';
        menu.classList.add('is-open');

        const menuRect = menu.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        // ב-RTL נפתח מעט שמאלה מהסמן, בלי לצאת מהמסך
        let left = clientX - menuRect.width;
        let top = clientY;

        if (left < 8) {
            left = 8;
        }
        if (left + menuRect.width > viewportWidth - 8) {
            left = viewportWidth - menuRect.width - 8;
        }
        if (top + menuRect.height > viewportHeight - 8) {
            top = viewportHeight - menuRect.height - 8;
        }
        if (top < 8) {
            top = 8;
        }

        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        menu.style.visibility = 'visible';
    }

    function buildMenuItems() {
        const items = [];

        if (menuState.eventId) {
            items.push(
                { label: 'ערוך אירוע', action: 'edit-event' },
                { label: 'מחק אירוע', action: 'delete-event', danger: true },
                { separator: true },
            );
        }

        items.push(
            { label: 'הוסף אירוע', action: 'add-event' },
            { label: 'רשימת אירועים', action: 'events-list' },
        );

        return items;
    }

    function showMenu(clientX, clientY) {
        const items = buildMenuItems();
        menu.innerHTML = items.map((item) => {
            if (item.separator) {
                return '<div class="context-menu-separator" role="separator"></div>';
            }
            const dangerClass = item.danger ? ' is-danger' : '';
            return `<button type="button" role="menuitem" data-action="${item.action}" class="${dangerClass.trim()}">${item.label}</button>`;
        }).join('');

        positionMenu(clientX, clientY);
    }

    function openMenuFromTarget(target, clientX, clientY) {
        const cell = target.closest('td[data-date]');
        if (!cell) {
            hideMenu();
            return false;
        }
        const eventItem = target.closest('.event-item[data-event-id]');
        menuState = {
            dateStr: cell.getAttribute('data-date'),
            eventId: eventItem ? eventItem.getAttribute('data-event-id') : null,
        };
        showMenu(clientX, clientY);
        return true;
    }

    function armSuppressClick() {
        suppressClick = true;
        setTimeout(() => {
            suppressClick = false;
        }, 700);
    }

    calendarBody.addEventListener('contextmenu', (event) => {
        // במגע contextmenu מגיע לפני pointerup. פותחים רק בשחרור, אחרת התפריט נסגר מהקליק.
        if (press) {
            event.preventDefault();
            return;
        }
        if (!openMenuFromTarget(event.target, event.clientX, event.clientY)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
    });

    // נפתח ב-pointerup, לא בזמן שהאצבע למטה — אחרת השחרור לוחץ על הפריט הראשון
    calendarBody.addEventListener('pointerdown', (event) => {
        if (event.pointerType === 'mouse' || !event.target.closest('td[data-date]')) {
            return;
        }
        press = {
            x: event.clientX,
            y: event.clientY,
            t: Date.now(),
            target: event.target,
            pointerId: event.pointerId,
            moved: false,
        };
    });

    calendarBody.addEventListener('pointermove', (event) => {
        if (!press || event.pointerId !== press.pointerId) {
            return;
        }
        const dx = event.clientX - press.x;
        const dy = event.clientY - press.y;
        if (dx * dx + dy * dy > 64) {
            press.moved = true;
        }
    });

    function finishPress(event) {
        if (!press || (event && event.pointerId !== press.pointerId)) {
            return;
        }
        const info = press;
        press = null;
        if (event.type === 'pointercancel' || info.moved || Date.now() - info.t < LONG_PRESS_MS) {
            return;
        }
        armSuppressClick();
        openMenuFromTarget(info.target, info.x, info.y);
    }

    calendarBody.addEventListener('pointerup', finishPress);
    calendarBody.addEventListener('pointercancel', finishPress);

    document.addEventListener('click', (event) => {
        if (!suppressClick || !calendarBody.contains(event.target)) {
            return;
        }
        suppressClick = false;
        event.preventDefault();
        event.stopPropagation();
    }, true);

    menu.addEventListener('click', async (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button) {
            return;
        }

        const action = button.getAttribute('data-action');
        const { dateStr, eventId } = menuState;
        hideMenu();

        if (action === 'add-event' && dateStr) {
            await openQuickEventModal(dateStr);
            return;
        }
        if (action === 'edit-event' && eventId) {
            await openEditEventModal(eventId);
            return;
        }
        if (action === 'delete-event' && eventId) {
            await deleteEvent(eventId);
            return;
        }
        if (action === 'events-list') {
            window.location.href = '/events_list';
        }
    });

    document.addEventListener('click', (event) => {
        if (!menu.contains(event.target)) {
            hideMenu();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            hideMenu();
        }
    });

    window.addEventListener('scroll', hideMenu, true);
    window.addEventListener('resize', hideMenu);
}
