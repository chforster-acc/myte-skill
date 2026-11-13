"""Tests for the daily limit check in preview (synthetic entries only)."""

from preview import days_over_limit


def entry(date, hours, action='enter'):
    return {'date': date, 'hours': hours, 'action': action}


def test_day_above_limit_is_reported_with_total():
    entries = [entry('10.11.', 7.61), entry('10.11.', 2.50)]
    assert days_over_limit(entries) == {'10.11.': 10.11}


def test_day_exactly_at_limit_is_not_reported():
    entries = [entry('10.11.', 7.50), entry('10.11.', 2.50)]
    assert days_over_limit(entries) == {}


def test_float_noise_at_limit_is_not_reported():
    entries = [entry('10.11.', 3.3), entry('10.11.', 3.3), entry('10.11.', 3.4)]
    assert days_over_limit(entries) == {}


def test_skipped_and_unclear_entries_do_not_count():
    entries = [entry('01.11.', 7.70, 'skip'), entry('01.11.', 5.0, 'unclear'),
               entry('01.11.', 5.0)]
    assert days_over_limit(entries) == {}


def test_days_are_summed_separately():
    entries = [entry('03.11.', 9.43), entry('04.11.', 9.0), entry('04.11.', 1.5)]
    assert days_over_limit(entries) == {'04.11.': 10.5}


def test_custom_limit():
    assert days_over_limit([entry('02.11.', 8.0)], limit=7.7) == {'02.11.': 8.0}
