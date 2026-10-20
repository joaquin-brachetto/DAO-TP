"""Tests de ComprasService (pohlsi): órdenes de compra al CD y recepción que ingresa stock."""

from datetime import date
from decimal import Decimal

import pytest

from src.dominio.inventario.modelos import EstadoOrdenCompra, TipoMovimiento
from src.excepciones import EntidadNoEncontradaError, ValidacionError
from src.persistencia.repositorio_inventario import MovimientoStockRepositorio
from src.servicios.compras_service import ComprasService
from src.servicios.stock_service import StockService


@pytest.fixture
def stock(db):
    return StockService(db)


@pytest.fixture
def compras(db, stock):
    return ComprasService(db, stock)


def renglones(e):
    return [(e.producto, 10, Decimal("90")), (e.otro_producto, 20, Decimal("40"))]


def test_crear_orden_queda_pendiente_con_su_total(compras, escenario):
    orden = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))

    guardada = compras.obtener(orden.id)
    assert guardada.estado == EstadoOrdenCompra.PENDIENTE
    assert guardada.fecha_emision == date.today()
    assert len(guardada.detalles) == 2
    assert guardada.total() == Decimal("1700")  # 10 x 90 + 20 x 40


def test_los_numeros_de_orden_son_correlativos(compras, escenario):
    primera = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))
    segunda = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))

    assert (primera.numero, segunda.numero) == (1, 2)


def test_crear_orden_no_ingresa_stock_todavia(compras, stock, escenario):
    compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))

    assert stock.stock_disponible(escenario.cd, escenario.producto) == 0


def test_la_orden_debe_ir_a_un_centro_de_distribucion(compras, escenario):
    with pytest.raises(ValidacionError):
        compras.crear_orden(escenario.proveedor, escenario.sucursal, renglones(escenario))


def test_proveedor_inexistente(compras, escenario):
    with pytest.raises(EntidadNoEncontradaError):
        compras.crear_orden(999, escenario.cd, renglones(escenario))


def test_proveedor_dado_de_baja(compras, escenario, db):
    db.ejecutar("UPDATE proveedor SET activo = 0 WHERE id = ?", (escenario.proveedor,))

    with pytest.raises(ValidacionError):
        compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))


def test_producto_inexistente(compras, escenario):
    with pytest.raises(EntidadNoEncontradaError):
        compras.crear_orden(escenario.proveedor, escenario.cd, [(999, 1, Decimal("10"))])


def test_la_orden_necesita_al_menos_un_producto(compras, escenario):
    with pytest.raises(ValidacionError):
        compras.crear_orden(escenario.proveedor, escenario.cd, [])


def test_no_se_repite_un_producto_en_la_orden(compras, escenario):
    repetidos = [(escenario.producto, 1, Decimal("10")), (escenario.producto, 2, Decimal("10"))]

    with pytest.raises(ValidacionError):
        compras.crear_orden(escenario.proveedor, escenario.cd, repetidos)


@pytest.mark.parametrize("cantidad, costo", [(0, "10"), (-1, "10"), (1, "-5"), (1, "abc")])
def test_cantidad_y_costo_invalidos(compras, escenario, cantidad, costo):
    with pytest.raises(ValidacionError):
        compras.crear_orden(escenario.proveedor, escenario.cd, [(escenario.producto, cantidad, costo)])


def test_una_orden_invalida_no_deja_nada_guardado(compras, escenario):
    with pytest.raises(EntidadNoEncontradaError):
        compras.crear_orden(escenario.proveedor, escenario.cd, [(escenario.producto, 1, Decimal("10")), (999, 1, 1)])

    assert compras.listar() == []


def test_recibir_la_orden_ingresa_el_stock_al_cd(compras, stock, escenario, db):
    orden = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))

    compras.recibir_orden(orden.id, usuario="pohlsi")

    assert compras.obtener(orden.id).estado == EstadoOrdenCompra.RECIBIDA
    assert stock.stock_disponible(escenario.cd, escenario.producto) == 10
    assert stock.stock_disponible(escenario.cd, escenario.otro_producto) == 20
    primero = MovimientoStockRepositorio(db).listar()[0]
    assert primero.tipo == TipoMovimiento.INGRESO_COMPRA
    assert (primero.tipo_documento, primero.documento_id, primero.usuario) == ("ORDEN_COMPRA", orden.id, "pohlsi")
    assert primero.costo_unitario == Decimal("90")  # el costo de la compra, no el costo actual del producto


def test_no_se_puede_recibir_dos_veces(compras, stock, escenario):
    orden = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))
    compras.recibir_orden(orden.id)

    with pytest.raises(ValidacionError):
        compras.recibir_orden(orden.id)
    assert stock.stock_disponible(escenario.cd, escenario.producto) == 10


