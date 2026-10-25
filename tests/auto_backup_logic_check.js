'use strict';

const assert = require('assert');
const api = require('../app/static/js/events/auto-backup-logic.js');

function memoryDirectory(name, initial) {
    const files = new Map(initial || []);
    return {
        name: name,
        files: files,
        async getFileHandle(filename) {
            return {
                async createWritable() {
                    let text = '';
                    return {
                        async write(data) {
                            if (typeof data === 'string') text += data;
                            else if (data && typeof data.text === 'function') text += await data.text();
                            else text += String(data);
                        },
                        async close() {
                            files.set(filename, text);
                        },
                    };
                },
            };
        },
        entries() {
            const keys = Array.from(files.keys());
            let index = 0;
            return {
                next() {
                    if (index >= keys.length) return Promise.resolve({ done: true, value: undefined });
                    const entryName = keys[index++];
                    return Promise.resolve({
                        done: false,
                        value: [entryName, { kind: 'file', name: entryName }],
                    });
                },
                [Symbol.asyncIterator]() {
                    return this;
                },
            };
        },
        async removeEntry(entryName) {
            if (!files.has(entryName)) throw new Error('missing ' + entryName);
            files.delete(entryName);
        },
    };
}

function run() {
    assert.strictEqual(api.clampBackupRetention(undefined), 3);
    assert.strictEqual(api.clampBackupRetention(null), 3);
    assert.strictEqual(api.clampBackupRetention(''), 3);
    assert.strictEqual(api.clampBackupRetention('abc'), 3);
    assert.strictEqual(api.clampBackupRetention(Number.NaN), 3);
    assert.strictEqual(api.clampBackupRetention(0), 1);
    assert.strictEqual(api.clampBackupRetention(-4), 1);
    assert.strictEqual(api.clampBackupRetention('0'), 1);
    assert.strictEqual(api.clampBackupRetention(31), 30);
    assert.strictEqual(api.clampBackupRetention(100), 30);
    assert.strictEqual(api.clampBackupRetention(30.6), 30);
    assert.strictEqual(api.clampBackupRetention(2.2), 2);
    assert.strictEqual(api.clampBackupRetention(2.5), 3);
    assert.strictEqual(api.clampBackupRetention(' 2 '), 2);
    assert.strictEqual(api.clampBackupRetention(1), 1);
    assert.strictEqual(api.clampBackupRetention(3), 3);
    assert.strictEqual(api.DEFAULT_RETENTION, 3);
    assert.strictEqual(api.MIN_RETENTION, 1);
    assert.strictEqual(api.MAX_RETENTION, 30);

    const morning = new Date(2026, 9, 25, 8, 0, 0);
    const evening = new Date(2026, 9, 25, 23, 30, 0);
    const next = new Date(2026, 9, 26, 0, 5, 0);
    assert.strictEqual(api.shouldRunBackupToday(null, morning), true);
    assert.strictEqual(api.shouldRunBackupToday(undefined, morning), true);
    assert.strictEqual(api.shouldRunBackupToday('', morning), true);
    assert.strictEqual(api.shouldRunBackupToday('not-a-date', morning), true);
    assert.strictEqual(api.shouldRunBackupToday(morning.toISOString(), evening), false);
    assert.strictEqual(api.shouldRunBackupToday(morning, evening), false);
    assert.strictEqual(api.shouldRunBackupToday(evening.toISOString(), next), true);
    assert.strictEqual(api.localBackupDateKey(morning), '2026-10-25');
    assert.strictEqual(api.localBackupDateKey(next), '2026-10-26');

    const early = api.backupFilename(new Date(2026, 0, 2, 3, 4, 5));
    const later = api.backupFilename(new Date(2026, 10, 9, 8, 7, 6));
    assert.strictEqual(early, 'heb-cal-backup-20260102-030405.json');
    assert.strictEqual(later, 'heb-cal-backup-20261109-080706.json');
    assert.ok(early < later);
    assert.strictEqual(api.isBackupFilename(early), true);
    assert.strictEqual(api.isBackupFilename('heb-cal-backup-20261025-080012.json'), true);
    assert.strictEqual(api.isBackupFilename('heb-cal-events.json'), false);
    assert.strictEqual(api.isBackupFilename('heb-cal-backup-notes.json'), false);
    assert.strictEqual(api.isBackupFilename('heb-cal-backup-20261025-080012 (1).json'), false);
    assert.strictEqual(api.FILENAME_PREFIX, 'heb-cal-backup-');
    assert.strictEqual(api.FOLDER_NAME, 'גיבוי יומן');

    const names = [
        'heb-cal-backup-20261001-000000.json',
        'heb-cal-backup-20261002-000000.json',
        'heb-cal-backup-20261003-000000.json',
        'heb-cal-backup-20261004-000000.json',
        'notes.txt',
        'heb-cal-events.json',
    ];
    assert.deepStrictEqual(api.pruneBackupNames(names, 2), [
        'heb-cal-backup-20261001-000000.json',
        'heb-cal-backup-20261002-000000.json',
    ]);
    assert.deepStrictEqual(api.pruneBackupNames(names, 1), [
        'heb-cal-backup-20261001-000000.json',
        'heb-cal-backup-20261002-000000.json',
        'heb-cal-backup-20261003-000000.json',
    ]);
    assert.deepStrictEqual(api.pruneBackupNames(names, 0), api.pruneBackupNames(names, 1));
    assert.deepStrictEqual(api.pruneBackupNames(names, 99), []);
    assert.deepStrictEqual(api.pruneBackupNames([], 3), []);
    assert.deepStrictEqual(api.pruneBackupNames(null, 3), []);
    assert.deepStrictEqual(api.pruneBackupNames([
        'heb-cal-backup-20261001-000000.json',
        'heb-cal-backup-20261001-000000.json',
        'heb-cal-backup-20261002-000000.json',
    ], 1), ['heb-cal-backup-20261001-000000.json']);
    assert.deepStrictEqual(api.pruneBackupNames(names, 1, 'heb-cal-backup-20261001-000000.json'), [
        'heb-cal-backup-20261002-000000.json',
        'heb-cal-backup-20261003-000000.json',
        'heb-cal-backup-20261004-000000.json',
    ]);

    assert.strictEqual(api.usableDirectoryHandle(null), false);
    assert.strictEqual(api.usableDirectoryHandle({ name: 'גיבוי יומן' }), false);
    assert.strictEqual(api.usableDirectoryHandle({ getFileHandle: function () {} }), true);

    assert.strictEqual(api.backupDirectoryApiAvailable(), false);
    assert.strictEqual(api.backupDirectoryApiAvailable({}), false);
    assert.strictEqual(api.backupDirectoryApiAvailable({ isSecureContext: true }), false);
    assert.strictEqual(api.backupDirectoryApiAvailable({
        isSecureContext: false,
        showDirectoryPicker: function () {},
    }), false);
    assert.strictEqual(api.backupDirectoryApiAvailable({
        isSecureContext: true,
        showDirectoryPicker: 'no',
    }), false);
    assert.strictEqual(api.backupDirectoryApiAvailable({
        isSecureContext: true,
        showDirectoryPicker: function () {},
    }), true);
}

