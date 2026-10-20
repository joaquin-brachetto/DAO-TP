"""Tests automatizados del Reporte R5 (turco):
`ReporteBultosRechazados` – Bultos rechazados y mermas por rotura o adulteración de precinto.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.dominio.inventario.modelos import Referencia
from src.excepciones import ValidacionError
from src.reportes.logistica_reporte import ReporteBultosRechazados, TipoAnomaliaPrecinto
from src.servicios.logistica_service import EspecificacionBulto, LogisticaService
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockService
from tests.utilidades import TestConBaseEnMemoria

REF = Referencia("ORDEN_COMPRA", 1, usuario="test")
DIA_BASE = datetime(2026, 10, 15, 10, 0, 0)


class Reloj:
    def __init__(self, momento: datetime = DIA_BASE) -> None:
        self.momento = momento

    def __call__(self) -> datetime:
        return self.momento

    def ir_a(self, momento: datetime) -> None:
        self.momento = momento


@pytest.fixture
def escenario_r5(db):
    reloj = Reloj(DIA_BASE)
    stock = StockService(db, ahora=reloj)
    reposicion = ReposicionService(db)
    logistica = LogisticaService(db, stock_service=stock, reposicion_service=reposicion, ahora=reloj)

    cd = db.ejecutar("INSERT INTO ubicacion (tipo, codigo, nombre) VALUES ('CD', 'CD1', 'CD Central')").lastrowid
    suc_1 = db.ejecutar(
        "INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('SUCURSAL', 'S1', 'Sucursal Centro', 1)"
    ).lastrowid
    suc_2 = db.ejecutar(
        "INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('SUCURSAL', 'S2', 'Sucursal Norte', 2)"
    ).lastrowid
    cat_almacen = db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Almacén')").lastrowid
    cat_lacteos = db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Lácteos')").lastrowid

    p_yerba = db.ejecutar(
        "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) VALUES (?, ?, ?, ?, ?)",
        ("YER-1", "Yerba 1kg", cat_almacen, Decimal("1000.00"), Decimal("1500.00")),
    ).lastrowid
    p_queso = db.ejecutar(
        "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) VALUES (?, ?, ?, ?, ?)",
        ("QUE-1", "Queso Horma", cat_lacteos, Decimal("2500.00"), Decimal("3800.00")),
    ).lastrowid

    stock.ingresar_compra(cd, p_yerba, 200, REF, costo_unitario=Decimal("1000.00"))
    stock.ingresar_compra(cd, p_queso, 200, REF, costo_unitario=Decimal("2500.00"))

    # Remito 1 a Sucursal Centro: 3 bultos (1 verificado, 1 precinto roto, 1 precinto no coincide)
    nec_1 = reposicion.crear_necesidad(suc_1, [(p_yerba, 15), (p_queso, 4)], fecha=DIA_BASE.date())
    orden_1 = reposicion.consolidar([nec_1.id], fecha=DIA_BASE)
    rem_1 = logistica.armar_remito(
        orden_1.id,
        [
            EspecificacionBulto([(p_yerba, 5)], numero_precinto="P-101"),
            EspecificacionBulto([(p_yerba, 10)], numero_precinto="P-102"),     # llegará roto ($10.000)
            EspecificacionBulto([(p_queso, 4)], numero_precinto="P-103"),      # llegará adulterado ($10.000)
        ],
    )
    logistica.registrar_despacho([rem_1.id], "Expreso 1", "AA 111 AA")
    b1, b2, b3 = rem_1.bultos
    logistica.procesar_recepcion_completa(
        rem_1.id,
        recibido_por="juan",
        controles_por_bulto=[
            (b1.id, "P-101", True, "OK"),
            (b2.id, "P-102", False, "Precinto cortado"),
            (b3.id, "P-999", True, "Número adulterado"),
        ],
    )

    # Remito 2 a Sucursal Norte (5 días después): 2 bultos (1 verificado, 1 roto y no coincide)
    reloj.ir_a(DIA_BASE + timedelta(days=5))
    nec_2 = reposicion.crear_necesidad(suc_2, [(p_yerba, 8)], fecha=reloj().date())
    orden_2 = reposicion.consolidar([nec_2.id], fecha=reloj())
    rem_2 = logistica.armar_remito(
        orden_2.id,
        [
            EspecificacionBulto([(p_yerba, 5)], numero_precinto="P-201"),
            EspecificacionBulto([(p_yerba, 3)], numero_precinto="P-202"),  # roto y no coincide ($3.000)
        ],
    )
    logistica.registrar_despacho([rem_2.id], "Expreso 2", "BB 222 BB")
    b2_1, b2_2 = rem_2.bultos
    logistica.procesar_recepcion_completa(
        rem_2.id,
        recibido_por="maria",
        controles_por_bulto=[
            (b2_1.id, "P-201", True, "OK"),
            (b2_2.id, "P-000", False, "Roto y distinto"),
        ],
    )

    return {
        "suc_1": suc_1,
        "suc_2": suc_2,
        "cat_almacen": cat_almacen,
        "cat_lacteos": cat_lacteos,
        "p_yerba": p_yerba,
        "p_queso": p_queso,
    }


def test_r5_calcula_totales_unidades_valor_merma_y_tasa_global(db, escenario_r5):
    reporte = ReporteBultosRechazados(db)
    resumen = reporte.consultar(date(2026, 10, 1), date(2026, 10, 31))

    assert resumen.total_bultos_evaluados == 5
    assert resumen.total_bultos_rechazados == 3
    assert resumen.tasa_rechazo_global == Decimal("60.00")
    assert resumen.total_unidades_merma == 17  # 10 yerba + 4 queso + 3 yerba
    assert resumen.total_valor_merma == Decimal("23000.00")


def test_r5_agrupa_resumen_por_sucursal_y_desglose_por_producto(db, escenario_r5):
    resumen = ReporteBultosRechazados(db).consultar(date(2026, 10, 1), date(2026, 10, 31))

    por_suc = {s.sucursal_id: s for s in resumen.por_sucursal}
    s1 = por_suc[escenario_r5["suc_1"]]
    s2 = por_suc[escenario_r5["suc_2"]]

    assert (s1.total_bultos_recibidos, s1.bultos_verificados, s1.bultos_rechazados) == (3, 1, 2)
    assert s1.porcentaje_rechazo == Decimal("66.67")
    assert (s1.unidades_merma, s1.valor_merma) == (14, Decimal("20000.00"))

    assert (s2.total_bultos_recibidos, s2.bultos_verificados, s2.bultos_rechazados) == (2, 1, 1)
    assert s2.porcentaje_rechazo == Decimal("50.00")
    assert (s2.unidades_merma, s2.valor_merma) == (3, Decimal("3000.00"))

    assert len(resumen.mermas_por_producto) == 3


def test_r5_filtra_por_sucursal_categoria_periodo_y_tipo_anomalia(db, escenario_r5):
    reporte = ReporteBultosRechazados(db)

    # Filtro por sucursal
    solo_s2 = reporte.consultar(
        date(2026, 10, 1), date(2026, 10, 31), sucursal_id=escenario_r5["suc_2"]
    )
    assert solo_s2.total_bultos_rechazados == 1
    assert solo_s2.total_valor_merma == Decimal("3000.00")

    # Filtro por categoría Lácteos
    solo_lacteos = reporte.consultar(
        date(2026, 10, 1), date(2026, 10, 31), categoria_id=escenario_r5["cat_lacteos"]
    )
    assert solo_lacteos.total_bultos_rechazados == 1
    assert solo_lacteos.total_unidades_merma == 4
    assert solo_lacteos.total_valor_merma == Decimal("10000.00")

    # Filtro por tipo de anomalía: PRECINTO_ROTO (incluye los que llegaron con precinto_integro == False)
    rotos = reporte.consultar(
        date(2026, 10, 1),
        date(2026, 10, 31),
        tipo_anomalia=TipoAnomaliaPrecinto.PRECINTO_ROTO,
    )
    assert rotos.total_bultos_rechazados == 2  # P-102 y P-202

    # Filtro por fecha acotada al primer día
    primer_dia = reporte.consultar(date(2026, 10, 15), date(2026, 10, 15))
    assert primer_dia.total_bultos_rechazados == 2


def test_r5_valida_periodo_y_tipo_anomalia(db):
    reporte = ReporteBultosRechazados(db)
    with pytest.raises(ValidacionError):
        reporte.consultar(date(2026, 10, 31), date(2026, 10, 1))
    with pytest.raises(ValidacionError):
        reporte.consultar(date(2026, 10, 1), date(2026, 10, 31), tipo_anomalia="INEXISTENTE")


class TestReporteR5Unittest(TestConBaseEnMemoria):
    """Ejecución del test de R5 bajo `python -m unittest`."""

    def test_reporte_r5_sobre_datos_de_prueba(self) -> None:
        from src.datos_prueba import cargar_datos_de_prueba
        from src.datos_prueba_inventario import cargar_stock_de_prueba
        from src.datos_prueba_logistica import cargar_logistica_de_prueba

        cargar_datos_de_prueba(self.db)
        cargar_stock_de_prueba(self.db)
        cargar_logistica_de_prueba(self.db)

        hoy = date.today()
        resumen = ReporteBultosRechazados(self.db).consultar(hoy - timedelta(days=10), hoy)
        self.assertEqual(resumen.total_bultos_rechazados, 2)
        self.assertGreater(resumen.total_valor_merma, Decimal("0"))
