import streamlit as st
import pandas as pd
import io
from datetime import datetime

# 1. PAGE & ACCESS CONFIGURATION
st.set_page_config(page_title="Monitor KPIs - Dashboard Operativo", layout="wide")

def check_password():
    """Returns True if the user had the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input("Introduce la contraseña de acceso", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input("Introduce la contraseña de acceso", type="password", on_change=password_entered, key="password")
        st.error("😕 Contraseña incorrecta")
        return False
    else:
        # Password correct.
        return True
    
if check_password():
    # 2. DATA PROCESSING ENGINE (INTERNAL LOGIC IN ENGLISH)
    @st.cache_data
    def process_full_data(report_file, master_file):
        """
        Handles asymmetric headers: Master (Row 1) | Report (Row 2)
        """
        try:
            # Master: Row 1 (header=0) | Report: Row 2 (header=1)
            df_master = pd.read_excel(master_file, header=0)
            df_master.columns = df_master.columns.str.lower().str.strip()
            
            df_report = pd.read_excel(report_file, header=1)
            df_report = df_report.loc[:, ~df_report.columns.astype(str).str.contains("Unnamed")].dropna(axis=1, how="all")
            
            # Unit ID Logic (Tractor + 1)
            report_cols = list(df_report.columns)
            tractor_idx = report_cols.index("Tractor")
            unit_col = report_cols[tractor_idx + 1]

            # Standardize for Join (Direct Match)
            df_master['patente'] = df_master['patente'].astype(str).str.upper().str.strip()
            df_report[unit_col] = df_report[unit_col].astype(str).str.upper().str.strip()

            # INNER JOIN
            combined_df = pd.merge(
                df_report, 
                df_master[['patente', 'negocio principal']], 
                left_on=unit_col, 
                right_on='patente', 
                how='inner'
            )

            # Data Cleaning & Type Conversion
            combined_df["Fecha"] = pd.to_datetime(combined_df["Fecha"], dayfirst=True, errors='coerce')
            combined_df = combined_df.dropna(subset=["Fecha"])
            combined_df["Precio Cliente"] = pd.to_numeric(combined_df["Precio Cliente"], errors='coerce').fillna(0)
            combined_df["Distancia total"] = pd.to_numeric(combined_df["Distancia total"], errors='coerce').fillna(0)
            combined_df["Month_Period"] = combined_df["Fecha"].dt.to_period("M").astype(str)
            
            return combined_df, unit_col
        except Exception as e:
            return f"error: {str(e)}", None

    # 3. MAIN INTERFACE
    st.title("📊 Monitor de KPIs de Unidades")
    
    with st.expander("📂 Carga de Archivos", expanded=True):
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            up_report = st.file_uploader("1. Reporte Tarifario", type=["xlsx"])
        with col_up2:
            up_master = st.file_uploader("2. Afectación", type=["xlsx"])

    if up_report and up_master:
        result, UNIT_COL = process_full_data(up_report, up_master)

        if isinstance(result, str) and "error" in result:
            st.error(f"⚠️ {result}")
        else:
            df = result

            with st.sidebar:
                st.header("⚙️ Panel de Control")
                month_opts = sorted(df["Month_Period"].unique(), reverse=True)
                sel_month = st.selectbox("📅 Mes de Análisis", month_opts)
                
                st.divider()
                bu_opts = sorted(df["negocio principal"].unique())
                st.write("**🏢 Negocios de Afectación**")
                sel_bus = st.pills("Filtra por afectación:", options=bu_opts, selection_mode="multi", default=bu_opts)

            if not sel_bus:
                st.warning("Selecciona al menos un negocio.")
            else:
                df_filtered = df[(df["negocio principal"].isin(sel_bus)) & (df["Month_Period"] == sel_month)].copy()
                
                last_report_date = df_filtered["Fecha"].max()
                summary = df_filtered.groupby(UNIT_COL).agg({
                    'Viaje': 'count', 'Precio Cliente': 'sum', 'Distancia total': 'sum', 'Fecha': 'max'
                }).reset_index()
                summary["Inactividad"] = (last_report_date - summary["Fecha"]).dt.days
                summary.columns = [UNIT_COL, "Viajes", "Facturacion", "KM", "Ult_Viaje", "Inactividad"]

                st.divider()
                tab_summary, tab_details = st.tabs(["📉 Resumen Ejecutivo", "🔍 Detalle y Auditoría"])

                with tab_summary:
                    st.subheader(f"📍 Resumen: {', '.join(sel_bus)}")
                    with st.container(border=True):
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Facturación Total", f"$ {df_filtered['Precio Cliente'].sum():,.0f}")
                        m2.metric("Total Viajes", f"{len(df_filtered):,}")
                        m3.metric("Unidades Activas", len(summary))
                        m4.metric("Inactividad > 7d", len(summary[summary["Inactividad"] > 7]), delta_color="inverse")
                    
                    st.write("### Distribución de Cumplimiento")
                    summary['Cat_Viajes'] = summary['Viajes'].apply(lambda x: '< 3' if x < 3 else ('> 5' if x > 5 else '3-5'))
                    summary['Cat_Fact'] = summary['Facturacion'].apply(lambda x: '< $4M' if x < 4000000 else '>= $4M')
                    summary['Cat_KM'] = summary['KM'].apply(lambda x: '< 5k' if x < 5000 else ('> 8k' if x > 8000 else '5k-8k'))
                    
                    g1, g2, g3 = st.columns(3)
                    with g1:
                        st.write("**Rango de Viajes**")
                        st.bar_chart(summary['Cat_Viajes'].value_counts(), color="#2F75B5")
                    with g2:
                        st.write("**Rango de Facturación**")
                        st.bar_chart(summary['Cat_Fact'].value_counts(), color="#27AE60")
                    with g3:
                        st.write("**Rango de Kilometraje**")
                        st.bar_chart(summary['Cat_KM'].value_counts(), color="#FF9800")

                with tab_details:
                    st.write("### 🚩 Semáforo de Desempeño por Unidad")
                    search_q = st.text_input("🔍 Buscar patente...", "").upper()
                    table_df = summary.copy()
                    if search_q:
                        table_df = table_df[table_df[UNIT_COL].str.contains(search_q)]

                    def style_table(df_styled):
                        s = df_styled.style.format({"Facturacion": "$ {:,.2f}", "KM": "{:,.2f} km"})
                        s = s.map(lambda v: 'color: #E74C3C; font-weight: bold' if v < 3 else ('color: #27AE60; font-weight: bold' if v > 5 else 'color: #F1C40F; font-weight: bold'), subset=['Viajes'])
                        s = s.map(lambda f: 'background-color: rgba(231, 76, 60, 0.15); color: #E74C3C' if f < 4000000 else 'background-color: rgba(39, 174, 96, 0.15); color: #27AE60', subset=['Facturacion'])
                        s = s.map(lambda k: 'color: #E74C3C; font-weight: bold' if k < 5000 else ('color: #27AE60; font-weight: bold' if k > 8000 else ''), subset=['KM'])
                        s = s.map(lambda d: 'color: #E74C3C; font-weight: bold' if d > 7 else '', subset=['Inactividad'])
                        return s

                    st.dataframe(style_table(table_df[[UNIT_COL, "Viajes", "Facturacion", "KM", "Inactividad"]]), use_container_width=True, hide_index=True)

                    st.divider()
                    st.write("### 🔎 Auditoría: Desglose Individual de Viajes")
                    selected_unit = st.selectbox("Unidad a auditar:", options=summary[UNIT_COL].unique())

                    if selected_unit:
                        trips_detail = df_filtered[df_filtered[UNIT_COL] == selected_unit].copy()
                        audit_cols = ["Fecha", "Precio Cliente", "Distancia total", "Dador", "Chofer", "Origen", "Destino"]
                        st.dataframe(trips_detail[audit_cols].style.format({"Precio Cliente": "$ {:,.2f}", "Distancia total": "{:,.2f} km", "Fecha": "{:%d/%m/%Y}"}), use_container_width=True, hide_index=True)

                    # EXPORT LOGIC
                    st.divider()
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        # Pestaña 1: Resumen General
                        summary.to_excel(writer, index=False, sheet_name='Resumen_General')
                        # Pestaña 2: Auditoría de la unidad seleccionada
                        if selected_unit:
                            trips_detail[audit_cols].to_excel(writer, index=False, sheet_name=f'Auditoria_{selected_unit}')
                    
                    st.download_button(
                        label="📥 Descargar Reporte y Auditoría (Excel)", 
                        data=output.getvalue(), 
                        file_name=f"KPI_Completo_{sel_month}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
else:
    st.info("👋 Por favor, sube ambos archivos para iniciar el análisis.")
