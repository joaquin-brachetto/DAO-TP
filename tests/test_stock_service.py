"""Tests de StockService (pohlsi): stock en tres baldes, movimientos, V1, V3 y Observer."""

import sqlite3
from decimal import Decimal

import pytest

from src.dominio.inventario.modelos import Referencia, TipoMovimiento
from src.excepciones import EntidadNoEncontradaError, ValidacionError
from src.persistencia.repositorio_inventario import MovimientoStockRepositorio
from src.servicios.observadores_stock import AlertaStockMinimo, ObservadorStock
from src.servicios.stock_service import StockInsuficienteError, StockService

REF = Referencia("TEST", 1)


@pytest.fixture
def servicio(db):
    return StockService(db)


# --- Consultas ----------------------------------------------------------------------------


def test_sin_movimientos_el_stock_disponible_es_cero(servicio, escenario):
    assert servicio.stock_disponible(escenario.sucursal, escenario.producto) == 0


# --- Compras al CD -------------------------------------------------------------------------


def test_compra_ingresa_como_disponible_en_el_cd(servicio, escenario):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 50, REF, costo_unitario=Decimal("90"))

    assert servicio.stock_disponible(escenario.cd, escenario.producto) == 50


def test_compra_no_puede_ingresar_a_una_sucursal(servicio, escenario):
    with pytest.raises(ValidacionError):
        servicio.ingresar_compra(escenario.sucursal, escenario.producto, 5, REF)


# --- V1: lo que llega a un local no se puede vender hasta verificarlo ------------------------


def test_mercaderia_pendiente_no_cuenta_como_disponible(servicio, escenario):
    servicio.ingresar_pendiente(escenario.sucursal, escenario.producto, 10, REF)

    stock = servicio.stock_de(escenario.sucursal, escenario.producto)
    assert stock.cantidad_pendiente == 10
    assert servicio.stock_disponible(escenario.sucursal, escenario.producto) == 0


def test_no_se_puede_vender_stock_pendiente(servicio, escenario):
    servicio.ingresar_pendiente(escenario.sucursal, escenario.producto, 10, REF)

    with pytest.raises(StockInsuficienteError):
        servicio.egresar(escenario.sucursal, escenario.producto, 1, REF)


def test_verificar_pasa_de_pendiente_a_disponible(servicio, escenario):
    servicio.ingresar_pendiente(escenario.sucursal, escenario.producto, 10, REF)
    servicio.confirmar_disponible(escenario.sucursal, escenario.producto, 10, REF)

    stock = servicio.stock_de(escenario.sucursal, escenario.producto)
    assert (stock.cantidad_pendiente, stock.cantidad_disponible) == (0, 10)


def test_rechazo_pasa_de_pendiente_a_merma_y_no_habilita_venta(servicio, escenario):
    servicio.ingresar_pendiente(escenario.sucursal, escenario.producto, 10, REF)
    servicio.registrar_merma(escenario.sucursal, escenario.producto, 10, REF)

    stock = servicio.stock_de(escenario.sucursal, escenario.producto)
    assert (stock.cantidad_pendiente, stock.cantidad_merma, stock.cantidad_disponible) == (0, 10, 0)


def test_no_se_puede_verificar_mas_de_lo_pendiente(servicio, escenario):
    servicio.ingresar_pendiente(escenario.sucursal, escenario.producto, 5, REF)

    with pytest.raises(StockInsuficienteError):
        servicio.confirmar_disponible(escenario.sucursal, escenario.producto, 6, REF)
    assert servicio.stock_de(escenario.sucursal, escenario.producto).cantidad_pendiente == 5


# --- V3: egresos y devoluciones ----------------------------------------------------------------


def test_egreso_descuenta_del_disponible(servicio, escenario):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 20, REF)
    servicio.egresar(escenario.cd, escenario.producto, 8, REF)

    assert servicio.stock_disponible(escenario.cd, escenario.producto) == 12


