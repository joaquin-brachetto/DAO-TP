"""Inventario: stock por ubicación, alertas, compras, necesidades y órdenes de reposición."""

from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, jsonify

from src.dominio.inventario.modelos import OrigenNecesidad, nombre_estado
from src.reportes.inventario_reporte import NOMBRE_TIPO, ReporteMovimientos, Sentido
from src.web.utiles import arg_entero, cuerpo, decimal, entero, servicios

bp = Blueprint("inventario", __name__)

DIAS_DE_MOVIMIENTOS = 365


def ok(**datos):
    return jsonify(ok=True, **datos)


# --- Stock por ubicación ----------------------------------------------------------------------------


@bp.get("/stock")
def stock_de_ubicacion():
    s = servicios()
    ubicacion_id = arg_entero("ubicacion", "Ubicación", opcional=False)
    minimos = s.minimos.de_ubicacion(ubicacion_id)
    filas = []
    for producto in s.productos.listar():
        stock = s.stock.stock_de(ubicacion_id, producto.id)
        filas.append({
            "producto_id": producto.id,
            "disponible": stock.cantidad_disponible,
            "pendiente": stock.cantidad_pendiente,
            "merma": stock.cantidad_merma,
            "minimo": minimos.get(producto.id, 0),
        })
    hoy = date.today()
    movimientos = ReporteMovimientos(s.db).consultar(
        hoy - timedelta(days=DIAS_DE_MOVIMIENTOS), hoy, ubicacion_id=ubicacion_id
    ).movimientos
    return jsonify(
        filas=filas,
        movimientos=[
            {
                "fecha": m.fecha_hora, "producto_id": m.producto_id, "tipo": NOMBRE_TIPO[m.tipo],
                "cantidad": -m.cantidad if m.sentido == Sentido.SALIDA else m.cantidad,
                "documento": m.documento,
            }
            for m in sorted(movimientos, key=lambda m: m.fecha_hora, reverse=True)
        ],
        alertas=[
            {"producto_id": a.producto_id, "disponible": a.disponible, "minimo": a.minimo, "fecha": a.fecha_hora}
            for a in s.alertas.alertas() if a.ubicacion_id == ubicacion_id
        ],
    )


@bp.post("/alertas/descartar")
def descartar_alerta():
    datos = cuerpo()
    servicios().alertas.descartar(entero(datos.get("producto_id"), "Producto"), entero(datos.get("ubicacion_id"), "Ubicación"))
    return ok()


# --- Compras a proveedores --------------------------------------------------------------------------


@bp.get("/compras")
def compras():
    return jsonify([
        {
            "id": o.id, "numero": o.numero, "proveedor_id": o.proveedor_id, "fecha": o.fecha_emision,
            "estado": str(o.estado), "estado_nombre": nombre_estado(o.estado), "total": o.total(),
            "items": [{"producto_id": d.producto_id, "cantidad": d.cantidad, "costo": d.costo_unitario} for d in o.detalles],
        }
        for o in sorted(servicios().compras.listar(), key=lambda o: o.numero, reverse=True)
    ])


@bp.get("/compras/sugerencia")
def sugerir_compra():
    s = servicios()
    proveedor_id = arg_entero("proveedor", "Proveedor", opcional=False)
    renglones = s.compras.sugerir_compras(s.centro_distribucion().id).por_proveedor.get(proveedor_id, [])
    return jsonify([{"producto_id": p, "cantidad": c, "costo": costo} for p, c, costo in renglones])


@bp.post("/compras")
def crear_compra():
    s = servicios()
    datos = cuerpo()
    renglones = [
        (entero(r.get("producto_id"), "Producto"), entero(r.get("cantidad"), "Cantidad"), decimal(r.get("costo"), "Costo"))
        for r in datos.get("renglones") or []
    ]
    orden = s.compras.crear_orden(entero(datos.get("proveedor_id"), "Proveedor"), s.centro_distribucion().id, renglones)
    return ok(id=orden.id, numero=orden.numero)


@bp.post("/compras/<int:orden_id>/recibir")
def recibir_compra(orden_id: int):
    return ok(numero=servicios().compras.recibir_orden(orden_id).numero)


@bp.post("/compras/<int:orden_id>/anular")
def anular_compra(orden_id: int):
    return ok(numero=servicios().compras.anular_orden(orden_id).numero)


# --- Necesidades de reposición -----------------------------------------------------------------------


@bp.get("/necesidades")
def necesidades():
    return jsonify([
        {
            "id": n.id, "sucursal_id": n.ubicacion_id, "fecha": n.fecha,
            "origen": "Automática (stock mínimo)" if n.origen == OrigenNecesidad.AUTOMATICA else "Manual",
            "estado": str(n.estado), "estado_nombre": nombre_estado(n.estado), "orden_id": n.orden_reposicion_id,
            "items": [{"producto_id": d.producto_id, "cantidad": d.cantidad_solicitada} for d in n.detalles],
        }
        for n in sorted(servicios().reposicion.listar_necesidades(), key=lambda n: n.id, reverse=True)
    ])


@bp.get("/necesidades/sugerencia")
def sugerir_necesidad():
    sugeridos = servicios().reposicion.sugerir_necesidad(arg_entero("sucursal", "Sucursal", opcional=False))
    return jsonify([{"producto_id": p, "cantidad": c} for p, c in sugeridos])


@bp.post("/necesidades")
def crear_necesidad():
    datos = cuerpo()
    renglones = [
        (entero(r.get("producto_id"), "Producto"), entero(r.get("cantidad"), "Cantidad"))
        for r in datos.get("renglones") or []
    ]
    necesidad = servicios().reposicion.crear_necesidad(entero(datos.get("sucursal_id"), "Sucursal"), renglones)
    return ok(id=necesidad.id)


@bp.post("/necesidades/<int:necesidad_id>/anular")
def anular_necesidad(necesidad_id: int):
    servicios().reposicion.anular_necesidad(necesidad_id)
    return ok()


@bp.post("/necesidades/consolidar")
def consolidar_necesidades():
    """Una necesidad sola o todas las pendientes de una sucursal: arma la orden de reposición (P3)."""
    ids = [entero(i, "Necesidad") for i in cuerpo().get("ids") or []]
    orden = servicios().reposicion.consolidar(ids)
    return ok(id=orden.id, numero=orden.numero)


# --- Órdenes de reposición -------------------------------------------------------------------------------


@bp.get("/ordenes")
def ordenes():
    s = servicios()
    necesidades_por_orden = defaultdict(list)
    for n in s.reposicion.listar_necesidades():
        if n.orden_reposicion_id is not None:
            necesidades_por_orden[n.orden_reposicion_id].append(n.id)
    return jsonify([orden_json(o, necesidades_por_orden[o.id]) for o in sorted(s.reposicion.listar(), key=lambda o: o.numero, reverse=True)])


def orden_json(o, necesidades: list[int] | None = None) -> dict:
    return {
        "id": o.id, "numero": o.numero, "fecha": o.fecha_emision, "destino_id": o.destino_id,
        "estado": str(o.estado), "estado_nombre": nombre_estado(o.estado), "necesidades": necesidades or [],
        "items": [
            {"producto_id": d.producto_id, "solicitada": d.cantidad_solicitada,
             "preparada": d.cantidad_preparada, "recibida": d.cantidad_recibida}
            for d in o  # Iterator: recorre los renglones de la orden
        ],
    }


@bp.post("/ordenes/<int:orden_id>/iniciar")
def iniciar_orden(orden_id: int):
    return ok(numero=servicios().reposicion.iniciar_preparacion(orden_id).numero)