def test_una_orden_anulada_no_se_puede_recibir(compras, stock, escenario):
    orden = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))
    compras.anular_orden(orden.id)

    with pytest.raises(ValidacionError):
        compras.recibir_orden(orden.id)
    assert compras.obtener(orden.id).estado == EstadoOrdenCompra.ANULADA
    assert stock.stock_disponible(escenario.cd, escenario.producto) == 0


def test_una_orden_recibida_no_se_puede_anular(compras, escenario):
    orden = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))
    compras.recibir_orden(orden.id)

    with pytest.raises(ValidacionError):
        compras.anular_orden(orden.id)


def test_si_falla_un_ingreso_no_queda_nada_a_medias(db, escenario):
    class StockQueFalla(StockService):
        llamadas = 0

        def ingresar_compra(self, *args, **kwargs):
            StockQueFalla.llamadas += 1
            if StockQueFalla.llamadas == 2:
                raise RuntimeError("falló el segundo ingreso")
            return super().ingresar_compra(*args, **kwargs)

    stock_roto = StockQueFalla(db)
    compras = ComprasService(db, stock_roto)
    orden = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))

    with pytest.raises(RuntimeError):
        compras.recibir_orden(orden.id)

    assert compras.obtener(orden.id).estado == EstadoOrdenCompra.PENDIENTE
    assert stock_roto.stock_disponible(escenario.cd, escenario.producto) == 0


def test_listar_filtra_por_estado(compras, escenario):
    una = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))
    otra = compras.crear_orden(escenario.proveedor, escenario.cd, renglones(escenario))
    compras.recibir_orden(una.id)

    assert [o.id for o in compras.listar(EstadoOrdenCompra.PENDIENTE)] == [otra.id]
    assert len(compras.listar()) == 2


# --- Compras sugeridas por faltantes del CD (opcional del plan) ---------------------------------------


@pytest.fixture
def con_faltante(db, stock, escenario, definir_minimo):
    """El CD tiene 4 unidades de yerba con mínimo 10; el proveedor la vende a $90."""
    db.ejecutar(
        "INSERT INTO producto_proveedor (producto_id, proveedor_id, costo_pactado) VALUES (?, ?, ?)",
        (escenario.producto, escenario.proveedor, Decimal("90")),
    )
    definir_minimo(escenario.producto, escenario.cd, 10)
    stock.ingresar_compra(escenario.cd, escenario.producto, 4, "CARGA")
    return escenario


def test_sugiere_lo_que_falta_al_proveedor_mas_barato(compras, con_faltante):
    sugerencia = compras.sugerir_compras()

    assert sugerencia.por_proveedor == {con_faltante.proveedor: [(con_faltante.producto, 6, Decimal("90"))]}
    assert sugerencia.sin_proveedor == []


def test_descuenta_lo_ya_pedido_en_ordenes_pendientes(compras, con_faltante):
    compras.crear_orden(con_faltante.proveedor, con_faltante.cd, [(con_faltante.producto, 4, Decimal("90"))])

    assert compras.sugerir_compras().por_proveedor[con_faltante.proveedor] == [(con_faltante.producto, 2, Decimal("90"))]


def test_si_lo_pedido_alcanza_no_sugiere_nada(compras, con_faltante):
    compras.crear_orden(con_faltante.proveedor, con_faltante.cd, [(con_faltante.producto, 6, Decimal("90"))])

    assert compras.sugerir_compras().vacia()


def test_elige_el_proveedor_con_menor_costo_pactado(db, compras, con_faltante):
    barato = db.ejecutar("INSERT INTO proveedor (cuit, razon_social) VALUES ('20123456786', 'Barato SRL')").lastrowid
    db.ejecutar("INSERT INTO producto_proveedor (producto_id, proveedor_id, costo_pactado) VALUES (?, ?, ?)",
                (con_faltante.producto, barato, Decimal("80")))

    assert list(compras.sugerir_compras().por_proveedor) == [barato]


def test_no_sugiere_si_el_cd_esta_sobre_el_minimo(compras, stock, con_faltante):
    stock.ingresar_compra(con_faltante.cd, con_faltante.producto, 7, "CARGA")  # 11 > 10

    assert compras.sugerir_compras().vacia()


def test_informa_los_productos_sin_proveedor(compras, stock, escenario, definir_minimo):
    definir_minimo(escenario.otro_producto, escenario.cd, 5)

    sugerencia = compras.sugerir_compras()

    assert sugerencia.sin_proveedor == [(escenario.otro_producto, 5)]
    assert sugerencia.por_proveedor == {}
