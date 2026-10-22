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
            showMessage('קובץ הגיבוי ירד בהצלחה (heb-cal-events.json)');
        }
    } catch (error) {
        console.error('שגיאה ביצוא האירועים:', error);
        alert('שגיאה בייצוא האירועים');
    }
}

async function importEventsFromFile(file, mode) {
    const operationText = mode === 'replace' ? 'להחליף את כל הנתונים הקיימים' : 'למזג את הנתונים לתוך הקיימים';
    if (!confirm(`האם לבצע ייבוא ול${operationText}?`)) {
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
            throw new Error(result.error || 'שגיאה בייבוא האירועים');
        }

        if (typeof refreshEventsViews === 'function') {
            await refreshEventsViews();
        }

        const inserted = result.inserted_events || 0;
        const updated = result.updated_events || 0;
        const colors = result.imported_colors || 0;
        const modeLabel = mode === 'replace' ? 'החלפה מלאה' : 'מיזוג';
        alert(
            `הייבוא הושלם (${modeLabel})\n\n` +
            `אירועים חדשים שנוספו: ${inserted}\n` +
            `אירועים קיימים שעודכנו: ${updated}\n` +
            `צבעים חדשים שנוספו: ${colors}\n\n` +
            `לחץ אישור כדי להמשיך.`
        );
    } catch (error) {
        console.error('שגיאה ביבוא האירועים:', error);
        alert(error.message || 'שגיאה בייבוא האירועים');
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