def test_no_se_puede_egresar_mas_que_el_disponible(servicio, escenario):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 3, REF)

    with pytest.raises(StockInsuficienteError):
        servicio.egresar(escenario.cd, escenario.producto, 4, REF)
    assert servicio.stock_disponible(escenario.cd, escenario.producto) == 3


def test_despacho_registra_un_movimiento_de_despacho(servicio, escenario, db):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)
    servicio.egresar(escenario.cd, escenario.producto, 4, REF, tipo=TipoMovimiento.EGRESO_DESPACHO)

    movimientos = MovimientoStockRepositorio(db).listar()
    assert [m.tipo for m in movimientos] == [TipoMovimiento.INGRESO_COMPRA, TipoMovimiento.EGRESO_DESPACHO]


def test_egreso_solo_acepta_tipos_de_egreso(servicio, escenario):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    with pytest.raises(ValidacionError):
        servicio.egresar(escenario.cd, escenario.producto, 1, REF, tipo=TipoMovimiento.INGRESO_COMPRA)


def test_devolucion_reingresa_al_disponible(servicio, escenario):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)
    servicio.egresar(escenario.cd, escenario.producto, 4, REF)
    servicio.reingresar(escenario.cd, escenario.producto, 2, REF)

    assert servicio.stock_disponible(escenario.cd, escenario.producto) == 8


# --- Validaciones de datos --------------------------------------------------------------------------


@pytest.mark.parametrize("cantidad", [0, -3, 1.5, "2", True])
def test_la_cantidad_debe_ser_un_entero_positivo(servicio, escenario, cantidad):
    with pytest.raises(ValidacionError):
        servicio.ingresar_compra(escenario.cd, escenario.producto, cantidad, REF)


def test_producto_inexistente(servicio, escenario):
    with pytest.raises(EntidadNoEncontradaError):
        servicio.ingresar_compra(escenario.cd, 999, 1, REF)


def test_ubicacion_inexistente(servicio, escenario):
    with pytest.raises(EntidadNoEncontradaError):
        servicio.ingresar_pendiente(999, escenario.producto, 1, REF)


@pytest.mark.parametrize("ref", [None, "", "   "])
def test_todo_movimiento_exige_documento_de_origen(servicio, escenario, ref):
    with pytest.raises(ValidacionError):
        servicio.ingresar_compra(escenario.cd, escenario.producto, 1, ref)


def test_la_referencia_texto_con_id_se_separa_en_tipo_y_numero(servicio, escenario, db):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 5, REF)
    servicio.egresar(escenario.cd, escenario.producto, 1, "VENTA:15")  # así lo llama ventas (vinchi)

    movimiento = MovimientoStockRepositorio(db).listar()[-1]
    assert (movimiento.tipo_documento, movimiento.documento_id) == ("VENTA", 15)


def test_la_referencia_puede_ser_un_texto(servicio, escenario, db):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 1, "ORDEN_COMPRA")

    movimiento = MovimientoStockRepositorio(db).listar()[0]
    assert (movimiento.tipo_documento, movimiento.documento_id) == ("ORDEN_COMPRA", None)


# --- Movimientos: trazabilidad inmutable ------------------------------------------------------------


def test_cada_operacion_deja_un_movimiento_con_su_referencia_y_costo(servicio, escenario, db):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, Referencia("ORDEN_COMPRA", 7, "pohlsi"), Decimal("90"))
    servicio.egresar(escenario.cd, escenario.producto, 2, Referencia("VENTA", 15))

    compra, venta = MovimientoStockRepositorio(db).listar()
    assert (compra.tipo, compra.cantidad, compra.costo_unitario) == (TipoMovimiento.INGRESO_COMPRA, 10, Decimal("90"))
    assert (compra.tipo_documento, compra.documento_id, compra.usuario) == ("ORDEN_COMPRA", 7, "pohlsi")
    # sin costo explícito se valoriza con el costo actual del producto
    assert (venta.tipo, venta.costo_unitario) == (TipoMovimiento.EGRESO_VENTA, Decimal("100"))


