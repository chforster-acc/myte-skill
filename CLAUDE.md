# myte-skill

Claude-Code-Skill, der Accenture-Zeitnachweis-PDFs parst und die Stunden per Browser in MyTE
(https://myte.accenture.com) einträgt. Bedienung steht in `README.md`, der eigentliche Ablauf in
`.claude/commands/myte.md` — hier nur, was man beim Arbeiten **am** Repo wissen muss.

## Aufbau

- `.claude/commands/myte.md` — der Skill (`/myte`). Ist per Symlink nach `~/.claude/commands/`
  eingebunden: Änderungen wirken sofort, ohne Release. Lauffähig ist `/myte` trotzdem nur mit
  diesem Repo als Arbeitsverzeichnis — der Skill ruft `timereports/preview.py` und die PDFs über
  relative Pfade auf.
- `timereports/parse_timereport.py` — PDF-Parser und Klassifizierung (Whitelist, Arzt-Berechnung).
  `--json` liefert die Einträge als JSON.
- `timereports/preview.py` — gibt eine Tabelle pro Periode aus (kein JSON) und listet Werktage ohne
  PDF-Daten; das ruft der Skill auf.

Maßgeblich ist bei Abweichungen: für die Klassifizierung der Parser, für Ablauf, Periodenlogik und
Summenregel (513B01 → 7.70h) der Skill. Die Tabellen in `README.md` und im Skill sind Abschriften —
bei Regeländerungen mitziehen.

## Voraussetzungen

- **Playwright MCP Server** muss konfiguriert sein. Der Skill nutzt dessen Tools (`browser_navigate`,
  `browser_evaluate`, `browser_type`, …) — nicht Claude in Chrome. Neue Browser-Schritte ebenfalls
  mit Playwright-Tools formulieren.
- Python mit `pdfminer.six` (`requirements.txt`). Lokal ist es nicht installiert; der Skill ruft
  aber `python3` direkt auf und scheitert dann. Manuell per Docker:
  ```bash
  docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
    sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python timereports/preview.py 10_2026 1"
  ```

## Zeitnachweis-PDFs

- Ablage unter `timereports/MM_YYYY.pdf` (z.B. `10_2026.pdf`), ein PDF pro Monat.
- Per `.gitignore` ungetrackt und **bleiben es** — persönliche Daten. Nie committen, keine Inhalte
  (Stunden, Abwesenheitsgründe) in Commits, Issues oder PRs übernehmen.

## Periodenlogik

- Periode 1 = Tag 1–15, Periode 2 = Tag 16–Monatsende.
- Die aktuelle Periode ergibt sich aus dem **heutigen Datum**, nicht aus dem, was MyTE gerade
  offen zeigt.
- Tage nach heute sind noch nicht im PDF. `preview.py` meldet sie trotzdem als fehlende Werktage —
  das Herausfiltern ist eine Anweisung an das Modell im Skill, kein Code. Fehlende Werktage bis
  heute melden, aber nicht abbrechen.

## Konventionen

- Skill, README und diese Datei sind bewusst deutsch (Prompts für eine deutsche Konversation);
  Commit-Messages englisch.
- Kein Feature-Branch: direkt auf `main` committen (Ausnahme zur globalen Branch-Regel).
- Tests gibt es noch keine. Erster Kandidat ist die Klassifizierung in `parse_timereport.py`
  (`classify_entries`, `arzt_hours`); Teststruktur vor Code-Änderungen gemeinsam mit dem User
  aufsetzen.
