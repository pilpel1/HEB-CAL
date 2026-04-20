# HEB-CAL

אפליקציית Flask ללוח שנה עברי עם CRUD לאירועים אישיים.

## דרישות

- Python 3.12+

## התקנה

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

בלינוקס / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
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

```bash
python -m flask --app app run
```

או:

```bash
python app/main.py
```

## מצב נוכחי

- בסיס הנתונים הוא SQLite מקומי.
- ממשק הווב פעיל.
- ה־Telegram bot עדיין לא גמור.
- קבצי Alembic היסטוריים כרגע לא מייצגים את סכמת ה־DB בפועל.
