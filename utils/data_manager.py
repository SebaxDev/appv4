"""
Gestor de datos para operaciones con Google Sheets
Versión mejorada con manejo robusto de datos
"""
import pandas as pd
import streamlit as st
from utils.api_manager import api_manager

@st.cache_data(ttl=30)
def safe_get_sheet_data(_sheet, columnas=None):
    """Carga datos de una hoja de forma segura"""
    try:
        data, error = api_manager.safe_sheet_operation(_sheet.get_all_values)
        if error:
            st.error(f"Error al obtener datos: {error}")
            return pd.DataFrame(columns=columnas)
        
        if len(data) <= 1:
            return pd.DataFrame(columns=columnas)
        
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)

        for col in columnas:
            if col not in df.columns:
                df[col] = None
        
        return df[columnas]
    
    except Exception as e:
        st.error(f"Error crítico al cargar datos: {str(e)}")
        return pd.DataFrame(columns=columnas)

def safe_normalize(df, column):
    """Normaliza una columna de forma segura"""
    if column in df.columns:
        df[column] = df[column].apply(
            lambda x: str(int(x)).strip() if isinstance(x, (int, float)) else str(x).strip()
        )
    return df

def update_sheet_data(sheet, data, is_batch=True):
    """Actualiza datos en una hoja con control de rate limiting"""
    try:
        if isinstance(data, list) and len(data) > 1:
            # Operación batch
            result, error = api_manager.safe_sheet_operation(
                sheet.clear, is_batch=True
            )
            if error:
                return False, error
            
            result, error = api_manager.safe_sheet_operation(
                sheet.append_row, data[0], is_batch=True
            )
            if error:
                return False, error
            
            if len(data) > 1:
                result, error = api_manager.safe_sheet_operation(
                    sheet.append_rows, data[1:], is_batch=True
                )
                if error:
                    return False, error
        else:
            # Operación simple
            result, error = api_manager.safe_sheet_operation(
                sheet.append_row, data, is_batch=False
            )
            if error:
                return False, error
        
        return True, None
    except Exception as e:
        return False, str(e)

def batch_update_sheet(sheet, updates):
    """Realiza múltiples actualizaciones en batch"""
    try:
        result, error = api_manager.safe_sheet_operation(
            sheet.batch_update, updates, is_batch=True
        )
        return result is not None, error
    except Exception as e:
        return False, str(e)