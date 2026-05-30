import json
import io
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Monitor KPIs - Dashboard Operativo", layout="wide")

TRIP_THRESHOLDS = {"low": 3, "high": 5}
BILLING_THRESHOLD = 4_000_000
KM_THRESHOLDS = {"low": 5000, "high": 8000}
INACTIVITY_THRESHOLD = 7
UNIT_COL = "patente_viaje"
TOKEN_CACHE_FILE = Path(".streamlit/token_cache.json")
CONFIG_FILE = Path("config.json")
REQUIRED_COLUMNS = {
    "master": ["patente", "negocio principal"],
    "trips": [UNIT_COL, "Fecha", "Precio Cliente", "Distancia estimada", "Viaje"],
}


def validate_dataframe(df, required_cols, file_type):
    df_cols_lower = df.columns.str.lower().str.strip()
    missing = [col for col in required_cols if col.lower() not in df_cols_lower]
    if missing:
        return False, f"Faltan columnas en {file_type}: {', '.join(missing)}"
    return True, None


def get_nested(data, path, default=None):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def parse_token_exp(token):
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = json.loads(__import__("base64").urlsafe_b64decode(payload + padding))
        exp = decoded.get("exp")
        return datetime.fromtimestamp(exp) if exp else None
    except Exception:
        return None


def is_token_valid(token, exp_iso):
    if not token:
        return False
    exp_dt = None
    if exp_iso:
        try:
            exp_dt = datetime.fromisoformat(exp_iso)
        except ValueError:
            exp_dt = None
    if exp_dt is None:
        exp_dt = parse_token_exp(token)
    if exp_dt is None:
        return True
    return datetime.utcnow() < exp_dt - timedelta(minutes=1)


def save_token_cache(token, exp_iso):
    TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_FILE.write_text(
        json.dumps({"token": token, "exp": exp_iso}, ensure_ascii=False), encoding="utf-8"
    )


def load_token_cache():
    if not TOKEN_CACHE_FILE.exists():
        return None, None
    try:
        payload = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
        return payload.get("token"), payload.get("exp")
    except Exception:
        return None, None


def clear_token_cache():
    if TOKEN_CACHE_FILE.exists():
        TOKEN_CACHE_FILE.unlink()


def load_config():
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_default_afectacion_url():
    cfg = load_config()
    return cfg.get("afectacion_url", "").strip()


def save_afectacion_url(url: str):
    url = (url or "").strip()
    if not url:
        return
    cfg = load_config()
    cfg["afectacion_url"] = url
    save_config(cfg)


@st.cache_data(show_spinner=False)
def fetch_excel_bytes(url: str) -> bytes:
    url = (url or "").strip()
    if not url:
        raise ValueError("La URL de Afectación está vacía.")
    r = requests.get(url, timeout=60)
    if not r.ok:
        raise RuntimeError(f"No se pudo descargar la Afectación ({r.status_code}).")
    return r.content


def get_api_base_url():
    return st.secrets["api_base_url"].rstrip("/")


