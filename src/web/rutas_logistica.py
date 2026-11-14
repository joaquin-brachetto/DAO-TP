"""Logística (P4, P5, P6): armado de bultos, precintos, despacho, recepción y trazabilidad."""

from flask import Blueprint, jsonify

from src.dominio.inventario.modelos import EstadoOrdenReposicion
from src.dominio.logistica.modelos import EstadoRemito, nombre_estado_logistica
from src.web.rutas_inventario import orden_json
from src.web.utiles import cuerpo, entero, servicios, texto

bp = Blueprint("logistica", __name__)


def ok(**datos):
    return jsonify(ok=True, **datos)


def bulto_json(b, control=None) -> dict:
    return {
        "id": b.id, "codigo": b.codigo, "remito_id": b.remito_id,
        "estado": b.nombre_estado, "estado_nombre": nombre_estado_logistica(b.nombre_estado),
        "precinto": b.precinto.numero if b.precinto else "", "motivo": b.motivo_rechazo or "",
        "items": [{"producto_id": d.producto_id, "cantidad": d.cantidad} for d in b.detalles],
        "control": None if control is None else {
            "precinto_leido": control.numero_precinto_leido, "integro": control.precinto_integro,
            "resultado": control.resultado,
        },
    }


def remito_json(r) -> dict:
    s = servicios()
    despacho = s.logistica.obtener_despacho(r.despacho_id) if r.despacho_id else None
    recepcion = s.logistica.obtener_recepcion_por_remito(r.id)
    controles = {c.bulto_id: c for c in recepcion.controles} if recepcion else {}
    return {
        "id": r.id, "numero": r.numero, "orden_id": r.orden_reposicion_id, "destino_id": r.destino_id,
        "estado": str(r.estado), "estado_nombre": nombre_estado_logistica(r.estado), "emision": r.fecha_emision,
        "salida": despacho.fecha_hora_salida if despacho else None,
        "transporte": f"{despacho.transportista} ({despacho.patente})" if despacho else "",
        "recepcion": None if recepcion is None else {
            "id": recepcion.id, "llegada": recepcion.fecha_hora_llegada,
            "recibido_por": recepcion.recibido_por, "cerrada": recepcion.cerrada,
        },
        "bultos": [bulto_json(b, controles.get(b.id)) for b in r.bultos],
    }


@bp.get("/logistica")
def logistica():
    """Órdenes para empaquetar (con el stock del CD) y todos los remitos con sus bultos."""
    s = servicios()
    ordenes = [
        o for o in s.reposicion.listar()
        if o.estado in (EstadoOrdenReposicion.PENDIENTE, EstadoOrdenReposicion.EN_PREPARACION)
    ]
    cd = s.centro_distribucion().id if ordenes else None
    return jsonify(
        ordenes=[
            {**orden_json(o), "disponible_cd": {str(d.producto_id): s.stock.stock_disponible(cd, d.producto_id) for d in o}}
            for o in sorted(ordenes, key=lambda o: o.numero)
        ],
        remitos=[remito_json(r) for r in sorted(s.logistica.listar_remitos(), key=lambda r: r.id, reverse=True)],
    )


@bp.post("/ordenes/<int:orden_id>/bultos")
def armar_bulto(orden_id: int):
    """Empaqueta un bulto de la orden. Lo agrega al remito abierto de la orden o crea uno nuevo (P4)."""
    s = servicios()
    datos = cuerpo()
    renglones = [
        (entero(r.get("producto_id"), "Producto"), entero(r.get("cantidad"), "Cantidad"))
        for r in datos.get("renglones") or []
    ]
    with s.db.transaccion():
        abiertos = s.logistica.listar_remitos(estado=EstadoRemito.EMITIDO, orden_reposicion_id=orden_id)
        remito = abiertos[0] if abiertos else s.logistica.crear_remito(orden_id)
        bulto = s.logistica.armar_bulto(remito.id, renglones, numero_precinto=texto(datos.get("precinto")) or None)
    return ok(bulto=bulto.codigo, remito=remito.numero, estado=nombre_estado_logistica(bulto.nombre_estado))


@bp.post("/bultos/<int:bulto_id>/precintar")
def precintar(bulto_id: int):
    bulto = servicios().logistica.precintar_bulto(bulto_id, texto(cuerpo().get("precinto")))
    return ok(bulto=bulto.codigo, precinto=bulto.precinto.numero)


@bp.post("/remitos/<int:remito_id>/despachar")
def despachar(remito_id: int):
    datos = cuerpo()
    servicios().logistica.registrar_despacho([remito_id], texto(datos.get("transportista")), texto(datos.get("patente")))
    return ok()


@bp.post("/remitos/<int:remito_id>/recibir")
def recibir(remito_id: int):
    recepcion = servicios().logistica.recibir_remito(remito_id, texto(cuerpo().get("recibido_por")))
    return ok(recepcion_id=recepcion.id)


@bp.post("/recepciones/<int:recepcion_id>/controles")
def controlar_bulto(recepcion_id: int):
    datos = cuerpo()
    control = servicios().logistica.registrar_control_bulto(
        recepcion_id,
        entero(datos.get("bulto_id"), "Bulto"),
        texto(datos.get("precinto_leido")),
        bool(datos.get("integro")),
        texto(datos.get("observacion")),
    )
    return ok(resultado=nombre_estado_logistica(control.resultado))


@bp.post("/recepciones/<int:recepcion_id>/cerrar")
def cerrar_recepcion(recepcion_id: int):
    s = servicios()
    recepcion = s.logistica.cerrar_recepcion(recepcion_id)
    remito = s.logistica.obtener_remito(recepcion.remito_id)
    return ok(remito=remito.numero, estado=nombre_estado_logistica(remito.estado))


@bp.get("/bultos")
def bultos():
    s = servicios()
    remitos = {r.id: r for r in s.logistica.listar_remitos()}
    return jsonify([
        {**bulto_json(b), "numero_remito": remitos[b.remito_id].numero, "destino_id": remitos[b.remito_id].destino_id}
        for b in sorted(s.logistica.listar_bultos(), key=lambda b: b.id, reverse=True)
        if b.remito_id in remitos
    ])


@bp.get("/bultos/<int:bulto_id>/historial")
def historial(bulto_id: int):
    return jsonify([
        {"fecha": c.fecha_hora, "estado": nombre_estado_logistica(c.estado_nuevo),
         "codigo": c.estado_nuevo, "usuario": c.usuario, "observacion": c.observacion}
        for c in servicios().logistica.historial_bulto(bulto_id)
    ])
