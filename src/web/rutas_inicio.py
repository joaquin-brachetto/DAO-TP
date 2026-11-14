"""Inicio, catálogo general y carga de datos de prueba."""

from flask import Blueprint, jsonify

from src.datos_prueba import cargar_datos_de_prueba
from src.datos_prueba_inventario import cargar_stock_de_prueba
from src.datos_prueba_logistica import cargar_logistica_de_prueba
from src.excepciones import ValidacionError
from src.web.utiles import servicios

bp = Blueprint("inicio", __name__)


def ubicacion_json(u) -> dict:
    return {
        "id": u.id, "codigo": u.codigo, "nombre": u.nombre, "tipo": str(u.tipo),
        "direccion": u.direccion or "", "telefono": u.telefono or "",
        "punto_venta": getattr(u, "punto_venta", None), "activa": u.activa,
    }


@bp.get("/catalogo")
def catalogo():
    """Todo lo que las pantallas necesitan para mostrar nombres y armar listas desplegables."""
    s = servicios()
    productos = s.productos.listar(incluir_inactivos=True)
    return jsonify(
        ubicaciones=[ubicacion_json(u) for u in s.ubicaciones.listar(incluir_inactivas=True)],
        categorias=[{"id": c.id, "nombre": c.nombre, "descripcion": c.descripcion or ""} for c in s.categorias.listar()],
        productos=[
            {
                "id": p.id, "sku": p.sku, "nombre": p.nombre, "categoria_id": p.categoria_id,
                "costo": p.costo_actual, "precio": p.precio_venta_actual,
                "descripcion": p.descripcion or "", "activo": p.activo,
                "proveedores": [r.proveedor_id for r in s.productos.proveedores_de(p.id)],
            }
            for p in productos
        ],
        proveedores=[
            {"id": p.id, "cuit": p.cuit, "razon_social": p.razon_social, "email": p.email or "",
             "telefono": p.telefono or "", "direccion": p.direccion or "", "activo": p.activo}
            for p in s.proveedores.listar(incluir_inactivos=True)
        ],
        clientes=[
            {"id": c.id, "documento": c.documento, "nombre": c.nombre, "condicion_iva": str(c.condicion_iva)}
            for c in s.ventas.listar_clientes()
        ],
        datos=s.tablero.datos_cargados(),
    )


@bp.get("/inicio")
def inicio():
    return jsonify(servicios().tablero.resumen())


PASOS_DATOS_PRUEBA = {
    "maestros": lambda s: cargar_datos_de_prueba(s.db),
    "stock": lambda s: cargar_stock_de_prueba(s.db),
    "logistica": lambda s: cargar_logistica_de_prueba(s.db, s.stock),
}


@bp.post("/datos-prueba/<paso>")
def datos_prueba(paso: str):
    """Carga los datos de prueba en orden: maestros, stock inicial y logística."""
    cargar = PASOS_DATOS_PRUEBA.get(paso)
    if cargar is None:
        raise ValidacionError(f"Paso de datos de prueba desconocido: {paso}.")
    return jsonify(creados=cargar(servicios()))