async function runAsync() {
    const same = { name: 'גיבוי יומן' };
    assert.strictEqual(await api.resolveBackupDirectory(same), same);
    assert.strictEqual(await api.resolveBackupDirectory(null), null);
    let created = null;
    const parent = {
        name: 'Downloads',
        async getDirectoryHandle(child, options) {
            created = { child: child, options: options };
            return { name: child };
        },
    };
    const child = await api.resolveBackupDirectory(parent);
    assert.strictEqual(child.name, 'גיבוי יומן');
    assert.deepStrictEqual(created.options, { create: true });

    const dir = memoryDirectory('גיבוי יומן', [
        ['heb-cal-backup-20261001-000000.json', 'a'],
        ['heb-cal-backup-20261002-000000.json', 'b'],
        ['heb-cal-backup-20261003-000000.json', 'c'],
        ['notes.txt', 'keep me'],
        ['heb-cal-events.json', 'manual'],
    ]);
    const written = await api.writeBackupToDirectory(
        dir,
        '{"version":1}',
        new Date(2026, 9, 4, 12, 0, 0),
        2,
    );
    assert.strictEqual(written.name, 'heb-cal-backup-20261004-120000.json');
    assert.deepStrictEqual(written.removed, [
        'heb-cal-backup-20261001-000000.json',
        'heb-cal-backup-20261002-000000.json',
    ]);
    assert.deepStrictEqual(written.failed, []);
    assert.strictEqual(dir.files.get(written.name), '{"version":1}');
    assert.strictEqual(dir.files.has('heb-cal-backup-20261003-000000.json'), true);
    assert.strictEqual(dir.files.has('heb-cal-backup-20261001-000000.json'), false);
    assert.strictEqual(dir.files.get('notes.txt'), 'keep me');
    assert.strictEqual(dir.files.get('heb-cal-events.json'), 'manual');
    assert.strictEqual(dir.files.size, 4);

    const skewed = memoryDirectory('גיבוי יומן', [
        ['heb-cal-backup-20261005-000000.json', 'newer'],
    ]);
    const keptOldWrite = await api.writeBackupToDirectory(
        skewed,
        'just-written',
        new Date(2026, 9, 1, 8, 0, 0),
        1,
    );
    assert.strictEqual(keptOldWrite.name, 'heb-cal-backup-20261001-080000.json');
    assert.strictEqual(skewed.files.get(keptOldWrite.name), 'just-written');
    assert.strictEqual(skewed.files.has('heb-cal-backup-20261005-000000.json'), false);

    const stuck = memoryDirectory('גיבוי יומן', [
        ['heb-cal-backup-20261001-000000.json', 'old'],
        ['heb-cal-backup-20261002-000000.json', 'mid'],
    ]);
    stuck.removeEntry = async function () {
        throw new Error('locked');
    };
    const partial = await api.writeBackupToDirectory(stuck, 'new', new Date(2026, 9, 3, 1, 2, 3), 1);
    assert.strictEqual(partial.name, 'heb-cal-backup-20261003-010203.json');
    assert.strictEqual(stuck.files.get(partial.name), 'new');
    assert.deepStrictEqual(partial.removed, []);
    assert.deepStrictEqual(partial.failed, [
        'heb-cal-backup-20261001-000000.json',
        'heb-cal-backup-20261002-000000.json',
    ]);

    const blobDir = memoryDirectory('גיבוי יומן', []);
    const blobWritten = await api.writeBackupToDirectory(
        blobDir,
        new Blob(['{"ok":true}']),
        new Date(2026, 9, 5, 6, 7, 8),
        3,
    );
    assert.strictEqual(blobWritten.name, 'heb-cal-backup-20261005-060708.json');
    assert.strictEqual(blobDir.files.get(blobWritten.name), '{"ok":true}');
}

run();
runAsync().then(function () {
    console.log('auto-backup logic ok');
}).catch(function (error) {
    console.error(error);
    process.exit(1);
});
