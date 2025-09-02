# --------------------------------------------------
# Aplicación principal de gestión de reclamos optimizada
# Versión 2.3 - Diseño optimizado para rendimiento
# --------------------------------------------------

# Standard library
import io
import json
import time
from datetime import datetime
import logging

# Third-party
import pandas as pd
import pytz
import streamlit as st
from google.oauth2 import service_account
import gspread
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from streamlit_lottie import st_lottie
from tenacity import retry, wait_exponential, stop_after_attempt

# Config
from config.settings import (
    SHEET_ID,
    WORKSHEET_RECLAMOS,
    WORKSHEET_CLIENTES, 
    WORKSHEET_USUARIOS,
    COLUMNAS_RECLAMOS,
    COLUMNAS_CLIENTES,
    COLUMNAS_USUARIOS,
    WORKSHEET_NOTIFICACIONES,
    NOTIFICATION_TYPES,
    COLUMNAS_NOTIFICACIONES,
    SECTORES_DISPONIBLES,
    TIPOS_RECLAMO,
    TECNICOS_DISPONIBLES,
    MATERIALES_POR_RECLAMO,
    ROUTER_POR_SECTOR,
    DEBUG_MODE
)

# Local components
from components.reclamos.nuevo import render_nuevo_reclamo
from components.reclamos.gestion import render_gestion_reclamos
from components.clientes.gestion import render_gestion_clientes
from components.reclamos.impresion import render_impresion_reclamos
from components.reclamos.planificacion import render_planificacion_grupos
from components.reclamos.cierre import render_cierre_reclamos
from components.resumen_jornada import render_resumen_jornada
from components.notifications import init_notification_manager
from components.notification_bell import render_notification_bell
from components.auth import has_permission, check_authentication, render_login
from components.navigation import render_sidebar_navigation, render_user_info
from components.metrics_dashboard import render_metrics_dashboard, metric_card
from components.ui import breadcrumb, metric_card, card, badge, loading_indicator
from utils.helpers import show_warning, show_error, show_success, show_info, format_phone_number, format_dni, get_current_datetime, format_datetime, truncate_text, is_valid_email, safe_float_conversion, safe_int_conversion, get_status_badge, format_currency, get_breadcrumb_icon

# Utils
from utils.styles import get_main_styles_v2, get_loading_spinner, loading_indicator
from utils.data_manager import safe_get_sheet_data, safe_normalize, update_sheet_data, batch_update_sheet
from utils.api_manager import api_manager, init_api_session_state
from utils.pdf_utils import agregar_pie_pdf
from utils.date_utils import parse_fecha, es_fecha_valida, format_fecha, ahora_argentina
from utils.permissions import has_permission

# CONFIGURACIÓN DE PÁGINA
st.set_page_config(
    page_title="Fusion Reclamos CRM",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "Sistema profesional de gestión de reclamos - Fusion CRM v2.3"
    }
)

# --------------------------
# FUNCIONES AUXILIARES OPTIMIZADAS
# --------------------------

def generar_id_unico():
    """Genera un ID único para reclamos"""
    import uuid
    return str(uuid.uuid4())[:8].upper()

def is_system_dark_mode():
    """Intenta detectar si el sistema está en modo oscuro"""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        if ctx is None:
            return False
        return st.session_state.get('modo_oscuro', False)
    except:
        return False

# --- 🔹 Funciones nuevas para persistencia de modo oscuro ---
MODO_OSCURO_KEY = "modo_oscuro"

def _coerce_bool(val):
    if isinstance(val, bool):
        return val
    if pd.isna(val):
        return False
    return str(val).strip().lower() in ("true", "verdadero", "si", "sí", "1", "yes", "y")

def init_modo_oscuro():
    """Inicializa st.session_state[MODO_OSCURO_KEY] desde df_usuarios si existe."""
    if MODO_OSCURO_KEY in st.session_state:
        return
    modo = is_system_dark_mode()
    df = st.session_state.get("df_usuarios")
    user_email = st.session_state.auth.get("user_info", {}).get("email")
    if df is not None and not df.empty and user_email:
        if "modo_oscuro" in df.columns:
            row = df[df["Email"] == user_email] if "Email" in df.columns else None
            if row is not None and not row.empty:
                modo = _coerce_bool(row.iloc[0].get("modo_oscuro", modo))
    st.session_state[MODO_OSCURO_KEY] = modo

