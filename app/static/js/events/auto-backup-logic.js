// כללי גיבוי בלי דפדפן: מתי לרוץ, שם קובץ, כמה עותקים למחוק.
// הקובץ נטען כסקריפט קלאסי. ב-Node הוא גם module.exports לבדיקות.

var hebCalAutoBackup = (function () {
    var FOLDER_NAME = 'גיבוי יומן';
    var FILENAME_PREFIX = 'heb-cal-backup-';
    var DEFAULT_RETENTION = 3;
    var MIN_RETENTION = 1;
    var MAX_RETENTION = 30;
    var FILENAME_RE = new RegExp('^' + FILENAME_PREFIX + '\\d{8}-\\d{6}\\.json$');

    function pad(value) {
        return String(value).padStart(2, '0');
    }

    function asDate(value) {
        if (value instanceof Date) return value;
        return new Date(value);
    }

    function clampBackupRetention(value) {
        if (value === null || value === undefined || value === '') return DEFAULT_RETENTION;
        var number = typeof value === 'number' ? value : Number(value);
        if (!Number.isFinite(number)) return DEFAULT_RETENTION;
        number = Math.round(number);
        if (number < MIN_RETENTION) return MIN_RETENTION;
        if (number > MAX_RETENTION) return MAX_RETENTION;
        return number;
    }

    function localBackupDateKey(value) {
        var date = asDate(value);
        if (isNaN(date.getTime())) return '';
        return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
    }

    // פעם אחת ביום מקומי. חותמת מאותו יום — לא רצים שוב. חותמת חסרה או שבורה — רצים.
    function shouldRunBackupToday(lastRun, now) {
        var current = asDate(now === undefined || now === null ? Date.now() : now);
        if (isNaN(current.getTime())) return true;
        if (lastRun === null || lastRun === undefined || lastRun === '') return true;
        var last = asDate(lastRun);
        if (isNaN(last.getTime())) return true;
        return localBackupDateKey(last) !== localBackupDateKey(current);
    }

    function backupFilename(value) {
        var date = asDate(value === undefined || value === null ? Date.now() : value);
        if (isNaN(date.getTime())) date = new Date();
        return FILENAME_PREFIX
            + date.getFullYear()
            + pad(date.getMonth() + 1)
            + pad(date.getDate())
            + '-'
            + pad(date.getHours())
            + pad(date.getMinutes())
            + pad(date.getSeconds())
            + '.json';
    }

    function isBackupFilename(name) {
        return typeof name === 'string' && FILENAME_RE.test(name);
    }

    // מוחק את הישנים לפי סדר השם (החותמת בתוכו). keepName תמיד נשאר, גם אם השעון זז אחורה.
    function pruneBackupNames(names, retention, keepName) {
        var keepCount = clampBackupRetention(retention);
        var seen = {};
        var unique = [];
        var list = names || [];
        var index;
        for (index = 0; index < list.length; index++) {
            var name = list[index];
            if (!isBackupFilename(name) || seen[name]) continue;
            seen[name] = true;
            unique.push(name);
        }
        unique.sort();
        var newestFirst = unique.slice().reverse();
        var kept = {};
        var keptCount = 0;
        if (keepName && seen[keepName]) {
            kept[keepName] = true;
            keptCount += 1;
        }
        for (index = 0; index < newestFirst.length && keptCount < keepCount; index++) {
            if (kept[newestFirst[index]]) continue;
            kept[newestFirst[index]] = true;
            keptCount += 1;
        }
        var remove = [];
        for (index = 0; index < unique.length; index++) {
            if (!kept[unique[index]]) remove.push(unique[index]);
        }
        return remove;
    }

    function usableDirectoryHandle(handle) {
        return !!(handle && typeof handle.getFileHandle === 'function');
    }

    function backupDirectoryApiAvailable(scope) {
        var target = scope;
        if (!target && typeof window !== 'undefined') target = window;
        if (!target) return false;
        return !!(target.isSecureContext && typeof target.showDirectoryPicker === 'function');
    }

    async function resolveBackupDirectory(handle) {
        if (!handle || typeof handle.getDirectoryHandle !== 'function') return handle || null;
        if (handle.name === FOLDER_NAME) return handle;
        return handle.getDirectoryHandle(FOLDER_NAME, { create: true });
    }

    async function writeBackupToDirectory(dirHandle, contents, now, retention) {
        if (!dirHandle || typeof dirHandle.getFileHandle !== 'function') {
            throw new Error('missing directory');
        }
        if (contents === undefined || contents === null) {
            throw new Error('empty backup');
        }
        var name = backupFilename(now);
        var fileHandle = await dirHandle.getFileHandle(name, { create: true });
        var writable = await fileHandle.createWritable();
        await writable.write(contents);
        await writable.close();

        var names = [];
        if (typeof dirHandle.entries === 'function') {
            var iterable = dirHandle.entries();
            for await (var entry of iterable) {
                var entryName = entry && entry[0];
                var entryHandle = entry && entry[1];
                if (!entryName) continue;
                if (entryHandle && entryHandle.kind && entryHandle.kind !== 'file') continue;
                names.push(entryName);
            }
        }
        if (names.indexOf(name) === -1) names.push(name);

        var removed = [];
        var failed = [];
        var doomed = pruneBackupNames(names, retention, name);
        var index;
        for (index = 0; index < doomed.length; index++) {
            if (typeof dirHandle.removeEntry !== 'function') {
                failed.push(doomed[index]);
                continue;
            }
            try {
                await dirHandle.removeEntry(doomed[index]);
                removed.push(doomed[index]);
            } catch (error) {
                failed.push(doomed[index]);
            }
        }
        return { name: name, removed: removed, failed: failed };
    }

    return {
        FOLDER_NAME: FOLDER_NAME,
        FILENAME_PREFIX: FILENAME_PREFIX,
        DEFAULT_RETENTION: DEFAULT_RETENTION,
        MIN_RETENTION: MIN_RETENTION,
        MAX_RETENTION: MAX_RETENTION,
        clampBackupRetention: clampBackupRetention,
        shouldRunBackupToday: shouldRunBackupToday,
        localBackupDateKey: localBackupDateKey,
        backupFilename: backupFilename,
        isBackupFilename: isBackupFilename,
        pruneBackupNames: pruneBackupNames,
        usableDirectoryHandle: usableDirectoryHandle,
        backupDirectoryApiAvailable: backupDirectoryApiAvailable,
        resolveBackupDirectory: resolveBackupDirectory,
        writeBackupToDirectory: writeBackupToDirectory,
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = hebCalAutoBackup;
}
