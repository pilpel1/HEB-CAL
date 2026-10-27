# Secret audit before making the repo public

אודיט סודות לפני הפיכת הריפו לציבורי.  
תאריך: 2026-10-24.  
HEAD שנבדק: `2fe44488441042a702e09509d2de163c72164c38` (`main`).  
הריפו עדיין **private**. לא שונתה היסטוריה, לא נעשה force-push, ולא סובב שום סוד.

## Verdict / שורה תחתונה

**לא נמצא סוד חי** — לא בעץ הנוכחי ולא בשום קומיט נגיש (כולל קבצים שנמחקו).

אין מה לסובב בגלל דליפה מהגיט. אין צורך בשכתוב היסטוריה **בשביל סודות**.  
שכתוב היסטוריה הוא אופציונלי ורק אם רוצים להוריד מההיסטוריה הציבורית יומן פיתוח אישי ישן ואת עץ ה-`venv` שנארז בקומיט הראשון. **לא בוצע.**

אין תגיות (`git tag`) ואין GitHub Releases.

## Scope / מה נסרק

| פריט | ערך |
|---|---|
| Remote | `https://github.com/pilpel1/HEB-CAL` |
| Refs | כל ה-heads אחרי `git fetch origin --tags --prune` (28 ענפים, כולל `main`). `git ls-remote --tags` ריק |
| קומיטים | `git rev-list --all` = **114** (2024-11-26 עד 2026-10-24). 2 merges. 56 קומיטים לא נמצאים ב-`origin/main` (ענפי feature) |
| אובייקטים | `git rev-list --all --objects` = 7407 נתיבים. `git fsck --unreachable` לא מצא אובייקטים יתומים |
| קבצים שנבדקו בשם | `.env*`, `config.py`, `config.example.py`, `NETWORK*`, `credentials*`, `secrets*`, `*.pem`, `*.key`, `*.db`, `telegram*`, `google*` / `gcal*` |

מגבלה: קומיט שנדחף פעם ונמחק מכל ה-refs הנוכחיים (force-push של ענף שכבר לא קיים) לא נמצא בקלוּן הזה. כל ref שקיים היום ב-GitHub נכלל.

GitHub secret-scanning alerts החזירו 403 לטוקן של הסוכן. זה לא סריקה של תוכן הגיט.

## Tools / כלים

| כלי | תוצאה |
|---|---|
| gitleaks 8.28.0 `detect` (ברירת מחדל וגם `--log-opts=--all`) | «110 commits scanned», **no leaks**. הפער מול 114 הוא אופן הספירה של הכלי (יש 2 merges). כל הבּלוֹבּים נסרקו ידנית בנפרד |
| trufflehog 3.90.6 `git file://` | 17 ממצאים, **0 verified**. כולם false positive (למטה) |
| git-secrets (awslabs) + דפוסי AWS, `ghp_`, טוקן טלגרם, `AIza` | `git secrets --scan-history` יצא 0, בלי פגיעות |
| סריקה ידנית | כל בּלוֹב טקסט מחוץ ל-`venv` (1427 קבצים) + `git log -G` על כל ההיסטוריה **כולל** `venv` + פתיחת כל קובצי ה-SQLite |

דפוסים שנבדקו: טוקן טלגרם (`123456789:AAH…`), `ghp_` / `github_pat_` / `gho_` / `ghu_` / `ghs_` / `ghr_`, `xoxb-` / `xoxp-` / `xoxa-`, `AIza`, `GOCSPX-`, `AKIA` / `ASIA`, `BEGIN PRIVATE KEY` / `BEGIN OPENSSH`, `tskey-`, `sk_live_` / `sk_test_`, webhook של Slack, כתובת iCal פרטית של גוגל, JWT (`eyJ`), מחרוזות חיבור עם סיסמה, `client_secret` / `refresh_token`, `AccountKey=`, service-account של GCP, כתובות פנימיות (`10.` / `192.168.` / `172.16–31.` / CGNAT של Tailscale `100.64/10`).

## Findings / ממצאים

### אין סוד חי

אין שורה בטבלה. לא נמצא מפתח, טוקן, סיסמה אמיתית, מפתח פרטי, או כתובת iCal אמיתית.

### נבדק ונוקה — placeholders, לא סודות

אלה ערכים מכוונים. לא לסובב. לא לשכתב היסטוריה בגללם.

