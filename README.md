# HEB-CAL

אפליקציית Flask ללוח שנה עברי עם CRUD לאירועים אישיים.

## התקנה לבית עם Docker

בלי Python על המחשב. מתאים ללינוקס ול-Windows. התמונה יורדת מוכנה מ-`ghcr.io/pilpel1/heb-cal` — לא בונים אותה אצלכם. צריך Docker שכבר מותקן ורץ: בלינוקס Docker Engine עם Compose (`docker compose version` עובד), וב-Windows [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/).

התמונה שנבנית ב-GitHub היא `linux/amd64` (מחשב רגיל, ו-Windows על מעבד כזה). Raspberry Pi ומחשב ARM לא נכללים בגרסה הזו.

היומן נפתח על המחשב הזה: `http://127.0.0.1:5000`. אין סיסמה חדשה. Tailscale, אם משתמשים בו, נשאר על המחשב — לא בתוך Docker.

הסקריפט בודק ש-Docker רץ, יוצר `.env` עם `SECRET_KEY` אקראי אם אין קובץ (המפתח לא מודפס), מושך את התמונה, ומעלה את האפליקציה ואת התזכורות. אם יש בוט, אחרי זה עורכים `TELEGRAM_BOT_TOKEN` ב-`.env` ומריצים `docker compose up -d`. אחרי עלייה מוצלחת, במסוף אינטראקטיבי, הסקריפט מציע (אופציונלי) Tailscale Serve על המארח. בלי Tailscale ההתקנה ממשיכה.

### Linux

```bash
git clone https://github.com/pilpel1/HEB-CAL.git
cd HEB-CAL
chmod +x install.sh
./install.sh
```

אחרי אתחול המחשב:

- אם יש `sudo` ויש `docker.service`, נוצרת יחידת systemd בשם `heb-cal.service`. היא עולה אחרי Docker ומריצה `docker compose up -d`. גם קונטיינר שנעצר ביד חוזר בהפעלה הבאה.
- בלי `sudo`, או ב-Docker rootless / בלי systemd, נשארת המדיניות `restart: unless-stopped` מ-`docker-compose.yml`. Docker מחזיר קונטיינר שלא נעצר ביד, בתנאי ש-Docker עצמו עולה עם המחשב.

### Windows

בלי Git: ב-GitHub לחצו Code → Download ZIP, חלצו, ולחצו פעמיים על `Install.bat`.

עם Git:

```powershell
git clone https://github.com/pilpel1/HEB-CAL.git
cd HEB-CAL
.\Install.bat
```

אפשר גם, מתוך התיקייה:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

אחרי כניסה למשתמש (לא לפני שמישהו מתחבר ל-Windows):

- משימה ב-Task Scheduler בשם `HEB-CAL` מפעילה את Docker Desktop אם הוא כבוי, מחכה לו, ומריצה `docker compose up -d`.
- אם אין כבר הפעלה אוטומטית, הסקריפט מוסיף את Docker Desktop לכניסה למשתמש.
- קונטיינר שרץ ולא נעצר ביד חוזר גם דרך `restart: unless-stopped`, ברגע שהמנוע של Docker עלה.

לוג קצר של העלייה אחרי אתחול: `logs\boot.log`.

### Tailscale Serve (אופציונלי)

Tailscale רץ על המחשב, לא בקונטיינר. ההתקנה לא דורשת אותו. אחרי שהיומן עלה, `install.sh` / `install.ps1` מציעים להגדיר Serve.

אם HTTPS 443 (נתיב `/`) כבר משרת משהו אחר — למשל רמקול על פורט 8765 — היומן **לא** מחליף אותו ולא מריץ `tailscale serve reset`. הוא מוסיף HTTPS בפורט 8443 (אפשר להחליף עם `HEB_CAL_TAILSCALE_HTTPS_PORT`):

```text
https://vostro.<tailnet>.ts.net/        → רמקול, פורט מקומי 8765 (נשאר)
https://vostro.<tailnet>.ts.net:8443/   → HEB-CAL, פורט מקומי 5000
```

אם 443 פנוי, אפשר Serve על `/` (443) במקום 8443. MagicDNS root נשאר לשאר האפליקציות כשהן כבר תופסות אותו.

בלי הרשאה בלינוקס, פעם אחת:

```bash
sudo tailscale set --operator=$USER
tailscale serve --bg --https=8443 http://127.0.0.1:5000
```

