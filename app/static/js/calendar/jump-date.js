// דלג לתאריך: לועזי (ברירת מחדל) או עברי. רשימת החודשים העבריים קבועה
// מתשרי, עם «אדר» אחד בכל שנה — בלי א׳/ב׳. אישור על אדר בשנה מעוברת
// קופץ לחודש הלועזי של א׳ באדר א׳ (שם נראים שני האדרים).

const JUMP_HEBREW_MONTHS = [
    { value: 7, name: 'תשרי' },
    { value: 8, name: 'חשון' },
    { value: 9, name: 'כסלו' },
    { value: 10, name: 'טבת' },
    { value: 11, name: 'שבט' },
    { value: 12, name: 'אדר' },
    { value: 1, name: 'ניסן' },
    { value: 2, name: 'אייר' },
    { value: 3, name: 'סיון' },
    { value: 4, name: 'תמוז' },
    { value: 5, name: 'אב' },
    { value: 6, name: 'אלול' },
];

let jumpCalendarMode = 'gregorian';
let jumpHebrewYearsPromise = null;
let jumpSyncToken = 0;
let jumpSyncPending = null;

function loadJumpHebrewYears() {
    if (!jumpHebrewYearsPromise) {
        if (typeof loadHebrewYearLabels === 'function') {
            jumpHebrewYearsPromise = loadHebrewYearLabels();
        } else {
            jumpHebrewYearsPromise = fetch('/api/hebrew-years?from=5660&to=5820')
                .then((response) => (response.ok ? response.json() : { years: [] }))
                .then((data) => (Array.isArray(data.years) ? data.years : []))
                .catch(() => []);
        }
    }
    return jumpHebrewYearsPromise;
}