| סוג | ערך | איפה | קומיט | תאריך | ב-HEAD? |
|---|---|---|---|---|---|
| Telegram placeholder | `YOUR_BOT_TOKEN` | `config.py` | `f8596701d28502cff856cfb0ae7b9b2f70e5fe21` | 2024-11-26 | לא. נמחק ב-`fc891ec25e4082f04650aa7a97068dde1ad03d81` (2026-04-28) |
| Flask placeholder | `your-secret-key` | `config.py` | אותו קומיט | 2024-11-26 | לא |
| Telegram placeholder | `YOUR_BOT_TOKEN_HERE` | `config.example.py` | אותו קומיט, נמחק ב-`05a3ed6a7ec16da047645fe66a049699969e3bd2` | 2024-11-26 → 2026-04-20 | לא |
| Flask placeholder | `your-secret-key-here` | `config.example.py` | אותו דבר | | לא |
| קובץ דוגמה | `TELEGRAM_BOT_TOKEN=` ו-`BOT_TOKEN=` ריקים, `SECRET_KEY=change-me-before-production` | `.env.example`, `README.md` | מ-`05a3ed6` והלאה | 2026-04-20 | כן, עדיין ריק / placeholder |
| סיסמת בדיקה | `secret-secret` | `tests/test_updates.py` | `81acbb768d94d51f29ea6e8a9e362839951fba90` | 2026-10-23 | לא ב-`main`. הענף `cursor/version-update-6128` |
| טוקן בדיקה | `ghp_SUPERSECRET`, `ghp_FROM_BROWSER` (קצרים מכדי להיות PAT אמיתי) | `tests/test_updates.py` | אותו קומיט | 2026-10-23 | לא ב-`main` |
| סיסמת מנהל | `ADMIN_PASSWORD=` ריק. ב-README: `בחרו-סיסמה-ארוכה` | `.env.example`, `README.md` | `81acbb7`, הוסר ב-`602b214432fa0e577849f81b0d4763b4c547676f` | 2026-10-23 → 2026-10-24 | לא ב-`main` |
| טוקן גיטהאב | `HEB_CAL_GITHUB_TOKEN=` ריק. ב-README: `טוקן-קריאה` | אותו ענף | `81acbb7` | 2026-10-23 | לא ב-`main` |
| iCal בדיקה | `…/private-SECRETVALUE/basic.ics` | `tests/test_gcal_sync.py` | `8022fea29ed8a1a365a0ca86fa6fb74a84b98aba` | 2026-10-23 | לא ב-`main`. הענף `cursor/gcal-ical-sync-5829` |

`.env` אמיתי **מעולם לא נוסף**. `git log --all --full-history` על `.env` מצא רק `.env.example`.  
`NETWORK*.md` **לא קיים** באף קומיט. אין `*.pem` / `*.key` מחוץ ל-`cacert.pem` של certifi בתוך `venv` (חבילת CA ציבורית, לא מפתח פרטי).

### False positives של trufflehog

| Detector | קובץ | למה זה לא סוד |
|---|---|---|
| URI | `tests/test_updates.py:82` | `ghp_SUPERSECRET` מהטבלה למעלה |
| Postgres | `venv/.../alembic`, `sqlalchemy` | `postgresql://user:pass@host` ו-`scott:tiger` מתיעוד הספרייה |
| URI | `venv/.../httpx`, `urllib3` | `username:password@host` בתיעוד |
| Alchemy / Box | `*.dist-info/RECORD` | רצף base64/sha256 שנראה כמו מפתח |

`AIza` היחיד בהיסטוריה הוא תת-מחרוזת של sha256 ב-`Flask_Migrate` RECORD (`…QoAIza7f_…`), בקומיט `f859670`, נמחק עם ה-`venv`.  
`eyJ…` היחיד הוא דוגמת JWT ב-METADATA של itsdangerous, באותו `venv`.  
`192.168.` / `10.` מופיעים רק בדוגמאות של httpx / requests / SQLAlchemy / werkzeug בתוך `venv`.

### מידע אישי בהיסטוריה — לא סוד, כן פרטיות

`data/calendar.db` נכנס בקומיט הראשון ונשאר בכמה בּלוֹבּים (8–17 שורות בטבלת `events`) עד המחיקה.

