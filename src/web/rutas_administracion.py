"""Administración (P1 y P2): sucursales y CD, categorías, productos, proveedores y clientes."""

from flask import Blueprint, jsonify

from src.dominio.maestros.modelos import (
    Categoria,
    CentroDistribucion,
    Producto,
    ProductoProveedor,
    Proveedor,
    StockMinimo,
    Sucursal,
)
from src.dominio.ventas.modelos import Cliente, CondicionIva
from src.excepciones import ValidacionError
from src.web.utiles import cuerpo, decimal, entero, servicios, texto, texto_opcional

bp = Blueprint("administracion", __name__)


def ok(**datos):
    return jsonify(ok=True, **datos)


# --- Sucursales y Centro de Distribución --------------------------------------------------------


def _armar_ubicacion(datos: dict, existente=None):
    comunes = dict(
        codigo=texto(datos.get("codigo")),
        nombre=texto(datos.get("nombre")),
        direccion=texto_opcional(datos.get("direccion")),
        telefono=texto_opcional(datos.get("telefono")),
        activa=existente.activa if existente else True,
        id=existente.id if existente else None,
    )
    tipo = str(existente.tipo) if existente else texto(datos.get("tipo")) or "SUCURSAL"
    if tipo == "CD":
        return CentroDistribucion(capacidad_m3=getattr(existente, "capacidad_m3", None), **comunes)
    return Sucursal(punto_venta=entero(datos.get("punto_venta"), "Punto de venta"), **comunes)


@bp.post("/ubicaciones")
def alta_ubicacion():
    ubicacion = servicios().ubicaciones.guardar(_armar_ubicacion(cuerpo()))
    return ok(id=ubicacion.id)


@bp.put("/ubicaciones/<int:ubicacion_id>")
def modificar_ubicacion(ubicacion_id: int):
    s = servicios()
    s.ubicaciones.guardar(_armar_ubicacion(cuerpo(), s.ubicaciones.obtener(ubicacion_id)))
    return ok(id=ubicacion_id)


@bp.post("/ubicaciones/<int:ubicacion_id>/baja")
def baja_ubicacion(ubicacion_id: int):
    servicios().ubicaciones.dar_de_baja(ubicacion_id)
    return ok()


@bp.post("/ubicaciones/<int:ubicacion_id>/reactivar")
def reactivar_ubicacion(ubicacion_id: int):
    servicios().ubicaciones.reactivar(ubicacion_id)
    return ok()


# --- Categorías -------------------------------------------------------------------------------------


@bp.post("/categorias")
def alta_categoria():
    datos = cuerpo()
    categoria = servicios().categorias.guardar(
        Categoria(texto(datos.get("nombre")), texto_opcional(datos.get("descripcion")))
    )
    return ok(id=categoria.id)


@bp.put("/categorias/<int:categoria_id>")
def modificar_categoria(categoria_id: int):
    datos = cuerpo()
    servicios().categorias.guardar(
        Categoria(texto(datos.get("nombre")), texto_opcional(datos.get("descripcion")), id=categoria_id)
    )
    return ok(id=categoria_id)


@bp.delete("/categorias/<int:categoria_id>")
def eliminar_categoria(categoria_id: int):
    servicios().categorias.eliminar(categoria_id)
    return ok()


# --- Productos, precios, proveedores del producto y stock mínimo ------------------------------------


@bp.get("/productos/<int:producto_id>")
def detalle_producto(producto_id: int):
    s = servicios()
    return jsonify(
        historial=[
            {"desde": h.fecha_desde, "hasta": h.fecha_hasta, "costo": h.costo, "precio": h.precio_venta}
            for h in s.productos.historial_precios(producto_id)
        ],
        minimos={str(m.ubicacion_id): m.cantidad_minima for m in s.minimos.de_producto(producto_id)},
    )


