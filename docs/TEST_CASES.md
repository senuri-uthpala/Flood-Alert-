# Test cases

Run everything:

```bash
cd backend
pip install pytest
pytest -v                       # 39 backend tests (unit + API), ~5 s
# browser end-to-end (23 checks): start the server, then
pip install playwright && playwright install chromium
python tests/e2e/browser_e2e.py
```

## Unit tests - risk engine (`tests/test_risk.py`)
| # | Case | Expected |
|---|---|---|
| U1 | All inputs zero | score 0, Low |
| U2 | Extreme inputs | score 100, Critical |
| U3 | More rain | higher score |
| U4 | Verified reports | higher score |
| U5 | Out-of-range inputs | clamped to 0-100 |
| U6 | Level boundaries 24.9 / 25 / 50 / 75 | Low / Medium / High / Critical |
| U7 | Forecast counts half | 100 mm + 40 mm forecast -> 120 |
| U8 | Alert text | exists in si, ta, en and contains the area name |
| U9 | Haversine Colombo-Kandy | about 94 km |

## API tests (`tests/test_api.py`)
| # | Area | Case | Expected |
|---|---|---|---|
| A1 | Auth | Register, login, `/me` | 201 / 200, role = citizen |
| A2 | Auth | Duplicate e-mail | 409 |
| A3 | Auth | Wrong password / garbage token | 401 |
| A4 | Auth | Register with `"role":"admin"` | role stays citizen |
| A5 | Areas | 25 districts seeded; unknown id | 25 rows; 404 |
| A6 | Reports | Report without login | 401 |
| A7 | Reports | Valid report with PNG | 201, pending, photo reachable |
| A8 | Reports | EXE renamed to .png with image content-type | 415 (magic-byte check) |
| A9 | Reports | 6 MB photo | 413 |
| A10 | Reports | Invalid type / unknown area | 422 / 404 |
| A11 | Reports | Public list shows only verified | pending hidden until verified |
| A12 | Reports | Citizen tries to verify | 403 (401 when anonymous) |
| A13 | Reports | Admin rejects | status = rejected |
| A14 | Reports | 3 distinct users, same area + type | all auto-verified |
| A15 | Reports | One user posts 4 times | stays pending |
| A16 | Subscriptions | Invalid phone number | 422 |
| A17 | Subscriptions | Delete another user's subscription | 404 |
| A18 | Subscriptions | Two users, same phone | each keeps own row, no overwrite |
| A19 | Alerts | Same phone in two accounts | notified once |
| A20 | Subscriptions | 11th subscription | 429 |
| A21 | Admin | Refresh as anonymous / citizen | 401 / 403 |
| A22 | Alerts | Refresh with heavy rain | all areas escalate; Tamil subscriber gets Tamil text; areas sorted by risk |
| A23 | Charts | History endpoint | rows with rainfall, forecast, time |
| A24 | Alerts | Manual broadcast | 201, `manual = true` |
| A25 | Safe zones | Nearest to Kandy | Kandy first, sorted by distance |
| A26 | Safe zones | Coordinates outside Sri Lanka | 422 |
| A27 | Safe zones | Admin add/delete; citizen add | 201/204; 403 |
| A28 | Stats | Public stats | 25 areas, 4 levels |

## Browser end-to-end (`tests/e2e/browser_e2e.py`)
25 areas listed · map circles drawn · default Sinhala · detail + chart · Tamil/English switch · report requires login ·
register · no admin tab for citizens · report with photo + GPS · subscription listed · admin login · pending report
visible · **XSS payload shown as text, not executed** · verify · manual refresh · alerts list · nearest safe zone (geolocated) ·
OSM directions link · no horizontal scroll at 390 px · service worker registered · no JS console errors.

## Manual test checklist (before a demo)
- [ ] Turn network off in dev-tools -> banner appears, areas still load from cache
- [ ] "Add to home screen" installs the PWA
- [ ] Subscribe your own number with real Twilio credentials and trigger *Send manual alert*
- [ ] Open on a phone: tabs, map and forms usable with one hand
