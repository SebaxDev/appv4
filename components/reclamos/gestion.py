# components/reclamos/gestion.py

import streamlit as st
import pandas as pd
from utils.date_utils import parse_fecha, format_fecha
from utils.api_manager import api_manager, batch_update_sheet
from config.settings import SECTORES_DISPONIBLES, DEBUG_MODE

def render_gestion_reclamos(df_reclamos, df_clientes, sheet_reclamos, user):
    """
    Muestra la sección de gestión de reclamos cargados
    
    Args:
        df_reclamos (pd.DataFrame): DataFrame con los reclamos
        df_clientes (pd.DataFrame): DataFrame con los clientes
        sheet_reclamos: Objeto de conexión a la hoja de reclamos
        user (dict): Información del usuario actual
        
    Returns:
        dict: {
            'needs_refresh': bool,  # Si se necesita recargar datos
            'message': str,         # Mensaje para mostrar al usuario
            'data_updated': bool    # Si se modificaron datos
        }
    """
    result = {
        'needs_refresh': False,
        'message': None,
        'data_updated': False
    }
    
    st.subheader("📊 Gestión de reclamos cargados")

    try:
        # Preprocesar datos una sola vez
        df = _preparar_datos(df_reclamos, df_clientes)
        
        # Mostrar estadísticas (no produce cambios)
        _mostrar_estadisticas(df)
        
        # Mostrar filtros y tabla (no produce cambios)
        df_filtrado = _mostrar_filtros_y_tabla(df)
        
        # Sección de edición de reclamos
        cambios_edicion = _mostrar_edicion_reclamo(df_filtrado, sheet_reclamos)
        if cambios_edicion:
            result.update({
                'needs_refresh': True,
                'message': 'Reclamo actualizado correctamente',
                'data_updated': True
            })
            return result
        
        # Gestión de desconexiones
        cambios_desconexiones = _gestionar_desconexiones(df_filtrado, sheet_reclamos)
        if cambios_desconexiones:
            result.update({
                'needs_refresh': True,
                'message': 'Desconexiones actualizadas',
                'data_updated': True
            })
            return result

    except Exception as e:
        st.error(f"⚠️ Error en la gestión de reclamos: {str(e)}")
        if DEBUG_MODE:
            st.exception(e)
        result['message'] = f"Error: {str(e)}"
    finally:
        st.markdown('</div>', unsafe_allow_html=True)
    
    return result

def _preparar_datos(df_reclamos, df_clientes):
    """Prepara y limpia los datos para su visualización"""
    # Hacer copias para no modificar los dataframes originales
    df = df_reclamos.copy()
    df_clientes = df_clientes.copy()
    
    # Normalización de datos (una sola vez)
    df_clientes["Nº Cliente"] = df_clientes["Nº Cliente"].astype(str).str.strip()
    df["Nº Cliente"] = df["Nº Cliente"].astype(str).str.strip()
    df["ID Reclamo"] = df["ID Reclamo"].astype(str).str.strip()

    # Optimización: Solo traer las columnas necesarias de clientes
    cols_clientes = ["Nº Cliente", "N° de Precinto", "Teléfono"]
    df_clientes = df_clientes[cols_clientes].drop_duplicates(subset=["Nº Cliente"])

    # Merge más eficiente con datos de clientes
    df = pd.merge(
        df, 
        df_clientes,
        on="Nº Cliente", 
        how="left", 
        suffixes=("", "_cliente")
    )

    # Procesamiento de fechas
    if 'Fecha y hora' in df.columns:
        df["Fecha y hora"] = df["Fecha y hora"].apply(parse_fecha)
        df["Fecha_formateada"] = df["Fecha y hora"].apply(
            lambda x: format_fecha(x, '%d/%m/%Y %H:%M')
        )

        # Validación de fechas
        if df["Fecha y hora"].isna().any():
            num_fechas_invalidas = df["Fecha y hora"].isna().sum()
            st.warning(f"⚠️ {num_fechas_invalidas} reclamos tienen fechas inválidas o faltantes")

    return df.sort_values("Fecha y hora", ascending=False)

