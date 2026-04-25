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
BOT_TOKEN=
```

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

## מצב נוכחי

- בסיס הנתונים הוא SQLite מקומי.
- ממשק הווב פעיל.
- ה־Telegram bot עדיין לא גמור.
- קבצי Alembic היסטוריים כרגע לא מייצגים את סכמת ה־DB בפועל.
