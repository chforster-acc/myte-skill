# MyTE – Zeiterfassung

Öffne myTimeAndExpenses (https://myte.accenture.com) und hilf dem User beim Eintragen seiner Arbeitszeiten aus dem Zeitnachweis-PDF.

---

## Modi

### Normalmodus: `/myte [ChargeCode]`
Liest das aktuelle Monats-PDF, filtert auf die **aktuelle Periode** (basierend auf dem heutigen Datum) und trägt die Werte in MyTE ein.

### Preview-Modus: `/myte --preview [MM_YYYY]`
Gibt nur den PDF-Inhalt aus — **kein Browser, keine Einträge in MyTE**.
Beispiel: `/myte --preview 04_2026` → zeigt alle klassifizierten Einträge aus April.

---

## Perioden-Logik

Periode ergibt sich aus dem **heutigen Datum** (nicht aus dem was in MyTE offen ist):
- **Tag 1–15** des Monats → **Periode 1** (1. bis 15.)
- **Tag 16–EOM** des Monats → **Periode 2** (16. bis letzter Tag)

Das passende PDF liegt unter `timereports/MM_YYYY.pdf` (z.B. `05_2026.pdf` für Mai 2026).

---

## Ablauf — Normalmodus

### Schritt 1: Periode und PDF bestimmen

Heutiges Datum auslesen, Periode ableiten, passendes PDF identifizieren:
```bash
uv run python -c "
from datetime import date
t = date.today()
p1 = t.day <= 15
print(f'Heute: {t}, Periode: {\"1\" if p1 else \"2\"}')
print(f'PDF: timereports/{t.month:02d}_{t.year}.pdf')
print(f'Tage: {1 if p1 else 16} bis {t.day}')  # bis heute!
"
```

### Schritt 2: PDF parsen + auf aktuelle Periode filtern

```bash
uv run python timereports/preview.py MM_YYYY [periode]
# z.B.: uv run python timereports/preview.py 05_2026 2
```

Aus der Ausgabe **nur Einträge behalten**, deren `date` ("DD.MM.") in den Tagen der aktuellen Periode liegt (Periode 1: 01–15, Periode 2: 16–EOM). Zukünftige Tage (nach heute) ignorieren — deren Daten sind noch nicht im PDF.

### Schritt 3: Charge Code erfragen (falls nicht in $ARGUMENTS)

**Pflicht** — kein Default, kein Raten:

> „Welchen Charge Code soll ich für reguläre Arbeitstage verwenden? (z.B. CWH2R001)"

Bei `--preview` entfällt dieser Schritt.

### Schritt 4: Fehlende Tage melden

Prüfen ob für alle Werktage der Periode PDF-Daten vorhanden sind. Fehlende Tage ausgeben:

> „Hinweis: Für folgende Tage sind keine PDF-Daten vorhanden: Do 22.05. — diese Tage werden nicht eingetragen."

Mögliche Gründe: PDF noch nicht aktuell (letzter Arbeitstag), fehlende Buchung (Kommen/Gehen fehlt), Wochenende/Feiertag ohne Eintrag. **Kein Abbruch** — einfach melden und weitermachen.

### Schritt 5: Unclear-Einträge prüfen

Falls `action = "unclear"` Einträge vorhanden: **Abbruch** — dem User die unklaren Tage zeigen:

> „⚠ Folgende Tage konnten nicht zugeordnet werden: [Liste]. Bitte sagen Sie was eingetragen werden soll."

Erst nach Klärung weitermachen.

### Schritt 6: Übersicht ausgeben

Alle geplanten Einträge übersichtlich ausgeben (auch Skips und fehlende Tage):

```
Datum    Text            Code          Stunden  Status
22.05.   Teleworking     CWH2R001        9.34h  → eintragen
21.05.   Teleworking     CWH2R001        8.15h  → eintragen  
20.05.   Gleitzeit lfd.  513B01          7.70h  → eintragen
19.05.   Pfingstmontag   515B01          7.70h  – skip (Feiertag)
```

Vor der Ausgabe die **Summenregel für Tage mit 513B01** anwenden (siehe Klassifizierungsregeln): Tagessumme = 7.70h, Rundungsdifferenzen werden bei 513B01 korrigiert.

Dann fragen: „Soll ich das so in MyTE eintragen?"

### Schritt 7: Browser öffnen + MyTE navigieren

1. Browser navigieren: `browser_navigate` zu `https://myte.accenture.com`
2. Viewport auf 1600×900: `browser_resize`
3. Zur richtigen Periode navigieren (falls MyTE eine andere Periode zeigt, mit `<`/`>` navigieren)

### Schritt 8: Mappings ermitteln

Per `browser_evaluate` Struktur auslesen:
```javascript
() => {
  const dayHeaders = Array.from(document.querySelectorAll('[role="columnheader"]'))
    .map(h => h.textContent.trim().replace(/\s+/g, ''))
    .filter(t => /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\d+$/.test(t));
  const uniqueDays = [];
  dayHeaders.forEach(d => { if (!uniqueDays.includes(d)) uniqueDays.push(d); });

  const codeButtons = Array.from(document.querySelectorAll('button[aria-label*="WBS"]'));
  const codes = codeButtons.map(b => ({
    name: b.textContent.trim().replace(/\s+/g,' '),
    y: Math.round(b.getBoundingClientRect().y)
  }));
  const firstColCells = Array.from(document.querySelectorAll('[id^="hours-cell-0-"]'));
  const rowMap = {};
  firstColCells.forEach(c => {
    const idx = c.id.match(/hours-cell-0-(\d+)/)[1];
    const cy = Math.round(c.getBoundingClientRect().y);
    const code = codes.find(co => Math.abs(co.y - cy) < 30);
    rowMap[idx] = code ? code.name : '(leer)';
  });
  return { days: uniqueDays, rows: rowMap };
}
```

Ergibt z.B.:
- `days[2]` = "Mon18" → Tag-Index X=2 für 18. des Monats
- `rows["1"]` = "AI for Social Impact (CWH2R001)" → Y=1

### Schritt 9: Benötigte Charge Codes prüfen + hinzufügen

Alle Codes die eingetragen werden sollen mit der `rows`-Map abgleichen. Falls ein Code fehlt:

1. Leere Zeile klicken — die konkrete Zeile adressieren, nicht die erste beste:
   `button[aria-label="Charge Codes Assignment {N} Empty "]`
   (Kandidaten vorher auflisten: alle `button[aria-label*="Empty"]` mit ihrem `aria-label`.)
2. Zeichenweise eintippen (`slowly: true`): `browser_type` auf `input[placeholder="Filter..."]`
3. Eintrag auswählen — **nicht** `div.ag-row` blind nehmen: Der Selektor matcht auch die
   Timesheet-Grid-Zeilen (Work Location, bestehende Charge Codes, Total hours …), und
   `querySelector` liefert dann die falsche Zeile. Stattdessen die Treffer erst auflisten
   und gezielt per Text klicken:
   ```javascript
   // Treffer prüfen — genau eine Zeile sollte den Code enthalten
   Array.from(document.querySelectorAll('div.ag-row')).map(r => r.textContent.replace(/\s+/g,' ').trim())
   ```
   Dann `browser_click` mit `div.ag-row:has-text("<eindeutiger Text des Treffers>")`,
   z.B. `div.ag-row:has-text("Overtime Vacation Taken")` für 513B01.
4. Nach dem Hinzufügen steht die neue Zeile im Edit-Modus (die erste Zelle hat dann keine
   `hours-cell-*` id) → `browser_press_key` `Escape`, danach Mapping erneut auslesen.

**Niemals auf bestehenden Charge Code klicken — überschreibt ihn!**

### Schritt 10: Bestehende Werte prüfen (kein Überschreiben)

Vor dem Eintragen jeder Zelle den aktuellen Wert lesen:
```javascript
document.getElementById('hours-cell-X-Y')?.value || 
document.getElementById('hours-cell-X-Y')?.textContent.trim()
```

- **Leer** → normal eintragen
- **Bereits befüllt** → **nicht überschreiben**, stattdessen ausgeben:
  > „ℹ 18.05. CWH2R001: bereits 9.34h eingetragen — übersprungen"

### Schritt 11: Stunden eintragen

**Pro Zelle einzeln** — niemals Tab (springt in andere Zeilen!):
1. `browser_click` auf `#hours-cell-{X}-{Y}`
2. Wert per `browser_type` in `.ag-cell-inline-editing input` tippen, mit `slowly: true` und
   `submit: true` (Alternative: Ziffern einzeln per `browser_press_key`, z.B. "8", ".", "1", "5")

**Zelle leeren** (nur bei bewusster Korrektur/Umbuchung, siehe unten): Zelle anklicken, dann
`browser_type` mit leerem Text und `submit: true`.

### Schritt 12: Speichern + Verifizieren

`browser_click` auf Save-Button, dann **echt neu laden** und erst dann prüfen + Screenshot zeigen.

Erneutes `browser_navigate` auf dieselbe Hash-URL lädt die Daten **nicht** neu — man sieht dann nur
den clientseitigen Stand. Für echtes Neuladen erst `about:blank`, dann zurück zur Perioden-URL:
`#/time?periodEnd=<base64("MM-DD-YYYY"), url-encoded>&viewMode=UmVjb3Jk`
(z.B. 10/31/2026 → `MTAtMzEtMjAyNg%253D%253D`).

Danach den User informieren — **Submit macht der User selbst**:
- Neue Periode (Status „Draft") → Button **„Submit"**
- Bereits eingereichte Periode, nachträglich geändert (Status „Draft Adjustment") → Button
  **„Complete Adjustment"**

---

## Ablauf — Preview-Modus

```bash
uv run python timereports/preview.py [MM_YYYY] [periode]
```

- Ohne Argumente: aktuelle Periode des laufenden Monats
- `02_2026` → beide Perioden Februar
- `02_2026 1` → nur Periode 1 Februar

**Fertig — kein Browser, kein MyTE**

---

## Klassifizierungsregeln (im Parser implementiert)

| Bedingung | Einträge in MyTE |
|---|---|
| Text nicht in Whitelist (= Feiertag) | Skip — 515B01 bereits auto-befüllt |
| Text = "Krankheit" | `Ist` → **706B01 Illness** |
| Text = "Erholungsurlaub" | `Ist` → **517B01 Regular Vacation** |
| Tag mit Arztbesuch-Block | (Ist − Arzt-h) → **[User-Code]** + Arzt-h → **706B02** + ggf. abs(Glz) → **513B01** |
| Glz negativ (kein Arzt) | `Ist` → **[User-Code]** + abs(Glz) → **513B01** |
| Teleworking / Office / Gleitzeit | `Ist` → **[User-Code]** |
| Bekannter Text ohne Regel | ⚠ unclear — Abbruch |

**Arzt-Berechnung**: Schnittmenge von [Beginn, min(Ende, nächster_Beginn)] mit **08:00–12:00** und **14:00–16:00**.

**Whitelist bekannter Arbeitstexte** (alles andere = Feiertag):
`teleworking`, `krankheit`, `gleitzeit lfd.`, `dienstreise`, `mitfahrer`, `erholungsurlaub`, `arztbesuch`, `` (leer = Office)

**Summenregel für Tage mit 513B01** (nicht im Parser, Prüfung in Schritt 6): Wird an einem Tag 513B01 eingetragen, muss die Tagessumme aller Einträge **exakt 7.70h** ergeben — nicht mehr und nicht weniger. Das PDF rundet Ist und Glz unabhängig voneinander, dadurch entstehen Abweichungen von ±0.01h (Beispiel 16.09.2026: Ist 6.89 + Glz 0.82 = 7.71). Korrektur: **513B01 = 7.70 − übrige Einträge des Tages** (im Beispiel 0.81), die übrigen Einträge bleiben unverändert. In der Übersicht (Schritt 6) die korrigierte Zahl zeigen und den PDF-Wert vermerken. Tage ohne 513B01 sind davon nicht betroffen (dort sind echte Überstunden wie 7.71h möglich).

---

## Zellen-Struktur

`hours-cell-{X}-{Y}` — **X = Tag-Index** (0-basiert ab Periodenstart), **Y = Charge-Code-Zeile** (1-basiert, dynamisch!). Immer dynamisch ermitteln, nie hartkodieren.

---

## Wichtige Hinweise

- **Dezimalpunkt**: Browser ist en-US — `8.15` nicht `8,15`
- **Daily Overtime**: MyTE berechnet es automatisch nach Save — nie manuell eintragen
- **Save → Status "Draft"**: Korrekt, Submit ist separat
- **MFA-Dialog**: Screenshot zeigen, User manuell authentifizieren lassen, dann warten
- **Fehlende PDF-Tage**: Melden aber nicht abbrechen (letzter Arbeitstag, Buchungsfehler etc.)
- **Aufteilung auf mehrere Charge Codes**: Arbeitszeit eines Tages (`Ist`, ohne 513B01) wird nach
  vorgegebenem Verhältnis aufgeteilt. Der größere Anteil bekommt einen Wert in 0.25h-Schritten,
  der kleinere den Rest (bei 50:50 egal welcher). Verhältnis kommt vom User — nicht raten.
- **Umbuchung bestehender Perioden**: Ausnahme von Schritt 10 — nur auf ausdrücklichen Wunsch.
  Vorher prüfen, dass der alte Code je Tag der Summe der neuen Codes entspricht (Abweichungen zum
  PDF melden und fragen), dann alte Zelle leeren und neue Werte eintragen. Pro Periode speichern,
  User informieren, auf dessen „erledigt" warten, dann nächste Periode.

---

## Argumente ($ARGUMENTS)

- `/myte CWH2R001` → Charge Code für reguläre Tage, Rest automatisch
- `/myte --preview` → Preview aktuelle Periode, kein MyTE
- `/myte --preview 04_2026` → Preview April 2026
- `/myte CWH2R001 --preview` → Preview mit Code-Auflösung
