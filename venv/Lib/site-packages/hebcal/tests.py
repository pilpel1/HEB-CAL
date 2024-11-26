import pytest
from __init__ import TimeInfo


ti = TimeInfo('2018, 9, 19, 7:15 pm', timezone='America/New_York',
              latitude=40.092383, longitude=-74.219996)


def test_sunset():
    assert str(ti.today_sunset()) == '2018-09-19 18:59:12.782791-04:00'


if __name__ == '__main__':
    test_sunset()
