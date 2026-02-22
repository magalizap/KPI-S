# 🚚 Monitor de KPIs de Unidades - Transporte GBA

![Streamlit App](https://static.streamlit.io)

Esta aplicación interactiva permite automatizar la validación de indicadores clave de desempeño (KPIs) para la flota de transporte. Procesa reportes tarifarios en formato `.xlsx` y genera un tablero de control visual con alertas automáticas.

## 📋 Funcionalidades principales

El monitor realiza cuatro validaciones críticas por cada unidad:

1.  **Validación de Viajes:** Identifica unidades con baja productividad (<3 viajes) o exceso de operación (>5 viajes).
2.  **Validación de Facturación:** Control de ingresos por unidad con un umbral objetivo de **$4.000.000**.
3.  **Análisis de Kilometraje:** Seguimiento de distancias totales (Alertas en <5.000 km y >8.000 km).
4.  **Control de Productividad:** Cálculo automático de días de inactividad desde el último servicio registrado.

## 🚀 Guía de Uso

1.  **Carga de datos:** Sube el archivo `.xlsx` exportado del sistema.
2.  **Filtros:** Selecciona la **Unidad de Negocio** y el **Mes** desde la barra lateral.
3.  **Visualización:**
    - Revisa las **Métricas Maestras** en la parte superior.
    - Analiza los **Gráficos de Distribución** para ver el estado general de la flota.
    - Consulta la **Tabla Detallada** con sistema de semáforo (Rojo/Amarillo/Verde).
4.  **Exportación:** Descarga el análisis procesado en un nuevo archivo Excel listo para reportar.

## 🛠️ Requisitos Técnicos

Para ejecutar este proyecto localmente, necesitas tener instalado Python y las siguientes librerías:

```text
streamlit
pandas
openpyxl
```
