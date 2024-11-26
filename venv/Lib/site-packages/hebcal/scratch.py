from util.sun import Sun
from datetime import datetime
from datetime import timedelta


s = Sun(datetime.now(), (40.092383, -74.219996), timezone='America/New_York')
s.observer.horizon = 0
print(s.observer.horizon)
print(s.observer.next_rising(s.sun))

s.observer.horizon = '-16.1'
print(s.observer.next_rising(s.sun, use_center=True).datetime() - timedelta(hours=4))

s.observer.horizon = '-11'
print(s.observer.next_rising(s.sun, use_center=True).datetime() - timedelta(hours=4))