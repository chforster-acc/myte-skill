"""Tests for the classification logic in parse_timereport.

Only synthetic day dicts — real time report PDFs contain personal data and stay out of the repo.
"""

import pytest

from parse_timereport import (
    arzt_hours,
    calc_arzt_hours_for_day,
    classify_entries,
    is_feiertag,
    is_pure_number,
    is_time,
    parse_decimal,
    parse_time_h,
)


def day(date='01.10.', ist=0.0, glz=0.0, main_text='', blocks=None):
    return {'date': date, 'ist': ist, 'soll': 7.7, 'glz': glz,
            'main_text': main_text, 'blocks': blocks or []}


def block(beginn, ende, text):
    return {'beginn': beginn, 'ende': ende, 'text': text, 'erf': 0.0}


def classify(d):
    return [(e['charge_code'], e['hours'], e['action']) for e in classify_entries({d['date']: d})]


# --- Helpers ---

@pytest.mark.parametrize('raw, expected', [
    ('7,70', 7.7),
    ('-0,82', -0.82),
    ('1.234,50', 1234.5),
    ('abc', None),
])
def test_parse_decimal(raw, expected):
    assert parse_decimal(raw) == expected


@pytest.mark.parametrize('raw, expected', [
    ('08:00', 8.0),
    ('9:30', 9.5),
    (' 17:15 ', 17.25),
    ('8.00', None),
    ('', None),
])
def test_parse_time_h(raw, expected):
    assert parse_time_h(raw) == expected


def test_is_time_and_is_pure_number():
    assert is_time('07:05')
    assert not is_time('7,05')
    assert is_pure_number('-0,82')
    assert not is_pure_number('0.82')
    assert not is_pure_number('4,82 Teleworking')


@pytest.mark.parametrize('text', ['Teleworking', ' teleworking ', 'Gleitzeit lfd.', '', 'Arztbesuch'])
def test_known_texts_are_not_feiertag(text):
    assert not is_feiertag(text)


@pytest.mark.parametrize('text', ['Tag der Deutschen Einheit', 'Allerheiligen'])
def test_unknown_texts_are_feiertag(text):
    assert is_feiertag(text)


# --- Arzt-Berechnung ---

@pytest.mark.parametrize('beginn, ende, expected', [
    ('09:00', '11:00', 2.0),     # fully inside the morning window
    ('07:00', '09:00', 1.0),     # clipped at 08:00
    ('11:00', '15:00', 2.0),     # 11–12 plus 14–15, lunch gap does not count
    ('12:00', '14:00', 0.0),     # entirely in the gap
    ('07:00', '17:00', 6.0),     # both windows in full
    ('10:00', '10:00', 0.0),
    ('11:00', '10:00', 0.0),     # end before start
    ('xx', '10:00', 0.0),
])
def test_arzt_hours(beginn, ende, expected):
    assert arzt_hours(beginn, ende) == pytest.approx(expected)


def test_arzt_block_is_capped_by_next_block():
    d = day(blocks=[block('08:00', '12:00', 'Arztbesuch'), block('10:00', '17:00', 'Teleworking')])
    assert calc_arzt_hours_for_day(d) == 2.0


def test_arzt_blocks_are_sorted_by_start():
    d = day(blocks=[block('10:00', '17:00', 'Teleworking'), block('08:00', '12:00', 'Arztbesuch')])
    assert calc_arzt_hours_for_day(d) == 2.0


def test_arzt_last_block_is_not_capped():
    d = day(blocks=[block('08:00', '11:00', 'Teleworking'), block('11:00', '15:30', 'Arztbesuch')])
    assert calc_arzt_hours_for_day(d) == 2.5


def test_arzt_block_spanning_both_windows():
    d = day(blocks=[block('10:30', '15:00', 'Arztbesuch')])
    assert calc_arzt_hours_for_day(d) == 2.5


def test_multiple_arzt_blocks_are_summed():
    d = day(blocks=[block('08:00', '09:00', 'Arztbesuch'), block('09:00', '14:00', 'Teleworking'),
                    block('14:00', '15:15', 'Arztbesuch')])
    assert calc_arzt_hours_for_day(d) == 2.25


@pytest.mark.parametrize('minute', range(60))
def test_arzt_keeps_minutes_of_next_block_start(minute):
    # Regression: converting decimal hours back to HH:MM truncated e.g. 10:01 to 10:00
    d = day(blocks=[block('08:00', '12:00', 'Arztbesuch'),
                    block(f'10:{minute:02d}', '17:00', 'Teleworking')])
    assert calc_arzt_hours_for_day(d) == round(2 + minute / 60, 2)


# --- Klassifizierung ---

def test_regular_workday_uses_user_code():
    assert classify(day(ist=8.15, main_text='Teleworking')) == [('USER_DEFINED', 8.15, 'enter')]


def test_office_day_has_empty_text():
    assert classify(day(ist=8.0, main_text='')) == [('USER_DEFINED', 8.0, 'enter')]


def test_empty_day_is_dropped():
    assert classify(day()) == []


def test_feiertag_is_skipped():
    assert classify(day(ist=7.7, main_text='Allerheiligen')) == [('515B01', 7.7, 'skip')]


def test_krankheit():
    assert classify(day(ist=7.7, main_text='Krankheit')) == [('706B01', 7.7, 'enter')]


def test_erholungsurlaub():
    assert classify(day(ist=7.7, main_text='Erholungsurlaub')) == [('517B01', 7.7, 'enter')]


def test_negative_glz_adds_513b01():
    assert classify(day(ist=6.89, glz=-0.82, main_text='Teleworking')) == [
        ('USER_DEFINED', 6.89, 'enter'),
        ('513B01', 0.82, 'enter'),
    ]


def test_full_day_gleitzeit_has_only_513b01():
    assert classify(day(ist=0.0, glz=-7.7, main_text='Gleitzeit lfd.')) == [('513B01', 7.7, 'enter')]


def test_arztbesuch_splits_work_and_doctor():
    d = day(ist=8.0, main_text='Teleworking',
            blocks=[block('08:00', '10:00', 'Arztbesuch'), block('10:00', '16:00', 'Teleworking')])
    assert classify(d) == [('USER_DEFINED', 6.0, 'enter'), ('706B02', 2.0, 'enter')]


def test_arztbesuch_with_negative_glz():
    d = day(ist=7.0, glz=-0.7, main_text='Teleworking',
            blocks=[block('08:00', '09:00', 'Arztbesuch'), block('09:00', '15:00', 'Teleworking')])
    assert classify(d) == [
        ('USER_DEFINED', 6.0, 'enter'),
        ('706B02', 1.0, 'enter'),
        ('513B01', 0.7, 'enter'),
    ]


def test_arztbesuch_only_day():
    d = day(ist=2.0, main_text='Arztbesuch', blocks=[block('08:00', '10:00', 'Arztbesuch')])
    assert classify(d) == [('706B02', 2.0, 'enter')]


def test_arztbesuch_wins_over_feiertag_text():
    d = day(ist=8.0, main_text='Allerheiligen',
            blocks=[block('08:00', '10:00', 'Arztbesuch'), block('10:00', '16:00', 'Teleworking')])
    assert classify(d) == [('USER_DEFINED', 6.0, 'enter'), ('706B02', 2.0, 'enter')]


@pytest.mark.parametrize('text', ['Dienstreise', 'Mitfahrer'])
def test_known_text_without_rule_is_unclear(text):
    assert classify(day(ist=8.0, main_text=text)) == [('???', 8.0, 'unclear')]
