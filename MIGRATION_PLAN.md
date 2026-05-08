# Documentación: Arquitectura API-based

> Migración completada. La arquitectura anterior (file-based) quedó como referencia legacy.

## Arquitectura Legacy (File-based)

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit App (main.py)              │
│                                                         │
│  1. Login: password estático en st.secrets["password"]  │
│  2. File Uploader "Reporte Tarifario" (.xlsx)           │
│  3. File Uploader "Afectación" (.xlsx)                  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  process_full_data(report.xlsx, master.xlsx)    │    │
│  │                                                 │    │
│  │  pd.read_excel(master, header=0)                │    │
│  │  pd.read_excel(report, header=1)                │    │
│  │                                                 │    │
│  │  Join: master.patente ↔ report[Tractor+1]       │    │
│  │  (columna inmediatamente después de "Tractor")  │    │
│  │                                                 │    │
│  │  Dates: dayfirst=True, invalid → drop           │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

**Limitaciones:**

- El usuario debe exportar manualmente 2 archivos `.xlsx` del sistema
- Los datos son un snapshot estático del momento de exportación
- Sin conversión de moneda, sin filtro de estado de viaje

---

## Arquitectura Actual (API-based)

```
┌───────────────────────────────────────────────────────────────┐
│                   Streamlit App (main.py)                     │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  FASE 1: Login                                          │  │
│  │                                                         │  │
│  │  Usuario ingresa credenciales → POST /api/v1/Auth       │  │
│  │  Basic Auth → recibe Bearer Token                       │  │
│  │  Token en st.session_state["api_token"]                 │  │
│  │  Token cache en .streamlit/token_cache.json             │  │
│  │  Credenciales NUNCA se persisten en disco               │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              ↓ (token válido)                 │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  FASE 2: Fetch de Datos                                │   │
│  │                                                        │   │
│  │  ┌───────────────────────┐  ┌──────────────────────┐   │   │
│  │  │  GET /Trips/          │  │  Afectación .xlsx    │   │   │
│  │  │  TripPricesList       │  │                      │   │   │
│  │  │  ?from=...&to=...     │  │  Auto-download desde │   │   │
│  │  │  Header: Bearer token │  │  URL configurable    │   │   │
│  │  │                       │  │  (Azure Blob)        │   │   │
│  │  │  Filter:              │  │                      │   │   │
│  │  │  TripState=="Cumplido"│  │  Override manual:    │   │   │
│  │  └───────────────────────┘  │  file uploader opc.  │   │   │
│  │             ↓               └──────────────────────┘   │   │
│  │  flatten JSON → DataFrame                              │   │
│  │  (nested objects → columnas planas)                    │   │
│  │  Price * MoneyPrice = Precio Cliente (normalizado)     │   │
│  └────────────────────────────────────────────────────────┘   │
│                              ↓                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  FASE 3: Merge & Procesar                               │  │
│  │                                                         │  │
│  │  process_full_data(trips_df, afectacion_bytes)          │  │
│  │                                                         │  │
│  │  Join: trips.Tractor.Description ↔ master.patente       │  │
│  │  (match directo, no más "columna después de Tractor")   │  │
│  │                                                         │  │
│  │  @st.cache_data por rango de fechas                     │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              ↓                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Dashboard                                              │  │
│  │  - Métricas maestras                                    │  │
│  │  - Gráficos de distribución                             │  │
│  │  - Tabla semáforo + auditoría por selección             │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Token expirado (401) → redirect automático a Login     │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

---

## Configuración de Variables de Entorno

### `.streamlit/secrets.toml` (gitignored — nunca commitear)

```toml
api_base_url = "<URL_BASE_API_NBCARGO>"
```

| Variable       | Descripción                   | Fuente       |
| -------------- | ----------------------------- | ------------ |
| `api_base_url` | Base URL de la API de NBCargo | `st.secrets` |

> La URL de afectación **no** va en `secrets.toml`. Es dinámica y editable por el usuario en cualquier momento.

### `config.json` (gitignored — generado en runtime)

Almacena preferencias editables por el usuario:

```json
{
  "afectacion_url": "<URL_DEL_BLOB_DE_AZURE>",
  "from_date": "2026-04-01",
  "to_date": "2026-04-30"
}
```

| Campo            | Descripción                                        |
| ---------------- | -------------------------------------------------- |
| `afectacion_url` | URL del Excel de afectación (editable por usuario) |
| `from_date`      | Fecha de inicio del rango de consulta              |
| `to_date`        | Fecha de fin del rango de consulta                 |

> La URL de afectación persiste en `config.json` hasta que el usuario la actualice desde la interfaz. Se inicializa con un valor default en la primera ejecución si está vacía.

---

## Mapping de Campos: API → DataFrame

| Campo API             | Columna DataFrame    | Notas                          |
| --------------------- | -------------------- | ------------------------------ |
| `Tractor.Description` | `patente_viaje`      | Key del join con Afectación    |
| `Date`                | `Fecha`              | ISO 8601 → `pd.to_datetime`    |
| `Price * MoneyPrice`  | `Precio Cliente`     | Normalización de moneda        |
| `EstimatedDistance`   | `Distancia estimada` | KM del viaje                   |
| `Giver.DisplayName`   | `Dador`              | Para auditoría                 |
| `Driver.DisplayName`  | `Chofer`             | Para auditoría                 |
| `Origin`              | `Origen`             | Para auditoría                 |
| `TripState`           | (filter)             | Solo `TripState == "Cumplido"` |

---

## Pasos de Implementación

### Paso 1: Configuración y archivos nuevos ✅

1. Crear `config.json` con URL default de afectación — ✅
2. Agregar `config.json` al `.gitignore` — ✅
3. Crear `.streamlit/secrets.toml` con `api_base_url` y `afectacion_url_default` — ✅

### Paso 2: API Layer — funciones de comunicación ✅

1. `api_login(user, password)` — ✅
2. `fetch_trips(token, from_date, to_date)` — ✅
3. `flatten_trip(trip)` — ✅
4. `fetch_excel_bytes(url)` — ✅
5. `save_afectacion_url(url)` / `load_config()` — ✅
6. Token cache (`save_token_cache`, `load_token_cache`, `is_token_valid`) — ✅

### Paso 3: Login UI ✅

1. Reemplazar `check_password()` por formulario de login — ✅
2. Guardar token en `st.session_state["api_token"]` — ✅
3. Si no hay token válido → mostrar login — ✅
4. Manejar token expirado (401 → redirect) — ✅
5. Logout con limpieza de cache — ✅

### Paso 4: Nuevo `process_full_data()` ✅

1. Cambiar firma: `process_full_data(trips_df, afectacion_bytes)` — ✅
2. Eliminar `get_unit_column()` — ✅
3. Join directo `patente_viaje` ↔ `patente` — ✅
4. Mantener limpieza de fechas, Month_Period, validaciones — ✅

### Paso 5: UI Changes ✅

1. Eliminar file uploader "Reporte Tarifario" — ✅
2. Reemplazar file uploader "Afectación" por URL configurable — ✅
3. Agregar selector de rango de fechas `from/to` en sidebar — ✅
4. Dashboard mantenido sin cambios — ✅

### Paso 6: Limpieza ✅

1. Eliminar `check_password()` y `st.secrets["password"]` — ✅
2. Eliminar `get_unit_column()` — ✅
3. Eliminar file uploader de reporte tarifario — ✅
4. Actualizar `REQUIRED_COLUMNS` con columnas del API — ✅

### Paso 7: Verificación ✅

1. Flujo completo: login → fetch trips → fetch afectación → merge → dashboard — ✅
2. Conversión de moneda (Price \* MoneyPrice) — ✅
3. Join por patente funciona correctamente — ✅
4. Cambio de URL de afectación y persistencia en `config.json` — ✅
5. Token expirado → redirect a login — ✅

---

## Comparación Rápida

| Aspecto                   | File-based (legacy)          | API-based (actual)                            |
| ------------------------- | ---------------------------- | --------------------------------------------- |
| Auth                      | Password estático en secrets | Login API con token en session                |
| Datos de trips            | Upload manual .xlsx          | GET automático con filtro de fechas           |
| Afectación                | Upload manual cada vez       | Auto-download desde URL configurable          |
| Join                      | Columna después de "Tractor" | `Tractor.Description` directo                 |
| Moneda                    | Sin conversión               | `Price * MoneyPrice` (normalizado)            |
| Filtro de estado          | No aplica                    | Solo `TripState == "Cumplido"`                |
| Persistencia credenciales | No (solo app password)       | Nunca en disco, solo token en cache           |
| Refresh de datos          | Re-subir archivos            | Cambiar rango de fechas                       |
| URLs sensibles            | N/A                          | Almacenadas en `st.secrets` (no hardcodeadas) |
