from datetime import datetime, timedelta
import calendar
from .jewish_calendar import JewishCalendarService

class CalendarService:
    @staticmethod
    def get_calendar_data(year, month):
        # קבלת לוח השנה הלועזי
        cal = calendar.monthcalendar(year, month)
        
        # קבלת שם החודש בעברית
        month_name = calendar.month_name[month]
        
        # יצירת מערך התאריכים
        calendar_data = []
        for week in cal:
            for day in week:
                if day == 0:
                    calendar_data.append({
                        'gregorian_day': None,
                        'hebrew_day': None,
                        'hebrew_month': None,
                        'is_hebrew_month_start': False
                    })
                else:
                    date_obj = datetime(year, month, day)
                    hebrew_date = JewishCalendarService.get_hebrew_date(date_obj)
                    hebrew_parts = hebrew_date.split()
                    
                    calendar_data.append({
                        'gregorian_day': day,
                        'hebrew_day': int(hebrew_parts[0]),
                        'hebrew_month': hebrew_parts[1],
                        'is_hebrew_month_start': int(hebrew_parts[0]) == 1
                    })
        
        # קבלת התאריך העברי של תחילת וסוף החודש
        first_day = datetime(year, month, 1)
        last_day = datetime(year, month, calendar.monthrange(year, month)[1])
        hebrew_first = JewishCalendarService.get_hebrew_date(first_day)
        hebrew_last = JewishCalendarService.get_hebrew_date(last_day)
        
        # חילוץ שנה עברית
        hebrew_year = hebrew_first.split()[-1]
        
        # חילוץ חודשים עבריים ייחודיים
        hebrew_months = []
        current_month = None
        for date_data in calendar_data:
            if date_data['hebrew_month'] and date_data['hebrew_month'] != current_month:
                current_month = date_data['hebrew_month']
                hebrew_months.append(current_month)
        
        return {
            'calendar': calendar_data,
            'month_name': month_name,
            'hebrew_months': hebrew_months,
            'hebrew_year': hebrew_year
        } 