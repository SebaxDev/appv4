# components/reclamos/cierre.py

import time
from datetime import datetime
import pytz
import pandas as pd
import streamlit as st

from utils.date_utils import format_fecha, ahora_argentina, parse_fecha
from utils.api_manager import api_manager
from utils.data_manager import batch_update_sheet
from config.settings import (
    SECTORES_DISPONIBLES,
    TECNICOS_DISPONIBLES,
    COLUMNAS_RECLAMOS,
    DEBUG_MODE
)

# === Helpers para mapear nombre de columna -> letra de Excel ===
def _excel_col_letter(n: int) -> str:
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters

def _col_letter(col_name: str) -> str:
    # Usa la lista oficial de columnas de la app
    idx = COLUMNAS_RECLAMOS.index(col_name) + 1
    return _excel_col_letter(idx)

def mostrar_overlay_cargando(mensaje="Procesando..."):
    """Muestra un spinner simple de Streamlit"""
    return st.spinner(mensaje)

def render_cierre_reclamos(df_reclamos, df_clientes, sheet_reclamos, sheet_clientes, user):
    result = {
        'needs_refresh': False,
        'message': None,
        'data_updated': False
    }
    
    # 🚩 Si venimos de un cambio (resuelto/pendiente), forzar refresh de datos
    if st.session_state.get('force_refresh'):
        st.session_state['force_refresh'] = False
        return {
            'needs_refresh': True,
            'message': 'Datos actualizados',
            'data_updated': True
        }

    st.subheader("✅ Cierre de reclamos en curso")

    try:
        # Normalización de datos
        df_reclamos["ID Reclamo"] = df_reclamos["ID Reclamo"].astype(str).str.strip()
        df_reclamos["Nº Cliente"] = df_reclamos["Nº Cliente"].astype(str).str.strip()
        df_reclamos["Técnico"] = df_reclamos["Técnico"].astype(str).fillna("")
        df_reclamos["Fecha y hora"] = df_reclamos["Fecha y hora"].apply(parse_fecha)

        # Procesar cada sección
        cambios_tecnicos = _mostrar_reasignacion_tecnico(df_reclamos, sheet_reclamos)
        if cambios_tecnicos:
            result.update({
                'needs_refresh': True,
                'message': 'Técnico reasignado correctamente',
                'data_updated': True
            })
            return result

        cambios_cierre = _mostrar_reclamos_en_curso(df_reclamos, df_clientes, sheet_reclamos, sheet_clientes)
        if cambios_cierre:
            result.update({
                'needs_refresh': True,
                'message': 'Estado de reclamos actualizado',
                'data_updated': True
            })
            return result

        cambios_limpieza = _mostrar_limpieza_reclamos(df_reclamos, sheet_reclamos)
        if cambios_limpieza:
            result.update({
                'needs_refresh': True,
                'message': 'Reclamos antiguos eliminados',
                'data_updated': True
            })
            return result

    except Exception as e:
        st.error(f"❌ Error en el cierre de reclamos: {str(e)}")
        if DEBUG_MODE:
            st.exception(e)
        result['message'] = f"Error: {str(e)}"
    
    return result

