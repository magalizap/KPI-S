# Monitor de KPIs de Unidades - Transporte GBA

![Streamlit App](https://static.streamlit.io)

Dashboard interactivo para validar indicadores clave de desempeño (KPIs) de la flota de transporte. Se conecta a la API de NBCargo para obtener datos de todos los viajes (independientemente de su estado) y los cruza con la afectación de unidades.

## Flujo de Uso

1. **Autenticación:** Ingresá tu usuario y contraseña de API.
2. **Configuración de fechas:** Seleccioná el rango de consulta desde el panel lateral.
3. **Afectación:** La планilla de afectación se descarga automáticamente desde la URL configurada. Podés cambiarla desde el expander "📦 Afectación".
4. **Dashboard:**
   - Revisá las **Métricas Maestras** (facturación, viajes, unidades activas, inactividad).
   - Analizá los **Gráficos de Distribución** por rango de viajes, facturación y kilometraje.
   - Consultá la **Tabla Semáforo** y hacé clic en una patente para ver el desglose individual de viajes.

## Validaciones de KPI

| KPI         | Umbral bajo         | Umbral alto        |
| ----------- | ------------------- | ------------------ |
| Viajes      | < 3 (rojo)          | > 5 (verde)        |
| Facturación | < $4.000.000 (rojo) | >= $4M (verde)     |
| Kilometraje | < 5.000 km (rojo)   | > 8.000 km (verde) |
| Inactividad | > 7 días (rojo)     | —                  |

## Configuración

### Variables de entorno

Creá el archivo `.streamlit/secrets.toml` (no commitear al repo):

```toml
api_base_url = "<URL_BASE_API_NBCARGO>"
```

Solo la URL base de la API va en `secrets.toml`. La URL de afectación es dinámica y se gestiona desde la interfaz.

### Archivo de configuración local

`config.json` se genera automáticamente en runtime y almacena:

- `afectacion_url` — URL de la afectación, editable por el usuario en cualquier momento
- `from_date` / `to_date` — rango de fechas seleccionado

## Requisitos Técnicos

```text
streamlit
pandas
openpyxl
requests
```
