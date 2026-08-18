# myte-skill

Parst Accenture Zeitnachweis-PDFs und trägt die Arbeitszeiten automatisch in [MyTE](https://myte.accenture.com) ein.

## Features

- **PDF-Parser**: Extrahiert Tageseinträge (Ist, Soll, Gleitzeit, Blöcke) aus Zeitnachweis-PDFs
- **Klassifizierung**: Ordnet jeden Tag automatisch dem richtigen Charge Code zu (Arbeit, Krankheit, Urlaub, Arztbesuch, Feiertag, Gleitzeit)
- **Preview**: Zeigt geplante Einträge vor dem Eintragen an
- **Claude Code Skill**: Automatisiert die Eingabe in MyTE per Browser (Playwright MCP)

## Setup

```bash
pip install -r requirements.txt
```

## Standalone-Nutzung

### Preview

```bash
# Aktuelle Periode
python3 timereports/preview.py

# Bestimmter Monat
python3 timereports/preview.py 05_2026

# Bestimmte Periode
python3 timereports/preview.py 05_2026 2
```

### Parser

```bash
python3 timereports/parse_timereport.py timereports/05_2026.pdf
python3 timereports/parse_timereport.py timereports/05_2026.pdf --json
```

PDFs im Format `MM_YYYY.pdf` unter `timereports/` ablegen (werden nicht ins Repo committed).

## Claude Code Skill

Der Skill unter `.claude/commands/myte.md` automatisiert den kompletten Workflow:

```
/myte CWH2R001           # Aktuelle Periode eintragen
/myte --preview           # Nur Preview, kein Browser
/myte --preview 04_2026   # Preview für April
```

Voraussetzung: [Playwright MCP Server](https://github.com/anthropics/playwright-mcp) konfiguriert.

### Global verfügbar machen

Damit `/myte` in jedem Workspace zur Verfügung steht, die Datei aus dem Checkout nach
`~/.claude/commands/` **verlinken** — nicht kopieren. So bleibt der Checkout die einzige
Wahrheit und ein `git pull` wirkt sofort; eine Kopie müsste man nach jeder Änderung
nachziehen, und welche Fassung `/myte` ausführt, sieht man nicht. Aus dem Wurzelverzeichnis
des Repos:

```bash
mkdir -p ~/.claude/commands
ln -sfn "$PWD/.claude/commands/myte.md" ~/.claude/commands/myte.md
```

## Klassifizierungsregeln

| Bedingung | Charge Code |
|---|---|
| Feiertag (nicht in Whitelist) | Skip — 515B01 bereits auto-befüllt |
| Krankheit | 706B01 |
| Erholungsurlaub | 517B01 |
| Arztbesuch | 706B02 (berechnet aus Zeitfenstern 08–12 / 14–16) |
| Gleitzeit negativ | 513B01 (Absolutwert) |
| Teleworking / Office | User-definierter Charge Code |

## Perioden

- **Periode 1**: Tag 1–15 des Monats
- **Periode 2**: Tag 16–Monatsende
