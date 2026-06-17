#!/usr/bin/env python3
"""Parse Accenture Zeitnachweis PDF and extract daily time entries for MyTE."""

import re
import json
import sys
from pdfminer.high_level import extract_text

# Ausschlussverfahren: alles was NICHT in dieser Liste steht, ist ein Feiertag
KNOWN_WORK_TEXTS = {
    'teleworking',
    'krankheit',
    'gleitzeit lfd.',
    'dienstreise',
    'mitfahrer',
    'erholungsurlaub',
    'arztbesuch',
    '',          # Leerstring = Präsenzarbeit im Office
}

# Texte die direkt als regulärer Arbeitstag gelten (→ USER_DEFINED)
REGULAR_WORK_TEXTS = {
    'teleworking',
    'gleitzeit lfd.',
    '',
}

# Arzt-Zeitfenster: (von, bis) in Dezimalstunden
ARZT_WINDOWS = [(8.0, 12.0), (14.0, 16.0)]


def parse_decimal(s):
    s = s.strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None

def parse_time_h(s):
    """'HH:MM' → Dezimalstunden (z.B. 9.05 = 09:03)."""
    m = re.match(r'^(\d{1,2}):(\d{2})$', s.strip())
    if not m:
        return None
    return int(m.group(1)) + int(m.group(2)) / 60.0

def is_feiertag(text):
    return text.strip().lower() not in KNOWN_WORK_TEXTS

def is_time(s):
    return bool(re.match(r'^\d{1,2}:\d{2}$', s.strip()))

def is_pure_number(s):
    return bool(re.match(r'^-?\d+,\d+$', s.strip()))

def arzt_hours(beginn_str, ende_str):
    """Berechne Arzt-Stunden als Schnittmenge von [beginn, ende] mit ARZT_WINDOWS."""
    b = parse_time_h(beginn_str)
    e = parse_time_h(ende_str)
    if b is None or e is None or e <= b:
        return 0.0
    total = 0.0
    for w_start, w_end in ARZT_WINDOWS:
        overlap = min(e, w_end) - max(b, w_start)
        if overlap > 0:
            total += overlap
    return round(total, 4)


