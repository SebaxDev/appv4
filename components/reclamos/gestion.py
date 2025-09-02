# components/reclamos/gestion.py

import streamlit as st
import pandas as pd
from utils.date_utils import parse_fecha, format_fecha
from utils.api_manager import api_manager, batch_update_sheet
from config.settings import SECTORES_DISPONIBLES, DEBUG_MODE, TECNICOS_DISPONIBLES

def render_gestion_reclamos(df_reclamos, df_clientes, sheet_reclamos, user):
    """
    Muestra la sección de gestión de reclamos con un flujo de edición optimizado.
    """
    st.subheader("📊 Gestión de Reclamos Cargados")

    try:
        if df_reclamos.empty:
            st.info("No hay reclamos para mostrar.")
            return

        # Prepara los datos una sola vez
        df_preparado = _preparar_datos(df_reclamos, df_clientes)

        # Muestra filtros y obtiene el dataframe filtrado
        df_filtrado = _mostrar_filtros_y_busqueda(df_preparado)

        # Muestra la lista interactiva de reclamos
        _mostrar_lista_reclamos_interactiva(df_filtrado, sheet_reclamos, user)

    except Exception as e:
        st.error(f"⚠️ Error en la gestión de reclamos: {str(e)}")
        if DEBUG_MODE:
            st.exception(e)

def _preparar_datos(df_reclamos, df_clientes):
    """Prepara y limpia los datos para su visualización."""
    df = df_reclamos.copy()
    df_clientes_norm = df_clientes.copy()

    # Normalización de columnas clave para el merge
    df_clientes_norm["Nº Cliente"] = df_clientes_norm["Nº Cliente"].astype(str).str.strip()
    df["Nº Cliente"] = df["Nº Cliente"].astype(str).str.strip()
    df["ID Reclamo"] = df["ID Reclamo"].astype(str).str.strip()

    # Merge eficiente
    df = pd.merge(df, df_clientes_norm[["Nº Cliente", "Teléfono"]], on="Nº Cliente", how="left")

    # Manejo de fechas
    df["Fecha y hora"] = pd.to_datetime(df["Fecha y hora"], errors='coerce')
    df.sort_values("Fecha y hora", ascending=False, inplace=True)

    return df

def _mostrar_filtros_y_busqueda(df):
    """Muestra los filtros y la barra de búsqueda, devolviendo el dataframe filtrado."""
    st.markdown("#### 🔍 Filtros y Búsqueda")

    # Contenedor para los filtros
    with st.container():
        col1, col2, col3 = st.columns(3)
        with col1:
            estado = st.selectbox("Estado", ["Todos"] + sorted(df["Estado"].dropna().unique()))
        with col2:
            sector = st.selectbox("Sector", ["Todos"] + SECTORES_DISPONIBLES)
        with col3:
            tipo_reclamo = st.selectbox("Tipo de reclamo", ["Todos"] + sorted(df["Tipo de reclamo"].dropna().unique()))

        busqueda_texto = st.text_input("Buscar por ID de Reclamo, N° de Cliente o Nombre", placeholder="Escribe para buscar...")

    # Aplicar filtros de selectbox
    df_filtrado = df.copy()
    if estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Estado"] == estado]
    if sector != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Sector"] == sector]
    if tipo_reclamo != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Tipo de reclamo"] == tipo_reclamo]

    # Aplicar filtro de búsqueda de texto
    if busqueda_texto:
        termino = busqueda_texto.lower()
        df_filtrado = df_filtrado[
            df_filtrado["ID Reclamo"].str.lower().contains(termino) |
            df_filtrado["Nº Cliente"].str.lower().contains(termino) |
            df_filtrado["Nombre"].str.lower().contains(termino)
        ]

    st.markdown(f"**Mostrando {len(df_filtrado)} de {len(df)} reclamos**")
    return df_filtrado

def _mostrar_lista_reclamos_interactiva(df, sheet_reclamos, user):
    """Muestra la lista de reclamos con acciones directas."""
    if df.empty:
        st.info("No se encontraron reclamos que coincidan con los filtros.")
        return

    for _, reclamo in df.iterrows():
        card_id = reclamo["ID Reclamo"]

        with st.container():
            col1, col2, col3 = st.columns([3, 2, 1])

            with col1:
                st.markdown(f"**{reclamo['Nombre']}** (`{reclamo['Nº Cliente']}`)")
                st.caption(f"ID Reclamo: {card_id} | Fecha: {format_fecha(reclamo['Fecha y hora'], '%d/%m/%Y %H:%M')}")
                st.markdown(f"*{reclamo['Tipo de reclamo']}* - Sector {reclamo['Sector']}")

            with col2:
                # Cambio de estado rápido
                estados_posibles = ["Pendiente", "En curso", "Resuelto"]
                try:
                    current_index = estados_posibles.index(reclamo["Estado"])
                except ValueError:
                    current_index = 0

                nuevo_estado = st.selectbox(
                    "Cambiar estado",
                    options=estados_posibles,
                    index=current_index,
                    key=f"estado_{card_id}",
                    label_visibility="collapsed"
                )
                if nuevo_estado != reclamo["Estado"]:
                    _actualizar_reclamo(df, sheet_reclamos, card_id, {"estado": nuevo_estado}, user)
                    st.rerun()

            with col3:
                # Botón para abrir el modal de edición
                if st.button("✏️ Editar", key=f"edit_{card_id}", use_container_width=True):
                    _mostrar_modal_edicion(df, sheet_reclamos, card_id, user)

            st.divider()