בלי מסוף אינטראקטיבי הסקריפט מדלג ומדפיס את הפקודות. `HEB_CAL_TAILSCALE_SERVE=1` מגדיר בלי שאלה, `=0` מדלג.

### עדכון

בתיקייה של `docker-compose.yml`:

```bash
docker compose pull && docker compose up -d
```

זו אותה פקודה שהמסך «עדכון גרסה» מראה בהתקנת Docker.

### התמונה ב-GitHub (פעם אחת, לבעל המאגר)

`.github/workflows/docker.yml` בונה ודוחף ל-`ghcr.io/pilpel1/heb-cal` בעלייה ל-`main`, בתג `v*.*.*`, ובפרסום Release. ההתחברות היא `GITHUB_TOKEN` עם הרשאת `packages: write`. אין סוד נוסף להגדיר ב-Actions.

חבילה חדשה ב-GHCR נוצרת פרטית. פעם אחת: GitHub → הפרופיל → Packages → `heb-cal` → Package settings → Change visibility → Public. בלי זה `docker pull` מהבית נכשל.

אחרי מיזוג של `1.0.7` צריך גם תג `v1.0.7` (Release ב-GitHub) כדי שמסך «עדכון גרסה» יראה אותה. ה-workflow לא יוצר את ה-Release בעצמו.

## דרישות

- Python 3.12+
- מאומת בפיתוח על Ubuntu ב־`WSL2`
- אמור לעבוד גם על Windows עם `venv` תקין ו־Python תואם

## סביבת הרצה

הפרויקט פותח ונבדק בפועל מתוך `WSL`/`Linux`, וזה מסלול הפיתוח המומלץ כרגע.

- ברמת הקוד אין כאן תלות מהותית בלינוקס, ולכן ההתקנה אמורה לעבוד גם על Windows.
- ההבדל העיקרי הוא בפקודות של הסביבה הווירטואלית ובנתיבי הקבצים.
- בפיתוח השוטף של הפרויקט הזה אנחנו מתמקדים ב־`WSL`, ולכן הדוגמאות במסמך משתמשות בפקודות Linux.
- כן אפשר לפתוח את הממשק מהדפדפן של Windows מול שרת שרץ ב־`WSL`.

## התקנה

ב־`WSL` / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

ב־Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## קונפיגורציה

צור קובץ `.env` לפי `.env.example`.

דוגמה:

```env
DATABASE_PATH=data/calendar.db
SECRET_KEY=change-me-before-production
FLASK_DEBUG=1
TELEGRAM_BOT_TOKEN=
REMINDER_TIMEZONE=Asia/Jerusalem
REMINDER_DEFAULT_TIME=09:00
REMINDER_POLL_SECONDS=45
BOT_TOKEN=
HEB_CAL_RESTART_COMMAND=
HEB_CAL_UPDATE_MODE=auto
HEB_CAL_GITHUB_REPO=
HEB_CAL_GITHUB_TOKEN=
HEB_CAL_UPDATE_AUTOCHECK=1
```

`TELEGRAM_BOT_TOKEN` הוא הטוקן היחיד שה-worker קורא. `BOT_TOKEN` נשאר שמור ולא בשימוש. לא לשמור טוקן אמיתי בגיט. `HEB_CAL_GITHUB_TOKEN`, אם צריך אותו למאגר פרטי, נשאר רק ב-`.env`.

## הרצה

ב־`WSL` / Linux:

```bash
source .venv/bin/activate
python -m flask --app app run
```

או:

```bash
source .venv/bin/activate
python app/main.py
```

ב־Windows, השתמש באותן פקודות הרצה אחרי אקטיבציה דרך:

```bash
.venv\Scripts\activate
```

## תזכורות

בטופס האירוע מסמנים «תזכורת», בוחרים מתי (כולל «אחר»), ואת מי להזכיר. אנשים ומזהה הצ׳אט שלהם מנוהלים ב־`/settings` («אנשים לתזכורות»).

אירוע בלי שעה נחשב כ־`REMINDER_DEFAULT_TIME` (ברירת מחדל 09:00) באזור `REMINDER_TIMEZONE` (ברירת מחדל `Asia/Jerusalem`). אין עדיין חזרות: התזכורת חלה על תאריך האירוע. כשיתווסף מודל חזרה, נקודת ההרחבה היא `occurrence_start` ב־`app/reminders/schedule.py`.