def test_un_movimiento_no_se_puede_modificar_ni_borrar(servicio, escenario, db):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    with pytest.raises(sqlite3.IntegrityError):
        db.ejecutar("UPDATE movimiento_stock SET cantidad = 99")
    with pytest.raises(sqlite3.IntegrityError):
        db.ejecutar("DELETE FROM movimiento_stock")


def test_si_falla_la_transaccion_externa_se_deshace_el_stock(servicio, escenario, db):
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    with pytest.raises(RuntimeError):
        with db.transaccion():  # por ejemplo, la confirmación de una venta
            servicio.egresar(escenario.cd, escenario.producto, 4, REF)
            raise RuntimeError("falló algo más adelante en la venta")

    assert servicio.stock_disponible(escenario.cd, escenario.producto) == 10
    assert len(MovimientoStockRepositorio(db).listar()) == 1


# --- Patrón Observer ------------------------------------------------------------------------------------


class ObservadorEspia(ObservadorStock):
    def __init__(self):
        self.avisos = []

    def stock_bajo_minimo(self, stock):
        self.avisos.append((stock.ubicacion_id, stock.producto_id, stock.cantidad_disponible))


def test_notifica_cuando_el_egreso_deja_el_stock_en_el_minimo(servicio, escenario, db, definir_minimo):
    definir_minimo(escenario.producto, escenario.cd, 5)
    espia = ObservadorEspia()
    servicio.suscribir(espia)
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    servicio.egresar(escenario.cd, escenario.producto, 4, REF)  # quedan 6: sobre el mínimo
    assert espia.avisos == []

    servicio.egresar(escenario.cd, escenario.producto, 1, REF)  # quedan 5: llegó al mínimo
    assert espia.avisos == [(escenario.cd, escenario.producto, 5)]


def test_no_notifica_si_el_producto_no_tiene_minimo_definido(servicio, escenario):
    espia = ObservadorEspia()
    servicio.suscribir(espia)
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    servicio.egresar(escenario.cd, escenario.producto, 10, REF)

    assert espia.avisos == []


def test_notifica_a_todos_los_suscriptos_y_respeta_la_baja(servicio, escenario, db, definir_minimo):
    definir_minimo(escenario.producto, escenario.cd, 10)
    uno, otro = ObservadorEspia(), ObservadorEspia()
    servicio.suscribir(uno)
    servicio.suscribir(otro)
    servicio.desuscribir(otro)
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    servicio.egresar(escenario.cd, escenario.producto, 1, REF)

    assert len(uno.avisos) == 1
    assert otro.avisos == []


def test_un_observador_que_falla_no_impide_el_egreso(servicio, escenario, db, definir_minimo):
    class Roto(ObservadorStock):
        def stock_bajo_minimo(self, stock):
            raise RuntimeError("falló el observador")

    definir_minimo(escenario.producto, escenario.cd, 10)
    servicio.suscribir(Roto())
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    servicio.egresar(escenario.cd, escenario.producto, 1, REF)

    assert servicio.stock_disponible(escenario.cd, escenario.producto) == 9


def test_alerta_de_stock_minimo_guarda_una_alerta_por_producto(servicio, escenario, db, definir_minimo):
    definir_minimo(escenario.producto, escenario.cd, 5)
    alerta = AlertaStockMinimo(servicio.minimos)
    servicio.suscribir(alerta)
    servicio.ingresar_compra(escenario.cd, escenario.producto, 10, REF)

    servicio.egresar(escenario.cd, escenario.producto, 5, REF)
    servicio.egresar(escenario.cd, escenario.producto, 2, REF)

    (vigente,) = alerta.alertas()
    assert (vigente.disponible, vigente.minimo, vigente.faltante) == (3, 5, 2)
