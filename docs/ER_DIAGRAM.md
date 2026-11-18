# Database design (ER diagram)

Render with any Mermaid viewer (GitHub, VS Code "Markdown Preview Mermaid", https://mermaid.live).

```mermaid
erDiagram
    USERS ||--o{ REPORTS : submits
    USERS ||--o{ SUBSCRIPTIONS : owns
    AREAS ||--o{ REPORTS : "has"
    AREAS ||--o{ SUBSCRIPTIONS : "watched by"
    AREAS ||--o{ WEATHER_READINGS : "measured in"
    AREAS ||--o{ ALERTS : "triggers"
    AREAS ||--o{ SAFE_ZONES : contains

    USERS {
        int id PK
        string name
        string email UK
        string phone
        string password_hash "PBKDF2-SHA256"
        string role "citizen | admin"
        string language "si | ta | en"
        datetime created_at
    }
    AREAS {
        int id PK
        string name UK
        string district
        float lat
        float lng
        float terrain_risk "0-1"
        float risk_score "0-100"
        string risk_level "Low|Medium|High|Critical"
        float ml_probability "nullable"
        datetime updated_at
    }
    WEATHER_READINGS {
        int id PK
        int area_id FK
        float rainfall_24h
        float rainfall_72h
        float forecast_24h
        float river_level "nullable, 0-1"
        float risk_score
        string source "open-meteo | mock"
        datetime recorded_at
    }
    REPORTS {
        int id PK
        int user_id FK
        int area_id FK
        string type "flood | landslide"
        text description
        float lat
        float lng
        string photo_path
        string status "pending|verified|rejected"
        bool auto_verified
        datetime created_at
    }
    SUBSCRIPTIONS {
        int id PK
        int user_id FK
        int area_id FK
        string channel "sms|email|push"
        string contact
        string language
    }
    ALERTS {
        int id PK
        int area_id FK
        string level
        text message_si
        text message_ta
        text message_en
        bool manual
        int recipients
        datetime sent_at
    }
    SAFE_ZONES {
        int id PK
        int area_id FK
        string name
        string kind "shelter|hospital|school|temple"
        float lat
        float lng
        int capacity
        string phone
        bool is_sample
    }
```

## Notes
- `SUBSCRIPTIONS` has a unique constraint on `(user_id, area_id, contact, channel)`: every account manages only its own rows.
- `WEATHER_READINGS` older than 30 days are pruned on every refresh.
- `ALERTS` stores the message in all three languages, so each subscriber receives it in their own language.
- `SAFE_ZONES.is_sample = true` marks placeholder rows seeded for the demo. Replace them with official DMC shelter data.
- Moving to PostgreSQL + PostGIS later: replace `lat`/`lng` with a `geometry(Point, 4326)` column and add a `geometry(MultiPolygon)` boundary column on `AREAS`.