### Worker (טלגרם)

```bash
python scripts/reminder_worker.py
```

סבב אחד בלי לולאה: `python scripts/reminder_worker.py --once`.

כל 30–60 שניות (ברירת מחדל 45) ה-worker שולח תזכורות שהמועד שלהן עבר ועדיין לא נשלחו, דרך Bot API. אותה לולאה עונה ל־`/start` עם מזהה הצ׳אט — מעתיקים את המספר לעמוד האנשים.

אותו תהליך מושך גם יומן גוגל (אם חיברתם כתובת iCal בהגדרות), בערך כל 15 דקות (`GCAL_SYNC_SECONDS`, ברירת מחדל 900).

### יומן גוגל (חד-כיווני)

בהגדרות, «חיבור ליומן גוגל»: מדביקים את הכתובת הסודית בפורמט iCal (בלי חשבון Google Cloud ובלי OAuth). אפשר כמה יומנים, עם שם וצבע. «סנכרן עכשיו» מושך מיד. אירוע שהגיע מגוגל אי אפשר לערוך כאן.

הכתובת נשמרת רק בבסיס. היא לא נכתבת ללוג, לא חוזרת לממשק (אחרי שמירה רואים מסכה), ולא שמים כתובת אמיתית בגיט.

בלי טלגרם מריצים רק את סנכרון היומן:

```bash
python scripts/gcal_sync_worker.py
```

סבב אחד: `python scripts/gcal_sync_worker.py --once`.

החלון הוא בערך חצי שנה אחורה וקצת יותר משנה קדימה (`GCAL_SYNC_PAST_DAYS` / `GCAL_SYNC_FUTURE_DAYS`). אירוע ישן יותר שנמשך בעבר נשאר. סנכרון דו-כיווני (מכאן אל גוגל) לא כלול — הוא דורש OAuth.

### התראות בדפדפן

כשהאפליקציה פתוחה (אנדרואיד או מחשב) היא שואבת את `GET /api/reminders/due` ומציגה `Notification`. זה לא עובד כשהדפדפן סגור. Web Push ברקע דורש HTTPS ו־PWA ומיועד להתווסף אחר כך על אותו payload (`title`, `body`, `tag`), בלי לשנות את חישוב ה-offset.

## עדכון גרסה

הגרסה המותקנת כתובה ב-`VERSION` (למשל `1.0.0`). יומן קצר בעברית: `CHANGELOG.md`. «יש עדכון» נקבע לפי release או tag ב-GitHub, לא לפי הקובץ המקומי. תג של גרסה נראה כמו `v1.2.0` או `1.2.0`, והשורות הראשונות בגוף ה-release הן מה שמופיע במסך.

בהגדרות רואים את הגרסה, כפתור «בדוק עדכונים», ואם יש חדשה — המספר, עיקרי השינויים, וכפתור אחד: «עדכן עכשיו». בדיקה אוטומטית פעם ביום (אפשר לכבות עם `HEB_CAL_UPDATE_AUTOCHECK=0`) מדליקה נקודה כתומה על גלגל השיניים. הנקודה לא מתקינה כלום.

### מי יכול ללחוץ

כל מי שכבר משתמש בלוח של הבית הזה. אין סיסמה נפרדת לעדכון. «בדוק עדכונים» ו«עדכן עכשיו» נשלחים עם אסימון שנשמר בעוגייה של הדפדפן (CSRF), כדי שאתר אחר לא יוכל ללחוץ במקומכם. אי אפשר לשלוח מהבקשה פקודת מסוף, נתיב, או טוקן — השרת מתעלם מהם. הפקודה עצמה נשארת ב-`.env`.

### מה קורה בלחיצה על «עדכן עכשיו»

נפתח תהליך נפרד, והוא נשאר בחיים גם כשהאפליקציה יורדת. המסך בהגדרות שואל כל שנייה וחצי איפה זה עומד, ומרענן כשנגמר.

1. גיבוי של קובץ ה-SQLite לתיקייה `backups/` (אפשר להחליף עם `HEB_CAL_BACKUP_DIR`).
2. הורדת התג מ-GitHub ב-HTTPS, ומעבר אליו. רק אם אין שינויים מקומיים בקוד, ורק אם התג הוא המשך ישיר (fast-forward). אין `reset --hard`.
3. `pip install -r requirements.txt`
4. מיגרציות (אותן מיגרציות שרצות בהפעלה).
5. הפעלה מחדש לפי `HEB_CAL_RESTART_COMMAND`.
6. בדיקה ש-`HEB_CAL_HEALTH_URL` עונה, ושהגרסה שם היא הגרסה החדשה.