def api_login(username, password):
    url = f"{get_api_base_url()}/Auth"
    try:
        response = requests.post(
            url,
            auth=(username, password),
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
    except requests.RequestException as exc:
        return None, f"No se pudo conectar al servicio de autenticación: {exc}"

    if response.status_code == 401:
        return None, "Credenciales inválidas."
    if not response.ok:
        return None, f"Error de autenticación ({response.status_code})."

    token = None
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "application/json" in content_type:
        data = response.json()
        if isinstance(data, str):
            token = data
        elif isinstance(data, dict):
            token = data.get("token") or data.get("access_token") or data.get("data")
    else:
        token = response.text.strip()

    if not token:
        return None, "La API no devolvió un token válido."
    return token, None


def flatten_trip(trip):
    price = pd.to_numeric(get_nested(trip, ["Price"], 0), errors="coerce")
    money_price = pd.to_numeric(get_nested(trip, ["MoneyPrice"], 1), errors="coerce")
    money_symbol = str(get_nested(trip, ["MoneySymbol"], "ARS")).upper().strip()
    
    # Solo multiplicar por MoneyPrice si es moneda extranjera (no ARS)
    if money_symbol != "ARS":
        normalized_price = (price if pd.notna(price) else 0) * (money_price if pd.notna(money_price) else 1)
    else:
        normalized_price = price if pd.notna(price) else 0

    return {
        UNIT_COL: str(get_nested(trip, ["Tractor", "Description"], "")).upper().strip(),
        "Fecha": get_nested(trip, ["Date"]),
        "Precio Cliente": normalized_price,
        "Distancia estimada": pd.to_numeric(get_nested(trip, ["EstimatedDistance"], 0), errors="coerce"),
        "Dador": get_nested(trip, ["Giver", "DisplayName"], ""),
        "Chofer": get_nested(trip, ["Driver", "DisplayName"], ""),
        "Origen": get_nested(trip, ["Origin"], ""),
        "TripState": str(get_nested(trip, ["TripState"], "")).strip(),
        "Viaje": 1,
    }


def normalize_trips_payload(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ["data", "result", "results", "items", "value"]:
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


@st.cache_data(show_spinner=False)
def fetch_trips(token, from_dt, to_dt):
    from_param = from_dt.strftime("%Y-%m-%dT00:00:00")
    to_param = to_dt.strftime("%Y-%m-%dT23:59:00")
    url = f"{get_api_base_url()}/Trips/TripPricesList"
    try:
        response = requests.get(
            url,
            params={"from": from_param, "to": to_param},
            headers={"Authorization": f"Bearer {token}"},
            timeout=45,
        )
    except requests.RequestException as exc:
        return f"No se pudieron obtener viajes desde API: {exc}", None

    if response.status_code == 401:
        return "TOKEN_EXPIRED", None
    if not response.ok:
        return f"La API respondió con error {response.status_code}.", None

    try:
        payload = response.json()
    except ValueError:
        return "La API devolvió un formato inválido.", None

    trips = normalize_trips_payload(payload)
    if not trips:
        return "No hay viajes para el rango seleccionado.", None

    flat_rows = [flatten_trip(t) for t in trips]
    df_trips = pd.DataFrame(flat_rows)

    if df_trips.empty:
        return "No hay viajes para el rango seleccionado.", None
    return None, df_trips


@st.cache_data(show_spinner=False)
def process_full_data(trips_df, master_bytes: bytes):
    try:
        df_master = pd.read_excel(io.BytesIO(master_bytes), header=0)
        df_master.columns = df_master.columns.str.lower().str.strip()

        is_valid, error_msg = validate_dataframe(df_master, REQUIRED_COLUMNS["master"], "Afectación")
        if not is_valid:
            return error_msg, None

        is_valid, error_msg = validate_dataframe(trips_df, REQUIRED_COLUMNS["trips"], "API Trips")
        if not is_valid:
            return error_msg, None

        df_master["patente"] = df_master["patente"].astype(str).str.upper().str.strip()
        trips_df[UNIT_COL] = trips_df[UNIT_COL].astype(str).str.upper().str.strip()

        combined_df = pd.merge(
            trips_df,
            df_master[["patente", "negocio principal"]],
            left_on=UNIT_COL,
            right_on="patente",
            how="left",
        )

        #  if no match, assign "OTROS" to negocio principal
        combined_df["negocio principal"] = combined_df["negocio principal"].fillna("OTROS")

        if combined_df.empty:
            return "No se encontraron coincidencias entre API y Afectación.", None

        combined_df["Fecha"] = pd.to_datetime(combined_df["Fecha"], dayfirst=True, errors="coerce")
        combined_df = combined_df.dropna(subset=["Fecha"])
        if combined_df.empty:
            return "No hay datos válidos después de limpiar fechas.", None

        combined_df["Precio Cliente"] = pd.to_numeric(
            combined_df["Precio Cliente"], errors="coerce"
        ).fillna(0)
        combined_df["Distancia estimada"] = pd.to_numeric(
            combined_df["Distancia estimada"], errors="coerce"
        ).fillna(0)
        combined_df["Month_Period"] = combined_df["Fecha"].dt.to_period("M").astype(str)

        return combined_df, UNIT_COL
    except Exception as exc:
        return f"Error en procesamiento de datos: {exc}", None


def categorize_trips(value):
    if value < TRIP_THRESHOLDS["low"]:
        return "< 3"
    if value > TRIP_THRESHOLDS["high"]:
        return "> 5"
    return "3-5"


def categorize_billing(value):
    return ">= $4M" if value >= BILLING_THRESHOLD else "< $4M"


def categorize_km(value):
    if value < KM_THRESHOLDS["low"]:
        return "< 5k"
    if value > KM_THRESHOLDS["high"]:
        return "> 8k"
    return "5k-8k"


def get_trip_style(value):
    if value < TRIP_THRESHOLDS["low"]:
        return "color: #E74C3C; font-weight: bold"
    if value > TRIP_THRESHOLDS["high"]:
        return "color: #27AE60; font-weight: bold"
    return "color: #F1C40F; font-weight: bold"


def get_billing_style(value):
    if value < BILLING_THRESHOLD:
        return "background-color: rgba(231, 76, 60, 0.15); color: #E74C3C"
    return "background-color: rgba(39, 174, 96, 0.15); color: #27AE60"


def get_km_style(value):
    if value < KM_THRESHOLDS["low"]:
        return "color: #E74C3C; font-weight: bold"
    if value > KM_THRESHOLDS["high"]:
        return "color: #27AE60; font-weight: bold"
    return ""


def get_inactivity_style(value):
    return "color: #E74C3C; font-weight: bold" if value > INACTIVITY_THRESHOLD else ""


def logout():
    st.session_state.pop("api_token", None)
    st.session_state.pop("api_token_exp", None)
    clear_token_cache()


if "api_token" not in st.session_state:
    cached_token, cached_exp = load_token_cache()
    if is_token_valid(cached_token, cached_exp):
        st.session_state["api_token"] = cached_token
        st.session_state["api_token_exp"] = cached_exp


st.title("📊 Monitor de KPIs de Unidades")

if "api_token" not in st.session_state:
    st.subheader("🔐 Ingreso API")
    with st.form("api_login_form", clear_on_submit=False):
        user_api = st.text_input("Usuario API")
        pass_api = st.text_input("Contraseña API", type="password")
        submit_login = st.form_submit_button("Ingresar")

    if submit_login:
        if not user_api or not pass_api:
            st.error("Completa usuario y contraseña.")
        else:
            token, error = api_login(user_api, pass_api)
            if error:
                st.error(error)
            else:
                exp_dt = parse_token_exp(token)
                exp_iso = exp_dt.isoformat() if exp_dt else None
                st.session_state["api_token"] = token
                st.session_state["api_token_exp"] = exp_iso
                save_token_cache(token, exp_iso)
                st.success("Sesión iniciada correctamente.")
                st.rerun()

    st.stop()


with st.sidebar:
    st.header("⚙️ Panel de Control")
    if st.button("Cerrar sesión", use_container_width=True):
        logout()
        st.rerun()

    # Rango de fechas en sidebar (persistente en config.json)
    today = date.today()
    first_day = today.replace(day=1)
    next_month = (first_day + timedelta(days=32)).replace(day=1)
    last_day = next_month - timedelta(days=1)

    cfg_dates = load_config()
    try:
        from_default = date.fromisoformat(str(cfg_dates.get("from_date")))
    except Exception:
        from_default = first_day
    try:
        to_default = date.fromisoformat(str(cfg_dates.get("to_date")))
    except Exception:
        to_default = last_day

    st.session_state.setdefault("from_date", from_default)
    st.session_state.setdefault("to_date", to_default)
    from_date = st.date_input("Desde", value=st.session_state["from_date"], key="from_date")
    to_date = st.date_input("Hasta", value=st.session_state["to_date"], key="to_date")

    # Persistir valores (mantiene afectacion_url si ya estaba guardada)
    cfg_persist = load_config()
    cfg_persist["from_date"] = from_date.isoformat()
    cfg_persist["to_date"] = to_date.isoformat()
    save_config(cfg_persist)

with st.expander("📦 Afectación", expanded=False):
    st.session_state.setdefault("afectacion_url", get_default_afectacion_url())
    url_input = st.text_input("URL de Afectación (.xlsx)", value=st.session_state["afectacion_url"])
    col_url, col_btn = st.columns([2, 1])
    with col_btn:
        apply_url = st.button("Aplicar URL", use_container_width=True)
    if apply_url:
        st.session_state["afectacion_url"] = url_input.strip()
        save_afectacion_url(st.session_state["afectacion_url"])

if from_date > to_date:
    st.error("La fecha 'Desde' no puede ser mayor que 'Hasta'.")
    st.stop()

with st.spinner("Descargando Afectación..."):
    try:
        master_bytes = fetch_excel_bytes(st.session_state.get("afectacion_url"))
    except Exception as exc:
        st.error(f"No se pudo descargar la Afectación desde la URL: {exc}")
        st.stop()

if not master_bytes:
    st.error("La Afectación descargada está vacía.")
    st.stop()

with st.spinner("Consultando viajes en API..."):
    fetch_error, trips_df = fetch_trips(st.session_state["api_token"], from_date, to_date)

if fetch_error == "TOKEN_EXPIRED":
    st.warning("La sesión expiró. Inicia sesión nuevamente.")
    logout()
    st.rerun()
if fetch_error:
    st.error(fetch_error)
    st.stop()

result, unit_col = process_full_data(trips_df, master_bytes)
if isinstance(result, str):
    st.error(f"⚠️ {result}")
    st.stop()

df = result

with st.sidebar:
    month_opts = sorted(df["Month_Period"].unique(), reverse=True)
    sel_month = st.selectbox("📅 Mes de Análisis", month_opts)
    
    # Filtro de cliente (Dador)
    cliente_opts = sorted(df["Dador"].dropna().astype(str).unique())
    sel_cliente = st.selectbox(
        "🏪 Cliente (Dador)",
        options=["Todos"] + cliente_opts,
        index=0
    )
    
    st.divider()
    bu_opts = sorted(df["negocio principal"].dropna().astype(str).unique())
    st.write("**🏢 Negocios de Afectación**")
    sel_bus = st.pills(
        "Filtra por afectación:",
        options=bu_opts,
        selection_mode="multi",
        default=bu_opts,
    )

if not sel_bus:
    st.warning("Selecciona al menos un negocio.")
    st.stop()

# Filtrado con cliente si aplica
if sel_cliente == "Todos":
    df_filtered = df[
        (df["negocio principal"].astype(str).isin(sel_bus)) & (df["Month_Period"] == sel_month)
    ].copy()
else:
    df_filtered = df[
        (df["negocio principal"].astype(str).isin(sel_bus)) & 
        (df["Month_Period"] == sel_month) &
        (df["Dador"].astype(str) == sel_cliente)
    ].copy()

if df_filtered.empty:
    st.warning("No hay datos para el mes y afectaciones seleccionadas.")
    st.stop()

last_report_date = df_filtered["Fecha"].max()
summary = (
    df_filtered.groupby(unit_col)
    .agg({"Viaje": "sum", "Precio Cliente": "sum", "Distancia estimada": "sum", "Fecha": "max"})
    .reset_index()
)
summary["Inactividad"] = (last_report_date - summary["Fecha"]).dt.days
summary.columns = ["Tipo", "Viajes", "Facturación", "KM", "Ult_Viaje", "Inactividad"]

st.divider()
tab_summary, tab_details = st.tabs(["📉 Resumen Ejecutivo", "🔍 Detalle y Auditoría"])

with tab_summary:
    st.subheader(f"📍 Resumen: {', '.join(sel_bus)}")
    with st.container(border=True):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Facturación Total", f"$ {df_filtered['Precio Cliente'].sum():,.0f}")
        m2.metric("Total Viajes", f"{int(df_filtered['Viaje'].sum()):,}")
        m3.metric("Unidades Activas", len(summary))
        m4.metric(
            "Inactividad > 7d",
            len(summary[summary["Inactividad"] > INACTIVITY_THRESHOLD]),
            delta_color="inverse",
        )

    st.write("### Distribución de Desempeño por Rango")
    summary["Cat_Viajes"] = summary["Viajes"].apply(categorize_trips)
    summary["Cat_Fact"] = summary["Facturación"].apply(categorize_billing)
    summary["Cat_KM"] = summary["KM"].apply(categorize_km)

    g1, g2, g3 = st.columns(3)
    with g1:
        st.write("**Rango de Viajes**")
        st.bar_chart(summary["Cat_Viajes"].value_counts(), color="#2F75B5")
    with g2:
        st.write("**Rango de Facturación**")
        st.bar_chart(summary["Cat_Fact"].value_counts(), color="#27AE60")
    with g3:
        st.write("**Rango de Kilometraje**")
        st.bar_chart(summary["Cat_KM"].value_counts(), color="#FF9800")

with tab_details:
    st.write("### 🚩 Semáforo de Desempeño por Unidad")
    search_q = st.text_input("🔍 Buscar patente...", "").upper()
    summary_view = summary[["Tipo", "Viajes", "Facturación", "KM", "Inactividad"]].copy()
    if search_q:
        summary_view = summary_view[
            summary_view["Tipo"].astype(str).str.contains(search_q, na=False)
        ].reset_index(drop=True)

    def style_table(df_styled):
        styled = df_styled.style.format({"Facturación": "$ {:,.2f}", "KM": "{:,.2f} km"})
        styled = styled.map(get_trip_style, subset=["Viajes"])
        styled = styled.map(get_billing_style, subset=["Facturación"])
        styled = styled.map(get_km_style, subset=["KM"])
        styled = styled.map(get_inactivity_style, subset=["Inactividad"])
        return styled

    selection_event = st.dataframe(
        style_table(summary_view),
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
    )

    selected_rows = selection_event.selection.rows
    if selected_rows:
        idx = selected_rows[0] if isinstance(selected_rows, list) else selected_rows
        patente_sel = summary_view.iloc[idx]["Tipo"]

        st.divider()
        st.subheader(f"🔍 Auditoría: Desglose Individual de Viajes - {patente_sel}")

        df_auditoria = df_filtered[df_filtered[unit_col] == patente_sel].copy()
        cols_auditoria = ["Fecha", "Precio Cliente", "Distancia estimada", "TripState", "Dador", "Chofer", "Origen"]
        cols_presentes = [col for col in cols_auditoria if col in df_auditoria.columns]

        st.dataframe(
            df_auditoria[cols_presentes],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Precio Cliente": st.column_config.NumberColumn(format="$ %.2f"),
                "Distancia estimada": st.column_config.NumberColumn(format="%.1f km"),
                "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "TripState": st.column_config.TextColumn(label="Estado"),
            },
        )
    else:
        st.info("👆 Selecciona una patente en la tabla superior para auditar sus viajes.")
