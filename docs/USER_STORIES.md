# Requirements & user stories

## Actors
**Citizen** (anonymous visitor or registered user) · **Admin** (DMC / council officer) · **System** (scheduler)

## Functional requirements
| ID | Story | Priority | Where |
|---|---|---|---|
| FR1 | As a visitor I can see a colour-coded risk map of all 25 districts without logging in. | Must | Map + Areas tab |
| FR2 | As a visitor I can open an area to see rainfall, forecast, risk score and a 72 h chart. | Must | Area detail |
| FR3 | As a visitor I can use the app in Sinhala, Tamil or English. | Must | Language selector |
| FR4 | As a user I can register and log in. | Must | Auth dialog |
| FR5 | As a user I can report a flood or landslide with description, GPS and photo. | Must | Report tab |
| FR6 | As a user I can subscribe to an area and receive alerts by SMS, e-mail or push in my language. | Must | Report tab |
| FR7 | As the system I refresh rainfall data and recompute risk every 30 minutes. | Must | Scheduler |
| FR8 | As the system I send an alert only when an area's level **rises** to Medium or above. | Must | `services.refresh_all` |
| FR9 | As an admin I can verify or reject reports. | Must | Admin tab |
| FR10 | As an admin I can send a manual alert to an area. | Should | Admin tab |
| FR11 | As a user in danger I can find the nearest safe zones and open directions. | Should | Safe zones tab |
| FR12 | As a user I get a browser notification for critical alerts and for areas I subscribed to. | Should | Alerts polling |
| FR13 | As a user I can still see the last downloaded data when I have no network. | Should | PWA / service worker |
| FR14 | As the system I auto-verify a report once 3 different users reported the same thing nearby. | Could | `maybe_auto_verify` |
| FR15 | As an admin I can add and remove official safe zones. | Could | `POST/DELETE /api/safe-zones` |
| FR16 | As an operator I can retrain the ML model from historical data. | Could | `ml/train.py` |

## Non-functional requirements
| ID | Requirement |
|---|---|
| NFR1 | Mobile-first responsive UI, usable at 390 px width. |
| NFR2 | Installable PWA; read-only offline mode. |
| NFR3 | Passwords hashed; JWT auth; admin role cannot be self-assigned. |
| NFR4 | Works with SQLite (zero setup) and PostgreSQL (production). |
| NFR5 | Degrades gracefully: no internet -> mock rainfall; no SMS credentials -> alerts logged. |
| NFR6 | Core logic covered by automated tests (see TEST_CASES.md). |

## Use cases
**UC1 - Receive a flood warning**
1. Citizen registers and subscribes to *Ratnapura* via SMS in Sinhala.
2. Scheduler refreshes data; Ratnapura rises from Medium to High.
3. System stores one alert and sends the Sinhala SMS to the citizen's number.
4. Citizen opens the app, taps the area, sees the chart and finds the nearest safe zone.

**UC2 - Community report**
1. Citizen logs in, photographs a flooded road, taps *Use my location*, submits.
2. Report is *pending*. Two other citizens in the same area report the same event within 6 h.
3. System auto-verifies all three; the area's risk score rises on the next refresh; the report appears on the public map.

**UC3 - Admin moderation**
1. Admin opens the Admin tab, reviews the photo and description of a pending report.
2. Admin verifies a genuine report or rejects a fake one.
