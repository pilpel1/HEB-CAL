// קיפול עצמאי לכל כרטיס בהגדרות. כמה יכולים להיות פתוחים יחד.
// נשמר ב-localStorage לכל מכשיר. ברירת מחדל: הראשון פתוח.

const SETTINGS_SECTIONS_KEY = 'heb-cal-settings-sections';

function settingsSectionHashId(hash) {
    const raw = String(hash || '').replace(/^#/, '');
    if (raw === 'settings-users') {
        return 'settings-reminders';
    }
    return raw;
}

function settingsSectionOpenMap(stored, sectionIds, firstId, hashId) {
    const map = {};
    const hasStore = stored && typeof stored === 'object' && !Array.isArray(stored);
    const hasHash = Boolean(hashId && sectionIds.indexOf(hashId) !== -1);
    sectionIds.forEach((id) => {
        if (hasStore && Object.prototype.hasOwnProperty.call(stored, id)) {
            map[id] = Boolean(stored[id]);
        } else if (hasHash) {
            map[id] = id === hashId;
        } else {
            map[id] = id === firstId;
        }
    });
    if (hasHash) {
        map[hashId] = true;
    }
    return map;
}

function readSettingsSectionStore() {
    try {
        const raw = localStorage.getItem(SETTINGS_SECTIONS_KEY);
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            return null;
        }
        return parsed;
    } catch (error) {
        return null;
    }
}

function writeSettingsSectionStore(map) {
    try {
        localStorage.setItem(SETTINGS_SECTIONS_KEY, JSON.stringify(map));
    } catch (error) {
        /* מצב פרטי */
    }
}

function settingsSectionNodes(root) {
    return Array.from((root || document).querySelectorAll('[data-settings-section]'));
}

function applySettingsSectionState(root, hash) {
    const sections = settingsSectionNodes(root);
    if (!sections.length) {
        return null;
    }
    const ids = sections.map((section) => section.getAttribute('data-settings-section'));
    const firstId = ids[0];
    const hashId = settingsSectionHashId(hash !== undefined ? hash : (window.location.hash || ''));
    const map = settingsSectionOpenMap(readSettingsSectionStore(), ids, firstId, hashId);
    sections.forEach((section) => {
        const id = section.getAttribute('data-settings-section');
        const open = Boolean(map[id]);
        section.classList.toggle('is-open', open);
        const toggle = section.querySelector('.settings-section-toggle');
        if (toggle) {
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        }
    });
    return map;
}

function currentSettingsSectionMap(root) {
    const map = {};
    settingsSectionNodes(root).forEach((section) => {
        map[section.getAttribute('data-settings-section')] = section.classList.contains('is-open');
    });
    return map;
}

function setSettingsSectionOpen(section, open) {
    if (!section) {
        return;
    }
    section.classList.toggle('is-open', Boolean(open));
    const toggle = section.querySelector('.settings-section-toggle');
    if (toggle) {
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
}

function toggleSettingsSection(section) {
    setSettingsSectionOpen(section, !section.classList.contains('is-open'));
    writeSettingsSectionStore(currentSettingsSectionMap(section.closest('.settings-page') || document));
}

let settingsSectionsBound = false;

function initSettingsSections() {
    const root = document.querySelector('.settings-page');
    if (!root) {
        return;
    }
    applySettingsSectionState(root);
    if (settingsSectionsBound) {
        return;
    }
    settingsSectionsBound = true;
    root.addEventListener('click', (event) => {
        const toggle = event.target.closest('.settings-section-toggle');
        if (!toggle || !root.contains(toggle)) {
            return;
        }
        event.preventDefault();
        toggleSettingsSection(toggle.closest('[data-settings-section]'));
    });
    window.addEventListener('hashchange', () => {
        applySettingsSectionState(root);
        const id = settingsSectionHashId(window.location.hash || '');
        const section = id && root.querySelector(`[data-settings-section="${id}"]`);
        if (section) {
            section.scrollIntoView({ block: 'start' });
        }
    });
}
