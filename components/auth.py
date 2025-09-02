"""
Componente de autenticación profesional estilo CRM
Versión mejorada con diseño elegante
"""
"""
Componente de autenticación profesional estilo CRM
Versión mejorada con diseño elegante
"""
import streamlit as st
from utils.data_manager import safe_get_sheet_data
from config.settings import (
    WORKSHEET_USUARIOS,
    COLUMNAS_USUARIOS,
    PERMISOS_POR_ROL
)
import time
from utils.styles import get_loading_spinner
from passlib.context import CryptContext

# Configura el contexto de hasheo de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def init_auth_session():
    """Inicializa las variables de sesión"""
    if 'auth' not in st.session_state:
        st.session_state.auth = {
            'logged_in': False,
            'user_info': None
        }

def logout():
    """Cierra la sesión del usuario"""
    st.session_state.auth = {'logged_in': False, 'user_info': None}
    st.cache_data.clear()  # Limpiar caché de datos

def verify_credentials(username, password, sheet_usuarios):
    """Verifica las credenciales del usuario usando hasheo de contraseñas."""
    try:
        df_usuarios = safe_get_sheet_data(sheet_usuarios, COLUMNAS_USUARIOS)
        
        # Normalización de datos
        df_usuarios["username"] = df_usuarios["username"].str.strip().str.lower()
        
        # Manejo flexible de campo 'activo'
        df_usuarios["activo"] = df_usuarios["activo"].astype(str).str.upper().isin(["SI", "TRUE", "1", "SÍ", "VERDADERO"])
        
        # Busca el usuario por nombre de usuario
        user_data = df_usuarios[df_usuarios["username"] == username.strip().lower()]
        
        if not user_data.empty:
            # Extrae la primera fila de datos del usuario
            usuario = user_data.iloc[0]

            # Verifica si el usuario está activo
            if not usuario["activo"]:
                return None  # Usuario inactivo

            # Verifica la contraseña usando el hash
            stored_hash = usuario["password_hash"]
            if pwd_context.verify(password, stored_hash):
                return {
                    "username": usuario["username"],
                    "nombre": usuario["nombre"],
                    "rol": usuario["rol"].lower(),
                    "permisos": PERMISOS_POR_ROL.get(usuario["rol"].lower(), {}).get('permisos', [])
                }

    except Exception as e:
        st.error(f"Error en autenticación: {str(e)}")
    return None

