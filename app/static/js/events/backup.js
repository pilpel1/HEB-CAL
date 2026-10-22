// ייצוא/ייבוא JSON של כל האירועים. הכפתורים חיים בעמוד ההגדרות.

async function exportEvents() {
    try {
        const response = await fetch('/api/events/export');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'heb-cal-events.json';
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
        if (typeof showMessage === 'function') {
            showMessage('הקובץ ירד (heb-cal-events.json)');
        }
    } catch (error) {
        console.error('שגיאה ביצוא האירועים:', error);
        alert('לא הצלחנו לייצא');
    }
}

async function importEventsFromFile(file, mode) {
    const question = mode === 'replace' ? 'לייבא ולהחליף את כל הנתונים?' : 'לייבא ולמזג עם הקיימים?';
    if (!confirm(question)) {
        return;
    }

    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('mode', mode);

        const response = await fetch('/api/events/import', {
            method: 'POST',
            body: formData,
        });

        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || 'לא הצלחנו לייבא');
        }

        if (typeof refreshEventsViews === 'function') {
            await refreshEventsViews();
        }

        const inserted = result.inserted_events || 0;
        const updated = result.updated_events || 0;
        const colors = result.imported_colors || 0;
        const modeLabel = mode === 'replace' ? 'החלפה' : 'מיזוג';
        alert(
            `הייבוא הושלם (${modeLabel})\n` +
            `נוספו: ${inserted}\n` +
            `עודכנו: ${updated}\n` +
            `צבעים חדשים: ${colors}`
        );
    } catch (error) {
        console.error('שגיאה ביבוא האירועים:', error);
        alert(error.message || 'לא הצלחנו לייבא');
    }
}

function initEventsBackup() {
    const exportBtn = document.getElementById('exportEventsBtn');
    const importBtn = document.getElementById('importEventsBtn');
    const importFile = document.getElementById('importEventsFile');
    const importMode = document.getElementById('importMode');
    if (!exportBtn || !importBtn || !importFile || exportBtn.dataset.bound === '1') {
        return;
    }
    exportBtn.dataset.bound = '1';
    exportBtn.addEventListener('click', exportEvents);
    importBtn.addEventListener('click', () => importFile.click());
    importFile.addEventListener('change', async function () {
        if (this.files && this.files[0]) {
            await importEventsFromFile(this.files[0], importMode ? importMode.value : 'merge');
            this.value = '';
        }
    });
}

document.addEventListener('DOMContentLoaded', initEventsBackup);
