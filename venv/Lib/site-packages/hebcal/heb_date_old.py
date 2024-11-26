from util import sun, proccess_time, location
from convertdate import hebrew
import datetime


class Date:
    def __init__(self, date_time, lat_lon, **kwargs):
        self.lat_lon = lat_lon

        if 'timezone' not in kwargs:
            print('timezone not in kwargs')
            self.timezone = location.get_timezone(self.lat_lon)
        else:
            self.timezone = kwargs['timezone']

        self.date_time = proccess_time.proccess_datetime(date_time,
                                                         timezone=self.timezone)

        self.sun = sun.Sun(self.date_time, self.lat_lon,
                           timezone=self.timezone)

        if self.sun.is_yom():
            self.datetime = self.date_time
        else:
            self.date_time = self.date_time + datetime.timedelta(days=1)

        self.greg_year = int(self.date_time.strftime('%Y'))
        self.greg_month = int(self.date_time.strftime('%m'))
        self.greg_day = int(self.date_time.strftime('%d'))

        self.heb_date = hebrew.from_gregorian(self.greg_year,
                                              self.greg_month,
                                              self.greg_day)
        self.heb_year = self.heb_date[0]
        self.heb_month = self.heb_date[1]
        self.heb_day = self.heb_date[2]
    
    def month_title_english(self):
        titles = ['Nissan',
                  'Iyar',
                  'Sivan',
                  'Tamuz',
                  'Av',
                  'Elul',
                  'Tishrei',
                  'Cheshvon',
                  'Kislev',
                  'Teves',
                  'Shevat']
        if hebrew.leap(self.heb_year):
            titles.append('Adar I')
            titles.append('Adar II')
        else:
            titles.append('Adar')

        return titles[self.heb_month - 1]

    def day_title_aleph_bet(self):
        titles = (' א ב ג ד ה ו ז ח ט י'
                  ' יא יב יג יד טו טז יז יח יט כ '
                  'כא כב כג כד כה כו כז כח כט ל ').split()
        return titles[self.heb_day - 1]


if __name__ == '__main__':
    # d = Date(datetime.datetime.now(), (40.092383, -74.219996))
    # print(d.hebrew_date)
    # print(str(d.date_time + datetime.timedelta(days=1)))
    pass