function jumpHebrewMonthFromName(name) {
    const raw = String(name || '').trim();
    if (!raw) {
        return null;
    }
    const stripped = raw.replace(/[״"׳']/g, '').replace(/\s+/g, ' ').trim();
    if (stripped === 'אדר' || stripped.startsWith('אדר ')) {
        return 12;
    }
    const match = JUMP_HEBREW_MONTHS.find((item) => item.name === raw || item.name === stripped);
    return match ? match.value : null;
}

function jumpHebrewMonthFromApi(month) {
    const value = Number(month);
    if (!Number.isFinite(value)) {
        return null;
    }
    if (value === 13) {
        return 12;
    }
    if (value >= 1 && value <= 12) {
        return value;
    }
    return null;
}

function fillJumpHebrewMonths(select, selected) {
    if (!select) {
        return;
    }
    const current = selected != null ? String(selected) : select.value;
    select.replaceChildren();
    JUMP_HEBREW_MONTHS.forEach((item) => {
        const option = document.createElement('option');
        option.value = String(item.value);
        option.textContent = item.name;
        select.append(option);
    });
    if ([...select.options].some((option) => option.value === current)) {
        select.value = current;
    }
}

function jumpHebrewMonthNames(select) {
    const target = select || document.getElementById('hebrewMonthSelect');
    if (!target) {
        return [];
    }
    return [...target.options].map((option) => option.textContent);
}

function setJumpCalendarMode(mode) {
    const hebrew = mode === 'hebrew';
    jumpCalendarMode = hebrew ? 'hebrew' : 'gregorian';
    const menu = document.getElementById('jumpDateMenu');
    if (menu) {
        menu.classList.toggle('is-hebrew', hebrew);
        menu.classList.toggle('is-gregorian', !hebrew);
    }
    const gregFields = document.getElementById('jumpGregorianFields');
    const hebFields = document.getElementById('jumpHebrewFields');
    if (gregFields) {
        gregFields.hidden = hebrew;
    }
    if (hebFields) {
        hebFields.hidden = !hebrew;
    }
    const gregBtn = document.getElementById('jumpCalGregorian');
    const hebBtn = document.getElementById('jumpCalHebrew');
    if (gregBtn) {
        gregBtn.classList.toggle('btn-primary', !hebrew);
        gregBtn.classList.toggle('btn-outline-primary', hebrew);
        gregBtn.classList.toggle('is-active', !hebrew);
        gregBtn.setAttribute('aria-pressed', String(!hebrew));
    }
    if (hebBtn) {
        hebBtn.classList.toggle('btn-primary', hebrew);
        hebBtn.classList.toggle('btn-outline-primary', !hebrew);
        hebBtn.classList.toggle('is-active', hebrew);
        hebBtn.setAttribute('aria-pressed', String(hebrew));
    }
}

function fillJumpGregorianYears() {
    const yearSelect = document.getElementById('yearSelect');
    const monthSelect = document.getElementById('monthSelect');
    if (!yearSelect) {
        return;
    }
    const now = new Date();
    const currentYear = now.getFullYear();
    if (!yearSelect.options.length) {
        for (let year = 1900; year <= currentYear + 20; year += 1) {
            const option = document.createElement('option');
            option.value = String(year);
            option.textContent = String(year);
            yearSelect.append(option);
        }
    }
    if ([...yearSelect.options].some((option) => option.value === String(currentYear))) {
        yearSelect.value = String(currentYear);
    }
    if (monthSelect) {
        monthSelect.value = String(now.getMonth());
    }
}

async function fillJumpHebrewYears() {
    const select = document.getElementById('hebrewYearSelect');
    if (!select || select.dataset.filled === '1') {
        return;
    }
    const years = await loadJumpHebrewYears();
    if (!Array.isArray(years) || !years.length) {
        return;
    }
    const current = select.value;
    select.replaceChildren();
    years.forEach((item) => {
        const option = document.createElement('option');
        option.value = String(item.year);
        option.textContent = item.label || String(item.year);
        select.append(option);
    });
    select.dataset.filled = '1';
    if (current && [...select.options].some((option) => option.value === current)) {
        select.value = current;
    }
}

function visibleJumpContext() {
    const result = {
        gregYear: null,
        gregMonth: null,
        hebrewName: '',
        dateStr: '',
    };
    const label = document.getElementById('current-month');
    const text = label && label.textContent ? label.textContent.trim() : '';
    const gregNames = typeof GREGORIAN_MONTH_NAMES_HE !== 'undefined' ? GREGORIAN_MONTH_NAMES_HE : [];
    const parts = text.split('|').map((part) => part.trim()).filter(Boolean);
    if (parts[0]) {
        const match = parts[0].match(/^(\S+)\s+(\d{4})$/);
        if (match) {
            const monthIndex = gregNames.indexOf(match[1]);
            if (monthIndex >= 0) {
                result.gregMonth = monthIndex + 1;
            }
            result.gregYear = Number(match[2]);
        }
    }
    if (parts[1]) {
        result.hebrewName = parts[1]
            .replace(/\s+\d{3,4}$/, '')
            .replace(/\s+ה?'?[\u05d0-\u05ea]+"?[\u05d0-\u05ea]*$/, '')
            .trim();
    }
    const body = (typeof infiniteCalendar !== 'undefined' && infiniteCalendar.body)
        || document.getElementById('calendar-weeks');
    const cell = body && body.querySelector ? body.querySelector('td[data-date]') : null;
    if (cell && cell.dataset) {
        result.dateStr = cell.dataset.date || result.dateStr;
        if (!result.hebrewName) {
            result.hebrewName = cell.dataset.hebrewMonth || '';
        }
    }
    if (!result.dateStr && result.gregYear && result.gregMonth) {
        result.dateStr = `${result.gregYear}-${String(result.gregMonth).padStart(2, '0')}-01`;
    }
    return result;
}

function onJumpHebrewYearChange() {
    const monthSelect = document.getElementById('hebrewMonthSelect');
    if (!monthSelect) {
        return;
    }
    fillJumpHebrewMonths(monthSelect, monthSelect.value);
}

async function syncJumpPickerFromVisible() {
    const token = ++jumpSyncToken;
    const job = (async () => {
        const ctx = visibleJumpContext();
        if (ctx.gregYear && ctx.gregMonth) {
            const monthSelect = document.getElementById('monthSelect');
            const yearSelect = document.getElementById('yearSelect');
            if (monthSelect) {
                monthSelect.value = String(ctx.gregMonth - 1);
            }
            if (yearSelect && [...yearSelect.options].some((option) => option.value === String(ctx.gregYear))) {
                yearSelect.value = String(ctx.gregYear);
            }
        }
        await fillJumpHebrewYears();
        if (token !== jumpSyncToken) {
            return;
        }
        const hebMonth = document.getElementById('hebrewMonthSelect');
        const hebYear = document.getElementById('hebrewYearSelect');
        let monthValue = jumpHebrewMonthFromName(ctx.hebrewName);
        let yearValue = null;
        if (ctx.dateStr) {
            try {
                const response = await fetch(`/api/hebrew-date/${ctx.dateStr}`);
                const data = await response.json();
                if (token !== jumpSyncToken) {
                    return;
                }
                if (response.ok && data.year) {
                    yearValue = data.year;
                    if (monthValue == null && data.month) {
                        monthValue = jumpHebrewMonthFromApi(data.month);
                    }
                }
            } catch (error) {
                /* בלי רשת נשארים על הבחירה הקיימת */
            }
        }
        if (token !== jumpSyncToken) {
            return;
        }
        if (hebMonth && monthValue) {
            fillJumpHebrewMonths(hebMonth, monthValue);
        }
        if (hebYear && yearValue && [...hebYear.options].some((option) => option.value === String(yearValue))) {
            hebYear.value = String(yearValue);
        }
    })();
    jumpSyncPending = job;
    return job;
}

function whenJumpPickerSynced() {
    return jumpSyncPending || Promise.resolve();
}

async function gregorianMonthForHebrewJump(year, month) {
    const params = new URLSearchParams({
        year: String(year),
        month: String(month),
        day: '1',
    });
    const response = await fetch(`/api/gregorian-from-hebrew?${params.toString()}`);
    const data = await response.json();
    if (!response.ok || !data.gregorian_date) {
        return null;
    }
    const [gregYear, gregMonth] = String(data.gregorian_date).split('-').map(Number);
    if (!gregYear || !gregMonth) {
        return null;
    }
    return { year: gregYear, month: gregMonth };
}

function hideJumpDateMenu() {
    const btn = document.getElementById('jumpToDateBtn');
    if (btn && window.bootstrap && bootstrap.Dropdown) {
        const dropdown = bootstrap.Dropdown.getInstance(btn);
        if (dropdown) {
            dropdown.hide();
        }
    }
}

async function jumpToDate() {
    if (jumpCalendarMode === 'hebrew') {
        const year = parseInt(document.getElementById('hebrewYearSelect')?.value, 10);
        const month = parseInt(document.getElementById('hebrewMonthSelect')?.value, 10);
        if (year && month) {
            const target = await gregorianMonthForHebrewJump(year, month);
            if (target && typeof jumpToMonth === 'function') {
                jumpToMonth(target.year, target.month);
            }
        }
    } else {
        const selectedMonth = parseInt(document.getElementById('monthSelect')?.value, 10);
        const selectedYear = parseInt(document.getElementById('yearSelect')?.value, 10);
        if (Number.isFinite(selectedMonth) && Number.isFinite(selectedYear) && typeof jumpToMonth === 'function') {
            jumpToMonth(selectedYear, selectedMonth + 1);
        }
    }
    hideJumpDateMenu();
}

function initJumpDatePicker() {
    const menu = document.getElementById('jumpDateMenu');
    if (!menu || menu.dataset.ready === '1') {
        return;
    }
    menu.dataset.ready = '1';
    fillJumpGregorianYears();
    fillJumpHebrewMonths(document.getElementById('hebrewMonthSelect'));
    setJumpCalendarMode('gregorian');
    const gregBtn = document.getElementById('jumpCalGregorian');
    const hebBtn = document.getElementById('jumpCalHebrew');
    if (gregBtn) {
        gregBtn.addEventListener('click', () => setJumpCalendarMode('gregorian'));
    }
    if (hebBtn) {
        hebBtn.addEventListener('click', () => {
            setJumpCalendarMode('hebrew');
            syncJumpPickerFromVisible();
        });
    }
    const hebMonth = document.getElementById('hebrewMonthSelect');
    if (hebMonth) {
        hebMonth.addEventListener('change', () => {
            jumpSyncToken += 1;
        });
    }
    const hebYear = document.getElementById('hebrewYearSelect');
    if (hebYear) {
        hebYear.addEventListener('change', () => {
            jumpSyncToken += 1;
            onJumpHebrewYearChange();
        });
    }
    const btn = document.getElementById('jumpToDateBtn');
    if (btn) {
        btn.addEventListener('show.bs.dropdown', () => {
            syncJumpPickerFromVisible();
        });
    }
    return fillJumpHebrewYears();
}