def _mostrar_modal_edicion(df, sheet_reclamos, reclamo_id, user):
    """Muestra un modal (st.dialog) para editar un reclamo específico."""
    reclamo = df[df["ID Reclamo"] == reclamo_id].iloc[0]

    with st.dialog("✏️ Editar Reclamo", width="large"):
        with st.form(key=f"form_edit_{reclamo_id}"):
            st.markdown(f"**Editando Reclamo ID:** {reclamo_id}")

            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input("Nombre", value=reclamo.get("Nombre", ""))
                direccion = st.text_input("Dirección", value=reclamo.get("Dirección", ""))
                telefono = st.text_input("Teléfono", value=reclamo.get("Teléfono", ""))
            with col2:
                sector = st.selectbox("Sector", options=SECTORES_DISPONIBLES, index=SECTORES_DISPONIBLES.index(reclamo["Sector"]) if reclamo["Sector"] in SECTORES_DISPONIBLES else 0)
                tipo_reclamo = st.selectbox("Tipo de Reclamo", options=sorted(df["Tipo de reclamo"].unique()), index=sorted(df["Tipo de reclamo"].unique()).tolist().index(reclamo["Tipo de reclamo"]))
                tecnico = st.selectbox("Técnico Asignado", options=[""] + TECNICOS_DISPONIBLES, index=TECNICOS_DISPONIBLES.index(reclamo["Técnico"]) + 1 if reclamo.get("Técnico") in TECNICOS_DISPONIBLES else 0)

            detalles = st.text_area("Detalles", value=reclamo.get("Detalles", ""), height=150)
            precinto = st.text_input("N° de Precinto", value=reclamo.get("N° de Precinto", ""))

            if st.form_submit_button("💾 Guardar Cambios", use_container_width=True):
                updates = {
                    "nombre": nombre,
                    "direccion": direccion,
                    "telefono": telefono,
                    "sector": sector,
                    "tipo_reclamo": tipo_reclamo,
                    "tecnico": tecnico,
                    "detalles": detalles,
                    "precinto": precinto,
                }
                if _actualizar_reclamo(df, sheet_reclamos, reclamo_id, updates, user, full_update=True):
                    st.rerun()

def _actualizar_reclamo(df, sheet_reclamos, reclamo_id, updates, user, full_update=False):
    """Actualiza un reclamo en la hoja de cálculo."""
    with st.spinner("Actualizando..."):
        try:
            fila_idx = df[df["ID Reclamo"] == reclamo_id].index[0]
            fila_google_sheets = fila_idx + 2  # +2 para la cabecera y el índice 1-based

            updates_list = []
            estado_anterior = df.loc[fila_idx, "Estado"]

            # Mapeo de claves a columnas de la hoja
            column_map = {
                "nombre": "D", "direccion": "E", "telefono": "F", "sector": "C",
                "tipo_reclamo": "G", "tecnico": "J", "detalles": "H", "precinto": "K",
                "estado": "I"
            }

            if full_update:
                for key, value in updates.items():
                    if key in column_map:
                        col = column_map[key]
                        updates_list.append({"range": f"{col}{fila_google_sheets}", "values": [[str(value)]]})
            elif "estado" in updates:
                # Actualización rápida solo para el estado
                col = column_map["estado"]
                updates_list.append({"range": f"{col}{fila_google_sheets}", "values": [[updates["estado"]]]})

            if not updates_list:
                st.toast("No hay cambios que guardar.")
                return False

            success, error = api_manager.safe_sheet_operation(
                batch_update_sheet, sheet_reclamos, updates_list, is_batch=True
            )

            if success:
                st.toast(f"✅ Reclamo {reclamo_id} actualizado.")
                # Notificación de cambio de estado
                if "estado" in updates and updates["estado"] != estado_anterior:
                    if 'notification_manager' in st.session_state:
                        st.session_state.notification_manager.add(
                            notification_type="status_change",
                            message=f"Reclamo {reclamo_id} cambió: {estado_anterior} ➜ {updates['estado']}",
                            user_target="all",
                            claim_id=reclamo_id
                        )
                return True
            else:
                st.error(f"❌ Error al actualizar: {error}")
                return False
        except Exception as e:
            st.error(f"❌ Error inesperado al actualizar: {e}")
            if DEBUG_MODE:
                st.exception(e)
            return False