def _mostrar_reasignacion_tecnico(df_reclamos, sheet_reclamos):
    st.markdown("### 🔄 Reasignar técnico por N° de cliente")
    cliente_busqueda = st.text_input("🔢 Ingresá el N° de Cliente para buscar", key="buscar_cliente_tecnico").strip()
    
    if not cliente_busqueda:
        return False

    reclamos_filtrados = df_reclamos[
        (df_reclamos["Nº Cliente"] == cliente_busqueda) & 
        (df_reclamos["Estado"].isin(["Pendiente", "En curso"]))
    ]

    if reclamos_filtrados.empty:
        st.warning("⚠️ No se encontró un reclamo pendiente o en curso para ese cliente.")
        return False

    reclamo = reclamos_filtrados.iloc[0]
    st.markdown(f"📌 **Reclamo encontrado:** {reclamo['Tipo de reclamo']} - Estado: {reclamo['Estado']}")
    st.markdown(f"👷 Técnico actual: `{reclamo['Técnico'] or 'No asignado'}`")
    st.markdown(f"📅 Fecha del reclamo: `{format_fecha(reclamo['Fecha y hora'])}`")
    st.markdown(f"📍 Sector: `{reclamo.get('Sector', 'No especificado')}`")

    tecnicos_actuales_raw = [t.strip().lower() for t in reclamo["Técnico"].split(",") if t.strip()]
    tecnicos_actuales = [tecnico for tecnico in TECNICOS_DISPONIBLES if tecnico.lower() in tecnicos_actuales_raw]

    nuevo_tecnico_multiselect = st.multiselect(
        "👷 Nuevo técnico asignado",
        options=TECNICOS_DISPONIBLES,
        default=tecnicos_actuales,
        key="nuevo_tecnico_input"
    )

    if st.button("💾 Guardar nuevo técnico", key="guardar_tecnico"):
        with st.spinner("Actualizando técnico..."):
            try:
                fila_index = reclamo.name + 2
                nuevo_tecnico = ", ".join(nuevo_tecnico_multiselect).upper()

                col_tecnico = _col_letter("Técnico")
                col_estado  = _col_letter("Estado")

                updates = [{"range": f"{col_tecnico}{fila_index}", "values": [[nuevo_tecnico]]}]
                if reclamo['Estado'] == "Pendiente":
                    updates.append({"range": f"{col_estado}{fila_index}", "values": [["En curso"]]})

                success, error = api_manager.safe_sheet_operation(
                    batch_update_sheet,
                    sheet_reclamos,
                    updates,
                    is_batch=True
                )
                
                if success:
                    st.success("✅ Técnico actualizado correctamente.")
                    if 'notification_manager' in st.session_state and nuevo_tecnico:
                        mensaje = f"📌 El cliente N° {reclamo['Nº Cliente']} fue asignado al técnico {nuevo_tecnico}."
                        st.session_state.notification_manager.add(
                            notification_type="reclamo_asignado",
                            message=mensaje,
                            user_target="all",
                            claim_id=reclamo["ID Reclamo"]
                        )
                    return True
                else:
                    st.error(f"❌ Error al actualizar: {error}")
                    if DEBUG_MODE:
                        st.write("Detalles del error:", error)
            except Exception as e:
                st.error(f"❌ Error inesperado: {str(e)}")
                if DEBUG_MODE:
                    st.exception(e)

    return False

