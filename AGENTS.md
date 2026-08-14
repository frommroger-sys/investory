# KIMI-Arbeitsregeln

Diese Regeln gelten verbindlich für jede Arbeit von KIMI Code in diesem Repository.

## Auftrag und Umfang

- KIMI bearbeitet immer genau **ein** von Roger ausdrücklich freigegebenes GitHub-Issue gleichzeitig.
- Eine Arbeitssession beginnt nur mit einer eindeutigen Issue-Nummer, z. B. `#99`.
- KIMI darf ausschließlich Änderungen vornehmen, die zur Lösung dieses Issues erforderlich sind.
- Keine Nebenarbeiten, Refactorings oder kosmetischen Änderungen außerhalb des Issue-Umfangs.
- Ist das Issue unklar oder widersprüchlich, muss KIMI stoppen und Roger fragen, bevor Code geändert wird.

## Git und GitHub

- Niemals direkt auf `main` arbeiten oder nach `main` pushen.
- Für jedes Issue einen eigenen Branch nach dem Muster `kimi/issue-<nr>-<kurztitel>` erstellen.
- Für das ausdrücklich freigegebene Issue darf KIMI auf diesem Issue-Branch selbständig committen und pushen sowie einen Pull Request gegen `main` erstellen und aktualisieren.
- KIMI darf Pull Requests **niemals selbst mergen**.
- KIMI darf keine Branch-Protection-, Repository-, Actions-, Secret- oder Deployment-Einstellungen verändern.
- KIMI darf CI/CD- oder Deployment-Dateien nur ändern, wenn das konkrete Issue dies ausdrücklich verlangt und Roger diese Änderung zusätzlich ausdrücklich freigegeben hat.

## Deployment und Produktion

- KIMI darf **niemals deployen**.
- KIMI darf keine Deployment-Workflows manuell auslösen.
- KIMI darf keine Verbindung zu Produktionsservern herstellen.
- KIMI darf keine SSH-, SCP-, SFTP-, FTP- oder vergleichbaren Remote-Befehle zu Servern ausführen.
- KIMI darf keine Produktionsdaten verändern.
- Merge und Live-Deployment erfolgen ausschließlich durch Roger.

## Geheimnisse und Zugänge

- Niemals SSH-Schlüssel lesen, kopieren, anzeigen oder verwenden.
- Niemals Dateien außerhalb des Projekt-Arbeitsverzeichnisses nach Zugangsdaten durchsuchen.
- Niemals `.env`, private Schlüssel, Tokens, Passwörter, API-Secrets oder andere Zugangsdaten lesen oder ausgeben.
- Niemals Produktions-Secrets in Code, Logs, Issues, Commits oder Pull Requests übernehmen.
- Testdaten müssen frei von echten Kunden- und Zugangsdaten sein.

## Verbindlicher Ablauf pro Issue

1. Issue inklusive aller Kommentare lesen.
2. Repository und betroffene Bereiche analysieren, ohne zunächst Code zu ändern.
3. Im Issue kurz dokumentieren: Problemverständnis, geplanter Lösungsweg, voraussichtlich betroffene Dateien und geplante Tests.
4. Eigenen `kimi/issue-...`-Branch erstellen.
5. Minimal notwendige Änderung implementieren.
6. Relevante lokale Prüfungen und Tests ausführen.
7. Bei Fehlern korrigieren und Tests wiederholen.
8. Eigenen Diff nochmals auf Regressionen, Sicherheitsprobleme, unnötige Änderungen und fehlende Fehlerbehandlung prüfen.
9. Resultat und Testergebnisse im Issue dokumentieren.
10. Commit(s) erstellen und den Issue-Branch pushen.
11. Pull Request gegen `main` erstellen. Der PR muss enthalten: Bezug zum Issue, Problem, Lösung, geänderte Bereiche, ausgeführte Tests, Testergebnisse, Risiken/offene Punkte.
12. Auf Feedback von Roger im PR eingehen, Änderungen erneut testen und den PR aktualisieren.
13. Nach Freigabe durch Roger endet die Aufgabe für KIMI. Merge und Deployment sind nicht Teil des KIMI-Auftrags.

## Qualitätsregel

KIMI darf niemals behaupten, eine Änderung funktioniere sicher, wenn dies nicht überprüft wurde. Stattdessen exakt dokumentieren, welche Builds, Tests und Prüfungen tatsächlich erfolgreich durchgeführt wurden und was nicht getestet werden konnte.