def _guardar_producto(datos: dict, producto_id: int | None = None) -> int:
    s = servicios()
    existente = s.productos.obtener(producto_id) if producto_id is not None else None
    producto = Producto(
        sku=texto(datos.get("sku")),
        nombre=texto(datos.get("nombre")),
        categoria_id=entero(datos.get("categoria_id"), "Categoría"),
        costo_actual=decimal(datos.get("costo"), "Costo"),
        precio_venta_actual=decimal(datos.get("precio"), "Precio de venta"),
        codigo_barras=existente.codigo_barras if existente else None,
        descripcion=texto_opcional(datos.get("descripcion")),
        unidad_medida=existente.unidad_medida if existente else "UN",
        activo=existente.activo if existente else True,
        id=producto_id,
    )
    with s.db.transaccion():  # producto, proveedores y mínimos: todo o nada
        s.productos.guardar(producto)

        elegidos = {entero(p, "Proveedor") for p in datos.get("proveedores") or []}
        actuales = {r.proveedor_id for r in s.productos.proveedores_de(producto.id)}
        for proveedor_id in elegidos - actuales:
            s.productos.asignar_proveedor(ProductoProveedor(producto.id, proveedor_id))
        for proveedor_id in actuales - elegidos:
            s.productos.quitar_proveedor(producto.id, proveedor_id)

        minimos_actuales = {m.ubicacion_id: m.cantidad_minima for m in s.minimos.de_producto(producto.id)}
        for ubicacion_id, cantidad in (datos.get("minimos") or {}).items():
            ubicacion_id = int(ubicacion_id)
            cantidad = entero(cantidad, "Stock mínimo", opcional=True) or 0
            if cantidad < 0:
                raise ValidacionError("El stock mínimo no puede ser negativo.")
            if cantidad == minimos_actuales.get(ubicacion_id, 0):
                continue
            if cantidad > 0:
                s.minimos.definir(StockMinimo(producto.id, ubicacion_id, cantidad))
            else:
                s.minimos.quitar(producto.id, ubicacion_id)
    return producto.id


@bp.post("/productos")
def alta_producto():
    return ok(id=_guardar_producto(cuerpo()))


@bp.put("/productos/<int:producto_id>")
def modificar_producto(producto_id: int):
    return ok(id=_guardar_producto(cuerpo(), producto_id))


@bp.post("/productos/<int:producto_id>/baja")
def baja_producto(producto_id: int):
    servicios().productos.dar_de_baja(producto_id)
    return ok()


@bp.post("/productos/<int:producto_id>/reactivar")
def reactivar_producto(producto_id: int):
    servicios().productos.reactivar(producto_id)
    return ok()


# --- Proveedores ----------------------------------------------------------------------------------


def _armar_proveedor(datos: dict, existente=None) -> Proveedor:
    return Proveedor(
        cuit=texto(datos.get("cuit")),
        razon_social=texto(datos.get("razon_social")),
        email=texto_opcional(datos.get("email")),
        telefono=texto_opcional(datos.get("telefono")),
        direccion=texto_opcional(datos.get("direccion")),
        activo=existente.activo if existente else True,
        id=existente.id if existente else None,
    )


@bp.post("/proveedores")
def alta_proveedor():
    return ok(id=servicios().proveedores.guardar(_armar_proveedor(cuerpo())).id)


@bp.put("/proveedores/<int:proveedor_id>")
def modificar_proveedor(proveedor_id: int):
    s = servicios()
    s.proveedores.guardar(_armar_proveedor(cuerpo(), s.proveedores.obtener(proveedor_id)))
    return ok(id=proveedor_id)


@bp.post("/proveedores/<int:proveedor_id>/baja")
def baja_proveedor(proveedor_id: int):
    servicios().proveedores.dar_de_baja(proveedor_id)
    return ok()


@bp.post("/proveedores/<int:proveedor_id>/reactivar")
def reactivar_proveedor(proveedor_id: int):
    servicios().proveedores.reactivar(proveedor_id)
    return ok()


# --- Clientes (los usa Ventas para elegir el comprobante) ------------------------------------------


def _armar_cliente(datos: dict, cliente_id: int | None = None) -> Cliente:
    try:
        condicion = CondicionIva(texto(datos.get("condicion_iva")) or "CONSUMIDOR_FINAL")
    except ValueError:
        raise ValidacionError("La condición frente al IVA no es válida.") from None
    return Cliente(texto(datos.get("documento")), texto(datos.get("nombre")), condicion, id=cliente_id)


@bp.post("/clientes")
def alta_cliente():
    return ok(id=servicios().ventas.registrar_cliente(_armar_cliente(cuerpo())).id)


@bp.put("/clientes/<int:cliente_id>")
def modificar_cliente(cliente_id: int):
    servicios().ventas.registrar_cliente(_armar_cliente(cuerpo(), cliente_id))
    return ok(id=cliente_id)