def _mostrar_reclamos_en_curso(df_reclamos, df_clientes, sheet_reclamos, sheet_clientes):
    en_curso = df_reclamos[df_reclamos["Estado"] == "En curso"].copy()
    
    filtro_sector = st.selectbox(
        "🔢 Filtrar por sector", 
        ["Todos"] + sorted(SECTORES_DISPONIBLES),
        key="filtro_sector_cierre",
        format_func=lambda x: f"Sector {x}" if x != "Todos" else x
    )
    
    if filtro_sector != "Todos":
        en_curso = en_curso[en_curso["Sector"] == str(filtro_sector)]

    if en_curso.empty:
        st.info("📭 No hay reclamos en curso en este momento.")
        # Limpiar el filtro si no hay reclamos
        if 'filtro_tecnicos_persistente' in st.session_state:
            st.session_state.filtro_tecnicos_persistente = []
        return False

    # Filtro por técnicos
    tecnicos_unicos = sorted(set(
        tecnico.strip().upper()
        for t in en_curso["Técnico"]
        for tecnico in t.split(",")
        if tecnico.strip()
    ))

    # Inicializar filtro en session_state si no existe
    if 'filtro_tecnicos_persistente' not in st.session_state:
        st.session_state.filtro_tecnicos_persistente = []

    # Filtrar los valores por defecto: solo mantener técnicos que existen actualmente
    filtro_valido = [t for t in st.session_state.filtro_tecnicos_persistente if t in tecnicos_unicos]
    
    # Actualizar el session_state con los valores válidos
    if filtro_valido != st.session_state.filtro_tecnicos_persistente:
        st.session_state.filtro_tecnicos_persistente = filtro_valido

    # Widget multiselect
    tecnicos_seleccionados = st.multiselect(
        "👷 Filtrar por técnico asignado", 
        tecnicos_unicos, 
        key="filtro_tecnicos_cierre",
        default=st.session_state.filtro_tecnicos_persistente
    )

    # Feedback visual del filtro
    if tecnicos_seleccionados:
        st.info(f"🔍 Filtrado por técnico(s): {', '.join(tecnicos_seleccionados)}")

    if tecnicos_seleccionados:
        en_curso = en_curso[
            en_curso["Técnico"].apply(lambda t: any(
                tecnico.strip().upper() in t.upper() 
                for tecnico in tecnicos_seleccionados
            ))
        ]

    st.write("### 📋 Reclamos en curso:")
    df_mostrar = en_curso[[
        "Fecha y hora",       # ingreso
        "Fecha_formateada",   # cierre
        "Nº Cliente",
        "Nombre",
        "Sector",
        "Tipo de reclamo",
        "Técnico"
    ]].copy()

    df_mostrar = df_mostrar.rename(columns={
        "Fecha y hora": "Ingreso",
        "Fecha_formateada": "Cierre"
    })

    st.dataframe(df_mostrar, use_container_width=True, height=400,
                column_config={
                    "Ingreso": st.column_config.TextColumn("Ingreso", help="Fecha de ingreso"),
                    "Cierre": st.column_config.TextColumn("Cierre", help="Fecha de cierre (si está resuelto)"),
                    "Sector": st.column_config.TextColumn("Sector", help="Número de sector asignado")
                })

    st.markdown("### ✏️ Acciones por reclamo:")
    
    cambios = False
    
    for i, row in en_curso.iterrows():
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                st.markdown(f"**#{row['Nº Cliente']} - {row['Nombre']}**")
                st.markdown(f"📅 Ingreso: {format_fecha(row['Fecha y hora'])}")
                st.markdown(f"📅 Cierre: {row.get('Fecha_formateada', '') or '—'}")
                st.markdown(f"📍 Sector: {row.get('Sector', 'N/A')}")
                st.markdown(f"📌 {row['Tipo de reclamo']}")
                st.markdown(f"👷 {row['Técnico']}")

                cliente_id = str(row["Nº Cliente"]).strip()
                cliente_info = df_clientes[df_clientes["Nº Cliente"] == cliente_id]
                precinto_actual = cliente_info["N° de Precinto"].values[0] if not cliente_info.empty else ""

                nuevo_precinto = st.text_input("🔒 Precinto", value=precinto_actual, key=f"precinto_{i}")

            with col2:
                if st.button("✅ Resuelto", key=f"resolver_{row['ID Reclamo']}", use_container_width=True):
                    if _cerrar_reclamo(row, nuevo_precinto, precinto_actual, cliente_info, sheet_reclamos, sheet_clientes):
                        # Guardar el filtro actual antes del rerun
                        st.session_state.filtro_tecnicos_persistente = tecnicos_seleccionados
                        st.session_state.force_refresh = True
                        st.rerun()

            with col3:
                if st.button("↩️ Pendiente", key=f"volver_{row['ID Reclamo']}", use_container_width=True):
                    if _volver_a_pendiente(row, sheet_reclamos):
                        # Guardar el filtro actual antes del rerun
                        st.session_state.filtro_tecnicos_persistente = tecnicos_seleccionados
                        st.session_state.force_refresh = True
                        st.rerun()

            st.divider()
    
    return cambios

