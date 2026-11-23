"""Ventas (P7): venta con uno o varios medios de pago, devoluciones y caja por sucursal."""

from flask import Blueprint, jsonify

from src.dominio.ventas.modelos import DetalleDevolucion
from src.servicios.inventario_app import describir_alerta
from src.servicios.ventas_service import PagoSolicitado
from src.web.utiles import arg_entero, comprobante, cuerpo, decimal, entero, servicios, texto

bp = Blueprint("ventas", __name__)


def ok(**datos):
    return jsonify(ok=True, **datos)


@bp.get("/ventas/contexto")
def contexto():
    """Stock disponible de cada producto en la sucursal y su caja abierta."""
    s = servicios()
    sucursal_id = arg_entero("sucursal", "Sucursal", opcional=False)
    return jsonify(
        disponible={str(p.id): s.stock.stock_disponible(sucursal_id, p.id) for p in s.productos.listar()},
        caja=s.ventas.caja_actual(sucursal_id),
    )


@bp.post("/ventas")
def registrar_venta():
    s = servicios()
    datos = cuerpo()
    sucursal_id = entero(datos.get("sucursal_id"), "Sucursal")
    items = {
        entero(r.get("producto_id"), "Producto"): entero(r.get("cantidad"), "Cantidad")
        for r in datos.get("items") or []
    }
    pagos = [
        PagoSolicitado(
            medio_pago=texto(p.get("medio")),
            monto=decimal(p.get("monto"), "Importe"),
            cuotas=entero(p.get("cuotas"), "Cuotas", opcional=True) or 1,
            datos={},
        )
        for p in datos.get("pagos") or []
    ]
    antes = {(a.producto_id, a.ubicacion_id) for a in s.alertas.alertas()}
    venta_id = s.ventas.registrar_venta(
        sucursal_id, items, pagos,
        cliente_id=entero(datos.get("cliente_id"), "Cliente", opcional=True),
        vendedor=texto(datos.get("vendedor")),
    )
    nuevas = [a for a in s.alertas.alertas() if (a.producto_id, a.ubicacion_id) not in antes]
    cp = s.ventas.comprobante_de_venta(venta_id)
    return ok(
        venta_id=venta_id,
        comprobante=comprobante(cp["tipo"], cp["punto_venta"], cp["numero"]),
        total=cp["total"],
        alertas=[describir_alerta(a, s.db) for a in nuevas],
    )


@bp.get("/ventas/devolvibles")
def ventas_devolvibles():
    sucursal_id = arg_entero("sucursal", "Sucursal", opcional=False)
    return jsonify([
        {
            "id": v["id"], "fecha": v["fecha_hora"], "total": v["total"],
            "comprobante": comprobante(v["tipo"], v["punto_venta"], v["numero_comprobante"]),
            "cliente": v["cliente"] or "Consumidor final",
        }
        for v in servicios().ventas.ventas_devolvibles() if v["ubicacion_id"] == sucursal_id
    ])


@bp.get("/ventas/<int:venta_id>/renglones")
def renglones(venta_id: int):
    return jsonify([
        {"id": r["id"], "producto": f"{r['sku']} – {r['nombre']}", "cantidad": r["cantidad"], "devuelta": r["cantidad_devuelta"]}
        for r in servicios().ventas.renglones_de_venta(venta_id)
    ])


@bp.post("/devoluciones")
def registrar_devolucion():
    datos = cuerpo()
    detalles = [
        DetalleDevolucion(
            entero(d.get("detalle_venta_id"), "Renglón"), entero(d.get("cantidad"), "Cantidad"),
            reingresa_stock=bool(d.get("reingresa_stock", True)),
        )
        for d in datos.get("detalles") or []
        if entero(d.get("cantidad"), "Cantidad", opcional=True)
    ]
    devolucion_id = servicios().ventas.registrar_devolucion(
        entero(datos.get("venta_id"), "Venta"), detalles, texto(datos.get("motivo"))
    )
    return ok(id=devolucion_id)


@bp.get("/devoluciones")
def devoluciones():
    sucursal_id = arg_entero("sucursal", "Sucursal", opcional=False)
    return jsonify([
        {
            "id": d["id"], "fecha": d["fecha_hora"], "motivo": d["motivo"], "total": d["total_reintegrar"],
            "nota": comprobante("NOTA_CREDITO", d["punto_venta"], d["numero_nota"]),
            "venta": comprobante(d["tipo_venta"], d["punto_venta"], d["numero_venta"]),
        }
        for d in servicios().ventas.devoluciones_de_sucursal(sucursal_id)
    ])


@bp.post("/caja/abrir")
def abrir_caja():
    datos = cuerpo()
    servicios().ventas.abrir_caja(entero(datos.get("sucursal_id"), "Sucursal"), decimal(datos.get("saldo_inicial"), "Saldo inicial"))
    return ok()


@bp.post("/caja/cerrar")
def cerrar_caja():
    saldo = servicios().ventas.cerrar_caja(entero(cuerpo().get("sucursal_id"), "Sucursal"))
    return ok(saldo=saldo)
