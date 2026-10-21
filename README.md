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
```

`TELEGRAM_BOT_TOKEN` הוא הטוקן היחיד שה-worker קורא. `BOT_TOKEN` נשאר שמור ולא בשימוש. לא לשמור טוקן אמיתי בגיט.

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

### התראות בדפדפן

כשהאפליקציה פתוחה (אנדרואיד או מחשב) היא שואבת את `GET /api/reminders/due` ומציגה `Notification`. זה לא עובד כשהדפדפן סגור. Web Push ברקע דורש HTTPS ו־PWA ומיועד להתווסף אחר כך על אותו payload (`title`, `body`, `tag`), בלי לשנות את חישוב ה-offset.

## מצב נוכחי

- בסיס הנתונים הוא SQLite מקומי. טבלאות התזכורות נוצרות בהפעלה אם הן חסרות.
- ממשק הווב פעיל.
- שליחת טלגרם רצה רק כשמפעילים את ה-worker, עם `TELEGRAM_BOT_TOKEN`.
- קבצי Alembic היסטוריים כרגע לא מייצגים את סכמת ה־DB בפועל.
