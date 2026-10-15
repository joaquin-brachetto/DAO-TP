"""Stock de prueba (pohlsi): deja la aplicación lista para vender y ver los reportes.

Se carga DESPUÉS de los datos de prueba de maestros (Archivo → Cargar datos de prueba),
porque usa sus productos, proveedores, sucursales y stock mínimo. Todo pasa por los
servicios de inventario, así que queda registrado en los movimientos como cualquier
operación real:

1. Una orden de compra por proveedor al Centro de Distribución, ya recibida.
2. Una carga inicial de cada sucursal desde el CD (referencia CARGA_INICIAL):
   sale del CD, entra como pendiente y se verifica en el local.
3. Una orden de compra más, PENDIENTE, para probar "Recibir" desde la pantalla.

Un producto queda justo en su stock mínimo en la primera sucursal: al venderle una
unidad se ve el Observer en acción (alerta + necesidad de reposición automática).

Uso:
    python -m src.datos_prueba_inventario
o menú Inventario → "Cargar stock de prueba".
"""

from decimal import Decimal

from src.dominio.inventario.modelos import Referencia, TipoMovimiento
from src.excepciones import ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.servicios.compras_service import ComprasService
from src.servicios.stock_service import StockService

MULTIPLO_SUCURSAL = 3     # cada sucursal recibe 3 veces su stock mínimo
MULTIPLO_CD = 12          # el CD se queda con 12 veces el mínimo de una sucursal (el doble de su mínimo)
SIN_MINIMO = 10           # productos sin mínimo definido: unidades por sucursal
SKU_EN_MINIMO = "CAF-250"  # queda justo en su mínimo en la primera sucursal
CARGA_INICIAL = Referencia("CARGA_INICIAL", usuario="datos de prueba")


def cargar_stock_de_prueba(db: BaseDeDatos | None = None) -> dict[str, int]:
    """Carga compras y stock inicial. Devuelve cuántos registros se crearon de cada tipo."""
    db = db or BaseDeDatos()
    if db.consultar_uno("SELECT 1 FROM producto LIMIT 1") is None:
        raise ValidacionError(
            "Primero cargá los datos de prueba de maestros (Archivo → Cargar datos de prueba)."
        )
    if db.consultar_uno("SELECT 1 FROM stock LIMIT 1") is not None:
        raise ValidacionError("Ya hay stock cargado. Para recargarlo, borrá datos/ventas.db y empezá de nuevo.")
    cd = db.consultar_uno("SELECT id FROM ubicacion WHERE tipo = 'CD' AND activa = 1")
    if cd is None:
        raise ValidacionError("No hay un Centro de Distribución activo.")
    sucursales = [f["id"] for f in db.consultar(
        "SELECT id FROM ubicacion WHERE tipo = 'SUCURSAL' AND activa = 1 ORDER BY codigo"
    )]
    productos = db.consultar(
        "SELECT p.id, p.sku, p.costo_actual, "
        "(SELECT MAX(sm.cantidad_minima) FROM stock_minimo sm JOIN ubicacion u ON u.id = sm.ubicacion_id "
        " WHERE sm.producto_id = p.id AND u.tipo = 'SUCURSAL') AS minimo "
        "FROM producto p WHERE p.activo = 1 ORDER BY p.id"
    )

    stock = StockService(db)  # sin observadores: la carga inicial no debe generar alertas
    compras = ComprasService(db, stock)
    por_proveedor: dict[int, list[tuple[int, int, Decimal]]] = {}
    por_sucursal: dict[int, int] = {}
    for producto in productos:
        minimo = producto["minimo"] or 0
        por_sucursal[producto["id"]] = minimo * MULTIPLO_SUCURSAL if minimo else SIN_MINIMO
        cantidad = (minimo * MULTIPLO_CD if minimo else SIN_MINIMO) + por_sucursal[producto["id"]] * len(sucursales)
        proveedor = db.consultar_uno(
            "SELECT proveedor_id, costo_pactado FROM producto_proveedor WHERE producto_id = ? "
            "ORDER BY costo_pactado, proveedor_id LIMIT 1",
            (producto["id"],),
        )
        if proveedor is None:
            continue  # sin proveedor no se puede comprar
        costo = proveedor["costo_pactado"] if proveedor["costo_pactado"] is not None else producto["costo_actual"]
        por_proveedor.setdefault(proveedor["proveedor_id"], []).append((producto["id"], cantidad, costo))

    movimientos_iniciales = 0
    with db.transaccion():
        ordenes = [compras.crear_orden(proveedor_id, cd["id"], renglones)
                   for proveedor_id, renglones in por_proveedor.items()]
        for orden in ordenes:
            compras.recibir_orden(orden.id, usuario="datos de prueba")

        comprados = {producto_id for renglones in por_proveedor.values() for producto_id, _, _ in renglones}
        en_minimo = next((p["id"] for p in productos if p["sku"] == SKU_EN_MINIMO), None)
        for indice, sucursal_id in enumerate(sucursales):
            for producto_id, cantidad in por_sucursal.items():
                if producto_id not in comprados:
                    continue
                if indice == 0 and producto_id == en_minimo:
                    cantidad = cantidad // MULTIPLO_SUCURSAL  # justo en el mínimo
                stock.egresar(cd["id"], producto_id, cantidad, CARGA_INICIAL, tipo=TipoMovimiento.EGRESO_DESPACHO)
                stock.ingresar_pendiente(sucursal_id, producto_id, cantidad, CARGA_INICIAL)
                stock.confirmar_disponible(sucursal_id, producto_id, cantidad, CARGA_INICIAL)
                movimientos_iniciales += 3

        # Una orden pendiente para probar "Recibir" desde la pantalla de compras.
        proveedor_id, renglones = next(iter(por_proveedor.items()))
        compras.crear_orden(proveedor_id, cd["id"], [(p, 20, c) for p, _, c in renglones[:3]])

    return {
        "órdenes de compra recibidas": len(ordenes),
        "órdenes de compra pendientes": 1,
        "productos en stock": len(comprados),
        "movimientos de carga inicial en sucursales": movimientos_iniciales,
    }


def main() -> None:
    db = BaseDeDatos()
    db.inicializar_esquema()
    try:
        cantidades = cargar_stock_de_prueba(db)
    except ValidacionError as error:
        print(error)
        return
    print(f"Stock de prueba cargado en {db.ruta}:")
    for tipo, cantidad in cantidades.items():
        print(f"  {cantidad:>4} {tipo}")


if __name__ == "__main__":
    main()