def parse_timereport(pdf_path):
    """
    Parse PDF und gib ein Dict zurück: {date_str: {ist, soll, glz, blocks}}.
    blocks = Liste aller Zeitblöcke des Tages: [{beginn, ende, text, erf}]
    """
    text = extract_text(pdf_path)
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Alle Records gruppieren (je Zeitblock ein Record)
    records = []
    current = []
    for line in lines:
        if re.match(r'^\d{2}\.\d{2}\.$', line) or re.match(r'^\d{2}\.\d{2}\.\s+(MO|DI|MI|DO|FR|SA|SO)', line):
            if current:
                records.append(current)
            current = [line]
        elif current:
            if line.startswith('SUMME'):
                records.append(current)
                current = []
            else:
                current.append(line)
    if current:
        records.append(current)

    days = {}

    for rec in records:
        if not rec:
            continue

        date_line = rec[0]
        date_m = re.match(r'^(\d{2}\.\d{2}\.)\s*(MO|DI|MI|DO|FR|SA|SO)?\s*(\d{1,2}:\d{2})?', date_line)
        if not date_m:
            continue

        date_str = date_m.group(1)
        beginn_in_date = date_m.group(3)  # Beginn im Datums-String (z.B. "07:00")

        rest = rec[1:]
        idx = 0

        # Day-Tag überspringen falls separat
        if idx < len(rest) and re.match(r'^(MO|DI|MI|DO|FR|SA|SO)$', rest[idx]):
            idx += 1

        # Beginn und Ende extrahieren
        # Hinweis: pdfminer kombiniert manchmal Ende+erf+Text auf einer Zeile
        # z.B. "17:09 10,00 Teleworking" → Ende=17:09, Rest="10,00 Teleworking"
        def extract_time_prefix(s):
            """Gibt (time_str, remainder) zurück falls Zeile mit HH:MM beginnt."""
            m = re.match(r'^(\d{1,2}:\d{2})\s*(.*)', s.strip())
            if m:
                return m.group(1), m.group(2).strip()
            return None, s

        beginn = None
        ende = None
        rest = list(rest)  # mutable copy

        if beginn_in_date:
            beginn = beginn_in_date
            if idx < len(rest):
                t, remainder = extract_time_prefix(rest[idx])
                if t:
                    ende = t
                    if remainder:
                        rest[idx] = remainder  # restlicher Inhalt für nächsten Schritt
                    else:
                        idx += 1
        else:
            if idx < len(rest) and is_time(rest[idx]):
                beginn = rest[idx]
                idx += 1
            if idx < len(rest):
                t, remainder = extract_time_prefix(rest[idx])
                if t:
                    ende = t
                    if remainder:
                        rest[idx] = remainder
                    else:
                        idx += 1

        # Text-Label (evtl. mit erf.-Präfix "4,82 Teleworking")
        text_label = ''
        erf = None
        if idx < len(rest) and not is_pure_number(rest[idx]):
            text_raw = rest[idx]
            erf_m = re.match(r'^(-?\d+,\d+)\s+(.*)', text_raw)
            if erf_m:
                erf = parse_decimal(erf_m.group(1))
                text_label = erf_m.group(2).strip()
            else:
                text_label = text_raw.strip()
            idx += 1
        elif idx < len(rest) and is_pure_number(rest[idx]):
            # Standalone erf-Zahl ohne Text (z.B. Office-Block "3,76" vor dem Ist-Wert)
            erf = parse_decimal(rest[idx])
            idx += 1

        # Ist, Soll, Glz (erste drei Zahlen)
        nums = []
        while idx < len(rest) and len(nums) < 3:
            if is_pure_number(rest[idx]):
                nums.append(parse_decimal(rest[idx]))
            idx += 1

        ist = nums[0] if len(nums) > 0 else 0.0
        soll = nums[1] if len(nums) > 1 else 0.0
        glz = nums[2] if len(nums) > 2 else 0.0

        if ist is None: ist = 0.0
        if glz is None: glz = 0.0

        # In Tages-Struktur einfügen
        if date_str not in days:
            days[date_str] = {'date': date_str, 'ist': 0.0, 'soll': 0.0, 'glz': 0.0,
                              'main_text': '', 'blocks': []}

        # Tages-Summen + Haupt-Text vom ersten Block mit Ist > 0
        if ist > 0 and days[date_str]['ist'] == 0.0:
            days[date_str]['ist'] = ist
            days[date_str]['soll'] = soll or 0.0
            days[date_str]['glz'] = glz or 0.0
            days[date_str]['main_text'] = text_label

        # Block hinzufügen (nur wenn Beginn/Ende vorhanden)
        if beginn and ende:
            days[date_str]['blocks'].append({
                'beginn': beginn,
                'ende': ende,
                'text': text_label,
                'erf': erf or 0.0,
            })

    return days


def calc_arzt_hours_for_day(day):
    """
    Berechne die effektiven Arzt-Stunden für einen Tag mit Arztbesuch-Blöcken.
    Regel: Schnittmenge von [Beginn, min(Ende, nächster_Beginn)] mit ARZT_WINDOWS.
    """
    blocks = sorted(day['blocks'], key=lambda b: parse_time_h(b['beginn']) or 0)
    total_arzt = 0.0

    for i, block in enumerate(blocks):
        if block['text'].strip().lower() != 'arztbesuch':
            continue

        beginn_h = parse_time_h(block['beginn'])
        ende_h = parse_time_h(block['ende'])
        if beginn_h is None or ende_h is None:
            continue

        # Ende kappen durch Beginn des nächsten Blocks
        if i + 1 < len(blocks):
            next_beginn_h = parse_time_h(blocks[i + 1]['beginn'])
            if next_beginn_h is not None:
                ende_h = min(ende_h, next_beginn_h)

        total_arzt += arzt_hours(
            f"{int(beginn_h):02d}:{int((beginn_h % 1)*60):02d}",
            f"{int(ende_h):02d}:{int((ende_h % 1)*60):02d}"
        )

    return round(total_arzt, 2)