def render_login(sheet_usuarios):
    """Formulario de login con diseño profesional CRM"""
    
    # CSS personalizado para el login (mantener igual)
    login_styles = """
    <style>
    .login-container {
        max-width: 400px;
        margin: 60px auto;
        padding: 40px;
        background: var(--bg-card);
        border-radius: var(--radius-xl);
        border: 1px solid var(--border-color);
        box-shadow: var(--shadow-lg);
        text-align: center;
    }
    
    .login-header {
        margin-bottom: 30px;
    }
    
    .login-logo {
        font-size: 3.5rem;
        margin-bottom: 15px;
        background: linear-gradient(135deg, #66D9EF 0%, #F92672 30%, #A6E22E 70%, #AE81FF 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .login-title {
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 10px;
        color: var(--text-primary);
    }
    
    .login-subtitle {
        color: var(--text-secondary);
        margin-bottom: 30px;
        font-size: 0.95rem;
    }
    
    .login-form {
        text-align: left;
    }
    
    .login-input {
        margin-bottom: 20px;
    }
    
    .login-button {
        width: 100%;
        margin-top: 10px;
        padding: 12px;
        font-size: 1rem;
        font-weight: 600;
    }
    
    .login-footer {
        margin-top: 30px;
        padding-top: 20px;
        border-top: 1px solid var(--border-light);
        color: var(--text-muted);
        font-size: 0.85rem;
    }
    
    .login-error {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.3);
        color: #EF4444;
        padding: 12px;
        border-radius: var(--radius-md);
        margin: 15px 0;
        text-align: center;
    }
    
    .login-success {
        background: rgba(16, 185, 129, 0.1);
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #10B981;
        padding: 12px;
        border-radius: var(--radius-md);
        margin: 15px 0;
        text-align: center;
    }
    </style>
    """
    
    st.markdown("""
    <div class="login-container">
        <div class="login-header">
            <h1 class="login-title">Fusion CRM</h1>
        </div>
    """, unsafe_allow_html=True)
    
    # Inicializar estado de carga
    if 'login_loading' not in st.session_state:
        st.session_state.login_loading = False
    if 'login_attempt' not in st.session_state:
        st.session_state.login_attempt = False
    if 'login_username' not in st.session_state:
        st.session_state.login_username = ""
    if 'login_password' not in st.session_state:
        st.session_state.login_password = ""
    
    # Mostrar spinner si está cargando
    if st.session_state.login_loading:
        st.markdown(get_loading_spinner(), unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align: center; margin-top: 20px;">
            <p style="color: var(--text-secondary);">Verificando credenciales...</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Procesar la autenticación
        try:
            user_info = verify_credentials(
                st.session_state.login_username, 
                st.session_state.login_password, 
                sheet_usuarios
            )
            
            if user_info:
                st.session_state.auth = {
                    'logged_in': True,
                    'user_info': user_info
                }
                st.session_state.login_loading = False
                st.session_state.login_attempt = False
                st.rerun()
            else:
                st.session_state.login_loading = False
                st.session_state.login_attempt = True
                st.rerun()
                
        except Exception as e:
            st.session_state.login_loading = False
            st.session_state.login_attempt = True
            st.error(f"Error en autenticación: {str(e)}")
            st.rerun()
    
    else:
        # Mostrar mensaje de error si hubo un intento fallido
        if st.session_state.login_attempt:
            st.error("❌ Credenciales incorrectas o usuario inactivo")
            st.session_state.login_attempt = False
        
        # Formulario de login
        with st.form("login_formulario"):
            st.markdown('<div class="login-form">', unsafe_allow_html=True)
            
            # Campo de usuario con icono
            col1, col2 = st.columns([1, 10])
            with col1:
                st.markdown('<div style="font-size: 1.5rem; padding-top: 10px;">👤</div>', unsafe_allow_html=True)
            with col2:
                username = st.text_input("Usuario", placeholder="Ingresa tu usuario", 
                                       value=st.session_state.login_username,
                                       label_visibility="collapsed").strip()
            
            # Campo de contraseña con icono
            col1, col2 = st.columns([1, 10])
            with col1:
                st.markdown('<div style="font-size: 1.5rem; padding-top: 10px;">🔒</div>', unsafe_allow_html=True)
            with col2:
                password = st.text_input("Contraseña", type="password", 
                                       placeholder="Ingresa tu contraseña", 
                                       value=st.session_state.login_password,
                                       label_visibility="collapsed")
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            if st.form_submit_button("🚀 Ingresar al sistema", use_container_width=True):
                if not username or not password:
                    st.error("⚠️ Usuario y contraseña son requeridos")
                else:
                    # Guardar credenciales y activar loading
                    st.session_state.login_username = username
                    st.session_state.login_password = password
                    st.session_state.login_loading = True
                    st.rerun()
    
    st.markdown("""
        <div class="login-footer">
            <p>© 2025 Fusion CRM • v2.3.0</p>
            <p style="font-size: 0.8rem; margin-top: 5px;">Sistema optimizado para gestión eficiente</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Procesar login después del render
    if st.session_state.login_loading:
        time.sleep(0.5)  # Pequeña pausa para el efecto visual
        user_info = verify_credentials(username, password, sheet_usuarios)
        
        if user_info:
            st.session_state.auth = {
                'logged_in': True,
                'user_info': user_info
            }
            st.session_state.login_loading = False
            st.success(f"✅ Bienvenido, {user_info['nombre']}!")
            time.sleep(1)
            st.rerun()
        else:
            st.session_state.login_loading = False
            st.error("❌ Credenciales incorrectas o usuario inactivo")
            time.sleep(2)
            st.rerun()

def check_authentication():
    """Verifica si el usuario está autenticado"""
    init_auth_session()
    return st.session_state.auth['logged_in']

def has_permission(required_permission):
    """Verifica permisos del usuario"""
    if not check_authentication():
        return False
        
    user_info = st.session_state.auth.get('user_info')
    if not user_info:
        return False
        
    # Admin tiene acceso completo
    if user_info['rol'] == 'admin':
        return True
        
    return required_permission in user_info.get('permisos', [])

def render_user_info():
    """Versión mejorada con iconos y estilo"""
    if not check_authentication():
        return
        
    user_info = st.session_state.auth['user_info']
    role_config = {
        'admin': {'icon': '👑', 'color': '#FF5733', 'badge': 'Administrador'},
        'oficina': {'icon': '💼', 'color': '#338AFF', 'badge': 'Oficina'},
        'tecnico': {'icon': '🔧', 'color': '#10B981', 'badge': 'Técnico'},
        'supervisor': {'icon': '👔', 'color': '#8B5CF6', 'badge': 'Supervisor'}
    }
    
    config = role_config.get(user_info['rol'].lower(), {'icon': '👤', 'color': '#555', 'badge': 'Usuario'})
    
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 20px;">
            <div style="font-size: 3rem; margin-bottom: 10px; background: linear-gradient(135deg, {config['color']}, #66D9EF); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                {config['icon']}
            </div>
            <h3 style="margin: 0; color: var(--text-primary); font-weight: 600;">{user_info['nombre']}</h3>
            <div style="background: rgba({int(config['color'][1:3], 16)}, {int(config['color'][3:5], 16)}, {int(config['color'][5:7], 16)}, 0.15); 
                      color: {config['color']}; 
                      padding: 4px 12px; 
                      border-radius: 20px; 
                      font-size: 0.8rem; 
                      font-weight: 600;
                      margin: 8px 0;
                      display: inline-block;
                      border: 1px solid rgba({int(config['color'][1:3], 16)}, {int(config['color'][3:5], 16)}, {int(config['color'][5:7], 16)}, 0.3);">
                {config['badge']}
            </div>
            <p style="color: var(--text-secondary); margin: 5px 0; font-size: 0.9rem;">
                @{user_info['username']}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚪 Cerrar sesión", use_container_width=True, key="logout_btn"):
            logout()
            st.rerun()
        st.markdown("---")