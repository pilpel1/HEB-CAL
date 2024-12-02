from pyluach import dates, parshios, hebrewcal
from datetime import date
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# מילון המרה מאנגלית לעברית עם סיווג החג
HOLIDAY_TRANSLATIONS = {
    'Rosh Hashana': {'name': 'ראש השנה', 'type': 'major_holiday'},
    'Yom Kippur': {'name': 'יום כיפור', 'type': 'fast_day'},
    'Succos': {'name': 'סוכות', 'type': 'major_holiday'},
    'Shmini Atzeres': {'name': 'שמיני עצרת', 'type': 'major_holiday'},
    'Simchas Torah': {'name': 'שמחת תורה', 'type': 'major_holiday'},
    'Chanuka': {'name': 'חנוכה', 'type': 'minor_holiday'},
    "Tu B'shvat": {'name': 'ט"ו בשבט', 'type': 'minor_holiday'},
    'Purim Katan': {'name': 'פורים קטן', 'type': 'minor_holiday'},
    'Purim': {'name': 'פורים', 'type': 'major_holiday'},
    'Shushan Purim': {'name': 'שושן פורים', 'type': 'minor_holiday'},
    'Pesach': {'name': 'פסח', 'type': 'major_holiday'},
    "Lag Ba'omer": {'name': 'ל"ג בעומר', 'type': 'minor_holiday'},
    'Shavuos': {'name': 'שבועות', 'type': 'major_holiday'},
    "Tu B'av": {'name': 'ט"ו באב', 'type': 'minor_holiday'},
    'Tzom Gedalia': {'name': 'צום גדליה', 'type': 'fast_day'},
    '10 of Teves': {'name': 'עשרה בטבת', 'type': 'fast_day'},
    'Taanis Esther': {'name': 'תענית אסתר', 'type': 'fast_day'},
    '17 of Tamuz': {'name': 'י"ז בתמוז', 'type': 'fast_day'},
    '9 of Av': {'name': 'תשעה באב', 'type': 'fast_day'}
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
    "V'zos Habrocha": 'וזאת הברכה'
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

class JewishCalendarService:
    @staticmethod
    def get_parasha(date_obj):
        logger.debug(f"Getting parasha for {date_obj}")
        try:
            # המרה לתאריך עברי
            greg_date = dates.GregorianDate(date_obj.year, date_obj.month, date_obj.day)
            logger.debug(f"Created Gregorian date: {greg_date}")
            
            # בדיקה אם זה שבת
            if date_obj.weekday() == 5:  # 5 = שבת
                logger.debug("Date is Shabbat, getting parasha")
                # קבלת פרשת השבוע
                parasha = parshios.getparsha_string(greg_date)
                logger.debug(f"Got parasha: {parasha}")
                if parasha:
                    parasha_heb = translate_parasha(parasha)
                    return {
                        'name': str(parasha_heb),
                        'type': 'parasha',
                        'display_type': 'jewish_calendar',
                        'color': '#4A90E2'
                    }
            return None
        except Exception as e:
            logger.error(f"Error in get_parasha for {date_obj}: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    def get_holidays(date_obj):
        logger.debug(f"Getting holidays for {date_obj}")
        try:
            # המרה לתאריך עברי
            greg_date = dates.GregorianDate(date_obj.year, date_obj.month, date_obj.day)
            heb_date = greg_date.to_heb()
            logger.debug(f"Converted to Hebrew date: {heb_date}")
            
            events = []
            
            # קבלת החגים
            holiday = hebrewcal.holiday(heb_date)
            if holiday:
                holiday_info = HOLIDAY_TRANSLATIONS.get(holiday, {'name': holiday, 'type': 'other'})
                # צבעים שונים לסוגי חגים שונים
                colors = {
                    'major_holiday': '#E74C3C',  # אדום - חגים ראשיים
                    'minor_holiday': '#E74C3C',  # צהוב כהה - חגים משניים (במקום F1C40F)
                    'fast_day': '#8E44AD',       # סגול - צומות
                    'other': '#95A5A6'           # אפור - אחר
                }
                events.append({
                    'name': holiday_info['name'],
                    'type': 'holiday',
                    'holiday_type': holiday_info['type'],
                    'display_type': 'jewish_calendar',
                    'color': colors[holiday_info['type']]
                })
            
            # קבלת ירשת השבוע (רק בשבת)
            if date_obj.weekday() == 5:  # 5 = שבת
                parsha = parshios.getparsha_string(greg_date)
                if parsha:
                    parsha_heb = translate_parasha(parsha)
                    events.append({
                        'name': f"פרשת {parsha_heb}",
                        'type': 'parasha',
                        'display_type': 'jewish_calendar',
                        'color': '#4A90E2'
                    })
            
            logger.debug(f"Got holidays: {events}")
            return events
            
        except Exception as e:
            logger.error(f"Error in get_holidays for {date_obj}: {str(e)}", exc_info=True)
            return []
    
    @staticmethod
    def get_all_jewish_events(date_obj):
        logger.debug(f"Getting all Jewish events for {date_obj}")
        try:
            events = JewishCalendarService.get_holidays(date_obj)
            logger.debug(f"Found events: {events}")
            return events
        except Exception as e:
            logger.error(f"Error in get_all_jewish_events for {date_obj}: {str(e)}", exc_info=True)
            return []
    
    @staticmethod
    def get_hebrew_date(date_obj):
        logger.debug(f"Getting Hebrew date for {date_obj}")
        try:
            # המרה לתאריך עברי
            heb_date = dates.GregorianDate(date_obj.year, date_obj.month, date_obj.day).to_heb()
            result = f"{heb_date.day} {JewishCalendarService.get_hebrew_month_name(heb_date.month)} {heb_date.year}"
            logger.debug(f"Hebrew date: {result}")
            return result
        except Exception as e:
            logger.error(f"Error in get_hebrew_date for {date_obj}: {str(e)}", exc_info=True)
            return ""
    
    @staticmethod
    def get_hebrew_month_name(month):
        hebrew_months = {
            1: 'תשרי',
            2: 'חשון',
            3: 'כסלו',
            4: 'טבת',
            5: 'שבט',
            6: 'אדר',
            7: 'ניסן',
            8: 'אייר',
            9: 'סיון',
            10: 'תמוז',
            11: 'אב',
            12: 'אלול',
            13: 'אדר א׳',
            14: 'אדר ב׳'
        }
        return hebrew_months.get(month, '')