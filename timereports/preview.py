#!/usr/bin/env python3
"""Preview Zeitnachweis PDF entries for one or both periods."""

import os
import sys
import calendar
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_timereport import parse_timereport, classify_entries


def preview(pdf_path, year, month, show_both_periods=True, period_filter=None):
    days = parse_timereport(pdf_path)
    entries = classify_entries(days)
    last_day = calendar.monthrange(year, month)[1]
    all_weekdays = [d for d in range(1, last_day + 1) if date(year, month, d).weekday() < 5]
    covered = {int(e['date'].split('.')[0]) for e in entries}
    missing = [d for d in all_weekdays if d not in covered]

    if period_filter:
        periods = [period_filter]
    else:
        periods = [1, 2]

    for p in periods:
        p_range = range(1, 16) if p == 1 else range(16, last_day + 1)
        end_day = 15 if p == 1 else last_day
        print(f"\n{calendar.month_name[month]} {year} — Periode {p} "
              f"(01.{month:02d}.–{end_day:02d}.{month:02d}.)" if p == 1 else
              f"\n{calendar.month_name[month]} {year} — Periode {p} "
              f"(16.{month:02d}.–{last_day:02d}.{month:02d}.)")
        print(f"{'Datum':<8} {'Text':<22} {'Code':<12} {'Std':>6}  Status")
        print('─' * 66)
        p_entries = [e for e in entries if int(e['date'].split('.')[0]) in p_range]
        for e in p_entries:
            if e['action'] == 'enter':
                marker = '→ eintragen'
            elif e['action'] == 'skip':
                marker = '– skip (Feiertag)'
            else:
                marker = '⚠ UNKLAR'
            code = e['charge_code'] if e['charge_code'] != 'USER_DEFINED' else '[User-Code]'
            print(f"{e['date']:<8} {e['text']:<22} {code:<12} {e['hours']:>5.2f}h  {marker}")

        p_missing = [d for d in missing if d in p_range]
        if p_missing:
            print(f"  ── fehlende Werktage: " +
                  ", ".join(f"{date(year,month,d).strftime('%a')} {d:02d}.{month:02d}." for d in p_missing))

    unclear = [e for e in entries if e['action'] == 'unclear']
    if unclear:
        print('\n⚠ ACHTUNG — nicht zugeordnet:')
        for e in unclear:
            print(f"  {e['date']} {e['text']}: {e['reason']}")


if __name__ == '__main__':
    # Usage: preview.py [MM_YYYY] [periode]
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    period_filter = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if arg:
        month_s, year_s = arg.split('_')
        m, y = int(month_s), int(year_s)
    else:
        t = date.today()
        m, y = t.month, t.year
        period_filter = 2 if t.day > 15 else 1

    pdf = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{m:02d}_{y}.pdf")
    preview(pdf, y, m, period_filter=period_filter)
