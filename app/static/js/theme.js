// מצב כהה/בהיר — מתג יחיד ב-/settings, מפתח אחד לכל האפליקציה
(function () {
    const STORAGE_KEY = 'heb-cal-theme';
    const root = document.documentElement;
    const media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

    function getStoredTheme() {
        try {
            const value = localStorage.getItem(STORAGE_KEY);
            return value === 'light' || value === 'dark' ? value : null;
        } catch (e) {
            return null;
        }
    }

    function syncThemeSwitch(theme) {
        const isDark = theme === 'dark';
        document.querySelectorAll('[data-theme-switch]').forEach((input) => {
            input.checked = isDark;
        });
    }

    function applyTheme(theme) {
        root.setAttribute('data-bs-theme', theme);
        syncThemeSwitch(theme);
    }

    document.addEventListener('change', (e) => {
        const input = e.target.closest('[data-theme-switch]');
        if (!input) {
            return;
        }
        const next = input.checked ? 'dark' : 'light';
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch (err) {
            // localStorage חסום (מצב פרטי) — הבחירה תחזיק רק עד רענון
        }
        applyTheme(next);
    });

    if (media && media.addEventListener) {
        media.addEventListener('change', (e) => {
            if (!getStoredTheme()) {
                applyTheme(e.matches ? 'dark' : 'light');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        syncThemeSwitch(root.getAttribute('data-bs-theme') || 'light');
    });
})();