def _mostrar_estadisticas(df):
    """Muestra estadísticas visuales de reclamos activos (no produce cambios)"""
    df_activos = df[df["Estado"].isin(["Pendiente", "En curso"])]
    
    if not df_activos.empty:
        # Detectar clientes con múltiples reclamos
        duplicados = df_activos.duplicated(subset="Nº Cliente", keep=False)
        
        st.markdown("#### 📊 Distribución de reclamos activos")
        cols = st.columns(3)
        
        with cols[0]:
            st.metric("Total activos", len(df_activos))
        with cols[1]:
            st.metric("Clientes únicos", len(df_activos["Nº Cliente"].unique()))
        with cols[2]:
            st.metric("Clientes múltiples", duplicados.sum())
        
        # Distribución por tipo
        st.markdown("#### Por tipo de reclamo")
        conteo_por_tipo = df_activos["Tipo de reclamo"].value_counts().sort_index()
        
        for i in range(0, len(conteo_por_tipo), 4):
            cols = st.columns(4)
            for j, col in enumerate(cols):
                if i + j < len(conteo_por_tipo):
                    tipo = conteo_por_tipo.index[i + j]
                    cant = conteo_por_tipo.values[i + j]
                    color = "#dc3545" if cant > 10 else "#0d6efd"
                    col.markdown(f"""
                    <div style='text-align:center;background:#f8f9fa;padding:5px;border-radius:8px;'>
                        <h5 style='margin:0;color:#6c757d;font-size:0.7rem'>{tipo}</h5>
                        <h4 style='margin:0;color:{color};font-size:1.2rem'>{cant}</h4>
                    </div>""", unsafe_allow_html=True)

def _mostrar_filtros_y_tabla(df):
    """Muestra filtros y tabla de reclamos (no produce cambios)"""
    st.markdown("#### 🔍 Filtros de búsqueda")
    
    # Filtros en columnas
    col1, col2, col3 = st.columns(3)
    
    with col1:
        estado = st.selectbox(
            "Estado", 
            ["Todos"] + sorted(df["Estado"].dropna().unique())
        )
    
    with col2:
        sector = st.selectbox(
            "Sector", 
            ["Todos"] + sorted(SECTORES_DISPONIBLES)
        )
    
    with col3:
        tipo = st.selectbox(
            "Tipo de reclamo", 
            ["Todos"] + sorted(df["Tipo de reclamo"].dropna().unique())
        )

    # Aplicar filtros
    df_filtrado = df.copy()
    if estado != "Todos": 
        df_filtrado = df_filtrado[df_filtrado["Estado"] == estado]
    if sector != "Todos": 
        df_filtrado = df_filtrado[df_filtrado["Sector"] == str(sector)]
    if tipo != "Todos": 
        df_filtrado = df_filtrado[df_filtrado["Tipo de reclamo"] == tipo]

    st.markdown(f"**Mostrando {len(df_filtrado)} de {len(df)} reclamos**")

    # Mostrar tabla optimizada
    columnas = [
        "Fecha_formateada", "Nº Cliente", "Nombre", 
        "Sector", "Tipo de reclamo", "Teléfono", "Estado"
    ]
    
    st.dataframe(
        df_filtrado[columnas].rename(columns={"Fecha_formateada": "Fecha y hora"}),
        use_container_width=True,
        hide_index=True,
        height=400
    )
    
    return df_filtrado