| | |
|---|---|
| בלוֹבּים | 10 של `data/calendar.db` + `instance/events.db` (0 שורות) |
| קומיט ראשון | `f8596701d28502cff856cfb0ae7b9b2f70e5fe21` 2024-11-26 |
| מחיקה מהעץ | `data/calendar.db` ב-`53566a959bb25faee20ac81b7b89355491ea95c7` (2026-04-26). `instance/events.db` ב-`fc891ec25e4082f04650aa7a97068dde1ad03d81` (2026-04-28) |
| ב-HEAD? | **לא** |
| עמודות | `title`, תאריך, `description`, צבע. אין עמודת token / password / chat id / email |
| תוכן | יומן פיתוח מנובמבר–דצמבר 2024: בדיקות UI, משמרות בוקר/ערב, הערה אחת על מילואים. אין טלפון, אימייל, URL, או טוקן |
| מה לעשות | אין סוד לסובב. אם הטקסט הזה לא צריך להיות ציבורי — שכתוב היסטוריה **לפני** פתיחת הריפו. אחרת הוא יישאר ניתן לשליפה גם אחרי המחיקה מהעץ. הערכים לא מצוטטים כאן |

### `venv` בהיסטוריה — נפח, לא סוד

הקומיט הראשון ארז `venv/Lib/site-packages` (כולל `python-telegram-bot`). ירד מהעץ ב-`fa12350165bfc78668d8d19fd5b94d2ed11679fa` (2026-04-20) וב-`fc891ec` (2026-04-28). לא ב-HEAD. נשאר בהיסטוריה ולכן רוב נפח הריפו (~60MB ב-GitHub) הוא הספרייה הזו. אין שם מפתח פרטי או טוקן.

## Tags and releases / תגיות וגרסאות

**אין.**

- `git tag -l` ריק
- `git ls-remote --tags origin` ריק
- GraphQL: `refs(refPrefix: "refs/tags/")` ריק, `releases` ריק
- `gh release list` ריק

קובץ `VERSION` עם התוכן `1.0.0` קיים רק על הענף שלא ממוזג `cursor/version-update-6128` (מ-`81acbb7`, 2026-10-23). **אין** `VERSION` ב-`main`.

## Hardening / חיזוק, לא דליפה

ב-HEAD, `app/__init__.py` נופל ל-`SECRET_KEY` קבוע אם אין משתנה סביבה:

```python
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
```

זו לא סיסמה שדלפה. המחרוזת כבר ציבורית בקוד. אם שרת רץ בלי `SECRET_KEY` אמיתי ב-`.env` (שכבר ב-`.gitignore`), עוגיות החתימה ניתנות לזיוף. להגדיר ערך אקראי ב-`.env` המקומי לפני חשיפה של שרת. לא לגעת בהיסטוריה בשביל זה.

`.gitignore` כבר מתעלם מ-`.env`, `.env.*` (חוץ מ-`.env.example`), `config.py`, `*.db`, `instance/`.  
`NETWORK.local.md` לא מופיע ב-gitignore. אם יוצרים קובץ כזה אחר כך, הוא עלול להיכנס בקומיט. שורה אפשרית: `NETWORK.local.md`. לא שונתה כאן.

## Remediation / מה לעשות

1. **לא לסובב** טוקן טלגרם, מפתח גוגל, או סיסמת מנהל בגלל הגיט — לא נמצא ערך אמיתי.
2. **אפשר לפתוח את הריפו** מבחינת סודות.
3. **לפני פתיחה, להחליט על היומן הישן.** אם המשפטים מ-2024 צריכים להישאר פרטיים — `git filter-repo` (או BFG) על `data/calendar.db` ו-`instance/events.db`, ואז force-push. זה שובר כל SHA. לעשות את זה רק במודע, לא מתוך האודיט הזה.
4. אותו שכתוב יכול גם לזרוק את `venv/` ולכווץ את הריפו. לא חובה בשביל אבטחה.
5. אחרי force-push, GitHub עדיין יכול להחזיק את האובייקטים הישנים זמן מה. לפתוח כרטיס תמיכה אם צריך מחיקה מיידית. כאן אין סוד, אז זה לא דחוף.
6. לשים `SECRET_KEY` אמיתי ב-`.env` של כל שרת שרץ.
7. לא להדביק כתובת iCal סודית או `TELEGRAM_BOT_TOKEN` לקומיט כשממזגים את ענפי היומן והעדכון.

## What this scan did not do / מה לא נעשה

- לא נקרא `.env` מקומי (אין כזה בעותק הזה; הקובץ ב-gitignore).
- לא נסרקו GitHub Actions secrets או משתני סביבה של שרת — הם לא בגיט.
- לא נכתבה היסטוריה מחדש.
- לא שונה קוד האפליקציה.
