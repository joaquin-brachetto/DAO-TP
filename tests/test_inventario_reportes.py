"""Tests de los reportes de inventario (pohlsi): R3 movimientos y valorización, R4 tiempo de tránsito."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.dominio.inventario.modelos import Referencia, TipoMovimiento
from src.excepciones import ValidacionError
from src.reportes.inventario_reporte import (
    ReporteMovimientos,
    ReporteTransito,
    Sentido,
    formato_duracion,
)
from src.servicios.stock_service import StockService

REF = Referencia("TEST", 1)
LUNES = datetime(2026, 10, 5, 10, 0)


class Reloj:
    """Hora fija que se puede adelantar: así los movimientos quedan con fechas conocidas."""

    def __init__(self, momento: datetime) -> None:
        self.momento = momento

    def __call__(self) -> datetime:
        return self.momento

    def ir_a(self, momento: datetime) -> None:
        self.momento = momento


@pytest.fixture
def reloj():
    return Reloj(LUNES)


@pytest.fixture
def stock(db, reloj):
    return StockService(db, ahora=reloj)


# === R3: movimientos y valorización =============================================================


@pytest.fixture
def con_movimientos(stock, escenario):
    """Compra 50 al CD, despacha 10 a la sucursal (8 verificadas, 2 rechazadas) y vende 3."""
    e = escenario
    stock.ingresar_compra(e.cd, e.producto, 50, REF, costo_unitario=Decimal("90"))
    stock.egresar(e.cd, e.producto, 10, REF, tipo=TipoMovimiento.EGRESO_DESPACHO)
    stock.ingresar_pendiente(e.sucursal, e.producto, 10, REF)
    stock.confirmar_disponible(e.sucursal, e.producto, 8, REF)
    stock.registrar_merma(e.sucursal, e.producto, 2, REF)
    stock.egresar(e.sucursal, e.producto, 3, Referencia("VENTA", 1))
    return e


def test_r3_separa_entradas_salidas_y_movimientos_internos(db, con_movimientos):
    resumen = ReporteMovimientos(db).consultar(date(2026, 10, 1), date(2026, 10, 31))

    assert len(resumen.movimientos) == 6
    assert resumen.entradas == (60, Decimal("5500.00"))   # compra 50 x $90 + ingreso pendiente 10 x $100
    assert resumen.salidas == (15, Decimal("1500.00"))    # despacho 10 + merma 2 + venta 3, a $100
    totales = {t.tipo: (t.sentido, t.movimientos, t.unidades) for t in resumen.por_tipo()}
    assert totales[TipoMovimiento.CONFIRMACION_VERIFICADO] == (Sentido.INTERNO, 1, 8)
    assert totales[TipoMovimiento.EGRESO_VENTA] == (Sentido.SALIDA, 1, 3)


def test_r3_valoriza_el_stock_actual_por_ubicacion_al_costo(db, con_movimientos):
    resumen = ReporteMovimientos(db).consultar(date(2026, 10, 1), date(2026, 10, 31))

    valor = {v.ubicacion_id: v for v in resumen.valorizacion}
    cd, sucursal = valor[con_movimientos.cd], valor[con_movimientos.sucursal]
    assert (cd.disponible, cd.valor_total) == (40, Decimal("4000.00"))          # costo actual $100
    assert (sucursal.disponible, sucursal.merma) == (5, 2)
    assert (sucursal.valor_total, sucursal.valor_merma) == (Decimal("500.00"), Decimal("200.00"))
    assert resumen.total_valorizado == Decimal("4500.00")  # la merma no suma


def test_r3_la_fecha_hasta_incluye_todo_el_dia(db, stock, escenario, reloj):
    reloj.ir_a(datetime(2026, 10, 31, 23, 59))
    stock.ingresar_compra(escenario.cd, escenario.producto, 5, REF)
    reloj.ir_a(datetime(2026, 11, 1, 0, 0))
    stock.ingresar_compra(escenario.cd, escenario.producto, 7, REF)

    octubre = ReporteMovimientos(db).consultar(date(2026, 10, 1), date(2026, 10, 31))

    assert [m.cantidad for m in octubre.movimientos] == [5]


@pytest.mark.parametrize("filtro, esperados", [
    ({"ubicacion_id": "cd"}, 2),
    ({"ubicacion_id": "sucursal"}, 4),
    ({"tipo": TipoMovimiento.EGRESO_VENTA}, 1),
])
def test_r3_filtra_por_ubicacion_y_tipo(db, con_movimientos, filtro, esperados):
    if "ubicacion_id" in filtro:
        filtro = {"ubicacion_id": getattr(con_movimientos, filtro["ubicacion_id"])}

    resumen = ReporteMovimientos(db).consultar(date(2026, 10, 1), date(2026, 10, 31), **filtro)

    assert len(resumen.movimientos) == esperados


def test_r3_filtra_por_categoria(db, con_movimientos):
    otra = db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Otra')").lastrowid

    resumen = ReporteMovimientos(db).consultar(date(2026, 10, 1), date(2026, 10, 31), categoria_id=otra)

    assert resumen.movimientos == [] and resumen.valorizacion == []


def test_r3_el_documento_se_muestra_con_su_numero(db, con_movimientos):
    resumen = ReporteMovimientos(db).consultar(date(2026, 10, 1), date(2026, 10, 31), tipo=TipoMovimiento.EGRESO_VENTA)

    assert resumen.movimientos[0].documento == "VENTA 1"


def test_r3_periodo_invertido(db):
    with pytest.raises(ValidacionError):
        ReporteMovimientos(db).consultar(date(2026, 10, 31), date(2026, 10, 1))


# === R4: tiempo de tránsito =======================================================================


def despachar(stock, reloj, e, remito, destino, cuando, cantidad=10):
    """Lo que hace logística al despachar: sale del CD y entra pendiente en el local."""
    reloj.ir_a(cuando)
    ref = Referencia("REMITO", remito, "turco")
    stock.egresar(e.cd, e.producto, cantidad, ref, tipo=TipoMovimiento.EGRESO_DESPACHO)
    stock.ingresar_pendiente(destino, e.producto, cantidad, ref)


def verificar(stock, reloj, e, remito, destino, cuando, cantidad=10, rechazadas=0):
    """Lo que hace logística al cerrar la recepción: verificados a disponible, rechazados a merma."""
    reloj.ir_a(cuando)
    ref = Referencia("REMITO", remito, "turco")
    if cantidad - rechazadas:
        stock.confirmar_disponible(destino, e.producto, cantidad - rechazadas, ref)
    if rechazadas:
        stock.registrar_merma(destino, e.producto, rechazadas, ref)


@pytest.fixture
def con_remitos(stock, reloj, escenario):
    e = escenario
    stock.ingresar_compra(e.cd, e.producto, 200, REF)
    despachar(stock, reloj, e, 1, e.sucursal, LUNES)
    verificar(stock, reloj, e, 1, e.sucursal, LUNES + timedelta(hours=26))
    despachar(stock, reloj, e, 2, e.sucursal, LUNES + timedelta(days=1))
    verificar(stock, reloj, e, 2, e.sucursal, LUNES + timedelta(days=1, hours=10), rechazadas=3)
    despachar(stock, reloj, e, 3, e.otra_sucursal, LUNES + timedelta(days=2))
    verificar(stock, reloj, e, 3, e.otra_sucursal, LUNES + timedelta(days=2, hours=4))
    despachar(stock, reloj, e, 4, e.otra_sucursal, LUNES + timedelta(days=3))  # todavía en tránsito
    return e


def test_r4_calcula_el_tiempo_de_cada_remito(db, con_remitos):
    resumen = ReporteTransito(db).consultar(date(2026, 10, 1), date(2026, 10, 31))

    horas = {f.remito_id: f.horas for f in resumen.filas}
    assert horas == {1: 26.0, 2: 10.0, 3: 4.0, 4: None}
    assert resumen.cantidad_en_transito == 1
    assert resumen.promedio_horas == pytest.approx(40 / 3)


def test_r4_promedio_minimo_y_maximo_por_sucursal(db, con_remitos):
    resumen = ReporteTransito(db).consultar(date(2026, 10, 1), date(2026, 10, 31))

    lento, rapido = resumen.por_sucursal()
    assert (lento.destino_id, lento.remitos, lento.promedio_horas) == (con_remitos.sucursal, 2, 18.0)
    assert (lento.minimo_horas, lento.maximo_horas) == (10.0, 26.0)
    assert (rapido.destino_id, rapido.remitos, rapido.promedio_horas) == (con_remitos.otra_sucursal, 1, 4.0)


def test_r4_marca_los_remitos_con_rechazos_y_cuenta_unidades(db, con_remitos):
    resumen = ReporteTransito(db).consultar(date(2026, 10, 1), date(2026, 10, 31))

    remito = next(f for f in resumen.filas if f.remito_id == 2)
    assert remito.con_rechazos and remito.unidades == 10


def test_r4_filtra_por_sucursal_y_por_fecha_de_despacho(db, con_remitos):
    reporte = ReporteTransito(db)

    assert [f.remito_id for f in reporte.consultar(date(2026, 10, 1), date(2026, 10, 31),
                                                   con_remitos.otra_sucursal).filas] == [3, 4]
    assert [f.remito_id for f in reporte.consultar(date(2026, 10, 6), date(2026, 10, 6)).filas] == [2]


def test_r4_ignora_movimientos_que_no_son_de_remitos(db, stock, escenario):
    stock.ingresar_compra(escenario.cd, escenario.producto, 10, REF)
    stock.egresar(escenario.cd, escenario.producto, 5, Referencia("CARGA_INICIAL"),
                  tipo=TipoMovimiento.EGRESO_DESPACHO)

    assert ReporteTransito(db).consultar(date(2026, 10, 1), date(2026, 10, 31)).filas == []


@pytest.mark.parametrize("horas, texto", [
    (None, "En tránsito"),
    (0.5, "30 min"),
    (4, "4 h 0 min"),
    (26.5, "1 d 2 h 30 min"),
])
def test_formato_duracion(horas, texto):
    assert formato_duracion(horas) == texto