def persist_modo_oscuro(new_value: bool):
    """Guarda la preferencia en sheet_usuarios."""
    df = st.session_state.get("df_usuarios")
    user_email = st.session_state.auth.get("user_info", {}).get("email")
    if df is None or not user_email:
        return False
    if "Email" in df.columns:
        row_index = df.index[df["Email"] == user_email]
        if not row_index.empty:
            idx = int(row_index[0])
            col_idx = df.columns.get_loc("modo_oscuro") if "modo_oscuro" in df.columns else None
            if col_idx is None:
                return False
            try:
                def _op(ws):
                    ws.update_cell(idx + 2, col_idx + 1, "TRUE" if new_value else "FALSE")
                api_manager.safe_sheet_operation(sheet_usuarios, _op)
                return True
            except Exception as e:
                logging.exception("Error persistiendo modo oscuro")
    return False

def _on_toggle_modo_oscuro():
    val = st.session_state.get(MODO_OSCURO_KEY, False)
    if persist_modo_oscuro(val):
        st.toast("Preferencia guardada ✅") if hasattr(st, "toast") else st.success("Preferencia guardada")
    else:
        st.info("Preferencia guardada solo en esta sesión")

# ------------------------------------------------------------

def is_mobile():
    """Detecta si la aplicación se está ejecutando en un dispositivo móvil"""
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    try:
        ctx = get_script_run_ctx()
        if ctx is None:
            return False
        user_agent = ctx.request.headers.get("User-Agent", "").lower()
        mobile_keywords = ['mobi', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone']
        return any(keyword in user_agent for keyword in mobile_keywords)
    except:
        return False

def migrar_uuids_existentes(sheet_reclamos, sheet_clientes):
    """Genera UUIDs para registros existentes que no los tengan"""
    try:
        if not sheet_reclamos or not sheet_clientes:
            st.error("No se pudo conectar a las hojas de cálculo")
            return False

        updates_reclamos = []
        updates_clientes = []
        
        # Para Reclamos
        if 'ID Reclamo' not in st.session_state.df_reclamos.columns:
            st.error("La columna 'ID Reclamo' no existe en los datos de reclamos")
            return False
            
        reclamos_sin_uuid = st.session_state.df_reclamos[
            st.session_state.df_reclamos['ID Reclamo'].isna() | 
            (st.session_state.df_reclamos['ID Reclamo'] == '')
        ]
        
        if not reclamos_sin_uuid.empty:
            with st.status("Generando UUIDs para reclamos...", expanded=True) as status:
                st.write(f"📋 {len(reclamos_sin_uuid)} reclamos sin UUID encontrados")
                
                for _, row in reclamos_sin_uuid.iterrows():
                    nuevo_uuid = generar_id_unico()
                    updates_reclamos.append({
                        "range": f"P{row.name + 2}",  # Usando row.name para precisión
                        "values": [[nuevo_uuid]]
                    })
                
                batch_size = 50
                total_batches = (len(updates_reclamos) // batch_size) + 1
                
                for i in range(0, len(updates_reclamos), batch_size):
                    batch = updates_reclamos[i:i + batch_size]
                    progress = min((i + batch_size) / len(updates_reclamos), 1.0)
                    status.update(label=f"Actualizando reclamos... {progress:.0%}", state="running")
                    
                    success, error = api_manager.safe_sheet_operation(
                        batch_update_sheet,
                        sheet_reclamos,
                        batch,
                        is_batch=True
                    )
                    if not success:
                        st.error(f"Error al actualizar lote de reclamos: {error}")
                        return False
                
                status.update(label="✅ UUIDs para reclamos completados", state="complete", expanded=False)

        # Para Clientes
        if 'ID Cliente' not in st.session_state.df_clientes.columns:
            st.error("La columna 'ID Cliente' no existe en los datos de clientes")
            return False
            
        clientes_sin_uuid = st.session_state.df_clientes[
            st.session_state.df_clientes['ID Cliente'].isna() | 
            (st.session_state.df_clientes['ID Cliente'] == '')
        ]
        
        if not clientes_sin_uuid.empty:
            with st.status("Generando UUIDs para clientes...", expanded=True) as status:
                st.write(f"👥 {len(clientes_sin_uuid)} clientes sin UUID encontrados")
                
                for _, row in clientes_sin_uuid.iterrows():
                    nuevo_uuid = generar_id_unico()
                    updates_clientes.append({
                        "range": f"G{row.name + 2}",  # Usando row.name para precisión
                        "values": [[nuevo_uuid]]
                    })
                
                batch_size = 50
                total_batches = (len(updates_clientes) // batch_size) + 1
                
                for i in range(0, len(updates_clientes), batch_size):
                    batch = updates_clientes[i:i + batch_size]
                    progress = min((i + batch_size) / len(updates_clientes), 1.0)
                    status.update(label=f"Actualizando clientes... {progress:.0%}", state="running")
                    
                    success, error = api_manager.safe_sheet_operation(
                        batch_update_sheet,
                        sheet_clientes,
                        batch,
                        is_batch=True
                    )
                    if not success:
                        st.error(f"Error al actualizar lote de clientes: {error}")
                        return False
                
                status.update(label="✅ UUIDs para clientes completados", state="complete", expanded=False)

        if not updates_reclamos and not updates_clientes:
            st.info("ℹ️ Todos los registros ya tienen UUIDs asignados")
            return False

        # Actualizar los DataFrames en caché
        st.session_state.df_reclamos = safe_get_sheet_data(sheet_reclamos, COLUMNAS_RECLAMOS)
        st.session_state.df_clientes = safe_get_sheet_data(sheet_clientes, COLUMNAS_CLIENTES)
        
        return True

    except Exception as e:
        st.error(f"❌ Error en la migración de UUIDs: {str(e)}")
        if DEBUG_MODE:
            st.exception(e)
        return False

# --------------------------
# CONEXIÓN CON GOOGLE SHEETS
# --------------------------
@st.cache_resource(ttl=3600)
def init_google_sheets():
    """Conexión optimizada a Google Sheets con retry automático"""
    @retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(3))
    def _connect():
        creds = service_account.Credentials.from_service_account_info(
            {**st.secrets["gcp_service_account"], "private_key": st.secrets["gcp_service_account"]["private_key"].replace("\\n", "\n")},
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        sheet_notifications = client.open_by_key(SHEET_ID).worksheet(WORKSHEET_NOTIFICACIONES)
        init_notification_manager(sheet_notifications)
        return (
            client.open_by_key(SHEET_ID).worksheet(WORKSHEET_RECLAMOS),
            client.open_by_key(SHEET_ID).worksheet(WORKSHEET_CLIENTES),
            client.open_by_key(SHEET_ID).worksheet(WORKSHEET_USUARIOS),
            sheet_notifications
        )
    try:
        return _connect()
    except Exception as e:
        st.error(f"Error de conexión: {str(e)}")
        st.stop()

def precache_all_data(sheet_reclamos, sheet_clientes, sheet_usuarios, sheet_notifications):
    _ = safe_get_sheet_data(sheet_reclamos, COLUMNAS_RECLAMOS)
    _ = safe_get_sheet_data(sheet_clientes, COLUMNAS_CLIENTES)
    _ = safe_get_sheet_data(sheet_usuarios, COLUMNAS_USUARIOS)
    _ = safe_get_sheet_data(sheet_notifications, COLUMNAS_NOTIFICACIONES)

loading_placeholder = st.empty()
loading_placeholder.markdown(get_loading_spinner(), unsafe_allow_html=True)
try:
    sheet_reclamos, sheet_clientes, sheet_usuarios, sheet_notifications = init_google_sheets()
    if not all([sheet_reclamos, sheet_clientes, sheet_usuarios, sheet_notifications]):
        st.stop()
finally:
    loading_placeholder.empty()

if not check_authentication():
    render_login(sheet_usuarios)
    st.stop()
    
# ✅ Datos del usuario actual
user_info = st.session_state.auth.get('user_info', {})
user_role = user_info.get('rol', '')

precache_all_data(sheet_reclamos, sheet_clientes, sheet_usuarios, sheet_notifications)

df_reclamos, df_clientes, df_usuarios = safe_get_sheet_data(sheet_reclamos, COLUMNAS_RECLAMOS), safe_get_sheet_data(sheet_clientes, COLUMNAS_CLIENTES), safe_get_sheet_data(sheet_usuarios, COLUMNAS_USUARIOS)
st.session_state.df_reclamos = df_reclamos
st.session_state.df_clientes = df_clientes
st.session_state.df_usuarios = df_usuarios

# --------------------------
# CONFIGURACIÓN DE PÁGINA
# --------------------------
# Navegación optimizada
if is_mobile():
    opcion = st.selectbox(
        "Menú principal",
        options=["Inicio", "Reclamos cargados", "Cierre de Reclamos"],
        index=0,
        key="mobile_nav"
    )
else:
    opcion = st.session_state.get('current_page', 'Inicio')

# 🔹 Inicializar modo oscuro con preferencia persistida
init_modo_oscuro()

st.markdown(get_main_styles_v2(dark_mode=st.session_state.modo_oscuro), unsafe_allow_html=True)

# --------------------------
# SIDEBAR
# --------------------------
with st.sidebar:
    # Header del sidebar
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0; border-bottom: 1px solid var(--border-color); margin-bottom: 1rem;">
        <h2 style="margin: 0; color: var(--primary-color);">📋 Fusion CRM</h2>
        <p style="color: var(--text-secondary); margin: 0.25rem 0 0 0; font-size: 0.9rem;">
            Panel de Control
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Información de usuario
    render_user_info()

    # Selector de modo oscuro
    col1, col2 = st.columns([1, 3])
    with col1:
        st.markdown("<div style='font-size: 1.5rem;'>🌙</div>", unsafe_allow_html=True)
    with col2:
        st.checkbox("Modo oscuro", value=st.session_state.modo_oscuro,
                    key=MODO_OSCURO_KEY, on_change=_on_toggle_modo_oscuro,
                    help="Cambiar entre tema claro y oscuro", label_visibility="visible")
    
    # Notificaciones
    if st.session_state.auth.get("logged_in", False):
        render_notification_bell()
    
    st.markdown("---")
    
    # Navegación profesional
    render_sidebar_navigation()
    
    # Herramientas de administrador (solo visible para admins)
    if user_role == 'admin':
        st.markdown("---")
        st.markdown("**🔧 Herramientas Admin**")
        if st.button("🆔 Generar UUIDs para registros", 
                    help="Genera IDs únicos para registros existentes que no los tengan",
                    disabled=st.session_state.get('uuid_migration_in_progress', False),
                    use_container_width=True):
            st.session_state.uuid_migration_in_progress = True
            with st.spinner("Migrando UUIDs..."):
                if migrar_uuids_existentes(sheet_reclamos, sheet_clientes):
                    st.rerun()
            st.session_state.uuid_migration_in_progress = False
    
    # En el sidebar, mejora el footer:
    st.markdown(
        f"""
        <div style="margin-top: 2rem; padding: 1rem; background: var(--bg-surface); border-radius: var(--radius-lg); border: 1px solid var(--border-color);">
            <div style="text-align: center; margin-bottom: 1rem;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">⚡</div>
                <p style="margin:0; font-size: 0.9rem; color: var(--text-secondary);"><strong>Versión:</strong> 2.3.0</p>
                <p style="margin:0; font-size: 0.8rem; color: var(--text-muted);">Última actualización</p>
                <p style="margin:0; font-size: 0.9rem; color: var(--primary-color); font-weight: 600;">
                    {ahora_argentina().strftime('%d/%m/%Y %H:%M')}
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <hr style="border:1px solid var(--border-light); margin:1rem 0;" />
        <div style="text-align:center; font-size:0.8rem; color: var(--text-muted);">
            Desarrollado con 💜<br>por  
            <a href="https://instagram.com/mellamansebax" target="_blank" 
               style="color: var(--primary-color); text-decoration:none; font-weight:600;">
               Sebastián Andrés
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )

# --------------------------
# INICIALIZACIÓN
# --------------------------

class AppState:
    def __init__(self):
        self._init_state()
        
    def _init_state(self):
        """Inicializa todos los estados necesarios"""
        defaults = {
            'app_initialized': False,
            'df_reclamos': pd.DataFrame(),
            'df_clientes': pd.DataFrame(),
            'last_update': None,
            'modo_oscuro': is_system_dark_mode(),
            'uuid_migration_in_progress': False
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

app_state = AppState()

# --------------------------
# CARGA DE DATOS OPTIMIZADA
# --------------------------

@st.cache_data(ttl=30, show_spinner=False)
def cargar_datos():
    """Carga datos de Google Sheets con manejo robusto de nombres y fechas."""
    try:
        loading_placeholder = st.empty()
        loading_placeholder.markdown(get_loading_spinner(), unsafe_allow_html=True)

        df_reclamos = safe_get_sheet_data(sheet_reclamos, COLUMNAS_RECLAMOS)
        df_clientes = safe_get_sheet_data(sheet_clientes, COLUMNAS_CLIENTES)
        df_usuarios = safe_get_sheet_data(sheet_usuarios, COLUMNAS_USUARIOS)

        if df_reclamos.empty:
            show_warning("La hoja de reclamos está vacía o no se pudo cargar")
        if df_clientes.empty:
            show_warning("La hoja de clientes está vacía o no se pudo cargar")
        if df_reclamos.empty or df_clientes.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # --- Normalizar nombres de columnas (quitar espacios)
        df_reclamos.columns = [str(c).strip() for c in df_reclamos.columns]
        df_clientes.columns = [str(c).strip() for c in df_clientes.columns]
        df_usuarios.columns = [str(c).strip() for c in df_usuarios.columns]

        # --- Detectar variantes y renombrar ---
        import re
        def _canon(colname):
            return re.sub(r'[^a-z0-9]', '', str(colname).lower())

        # Mapeo a "Fecha_formateada"
        for col in list(df_reclamos.columns):
            if _canon(col) in ("fechaformateada","fechadecierre","fechacierre","fecha_cierre","fechacierrehora"):
                if col != "Fecha_formateada":
                    df_reclamos.rename(columns={col: "Fecha_formateada"}, inplace=True)
                break

        # Mapeo a "Fecha y hora"
        for col in list(df_reclamos.columns):
            if _canon(col) in ("fechayhora","fechahora","fechaingreso","fechaingresohora","fecha_hora"):
                if col != "Fecha y hora":
                    df_reclamos.rename(columns={col: "Fecha y hora"}, inplace=True)
                break

        # Normalizaciones simples
        for col in ["Nº Cliente", "N° de Precinto"]:
            if col in df_clientes.columns:
                df_clientes[col] = df_clientes[col].astype(str).str.strip()
            if col in df_reclamos.columns:
                df_reclamos[col] = df_reclamos[col].astype(str).str.strip()

        # Parseo seguro: Fecha y hora (ingreso)
        if "Fecha y hora" in df_reclamos.columns:
            df_reclamos["Fecha y hora"] = df_reclamos["Fecha y hora"].apply(
                lambda x: parse_fecha(x) if not pd.isna(x) else pd.NaT
            )

        # Parseo robusto: Fecha_formateada (cierre)
        import numpy as np
        if "Fecha_formateada" in df_reclamos.columns:
            raw = df_reclamos["Fecha_formateada"].copy()
            # Limpieza inicial
            df_reclamos["Fecha_formateada"] = (
                raw.astype(str)
                .str.replace(r"\s+", " ", regex=True)
                .str.strip()
                .replace({"": np.nan, "nan": np.nan, "NaN": np.nan})
            )
            # Intentar parseo con pandas
            df_reclamos["Fecha_formateada"] = pd.to_datetime(
                df_reclamos["Fecha_formateada"],
                errors="coerce",
                dayfirst=True,
                infer_datetime_format=True
            )
        else:
            df_reclamos["Fecha_formateada"] = pd.NaT

        return df_reclamos, df_clientes, df_usuarios

    except Exception as e:
        show_error(f"Error al cargar datos: {str(e)}")
        if DEBUG_MODE:
            st.exception(e)
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    finally:
        loading_placeholder.empty()

df_reclamos, df_clientes, df_usuarios = cargar_datos()
st.session_state.df_reclamos = df_reclamos
st.session_state.df_clientes = df_clientes
st.session_state.df_usuarios = df_usuarios

# --------------------------
# INTERFAZ PRINCIPAL OPTIMIZADA
# --------------------------

st.markdown("""
<div style="text-align: center; padding: 2.5rem 0; background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-primary) 100%); border-radius: var(--radius-xl); margin: 2rem 0; border: 1px solid var(--border-color); box-shadow: var(--shadow-lg);">
    <h1 style="margin: 0; background: linear-gradient(135deg, #66D9EF 0%, #F92672 30%, #A6E22E 70%, #AE81FF 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.8rem;">
        Fusion Reclamos CRM
    </h1>
    <div style="margin-top: 1rem;">
        <span style="background: var(--primary-color); color: #272822; padding: 0.25rem 1rem; border-radius: var(--radius-md); font-size: 0.9rem; font-weight: 500;">
            Sistema profesional en gestión de Reclamos
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# Dashboard de métricas
render_metrics_dashboard(df_reclamos, is_mobile=is_mobile())

# BREADCRUMB DE NAVEGACIÓN mejorado
st.markdown(f"""
<div style="
    display: flex; 
    align-items: center; 
    gap: 0.5rem; 
    margin: 2rem 0 1.5rem 0; 
    padding: 1.25rem; 
    background: var(--bg-card); 
    border-radius: var(--radius-xl); 
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-sm);
    font-size: 0.95rem;
">
    <span style="color: var(--text-muted); display: flex; align-items: center; gap: 0.5rem;">
        <span style="font-size: 1.2rem;">📋</span>
        <span>Navegación:</span>
    </span>
    <span style="color: var(--primary-color); display: flex; align-items: center; gap: 0.5rem; font-weight: 600;">
        <span style="font-size: 1.1rem;">{get_breadcrumb_icon(opcion)}</span>
        <span>{opcion}</span>
    </span>
    <div style="flex: 1;"></div>
    <span style="color: var(--text-muted); font-size: 0.85rem;">
        {ahora_argentina().strftime('%d/%m/%Y %H:%M')}
    </span>
</div>
""", unsafe_allow_html=True)

# --------------------------
# RUTEO DE COMPONENTES
# --------------------------

COMPONENTES = {
    "Inicio": {
        "render": render_nuevo_reclamo,
        "permiso": "inicio",
        "params": {
            "df_reclamos": df_reclamos,
            "df_clientes": df_clientes,
            "sheet_reclamos": sheet_reclamos,
            "sheet_clientes": sheet_clientes,
            "current_user": user_info.get('nombre', '')
        }
    },
    "Reclamos cargados": {
        "render": render_gestion_reclamos,
        "permiso": "reclamos_cargados",
        "params": {
            "df_reclamos": df_reclamos,
            "df_clientes": df_clientes,
            "sheet_reclamos": sheet_reclamos,
            "user": user_info
        }
    },
    "Gestión de clientes": {
        "render": render_gestion_clientes,
        "permiso": "gestion_clientes",
        "params": {
            "df_clientes": df_clientes,
            "df_reclamos": df_reclamos,
            "sheet_clientes": sheet_clientes,
            "user_role": user_info.get('rol', '')
        }
    },
    "Imprimir reclamos": {
        "render": render_impresion_reclamos,
        "permiso": "imprimir_reclamos",
        "params": {
            "df_clientes": df_clientes,
            "df_reclamos": df_reclamos,
            "user": user_info
        }
    },
    "Seguimiento técnico": {
        "render": render_planificacion_grupos,
        "permiso": "seguimiento_tecnico",
        "params": {
            "df_reclamos": df_reclamos,
            "sheet_reclamos": sheet_reclamos,
            "user": user_info
        }
    },
    "Cierre de Reclamos": {
        "render": render_cierre_reclamos,
        "permiso": "cierre_reclamos",
        "params": {
            "df_reclamos": df_reclamos,
            "df_clientes": df_clientes,
            "sheet_reclamos": sheet_reclamos,
            "sheet_clientes": sheet_clientes,
            "user": user_info
        }
    }
}

# Renderizar componente seleccionado
if opcion in COMPONENTES and has_permission(COMPONENTES[opcion]["permiso"]):
    with st.container():
        st.markdown("---")
        resultado = COMPONENTES[opcion]["render"](**COMPONENTES[opcion]["params"])
        
        if resultado and resultado.get('needs_refresh'):
            st.cache_data.clear()
            time.sleep(1)
            st.rerun()

# --------------------------
# RESUMEN DE JORNADA OPTIMIZADO
# --------------------------
with st.container():
    render_resumen_jornada(df_reclamos)
    st.markdown('</div>', unsafe_allow_html=True)