import datetime
from calculate_sun import convert_to_local_tz
import pytz


class Greg:
    def __init__(self, **kwargs):
        if 'datetime_object' in kwargs:
            self.parse_datetime_object(kwargs['datetime_object'])

        elif 'datetime_tuple' in kwargs:
            self.parse_datetime_tuple(kwargs['datetime_tuple'])

        else:
            now = datetime.datetime.now()
            if 'year' in kwargs:
                self.year = kwargs['year']
            else:
                self.year = now.year
            if 'month' in kwargs:
                self.month = kwargs['month']
            else:
                self.month = now.month
            if 'day' in kwargs:
                self.day = kwargs['day']
            else:
                self.day = now.day
            if 'hour' in kwargs:
                self.hour = kwargs['hour']
            else:
                self.hour = now.hour
            if 'minute' in kwargs:
                self.minute = kwargs['minute']
            else:
                self.minute = now.minute
            if 'second' in kwargs:
                self.second = kwargs['second']
            else:
                self.second = now.second

        self.datetime = datetime.datetime.strptime(f'{self.year}-' +
                                                   f'{self.month}-' +
                                                   f'{self.day}/' +
                                                   f'{self.hour}:' +
                                                   f'{self.minute}:' +
                                                   f'{self.second}',
                                                   '%Y-%m-%d/%H:%M:%S')
        self.timezone = kwargs['tz']
        self.datetime = self.datetime.astimezone(pytz.timezone(self.timezone))
        # d_object.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(tz))

    def parse_datetime_object(self, d_object):
        self.year = d_object.year
        self.month = d_object.month
        self.day = d_object.day
        self.hour = d_object.hour
        self.minute = d_object.minute
        self.second = d_object.second

    def parse_datetime_tuple(self, datetime):
        self.year = datetime[0]
        self.month = datetime[1]
        self.day = datetime[2]
        self.hour = datetime[3]
        self.minute = datetime[4]
        self.second = datetime[5]


if __name__ == '__main__':
    g = Greg(day=10, hour=10)
    print(g.day)
    print(g.datetime)
