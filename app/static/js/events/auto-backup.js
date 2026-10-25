// גיבוי אוטומטי פעם ביום, כל עוד הדף פתוח. אותו JSON כמו «ייצוא» (/api/events/export).
// ב-Chromium על HTTPS/localhost: תיקייה שנבחרה פעם אחת (IndexedDB) ובתוכה «גיבוי יומן».
// בלי ה-API (Safari, Firefox, כתובת לא מאובטחת): הורדה רגילה אחרי הלחיצה הראשונה באותו יום.

(function () {
    var ENABLED_KEY = 'heb-cal-auto-backup-enabled';
    var RETENTION_KEY = 'heb-cal-auto-backup-retention';
    var LAST_RUN_KEY = 'heb-cal-auto-backup-last-run';
    var FOLDER_LABEL_KEY = 'heb-cal-auto-backup-folder-label';
    var PERM_ASKED_KEY = 'heb-cal-auto-backup-perm-asked';
    var DB_NAME = 'heb-cal-auto-backup';
    var DB_STORE = 'handles';
    var HANDLE_KEY = 'directory';

    var cachedHandle = null;
    var pendingBlob = null;
    var inFlight = null;
    var gestureArmed = false;

    function storageGet(key) {
        try {
            return window.localStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }

    function storageSet(key, value) {
        try {
            window.localStorage.setItem(key, value);
            return true;
        } catch (error) {
            return false;
        }
    }

    function storageRemove(key) {
        try {
            window.localStorage.removeItem(key);
        } catch (error) {
            return;
        }
    }

    function readEnabled() {
        return storageGet(ENABLED_KEY) === '1';
    }

    function readRetention() {
        return hebCalAutoBackup.clampBackupRetention(storageGet(RETENTION_KEY));
    }

    function readLastRun() {
        return storageGet(LAST_RUN_KEY);
    }

    function setStatus(text) {
        var el = document.getElementById('autoBackupStatus');
        if (!el) return;
        el.textContent = text || '';
    }

    function toast(text) {
        if (typeof showMessage === 'function') showMessage(text);
    }

    function renderLastRun() {
        var el = document.getElementById('autoBackupLastRun');
        if (!el) return;
        var iso = readLastRun();
        var date = iso ? new Date(iso) : null;
        if (!date || isNaN(date.getTime())) {
            el.textContent = 'עדיין לא רץ גיבוי מהמכשיר הזה.';
            return;
        }
        var formatted;
        try {
            formatted = date.toLocaleString('he-IL', { dateStyle: 'short', timeStyle: 'short' });
        } catch (error) {
            formatted = date.toLocaleString('he-IL');
        }
        el.textContent = 'גיבוי אחרון: ' + formatted;
    }

    function renderFolder() {
        var el = document.getElementById('autoBackupFolderStatus');
        if (!el || el.hidden) return;
        var label = storageGet(FOLDER_LABEL_KEY);
        if (!label && cachedHandle && cachedHandle.name) {
            label = cachedHandle.name === hebCalAutoBackup.FOLDER_NAME
                ? hebCalAutoBackup.FOLDER_NAME
                : hebCalAutoBackup.FOLDER_NAME + ' בתוך ' + cachedHandle.name;
        }
        el.textContent = label ? ('התיקייה: ' + label) : 'עדיין לא נבחרה תיקייה.';
    }

    function setBusy(on) {
        var nowBtn = document.getElementById('autoBackupNow');
        var pick = document.getElementById('autoBackupPickFolder');
        if (nowBtn) nowBtn.disabled = on;
        if (pick) pick.disabled = on;
    }

    function openDb() {
        return new Promise(function (resolve, reject) {
            if (!window.indexedDB) {
                reject(new Error('indexedDB'));
                return;
            }
            var request = window.indexedDB.open(DB_NAME, 1);
            request.onupgradeneeded = function () {
                var db = request.result;
                if (!db.objectStoreNames.contains(DB_STORE)) {
                    db.createObjectStore(DB_STORE);
                }
            };
            request.onsuccess = function () { resolve(request.result); };
            request.onerror = function () { reject(request.error || new Error('indexedDB')); };
        });
    }

    function idbRequest(mode, runner) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(DB_STORE, mode);
                var request;
                try {
                    request = runner(tx.objectStore(DB_STORE));
                } catch (error) {
                    db.close();
                    reject(error);
                    return;
                }
                tx.oncomplete = function () {
                    var value = request ? request.result : undefined;
                    db.close();
                    resolve(value);
                };
                tx.onerror = function () {
                    var error = tx.error;
                    db.close();
                    reject(error || new Error('indexedDB'));
                };
                tx.onabort = tx.onerror;
            });
        });
    }

    function saveHandle(handle) {
        return idbRequest('readwrite', function (store) {
            return store.put(handle, HANDLE_KEY);
        });
    }

    function loadHandle() {
        return idbRequest('readonly', function (store) {
            return store.get(HANDLE_KEY);
        }).then(function (value) {
            if (!hebCalAutoBackup.usableDirectoryHandle(value)) return null;
            return value;
        });
    }

    async function fetchExportBlob() {
        var response = await fetch('/api/events/export', { headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.blob();
    }

    function triggerDownload(blob, filename) {
        var url = window.URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.rel = 'noopener';
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(function () {
            window.URL.revokeObjectURL(url);
        }, 1500);
    }

    async function showBackupDirectoryPicker() {
        var base = { id: 'heb-cal-backup', mode: 'readwrite' };
        try {
            return await window.showDirectoryPicker(Object.assign({ startIn: 'downloads' }, base));
        } catch (error) {
            if (error && error.name === 'AbortError') throw error;
            return window.showDirectoryPicker(base);
        }
    }

    function showResult(result) {
        renderLastRun();
        if (!result || result.skipped) return;
        if (result.needsFolder) {
            setStatus('בחרו תיקייה. אם הדפדפן מסרב להורדות עצמן, צרו בחלון הבחירה תיקייה בשם «' + hebCalAutoBackup.FOLDER_NAME + '».');
            return;
        }
        if (result.needsPermission) {
            setStatus('צריך לאשר גישה לתיקייה.');
            return;
        }
        if (!result.ok) return;
        var text = result.downloaded
            ? ('הקובץ ירד: ' + result.name)
            : ('הגיבוי נשמר: ' + result.name);
        if (result.removed && result.removed.length) {
            text += ' (נמחקו ' + result.removed.length + ' ישנים)';
        }
        if (result.failed && result.failed.length) {
            text += ' (חלק מהעותקים הישנים נשארו)';
        }
        setStatus(text);
        toast(text);
    }

    function handleError(error) {
        if (error && error.name === 'AbortError') {
            setStatus('הבחירה בוטלה.');
            return;
        }
        console.error('גיבוי אוטומטי', error);
        var text = 'לא הצלחנו לגבות.';
        if (error && (error.name === 'NotFoundError' || error.name === 'NotAllowedError')) {
            text = 'אין גישה לתיקייה. בחרו אותה שוב.';
        }
        setStatus(text);
        if (!document.getElementById('autoBackupStatus')) toast(text);
    }

    function rollbackLastRun(previous) {
        if (previous) storageSet(LAST_RUN_KEY, previous);
        else storageRemove(LAST_RUN_KEY);
    }

    async function performInner(options) {
        options = options || {};
        var now = options.now instanceof Date ? options.now : new Date();
        var force = !!options.force;
        if (!force && !hebCalAutoBackup.shouldRunBackupToday(readLastRun(), now)) {
            return { skipped: true };
        }

        var api = hebCalAutoBackup.backupDirectoryApiAvailable();
        var handle = cachedHandle;
        if (api && !handle) {
            try {
                handle = await loadHandle();
                cachedHandle = handle;
            } catch (error) {
                handle = null;
            }
        }
        if (api && !handle) return { needsFolder: true };

        if (api && handle && !options.permissionReady) {
            var perm = 'prompt';
            try {
                perm = await handle.queryPermission({ mode: 'readwrite' });
            } catch (error) {
                perm = 'prompt';
            }
            if (perm !== 'granted') {
                if (!options.userGesture) return { needsPermission: true };
                try {
                    perm = await handle.requestPermission({ mode: 'readwrite' });
                } catch (error) {
                    return { needsPermission: true };
                }
                if (perm !== 'granted') return { needsPermission: true };
            }
        }

        var blob = pendingBlob;
        pendingBlob = null;
        if (!blob) blob = await fetchExportBlob();

        var previous = readLastRun();
        var claimed = false;
        try {
            if (!force) {
                storageSet(LAST_RUN_KEY, now.toISOString());
                claimed = true;
            }
            if (api && handle) {
                var dir = await hebCalAutoBackup.resolveBackupDirectory(handle);
                var written = await hebCalAutoBackup.writeBackupToDirectory(dir, blob, now, readRetention());
                storageSet(LAST_RUN_KEY, now.toISOString());
                storageRemove(PERM_ASKED_KEY);
                return {
                    ok: true,
                    name: written.name,
                    removed: written.removed,
                    failed: written.failed,
                };
            }
            var filename = hebCalAutoBackup.backupFilename(now);
            triggerDownload(blob, filename);
            storageSet(LAST_RUN_KEY, now.toISOString());
            return { ok: true, downloaded: true, name: filename };
        } catch (error) {
            if (claimed) rollbackLastRun(previous);
            throw error;
        }
    }

    function perform(options) {
        options = options || {};
        if (inFlight && !options.force) return inFlight;
        var run = performInner(options).finally(function () {
            if (inFlight === run) inFlight = null;
        });
        inFlight = run;
        return run;
    }

    function armGesture(fn) {
        if (gestureArmed) return;
        gestureArmed = true;
        function once(event) {
            var section = document.getElementById('settingsAutoBackup');
            if (section && event.target && section.contains(event.target)) return;
            window.removeEventListener('click', once, true);
            window.removeEventListener('keydown', once, true);
            gestureArmed = false;
            fn();
        }
        window.addEventListener('click', once, true);
        window.addEventListener('keydown', once, true);
    }

    function requestThenBackup() {
        if (!cachedHandle) return;
        cachedHandle.requestPermission({ mode: 'readwrite' }).then(function (perm) {
            if (perm !== 'granted') {
                storageSet(PERM_ASKED_KEY, hebCalAutoBackup.localBackupDateKey(new Date()));
                setStatus('בלי אישור לתיקייה הגיבוי לא נשמר. «גבה עכשיו» יבקש שוב.');
                return;
            }
            return perform({ permissionReady: true }).then(showResult);
        }).catch(handleError);
    }

    async function maybeRunScheduled() {
        if (!readEnabled()) return;
        var now = new Date();
        if (!hebCalAutoBackup.shouldRunBackupToday(readLastRun(), now)) return;

        if (hebCalAutoBackup.backupDirectoryApiAvailable()) {
            if (!cachedHandle) {
                try {
                    cachedHandle = await loadHandle();
                } catch (error) {
                    cachedHandle = null;
                }
            }
            renderFolder();
            if (!cachedHandle) {
                setStatus('הגיבוי האוטומטי דולק. בחרו תיקייה כדי לשמור את «' + hebCalAutoBackup.FOLDER_NAME + '».');
                return;
            }
            var perm = 'prompt';
            try {
                perm = await cachedHandle.queryPermission({ mode: 'readwrite' });
            } catch (error) {
                perm = 'prompt';
            }
            if (perm === 'granted') {
                showResult(await perform({ permissionReady: true, now: now }));
                return;
            }
            if (storageGet(PERM_ASKED_KEY) === hebCalAutoBackup.localBackupDateKey(now)) {
                setStatus('הגיבוי לא רץ היום: אין אישור לתיקייה. «גבה עכשיו» יבקש שוב.');
                return;
            }
            setStatus('צריך לאשר את תיקיית הגיבוי. לחצו במקום כלשהו ביומן, או על «גבה עכשיו».');
            if (!document.getElementById('autoBackupStatus')) {
                toast('צריך לאשר את תיקיית הגיבוי — לחצו במקום כלשהו');
            }
            armGesture(requestThenBackup);
            return;
        }

        setStatus('היום הגיבוי ירד להורדות אחרי לחיצה ביומן.');
        if (!document.getElementById('autoBackupStatus')) {
            toast('גיבוי היום ירד להורדות אחרי לחיצה ביומן');
        }
        try {
            pendingBlob = await fetchExportBlob();
        } catch (error) {
            pendingBlob = null;
        }
        armGesture(function () {
            perform({ userGesture: true }).then(showResult).catch(handleError);
        });
    }

    async function pickFolder() {
        var picked = await showBackupDirectoryPicker();
        var target = await hebCalAutoBackup.resolveBackupDirectory(picked);
        cachedHandle = target;
        var label = picked.name === hebCalAutoBackup.FOLDER_NAME
            ? hebCalAutoBackup.FOLDER_NAME
            : hebCalAutoBackup.FOLDER_NAME + ' בתוך ' + (picked.name || 'התיקייה שנבחרה');
        storageSet(FOLDER_LABEL_KEY, label);
        renderFolder();
        try {
            await saveHandle(target);
        } catch (error) {
            console.error(error);
            setStatus('התיקייה נבחרה, אבל הדפדפן לא שמר אותה לפעם הבאה.');
        }
        showResult(await perform({ force: true, permissionReady: true }));
    }

    async function backupNow() {
        var api = hebCalAutoBackup.backupDirectoryApiAvailable();
        if (api && !cachedHandle) {
            try {
                cachedHandle = await loadHandle();
            } catch (error) {
                cachedHandle = null;
            }
        }
        if (api && !cachedHandle) {
            await pickFolder();
            return;
        }
        if (api && cachedHandle) {
            var perm = 'prompt';
            try {
                perm = await cachedHandle.queryPermission({ mode: 'readwrite' });
            } catch (error) {
                perm = 'prompt';
            }
            if (perm !== 'granted') {
                perm = await cachedHandle.requestPermission({ mode: 'readwrite' });
            }
            if (perm !== 'granted') {
                setStatus('בלי אישור לתיקייה אי אפשר לשמור. נסו לבחור אותה שוב.');
                return;
            }
        }
        showResult(await perform({ force: true, permissionReady: true, userGesture: true }));
    }

    function bindSettings() {
        var enabled = document.getElementById('autoBackupEnabled');
        var retention = document.getElementById('autoBackupRetention');
        var pick = document.getElementById('autoBackupPickFolder');
        var nowBtn = document.getElementById('autoBackupNow');
        var note = document.getElementById('autoBackupApiNote');
        var help = document.getElementById('autoBackupFolderHelp');
        var folderStatus = document.getElementById('autoBackupFolderStatus');
        var apiOk = hebCalAutoBackup.backupDirectoryApiAvailable();

        if (note) note.hidden = apiOk;
        if (help) help.hidden = !apiOk;
        if (pick) pick.hidden = !apiOk;
        if (folderStatus) folderStatus.hidden = !apiOk;

        if (enabled && enabled.dataset.bound !== '1') {
            enabled.dataset.bound = '1';
            enabled.checked = readEnabled();
            enabled.addEventListener('change', function () {
                storageSet(ENABLED_KEY, enabled.checked ? '1' : '0');
                if (!enabled.checked) {
                    setStatus('הגיבוי האוטומטי כבוי.');
                    return;
                }
                if (!hebCalAutoBackup.shouldRunBackupToday(readLastRun(), new Date())) {
                    setStatus('הגיבוי פעיל. היום כבר נשמר עותק.');
                    return;
                }
                maybeRunScheduled();
            });
        }
        if (retention && retention.dataset.bound !== '1') {
            retention.dataset.bound = '1';
            var clamped = readRetention();
            retention.value = String(clamped);
            storageSet(RETENTION_KEY, String(clamped));
            retention.addEventListener('change', function () {
                var next = hebCalAutoBackup.clampBackupRetention(retention.value);
                retention.value = String(next);
                storageSet(RETENTION_KEY, String(next));
            });
        }
        if (pick && pick.dataset.bound !== '1') {
            pick.dataset.bound = '1';
            pick.addEventListener('click', function () {
                setBusy(true);
                pickFolder().catch(handleError).finally(function () { setBusy(false); });
            });
        }
        if (nowBtn && nowBtn.dataset.bound !== '1') {
            nowBtn.dataset.bound = '1';
            nowBtn.addEventListener('click', function () {
                setBusy(true);
                backupNow().catch(handleError).finally(function () { setBusy(false); });
            });
        }
        renderFolder();
        renderLastRun();
    }

    function init() {
        bindSettings();
        var wantHandle = readEnabled() || !!document.getElementById('settingsAutoBackup');
        var pending = wantHandle
            ? loadHandle().catch(function () { return null; })
            : Promise.resolve(null);
        pending.then(function (handle) {
            cachedHandle = handle || null;
            renderFolder();
            return maybeRunScheduled();
        }).catch(handleError);
    }

    document.addEventListener('DOMContentLoaded', init);
})();
