from pyluach import dates, parshios, hebrewcal
from datetime import date, timedelta
import calendar

# מילון המרה מאנגלית לעברית
HOLIDAY_TRANSLATIONS = {
    'Rosh Hashana': 'ראש השנה',
    'Yom Kippur': 'יום כיפור',
    'Succos': 'סוכות',
    'Shmini Atzeres': 'שמיני עצרת',
    'Simchas Torah': 'שמחת תורה',
    'Chanuka': 'חנוכה',
    "Tu B'shvat": 'ט"ו בשבט',
    'Purim Katan': 'פורים קטן',
    'Purim': 'פורים',
    'Shushan Purim': 'שושן פורים',
    'Pesach': 'פסח',
    "Lag Ba'omer": 'ל"ג בעומר',
    'Shavuos': 'שבועות',
    "Tu B'av": 'ט"ו באב',
    'Tzom Gedalia': 'צום גדליה',
    '10 of Teves': 'עשרה בטבת',
    'Taanis Esther': 'תענית אסתר',
    '17 of Tamuz': 'י"ז בתמוז',
    '9 of Av': 'תשעה באב'
}

# מילון המרה לפרשות השבוע
PARASHA_TRANSLATIONS = {
    'Beraishis': 'בראשית',
    'Noach': 'נח',
    "Lech L'cha": 'לך לך',
    'Vayera': 'וירא',
    'Chayei Sarah': 'חיי שרה',
    'Toldos': 'תולדות',
    'Vayetzei': 'ויצא',
    'Vayishlach': 'וישלח',
    'Vayeshev': 'וישב',
    'Miketz': 'מקץ',
    'Vayigash': 'ויגש',
    'Vayechi': 'ויחי',
    'Shemos': 'שמות',
    "Va'era": 'וארא',
    'Bo': 'בא',
    'Beshalach': 'בשלח',
    'Yisro': 'יתרו',
    'Mishpatim': 'משפטים',
    'Teruma': 'תרומה',
    'Tetzave': 'תצוה',
    'Ki Sisa': 'כי תשא',
    'Vayakhel': 'ויקהל',
    'Pekudei': 'פקודי',
    'Vayikra': 'ויקרא',
    'Tzav': 'צו',
    'Shemini': 'שמיני',
    'Tazria': 'תזריע',
    'Metzora': 'מצורע',
    'Acharei Mos': 'אחרי מות',
    'Kedoshim': 'קדושים',
    'Emor': 'אמור',
    'Behar': 'בהר',
    'Bechukosai': 'בחוקותי',
    'Bamidbar': 'במדבר',
    'Naso': 'נשא',
    "Beha'aloscha": 'בהעלותך',
    'Shelach': 'שלח',
    'Korach': 'קרח',
    'Chukas': 'חקת',
    'Balak': 'בלק',
    'Pinchas': 'פנחס',
    'Matos': 'מטות',
    "Ma'sei": 'מסעי',
    'Devarim': 'דברים',
    "Va'eschanan": 'ואתחנן',
    'Eikev': 'עקב',
    "R'ey": 'ראה',
    'Shoftim': 'שופטים',
    'Ki Setzei': 'כי תצא',
    'Ki Savo': 'כי תבוא',
    'Netzavim': 'נצבים',
    'Vayelech': 'וילך',
    'Haazinu': 'האזינו',
    "V'zos Habrocha": 'וזאת הברכה',
    # פרשות כפולות
    'Vayakhel-Pekudei': 'ויקהל-פקודי',
    'Tazria-Metzora': 'תזריע-מצורע',
    'Acharei Mos-Kedoshim': 'אחרי מות-קדושים',
    'Behar-Bechukosai': 'בהר-בחוקותי',
    'Chukas-Balak': 'חקת-בלק',
    'Matos-Masei': 'מטות-מסעי',
    'Netzavim-Vayelech': 'נצבים-וילך'
}

def translate_parasha(parsha):
    """
    מתרגם את שם הפרשה לעברית. אם אין תרגום, מחזיר את השם המקורי.
    במקרה של פרשה כפולה, מתרגם כל חלק בנפרד ומחבר עם מקף.
    """
    if ',' in parsha:
        # מטפל בפרשות מחוברות (למשל "Tazria, Metzora")
        parts = [part.strip() for part in parsha.split(',')]
        translated_parts = [PARASHA_TRANSLATIONS.get(part, part) for part in parts]
        return '-'.join(translated_parts)
    elif '-' in parsha:
        # מטפל בפרשות מחוברות עם מקף (למשל "Tazria-Metzora")
        parts = [part.strip() for part in parsha.split('-')]
        translated_parts = [PARASHA_TRANSLATIONS.get(part, part) for part in parts]
        return '-'.join(translated_parts)
    else:
        # פרשה רגילה
        return PARASHA_TRANSLATIONS.get(parsha, parsha)

def check_month(year, month):
    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)
    
    current_date = start_date
    while current_date <= end_date:
        greg_date = dates.GregorianDate(current_date.year, current_date.month, current_date.day)
        heb_date = greg_date.to_heb()
        
        print(f"\nתאריך לועזי: {current_date}")
        print(f"תאריך עברי: {heb_date}")
        
        # בדיקת חג
        holiday = hebrewcal.holiday(heb_date)
        if holiday:
            holiday_heb = HOLIDAY_TRANSLATIONS.get(holiday, holiday)
            print(f"חג: {holiday_heb}")
            
        # בדיקת פרשה (רק בשבת)
        if current_date.weekday() == 5:  # שבת
            parsha = parshios.getparsha_string(greg_date)
            if parsha:
                parsha_heb = translate_parasha(parsha)
                print(f"פרשה באנגלית: {parsha}")
                print(f"פרשה בעברית: {parsha_heb}")
        
        current_date += timedelta(days=1)

# בדיקת חודשים שבהם יש פרשות כפולות
print("בדיקת חודש אפריל 2025 (תזריע-מצורע):")
check_month(2025, 4)

print("\nבדיקת חודש מאי 2025 (בהר-בחוקותי):")
check_month(2025, 5) 