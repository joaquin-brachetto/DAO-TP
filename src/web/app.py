"""Aplicación web (Flask).

El navegador muestra las pantallas (`static/`) y le pide los datos a esta API JSON. Las rutas
no tienen reglas de negocio ni SQL: leen lo que manda el navegador, llaman a los mismos servicios
que usa el resto del sistema y devuelven el resultado. Si un servicio lanza un `ErrorDeNegocio`
(stock insuficiente, SKU repetido, etc.), la API responde 400 con el mensaje para el usuario.
"""

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask.json.provider import DefaultJSONProvider

from src.excepciones import EntidadNoEncontradaError, ErrorDeNegocio
from src.persistencia.conexion import BaseDeDatos
from src.web.rutas_administracion import bp as administracion
from src.web.rutas_inicio import bp as inicio
from src.web.rutas_inventario import bp as inventario
from src.web.rutas_logistica import bp as logistica
from src.web.rutas_reportes import bp as reportes
from src.web.rutas_ventas import bp as ventas
from src.web.servicios import Servicios

CARPETA_ESTATICA = Path(__file__).resolve().parent / "static"


class ProveedorJSON(DefaultJSONProvider):
    """Convierte a JSON los tipos que usan los servicios: Decimal, fechas, enums y filas de SQLite."""

    ensure_ascii = False
    sort_keys = False

    @staticmethod
    def default(objeto):
        if isinstance(objeto, Decimal):
            return float(objeto)
        if isinstance(objeto, (datetime, date)):
            return objeto.isoformat()
        if isinstance(objeto, Enum):
            return objeto.value
        if isinstance(objeto, sqlite3.Row):
            return dict(objeto)
        return DefaultJSONProvider.default(objeto)


def crear_app(db: BaseDeDatos | None = None) -> Flask:
    db = db or BaseDeDatos()
    db.inicializar_esquema()

    app = Flask(__name__, static_folder=str(CARPETA_ESTATICA), static_url_path="/static")
    app.json = ProveedorJSON(app)
    app.extensions["servicios"] = Servicios(db)

    for blueprint in (inicio, administracion, inventario, logistica, ventas, reportes):
        app.register_blueprint(blueprint, url_prefix="/api")

    @app.get("/")
    def pagina():
        return send_from_directory(CARPETA_ESTATICA, "index.html")

    @app.errorhandler(EntidadNoEncontradaError)
    def no_encontrado(error):
        return jsonify(error=str(error)), 404

    @app.errorhandler(ErrorDeNegocio)
    def error_de_negocio(error):
        return jsonify(error=str(error)), 400

    return app