def _mostrar_edicion_reclamo(df, sheet_reclamos):
    """Muestra la interfaz para editar reclamos (puede producir cambios)"""
    st.markdown("---")
    st.markdown("### ✏️ Editar un reclamo puntual")
    
    # Crear selector mejorado (sin UUID visible)
    df["selector"] = df.apply(
        lambda x: f"{x['Nº Cliente']} - {x['Nombre']} ({x['Estado']})", 
        axis=1
    )
    
    # Añadir búsqueda por número de cliente o nombre
    busqueda = st.text_input("🔍 Buscar por número de cliente o nombre")
    
    # Filtrar opciones basadas en la búsqueda
    opciones_filtradas = [""] + df["selector"].tolist()
    if busqueda:
        opciones_filtradas = [""] + [
            opc for opc in df["selector"].tolist() 
            if busqueda.lower() in opc.lower()
        ]
    
    seleccion = st.selectbox(
        "Seleccioná un reclamo para editar", 
        opciones_filtradas,
        index=0
    )

    if not seleccion:
        return False

    # Obtener el ID del reclamo (usando el UUID interno)
    numero_cliente = seleccion.split(" - ")[0]
    reclamo_actual = df[df["Nº Cliente"] == numero_cliente].iloc[0]
    reclamo_id = reclamo_actual["ID Reclamo"]  # <-- Esto sigue usando el UUID internamente

    # Mostrar información del reclamo
    with st.expander("📄 Información del reclamo", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**📅 Fecha:** {format_fecha(reclamo_actual['Fecha y hora'])}")
            st.markdown(f"**👤 Cliente:** {reclamo_actual['Nombre']}")
            st.markdown(f"**📍 Sector:** {reclamo_actual['Sector']}")
        with col2:
            st.markdown(f"**📌 Tipo:** {reclamo_actual['Tipo de reclamo']}")
            st.markdown(f"**⚙️ Estado actual:** {reclamo_actual['Estado']}")
            st.markdown(f"**👷 Técnico:** {reclamo_actual.get('Técnico', 'No asignado')}")

    # Formulario de edición
    with st.form(f"form_editar_{reclamo_id}"):
        col1, col2 = st.columns(2)
        
        with col1:
            direccion = st.text_input(
                "Dirección", 
                value=reclamo_actual.get("Dirección", ""),
                help="Dirección completa del cliente"
            )
            telefono = st.text_input(
                "Teléfono", 
                value=reclamo_actual.get("Teléfono", ""),
                help="Número de contacto del cliente"
            )
        
        with col2:
            tipo_reclamo = st.selectbox(
                "Tipo de reclamo", 
                sorted(df["Tipo de reclamo"].unique()),
                index=sorted(df["Tipo de reclamo"].unique()).index(
                    reclamo_actual["Tipo de reclamo"]
                )
            )
            try:
                sector_normalizado = str(int(str(reclamo_actual.get("Sector", "")).strip()))
                index_sector = SECTORES_DISPONIBLES.index(sector_normalizado) if sector_normalizado in SECTORES_DISPONIBLES else 0
            except Exception:
                index_sector = 0

            sector_edit = st.selectbox(
                "Sector",
                options=SECTORES_DISPONIBLES,
                index=index_sector
            )
        
        detalles = st.text_area(
            "Detalles", 
            value=reclamo_actual.get("Detalles", ""), 
            height=100
        )
        
        precinto = st.text_input(
            "N° de Precinto", 
            value=reclamo_actual.get("N° de Precinto", ""),
            help="Número de precinto del medidor"
        )

        estado_nuevo = st.selectbox(
            "Nuevo estado", 
            ["Pendiente", "En curso", "Resuelto"],
            index=["Pendiente", "En curso", "Resuelto"].index(
                reclamo_actual["Estado"]
            ) if reclamo_actual["Estado"] in ["Pendiente", "En curso", "Resuelto"] 
            else 0
        )

        # Botones de acción
        col1, col2 = st.columns(2)
        
        guardar_cambios = col1.form_submit_button(
            "💾 Guardar todos los cambios",
            use_container_width=True
        )
        
        cambiar_estado = col2.form_submit_button(
            "🔄 Cambiar solo estado",
            use_container_width=True
        )

    # Procesar acciones
    if guardar_cambios:
        if not direccion.strip() or not detalles.strip():
            st.warning("⚠️ Dirección y detalles no pueden estar vacíos.")
            return False
        
        return _actualizar_reclamo(
            df, sheet_reclamos, reclamo_id,
            {
                "direccion": direccion,
                "telefono": telefono,
                "tipo_reclamo": tipo_reclamo,
                "detalles": detalles,
                "precinto": precinto,
                "sector": sector_edit,
                "estado": estado_nuevo,
                "nombre": reclamo_actual.get("Nombre", "")  # ✅ Se agrega aquí
            },
            full_update=True
        )

    if cambiar_estado:
        return _actualizar_reclamo(
            df, sheet_reclamos, reclamo_id,
            {"estado": estado_nuevo},
            full_update=False
        )
    
    return False

def _actualizar_reclamo(df, sheet_reclamos, reclamo_id, updates, full_update=False):
    """Actualiza el reclamo en la hoja de cálculo y genera notificaciones si corresponde"""
    from config.settings import NOTIFICATION_TYPES  # Para íconos (opcional)
    
    with st.spinner("Actualizando reclamo..."):
        try:
            fila = df[df["ID Reclamo"] == reclamo_id].index[0] + 2
            updates_list = []
            estado_anterior = df[df["ID Reclamo"] == reclamo_id]["Estado"].values[0]

            if full_update:
                # ✅ Mapeo corregido de columnas según tu hoja
                updates_list.extend([
                    {"range": f"E{fila}", "values": [[updates['direccion'].upper()]]},  # Dirección
                    {"range": f"F{fila}", "values": [[str(updates['telefono'])]]},     # Teléfono
                    {"range": f"G{fila}", "values": [[updates['tipo_reclamo']]]},      # Tipo reclamo
                    {"range": f"H{fila}", "values": [[updates['detalles']]]},          # Detalles
                    {"range": f"K{fila}", "values": [[updates['precinto']]]},          # Precinto
                    {"range": f"C{fila}", "values": [[str(updates['sector'])]]},       # Sector
                ])

            # ✅ Estado (columna I)
            updates_list.append({"range": f"I{fila}", "values": [[updates['estado']]]})

            # Si pasa a pendiente, limpiar columna J (técnico)
            if updates['estado'] == "Pendiente":
                updates_list.append({"range": f"J{fila}", "values": [[""]]})

            # Guardar en Google Sheets
            success, error = api_manager.safe_sheet_operation(
                batch_update_sheet, 
                sheet_reclamos, 
                updates_list, 
                is_batch=True
            )

            if success:
                st.success("✅ Reclamo actualizado correctamente.")

                # Crear notificación si cambió el estado
                if updates['estado'] != estado_anterior and 'notification_manager' in st.session_state:
                    mensaje = f"El reclamo {reclamo_id} cambió de estado: {estado_anterior} ➜ {updates['estado']}"
                    usuario = st.session_state.auth.get('user_info', {}).get('username', 'desconocido')
                    st.session_state.notification_manager.add(
                        notification_type="status_change",
                        message=mensaje,
                        user_target="all",
                        claim_id=reclamo_id
                    )

                return True
            else:
                st.error(f"❌ Error al actualizar: {error}")
                return False

        except Exception as e:
            st.error(f"❌ Error inesperado: {str(e)}")
            if DEBUG_MODE:
                st.exception(e)
            return False

def _gestionar_desconexiones(df, sheet_reclamos):
    """Gestiona las desconexiones a pedido (puede producir cambios)"""
    st.markdown("---")
    st.markdown("### 🔌 Gestión de Desconexiones a Pedido")

    desconexiones = df[
        (df["Tipo de reclamo"].str.strip().str.lower() == "desconexion a pedido") &
        (df["Estado"].str.strip().str.lower() == "desconexión")
    ]

    if desconexiones.empty:
        st.success("✅ No hay desconexiones pendientes de marcar como resueltas.")
        return False

    st.info(f"📄 Hay {len(desconexiones)} desconexiones cargadas ir a Impresion para imprimir listado.")
    
    cambios = False
    
    for i, row in desconexiones.iterrows():
        with st.container():
            col1, col2 = st.columns([4, 1])
            
            with col1:
                st.markdown(f"**{row['Nº Cliente']} - {row['Nombre']}**")
                st.markdown(f"📅 {format_fecha(row['Fecha y hora'])} - Sector {row['Sector']}")
            
            with col2:
                if st.button("✅ Marcar como resuelto", key=f"resuelto_{i}", use_container_width=True):
                    if _marcar_desconexion_como_resuelta(row, sheet_reclamos):
                        cambios = True
            
            st.divider()
    
    return cambios

def _marcar_desconexion_como_resuelta(row, sheet_reclamos):
    """Marca una desconexión como resuelta en la hoja de cálculo"""
    with st.spinner("Actualizando estado..."):
        try:
            fila = row.name + 2
            success, error = api_manager.safe_sheet_operation(
                sheet_reclamos.update, 
                f"I{fila}", 
                [["Resuelto"]]
            )
            
            if success:
                st.success(f"✅ Desconexión de {row['Nombre']} marcada como resuelta.")
                return True
            else:
                st.error(f"❌ Error al actualizar: {error}")
                return False
        except Exception as e:
            st.error(f"❌ Error inesperado: {str(e)}")
            if DEBUG_MODE:
                st.exception(e)
            return False
