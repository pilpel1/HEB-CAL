// מצב כהה/בהיר — הערכה הראשונית נקבעת בסקריפט inline ב-<head> של base.html
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

    function updateToggleButtons(theme) {
        const isDark = theme === 'dark';
        const label = isDark ? 'מצב בהיר' : 'מצב כהה';
        document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
            btn.title = label;
            btn.setAttribute('aria-label', label);
            btn.setAttribute('aria-pressed', String(isDark));
            const icon = btn.querySelector('i');
            if (icon) {
                icon.className = isDark ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
            }
        });
    }

    function applyTheme(theme) {
        root.setAttribute('data-bs-theme', theme);
        updateToggleButtons(theme);
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-theme-toggle]');
        if (!btn) {
            return;
        }
        const next = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch (err) {
            // localStorage חסום (מצב פרטי) — הבחירה תחזיק רק עד רענון
        }
        applyTheme(next);
    });

    // כל עוד המשתמש לא בחר ידנית — עוקבים אחרי הגדרת מערכת ההפעלה
    if (media && media.addEventListener) {
        media.addEventListener('change', (e) => {
            if (!getStoredTheme()) {
                applyTheme(e.matches ? 'dark' : 'light');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        updateToggleButtons(root.getAttribute('data-bs-theme') || 'light');
    });
})();
