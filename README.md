# HEB-CAL

אפליקציית Flask ללוח שנה עברי עם CRUD לאירועים אישיים.

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

`HEB_CAL_UPDATE_MODE=auto` בוחר `docker` אם קיים `/.dockerenv` או ש-`HEB_CAL_DOCKER=1`. אחרת `git`.

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

## מצב נוכחי

- בסיס הנתונים הוא SQLite מקומי. טבלאות התזכורות נוצרות בהפעלה אם הן חסרות.
- ממשק הווב פעיל.
- שליחת טלגרם רצה רק כשמפעילים את ה-worker, עם `TELEGRAM_BOT_TOKEN`.
- קבצי Alembic היסטוריים כרגע לא מייצגים את סכמת ה־DB בפועל.