אם משהו נכשל אחרי שכבר נגענו בקוד או במסד: חוזרים לקומיט הקודם, מתקינים שוב את החבילות הישנות, עוצרים את האפליקציה, משחזרים את מסד הנתונים מהגיבוי, ומפעילים מחדש. במסך מופיעה הודעה בעברית. הגיבוי נשאר בתיקייה גם כשהחזרה הצליחה.

ההורדה לא משתמשת ב-remote של git (לפעמים שמור בו טוקן בכתובת). היא פונה אל `https://github.com/owner/name.git`. עותק shallow (`--depth 1`) נחסם — צריך clone מלא.

בשרת הבית שמים `FLASK_DEBUG=0`. רילודר של פיתוח קם באמצע החלפת קבצים ומבלבל את הבדיקה.

### שרת בבית, בלי systemd ובלי sudo

מעתיקים את `scripts/restart.example.sh` לשם אחר, מתאימים פורט אם צריך, ונותנים הרשאת הרצה:

```bash
cp scripts/restart.example.sh scripts/restart.sh
chmod +x scripts/restart.sh
```

ב-`.env`, נתיב יחסי לשורש הפרויקט, או נתיב מלא:

```env
HEB_CAL_RESTART_COMMAND=scripts/restart.sh
```

נתיב שמתחיל ב-`/` (למשל `/home/you/HEB-CAL/scripts/restart.sh`) נשאר כמו שהוא. נתיב יחסי כמו `scripts/restart.sh` מחובר לשורש הפרויקט בזמן הריצה, לא לפי התיקייה שממנה הפעלתם את פלאסק.

הסקריפט חייב לצאת אחרי שהתהליכים עלו. הוא לא נשאר בחזית. כשהעדכון משחזר גיבוי הוא מריץ את אותה פקודה עם `HEB_CAL_UPDATE_ACTION=stop` — הדוגמה אז רק עוצרת. אחר כך היא רצה שוב בלי המשתנה הזה ומעלה את האפליקציה ואת worker התזכורות.

### מאגר פרטי

```env
HEB_CAL_GITHUB_REPO=owner/name
HEB_CAL_GITHUB_TOKEN=טוקן-קריאה
```

בלי טוקן משתמשים ב-API הציבורי. הטוקן נשלח רק ככותרת ל-GitHub ול-`git fetch`, לא כארגומנט בשורת הפקודה, ולא נכתב לקובץ המצב או ללוג.

### Docker, או סקריפט משלכם

ההתקנה עצמה מתוארת ב«הרצה ב-Docker» למטה. `HEB_CAL_RESTART_COMMAND` הוא להרצה בלי Docker.

`HEB_CAL_UPDATE_MODE=auto` בוחר `docker` אם קיים `/.dockerenv` או ש-`HEB_CAL_DOCKER=1`. אחרת `git`. ב-`docker compose` המצב קבוע על `docker`.

במצב Docker המסך לא עושה checkout. אם יש גרסה חדשה הוא מראה:

```text
docker compose pull && docker compose up -d
```

אפשר אחר כך לחבר סקריפט. `HEB_CAL_UPDATE_HOOK` הוא נתיב מלא לקובץ ניתן להרצה, בלי רווחים ובלי ארגומנטים (ארגומנטים שמים בתוך הסקריפט). הממשק רק מפעיל את הקובץ הזה, אחרי גיבוי, עם משתנה `HEB_CAL_TARGET_VERSION`. הפקודה עצמה לא מגיעה מהדפדפן.

```env
HEB_CAL_UPDATE_MODE=hook
HEB_CAL_UPDATE_HOOK=/home/you/HEB-CAL/scripts/update-hook.sh
```

במצב `docker` עם hook מוגדר מופיעים גם המשפט על `docker compose` וגם הכפתור, שמריץ את הסקריפט.

`HEB_CAL_UPDATE_MODE=off` משאיר את מספר הגרסה ומכבה את העדכון.

## הרצה ב-Docker

התקנה מוכנה לבית (מושכת תמונה, בלי לבנות מהקוד): «התקנה לבית עם Docker» למעלה. הפקודות כאן הן להרצה ידנית מתוך העותק.

