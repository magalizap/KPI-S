# AGENTS.md - KPI-S (Monitor de KPIs de Unidades)

## Project

Single-file Streamlit dashboard (`main.py`) que valida KPIs de flota consultando la API de NBCargo.

## Commands

- `streamlit run main.py` — starts the dev server

## Secrets & Config

- `.streamlit/secrets.toml` (gitignored) — contiene `api_base_url`. Crear localmente para correr la app.
- `config.json` (gitignored, generado en runtime) — almacena `afectacion_url`, `from_date`, `to_date`.

## Data Pipeline

- **Login API**: usuario/contraseña → POST `/api/v1/Auth` → Bearer token en `session_state`.
- **Trips desde API**: GET `/api/v1/Trips/TripPricesList?from=...&to=...` con Bearer token.
  - Filtro: `TripState == "Cumplido"`.
  - Flatten: `Price * MoneyPrice` → `Precio Cliente`, `Tractor.Description` → `patente_viaje`.
- **Afectación**: descarga automática desde URL configurable en Azure Blob (editada por el usuario).
- **Join**: `trips.patente_viaje` ↔ `master.patente` (inner join).
- Fechas: `dayfirst=True`; fechas inválidas descartadas.

## KPI Thresholds

| KPI         | Low                | High            |
| ----------- | ------------------ | --------------- |
| Viajes      | < 3 (red)          | > 5 (green)     |
| Facturación | < $4,000,000 (red) | >= $4M (green)  |
| KM          | < 5,000 (red)      | > 8,000 (green) |
| Inactividad | > 7 days (red)     | —               |

## Style Conventions

- All UI text in Spanish.
- Pandas column matching is case-insensitive and whitespace-trimmed.
- `@st.cache_data` on `process_full_data`, `fetch_trips`, `fetch_excel_bytes`.
