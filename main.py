import streamlit as st
import pandas as pd
import io


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

    # 1. PAGE CONFIGURATION
    st.set_page_config(page_title="Monitor KPIs Transporte", layout="wide")

    st.title("🚚 Monitor de KPIs de Unidades")
    st.markdown("Control de Viajes, Facturación, Kilometraje y Productividad.")

    # 2. DATA PROCESSING FUNCTION WITH ERROR HANDLING
    @st.cache_data
    def process_data(file):
        """
        Reads the excel file, validates columns, and cleans data types.
        Returns: (DataFrame, unit_column_name) or (error_message, None)
        """
        try:
            # Read excel skipping the first title row (header=1)
            raw_df = pd.read_excel(file, sheet_name=0, header=1)
            if raw_df.empty: 
                return "error_empty_file", None
            
            # Clean unnamed and empty columns
            clean_df = raw_df.loc[:, ~raw_df.columns.astype(str).str.contains("Unnamed")].dropna(axis=1, how="all")
            
            # Validate mandatory business columns
            required_cols = ["Tractor", "Fecha", "Unidad de negocios", "Viaje", "Precio Cliente", "Distancia total"]
            missing_cols = [c for c in required_cols if c not in clean_df.columns]
            if missing_cols: 
                return f"error_missing_columns: {', '.join(missing_cols)}", None

            # Identify Unit ID column (the one to the right of 'Tractor')
            all_cols = list(clean_df.columns)
            tractor_idx = all_cols.index("Tractor")
            unit_id_col = all_cols[tractor_idx + 1]

            # Data type sanitization
            clean_df["Fecha"] = pd.to_datetime(clean_df["Fecha"], dayfirst=True, errors='coerce')
            clean_df = clean_df.dropna(subset=["Fecha"])
            clean_df["Precio Cliente"] = pd.to_numeric(clean_df["Precio Cliente"], errors='coerce').fillna(0)
            clean_df["Distancia total"] = pd.to_numeric(clean_df["Distancia total"], errors='coerce').fillna(0)
            
            # Create Period column for filtering
            clean_df["Month_Period"] = clean_df["Fecha"].dt.to_period("M").astype(str)
            
            return clean_df, unit_id_col
        except Exception as e:
            return f"error_critical: {str(e)}", None

    # 3. FILE UPLOADER
    uploaded_file = st.file_uploader("Sube el reporte tarifario (.xlsx)", type=["xlsx"])

    if uploaded_file:
        processing_result, UNIT_COL = process_data(uploaded_file)

        if isinstance(processing_result, str) and "error" in processing_result:
            st.error(f"⚠️ {processing_result}")
        else:
            df = processing_result

            # --- SIDEBAR CONFIGURATION ---
            with st.sidebar:
                st.header("Configuración")
                business_unit_sel = st.selectbox("Unidad de Negocios", sorted(df["Unidad de negocios"].unique()))
                month_sel = st.selectbox("Mes de Análisis", sorted(df["Month_Period"].unique(), reverse=True))

            # --- DATA FILTERING AND KPI CALCULATIONS ---
            filtered_df = df[(df["Unidad de negocios"] == business_unit_sel) & (df["Month_Period"] == month_sel)].copy()
            
            if filtered_df.empty:
                st.warning("No hay datos para esta selección.")
            else:
                last_report_date = filtered_df["Fecha"].max()
                
                # Aggregation by Unit
                summary_df = filtered_df.groupby(UNIT_COL).agg({
                    'Viaje': 'count', 
                    'Precio Cliente': 'sum', 
                    'Distancia total': 'sum', 
                    'Fecha': 'max'
                }).reset_index()
                
                # Productivity calculation (Inactivity days)
                summary_df["Inactivity_Days"] = (last_report_date - summary_df["Fecha"]).dt.days
                
                # Rename for final Spanish UI headers
                summary_df.columns = [UNIT_COL, "Viajes", "Facturacion", "KM_Totales", "Ult_Viaje", "Dias_Inactivos"]

                # --- 4. MONTHLY SUMMARY (Spanish UI) ---
                st.subheader(f"📍 Resumen Mensual: {business_unit_sel} ({month_sel})")
                with st.container(border=True):
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Facturación Total Mes", f"$ {filtered_df['Precio Cliente'].sum():,.0f}")
                    m2.metric("Total Viajes Realizados", f"{len(filtered_df):,}")
                    m3.metric("Unidades Activas", len(summary_df))
                    m4.metric("Promedio Fact. p/Unidad", f"$ {summary_df['Facturacion'].mean():,.0f}")

                # --- 5. DISTRIBUTION CHARTS ---
                st.divider()
                st.subheader("📊 Distribución")
                
                # Category binning for charts
                summary_df['Trips_Cat'] = summary_df['Viajes'].apply(lambda x: '< 3' if x < 3 else ('> 5' if x > 5 else '3-5'))
                summary_df['Rev_Cat'] = summary_df['Facturacion'].apply(lambda x: '< $4M' if x < 4000000 else '>= $4M')
                summary_df['KM_Cat'] = summary_df['KM_Totales'].apply(lambda x: '< 5k' if x < 5000 else ('> 8k' if x > 8000 else '5k-8k'))

                g1, g2, g3 = st.columns(3)
                with g1:
                    st.write("**Unidades por Rango de Viajes**")
                    st.bar_chart(summary_df['Trips_Cat'].value_counts(), color="#2F75B5")
                with g2:
                    st.write("**Unidades por Rango de Facturación**")
                    st.bar_chart(summary_df['Rev_Cat'].value_counts(), color="#27AE60")
                with g3:
                    st.write("**Unidades por Rango de KM**")
                    st.bar_chart(summary_df['KM_Cat'].value_counts(), color="#F1C40F")

                # --- 6. DETAILED TABLE WITH CONDITIONAL STYLING (Spanish Headers) ---
                st.divider()
                st.write("### 🔍 Detalle por Unidad")
                
                def apply_table_styles(df_to_style):
                    styler = df_to_style.style.format({"Facturacion": "$ {:,.2f}", "KM_Totales": "{:,.2f} km"})
                    
                    # Trips Style (Text Color)
                    styler = styler.map(lambda v: 'color: #E74C3C; font-weight: bold' if v < 3 else ('color: #27AE60; font-weight: bold' if v > 5 else 'color: #F1C40F; font-weight: bold'), subset=['Viajes'])
                    
                    # Revenue Style (Background Color)
                    styler = styler.map(lambda f: 'background-color: rgba(231, 76, 60, 0.15); color: #E74C3C' if f < 4000000 else 'background-color: rgba(39, 174, 96, 0.15); color: #27AE60', subset=['Facturacion'])
                    
                    # KM Style (Text Color)
                    styler = styler.map(lambda k: 'color: #E74C3C; font-weight: bold' if k < 5000 else ('color: #27AE60; font-weight: bold' if k > 8000 else ''), subset=['KM_Totales'])
                    
                    # Inactivity Style (Text Color)
                    styler = styler.map(lambda d: 'color: #E74C3C; font-weight: bold' if d > 7 else '', subset=['Dias_Inactivos'])
                    
                    return styler

                # Display final styled table
                st.dataframe(
                    apply_table_styles(summary_df[[UNIT_COL, "Viajes", "Facturacion", "KM_Totales", "Dias_Inactivos"]]),
                    use_container_width=True, hide_index=True
                )

                # --- 7. EXCEL EXPORT ---
                export_buffer = io.BytesIO()
                with pd.ExcelWriter(export_buffer, engine='openpyxl') as writer:
                    summary_df.drop(columns=['Trips_Cat', 'Rev_Cat', 'KM_Cat']).to_excel(writer, index=False)
                st.download_button("📥 Descargar Reporte Validado", export_buffer.getvalue(), f"KPI_{business_unit_sel}.xlsx")

    else:
        st.info("👋 Sube el archivo .xlsx para generar el Monitor de KPIs.")