אותה תמונה רצה על שרת בית, על Windows (Docker Desktop), או על ענן קטן. צריך Docker עם Compose. אין צורך ב-Python על המארח, ואין צורך בפורט פתוח לאינטרנט.

בתוך הקונטיינר האפליקציה מאזינה על `0.0.0.0:5000`. על המארח הפורט נפתח רק על `127.0.0.1` (`HEB_CAL_BIND_HOST` / `HEB_CAL_PORT` ב-`.env.example`).

```bash
cp .env.example .env
```

ב-Windows (PowerShell): `copy .env.example .env`.

עורכים את `.env`: מחליפים את `SECRET_KEY`. `TELEGRAM_BOT_TOKEN` רק אם יש בוט. `BOT_TOKEN` נשאר ריק — ה-worker לא קורא אותו. `HEB_CAL_RESTART_COMMAND` נשאר ריק בהתקנת Docker. `DATABASE_PATH` נשאר `data/calendar.db` (התיקייה שמחוברת לקונטיינר, לא נתיב של Windows).

```bash
docker compose up -d --build
```

בדפדפן על אותו מחשב: `http://127.0.0.1:5000`.

הפקודה מעלה שני תהליכים מאותה תמונה:

- `web` — האפליקציה.
- `reminder` — תזכורות טלגרם, תפריט הבוט, וסנכרון יומן גוגל. בלי טלגרם משאירים את `TELEGRAM_BOT_TOKEN` ריק; הסנכרון של היומן ממשיך.

`scripts/gcal_sync_worker.py` הוא אותו סנכרון בלי טלגרם. הוא לא עולה כברירת מחדל, כי `reminder` כבר מריץ אותו. רק בית שלא רוצה את תהליך התזכורות מפעיל את הפרופיל, ואז לא משאירים את `reminder` רץ (אחרת היומן נמשך פעמיים):

```bash
docker compose stop reminder
docker compose --profile gcal up -d --no-deps gcal
```

אחרי שינוי ב-`.env`: `docker compose up -d`.

### גיבוי

עוצרים, מעתיקים את `data/` (קובץ ה-SQLite וגם `-wal` / `-shm` אם קיימים), ומפעילים. הפקודה הזו עובדת גם בלינוקס וגם ב-Windows:

```bash
docker compose stop
docker compose cp web:/app/data ./data-backup
docker compose start
```

אם יש הרשאת קריאה על התיקייה במארח, אפשר גם להעתיק את `data/` ידנית אחרי `docker compose stop`. `logs/` הוא טקסט שאפשר למחוק כשהקונטיינרים כבויים. `backups/` שמור לגיבוי שירוץ מתוך הקונטיינר.

### עדכון

בקונטיינר המצב הוא `HEB_CAL_UPDATE_MODE=docker`. המסך לא מושך git ולא קורא ל-`HEB_CAL_RESTART_COMMAND`. כשיש גרסה חדשה הוא מראה את הפקודה הזו, ומריצים אותה בתיקייה של `docker-compose.yml`:

```bash
docker compose pull && docker compose up -d
```

התמונה היא `ghcr.io/pilpel1/heb-cal:latest`. לפני העדכון מעתיקים את `data/` כמו בגיבוי. אם `pull` נכשל כי החבילה ב-GitHub עדיין לא ציבורית, מעדכנים מהקוד: `git pull` ואז `docker compose up -d --build`.

### Tailscale

Tailscale מותקן על המארח (המחשב, שרת הבית, או הענן) — לא בתוך הקונטיינר, ואין sidecar בקומפוז. משאירים את `HEB_CAL_BIND_HOST=127.0.0.1` כדי לא לפרסם פורט. מחשב אחר באותו tailnet מגיע למארח. HTTPS דרך `tailscale serve` הוא צעד אופציונלי על המארח (`install.sh` / `install.ps1`): אם `/` על 443 כבר תפוס, היומן על `https://<MagicDNS>:8443/` והשורש נשאר לשאר האפליקציות.

## מצב נוכחי

- בסיס הנתונים הוא SQLite מקומי. טבלאות התזכורות נוצרות בהפעלה אם הן חסרות.
- ממשק הווב פעיל.
- שליחת טלגרם רצה רק כשמפעילים את ה-worker, עם `TELEGRAM_BOT_TOKEN`.
- קבצי Alembic היסטוריים כרגע לא מייצגים את סכמת ה־DB בפועל.