def classify_entries(days):
    """Klassifiziere jeden Tag in MyTE-Einträge."""
    entries = []

    for date_str, day in sorted(days.items()):
        ist = day['ist']
        glz = day['glz']
        main_text = day.get('main_text', '')

        has_arztbesuch = any(
            b['text'].strip().lower() == 'arztbesuch'
            for b in day['blocks']
        )

        # --- Feiertag ---
        if ist == 0.0 and not has_arztbesuch and glz == 0.0:
            # Komplett leer → vermutlich nicht erfasst, überspringen
            continue

        if is_feiertag(main_text) and not has_arztbesuch:
            entries.append({
                'date': date_str, 'text': main_text,
                'action': 'skip',
                'reason': 'Feiertag → 515B01 bereits befüllt',
                'charge_code': '515B01', 'hours': ist
            })

        # --- Krankheit ---
        elif 'krankheit' in main_text.lower():
            entries.append({
                'date': date_str, 'text': main_text,
                'action': 'enter',
                'reason': 'Krankheit → 706B01 Illness',
                'charge_code': '706B01', 'hours': ist
            })

        # --- Erholungsurlaub ---
        elif 'erholungsurlaub' in main_text.lower():
            entries.append({
                'date': date_str, 'text': main_text,
                'action': 'enter',
                'reason': 'Erholungsurlaub → 517B01 Regular Vacation',
                'charge_code': '517B01', 'hours': ist
            })

        # --- Tag mit Arztbesuch ---
        elif has_arztbesuch:
            arzt_h = calc_arzt_hours_for_day(day)
            work_h = round(ist - arzt_h, 2)

            if work_h > 0:
                entries.append({
                    'date': date_str, 'text': main_text,
                    'action': 'enter',
                    'reason': f'Reguläre Arbeit (IST {ist:.2f}h − Arzt {arzt_h:.2f}h)',
                    'charge_code': 'USER_DEFINED', 'hours': work_h
                })
            entries.append({
                'date': date_str, 'text': 'Arztbesuch',
                'action': 'enter',
                'reason': f'Arztbesuch → 706B02 (berechnet aus Zeitfenstern 8-12/14-16)',
                'charge_code': '706B02', 'hours': arzt_h
            })
            if glz < 0:
                entries.append({
                    'date': date_str, 'text': main_text,
                    'action': 'enter',
                    'reason': f'Glz={glz:+.2f} → 513B01 Overtime Vacation (Absolutwert)',
                    'charge_code': '513B01', 'hours': round(abs(glz), 2)
                })

        # --- Glz negativ (ohne Arztbesuch) ---
        elif glz < 0:
            if ist > 0:
                entries.append({
                    'date': date_str, 'text': main_text,
                    'action': 'enter',
                    'reason': 'Regulärer Arbeitstag (Glz negativ)',
                    'charge_code': 'USER_DEFINED', 'hours': ist
                })
            entries.append({
                'date': date_str, 'text': main_text,
                'action': 'enter',
                'reason': f'Glz={glz:+.2f} → 513B01 Overtime Vacation (Absolutwert)',
                'charge_code': '513B01', 'hours': round(abs(glz), 2)
            })

        # --- Regulärer Arbeitstag ---
        elif main_text.strip().lower() in REGULAR_WORK_TEXTS:
            entries.append({
                'date': date_str, 'text': main_text,
                'action': 'enter',
                'reason': 'Regulärer Arbeitstag',
                'charge_code': 'USER_DEFINED', 'hours': ist
            })

        # --- Unklar ---
        else:
            entries.append({
                'date': date_str, 'text': main_text,
                'action': 'unclear',
                'reason': f'⚠ Kein Charge Code für "{main_text}" definiert — bitte manuell prüfen!',
                'charge_code': '???', 'hours': ist
            })

    return entries


if __name__ == '__main__':
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else '05_2026.pdf'
    days = parse_timereport(pdf_path)
    entries = classify_entries(days)

    print(f"{'Datum':<8} {'Text':<22} {'Code':<12} {'Stunden':>8}  Aktion")
    print('-' * 72)
    for e in entries:
        if e['action'] == 'enter':
            marker = '✓'
        elif e['action'] == 'skip':
            marker = '–'
        else:
            marker = '⚠'
        print(f"{e['date']:<8} {e['text']:<22} {e['charge_code']:<12} {e['hours']:>8.2f}  {marker} {e['reason']}")

    unclear = [e for e in entries if e['action'] == 'unclear']
    if unclear:
        print()
        print('=' * 72)
        print(f'ACHTUNG: {len(unclear)} Tag/Tage konnten nicht zugeordnet werden!')
        print('Bitte vor dem Eintragen in MyTE manuell klären.')
        print('=' * 72)

    if '--json' in sys.argv:
        print('\n' + json.dumps(entries, indent=2, ensure_ascii=False))