def _cerrar_reclamo(row, nuevo_precinto, precinto_actual, cliente_info, sheet_reclamos, sheet_clientes):
    try:
        with st.spinner("Cerrando reclamo..."):
            time.sleep(1)
            fila_index = row.name + 2

            col_estado           = _col_letter("Estado")
            col_fecha_formateada = _col_letter("Fecha_formateada")
            col_precinto         = _col_letter("N° de Precinto")

            fecha_resolucion = ahora_argentina().strftime('%d/%m/%Y %H:%M')

            updates = [
                {"range": f"{col_estado}{fila_index}", "values": [["Resuelto"]]},
                {"range": f"{col_fecha_formateada}{fila_index}", "values": [[fecha_resolucion]]},
            ]

            if nuevo_precinto.strip() and nuevo_precinto != precinto_actual:
                updates.append({"range": f"{col_precinto}{fila_index}", "values": [[nuevo_precinto.strip()]]})

            success, error = api_manager.safe_sheet_operation(
                batch_update_sheet,
                sheet_reclamos,
                updates,
                is_batch=True
            )
            
            if success:
                if nuevo_precinto.strip() and nuevo_precinto != precinto_actual and not cliente_info.empty:
                    index_cliente_en_clientes = cliente_info.index[0] + 2
                    success_precinto, error_precinto = api_manager.safe_sheet_operation(
                        sheet_clientes.update,
                        f"F{index_cliente_en_clientes}",
                        [[nuevo_precinto.strip()]]
                    )
                    if not success_precinto:
                        st.warning(f"⚠️ Precinto guardado en reclamo pero no en hoja de clientes: {error_precinto}")

                st.success(f"🟢 Reclamo de {row['Nombre']} cerrado correctamente. Fecha cierre: {fecha_resolucion}")
                return True
            else:
                st.error(f"❌ Error al actualizar: {error}")
                if DEBUG_MODE:
                    st.write("Detalles del error:", error)
    except Exception as e:
        st.error(f"❌ Error inesperado: {str(e)}")
        if DEBUG_MODE:
            st.exception(e)

    return False

def _volver_a_pendiente(row, sheet_reclamos):
    try:
        with st.spinner("Cambiando estado..."):
            time.sleep(1)
            fila_index = row.name + 2

            col_estado           = _col_letter("Estado")
            col_tecnico          = _col_letter("Técnico")
            col_fecha_formateada = _col_letter("Fecha_formateada")

            updates = [
                {"range": f"{col_estado}{fila_index}", "values": [["Pendiente"]]},
                {"range": f"{col_tecnico}{fila_index}", "values": [[""]]},
                {"range": f"{col_fecha_formateada}{fila_index}", "values": [[""]]},
            ]

            success, error = api_manager.safe_sheet_operation(
                batch_update_sheet,
                sheet_reclamos,
                updates,
                is_batch=True
            )
            
            if success:
                st.success(f"🔄 Reclamo de {row['Nombre']} vuelto a PENDIENTE. Se borró la fecha de cierre.")
                return True
            else:
                st.error(f"❌ Error al actualizar: {error}")
                if DEBUG_MODE:
                    st.write("Detalles del error:", error)
    except Exception as e:
        st.error(f"❌ Error inesperado: {str(e)}")
        if DEBUG_MODE:
            st.exception(e)

    return False

def _mostrar_limpieza_reclamos(df_reclamos, sheet_reclamos):
    st.markdown("---")
    st.markdown("### 🗑️ Limpieza de reclamos antiguos")

    tz_argentina = pytz.timezone("America/Argentina/Buenos_Aires")
    df_resueltos = df_reclamos[df_reclamos["Estado"] == "Resuelto"].copy()
    df_resueltos["Fecha y hora"] = pd.to_datetime(df_resueltos["Fecha y hora"])
    
    if df_resueltos["Fecha y hora"].dt.tz is None:
        df_resueltos["Fecha y hora"] = df_resueltos["Fecha y hora"].dt.tz_localize(tz_argentina)
    else:
        df_resueltos["Fecha y hora"] = df_resueltos["Fecha y hora"].dt.tz_convert(tz_argentina)
    
    df_resueltos["Dias_resuelto"] = (datetime.now(tz_argentina) - df_resueltos["Fecha y hora"]).dt.days
    df_antiguos = df_resueltos[df_resueltos["Dias_resuelto"] > 10]

    st.markdown(f"📅 **Reclamos resueltos con más de 10 días:** {len(df_antiguos)}")

    if len(df_antiguos) > 0:
        if st.button("🔍 Ver reclamos antiguos", key="ver_antiguos"):
            st.dataframe(df_antiguos[["Fecha y hora", "Nº Cliente", "Nombre", "Sector", "Tipo de reclamo", "Dias_resuelto"]])
        
        if st.button("🗑️ Eliminar reclamos antiguos", key="eliminar_antiguos"):
            with st.spinner("Eliminando reclamos antiguos..."):
                try:
                    resultado = _eliminar_reclamos_antiguos(df_antiguos, sheet_reclamos)
                    return resultado
                except Exception as e:
                    st.error(f"❌ Error al eliminar reclamos: {str(e)}")
                    if DEBUG_MODE:
                        st.exception(e)
    
    return False
