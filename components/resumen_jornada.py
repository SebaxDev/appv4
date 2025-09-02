# components/resumen_jornada.py

import streamlit as st
import pandas as pd
import pytz
from datetime import datetime, timedelta
from utils.date_utils import format_fecha, ahora_argentina
from config.settings import NOTIFICATION_TYPES, DEBUG_MODE

def render_resumen_jornada(df_reclamos):
    """Muestra el resumen de la jornada en el footer (versión mejorada)"""
    st.markdown("---")
    st.markdown("### 📋 Resumen de la jornada")

    try:
        df_reclamos["Fecha y hora"] = pd.to_datetime(
            df_reclamos["Fecha y hora"],
            dayfirst=True,
            format='mixed',
            errors='coerce'
        )

        argentina = pytz.timezone("America/Argentina/Buenos_Aires")
        hoy = datetime.now(argentina).date()

        df_hoy = df_reclamos[
            df_reclamos["Fecha y hora"].dt.tz_localize(None).dt.date == hoy
        ].copy()

        df_en_curso = df_reclamos[df_reclamos["Estado"] == "En curso"].copy()

        col1, col2 = st.columns(2)
        col1.metric("📌 Reclamos cargados hoy", len(df_hoy))
        col2.metric("⚙️ Reclamos en curso", len(df_en_curso))

        st.markdown("### 👷 Reclamos en curso por técnicos")

        if not df_en_curso.empty and "Técnico" in df_en_curso.columns:
            df_en_curso["Técnico"] = df_en_curso["Técnico"].fillna("").astype(str)
            df_en_curso = df_en_curso[df_en_curso["Técnico"].str.strip() != ""]

            df_en_curso["tecnicos_set"] = df_en_curso["Técnico"].apply(
                lambda x: tuple(sorted([t.strip().upper() for t in x.split(",") if t.strip()]))
            )

            conteo_grupos = df_en_curso.groupby("tecnicos_set").size().reset_index(name="Cantidad")

            if not conteo_grupos.empty:
                st.markdown("#### Distribución de trabajo:")
                for fila in conteo_grupos.itertuples():
                    tecnicos = ", ".join(fila.tecnicos_set)
                    st.markdown(f"- 👥 **{tecnicos}**: {fila.Cantidad} reclamos")

                reclamos_antiguos = df_en_curso.sort_values("Fecha y hora").head(3)
                if not reclamos_antiguos.empty:
                    st.markdown("#### ⏳ Reclamos más antiguos aún en curso:")
                    for _, row in reclamos_antiguos.iterrows():
                        fecha_formateada = format_fecha(row["Fecha y hora"])
                        st.markdown(
                            f"- **{row['Nombre']}** ({row['Nº Cliente']}) - "
                            f"Desde: {fecha_formateada} - "
                            f"Técnicos: {row['Técnico']}"
                        )
            else:
                st.info("No hay técnicos asignados actualmente a reclamos en curso.")
        else:
            st.info("No hay reclamos en curso en este momento.")

        _notificar_reclamos_no_asignados(df_reclamos)

        st.markdown(f"*Última actualización: {datetime.now(argentina).strftime('%d/%m/%Y %H:%M')}*")

        st.markdown("""
            <div style='text-align: center; margin-top: 20px; font-size: 0.9em; color: gray;'>
                © 2025 - Sistema de Gestión de Reclamos
            </div>
        """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Error al generar resumen: {str(e)}")
    finally:
        st.markdown("---")


def _notificar_reclamos_no_asignados(df):
    """
    Detecta reclamos sin técnico hace más de 36 horas y notifica globalmente (una vez)
    """
    if 'notification_manager' not in st.session_state or st.session_state.notification_manager is None:
        return

    ahora = ahora_argentina()
    umbral = ahora - timedelta(hours=36)

    df_filtrado = df[
        (df["Estado"].isin(["Pendiente", "En curso"])) &
        (df["Técnico"].isna() | (df["Técnico"].str.strip() == "")) &
        (pd.to_datetime(df["Fecha y hora"], errors='coerce') < umbral)
    ].copy()

    if df_filtrado.empty:
        return

    try:
        ya_existe = any(
            n.get("Tipo") == "unassigned_claim"
            for n in st.session_state.notification_manager.get_for_user("all", unread_only=False, limit=10)
        )

        if ya_existe:
            return

        mensaje = f"Hay {len(df_filtrado)} reclamos sin técnico asignado desde hace más de 36 horas."
        st.session_state.notification_manager.add(
            notification_type="unassigned_claim",
            message=mensaje,
            user_target="all"
        )

    except Exception as e:
        if DEBUG_MODE:
            st.warning("⚠️ No se pudo generar la notificación global")
            st.exception(e)
