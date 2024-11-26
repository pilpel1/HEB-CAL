import ephem
from datetime import datetime
import pytz
from tzwhere import tzwhere
from . import proccess_time as time
# from .util import proccess_time as time
# from .util import location


class Sun:
    """Get the sunrise and sunset of a given date and time

    """

    def __init__(self, date_time, lat_lon, **kwargs):

        # Configure timezone
        if 'timezone' not in kwargs:
            self.timezone = location.get_timezone(lat_lon)
        else:
            self.timezone = kwargs['timezone']

        self.date_time = time.proccess_datetime(date_time,
                                                timezone=self.timezone)

        self.observer = ephem.Observer()
        self.observer.lat = str(lat_lon[0])
        self.observer.lon = str(lat_lon[1])
        self.observer.date = time.convert_datetime_to_utc(self.date_time)

        self.sun = ephem.Sun()

        self.calculate_rise_set()
        self.calculate_alot()

    def calculate_rise_set(self):
        self.next_set_utc = self.observer.next_setting(self.sun).datetime()
        self.next_set = time.convert_datetime_to_local(self.next_set_utc,
                                                       self.timezone)

        self.next_rise_utc = self.observer.next_rising(self.sun).datetime()
        self.next_rise = time.convert_datetime_to_local(self.next_rise_utc,
                                                        self.timezone)

        self.previous_set_utc = self.observer.previous_setting(self.sun).datetime()
        self.previous_set = time.convert_datetime_to_local(self.previous_set_utc,
                                                           self.timezone)

        self.previous_rise_utc = self.observer.previous_rising(self.sun).datetime()
        self.previous_rise = time.convert_datetime_to_local(self.previous_rise_utc,
                                                            self.timezone)
    
    def calculate_alot(self):
        self.observer.horizon = '-16.1'

        self.next_alot_utc = self.observer.next_rising(self.sun,
                                                       use_center=True).datetime()
        self.next_alot = time.convert_datetime_to_local(self.next_alot_utc,
                                                        self.timezone)

        self.previous_alot_utc = self.observer.previous_rising(self.sun,
                                                               use_center=True).datetime()
        self.previous_alot = time.convert_datetime_to_local(self.previous_alot_utc,
                                                            self.timezone)

    def is_yom(self):
        if self.next_rise > self.next_set:
            return True
        else:
            return False

    def today_sunrise(self):
        if self.date_time.strftime('%d') == self.previous_rise.strftime('%d'):
            return self.previous_rise
        elif self.date_time.strftime('%d') == self.next_rise.strftime('%d'):
            return self.next_rise
        else:
            raise Exception("This 'else' shouldn't be possible.")

    def today_sunset(self):
        if self.date_time.strftime('%d') == self.previous_set.strftime('%d'):
            return self.previous_set
        elif self.date_time.strftime('%d') == self.next_set.strftime('%d'):
            return self.next_set
        else:
            raise Exception("This 'else' shouldn't be possible.")
    
    def today_alot_hashachar(self):
        if self.date_time.strftime('%d') == self.previous_alot.strftime('%d'):
            return self.previous_alot
        elif self.date_time.strftime('%d') == self.next_alot.strftime('%d'):
            return self.next_alot
        else:
            raise Exception("This 'else' shouldn't be possible.")


if __name__ == '__main__':
    s = Sun('2018 9 13 2:57 PM', (40.092383, -74.219996))
    print(s.next_rise)
