"""Configuración general de la aplicación."""

import os
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

# Se puede cambiar con la variable de entorno DAO_TP_BD (por ejemplo, para usar otra base de prueba).
RUTA_BD = Path(os.environ.get("DAO_TP_BD", RAIZ_PROYECTO / "datos" / "ventas.db"))

# Carpeta con los scripts SQL del esquema. Se ejecutan en orden alfabético.
CARPETA_ESQUEMA = Path(__file__).resolve().parent / "persistencia" / "esquema"

TITULO_APP = "Sistema de Ventas e Inventario"
