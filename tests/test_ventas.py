"""Tests del módulo de ventas (vinchi): P7, V3, V5, Strategy de medios de pago y R6.

La mayoría usa un doble del contrato de StockService; los dos últimos usan el real.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.dominio.inventario.modelos import Referencia
from src.dominio.ventas.modelos import (
    Cliente,
    CondicionIva,
    DetalleDevolucion,
    TarjetaCredito,
)
from src.excepciones import EntidadDuplicadaError, ValidacionError
from src.reportes.ventas_reporte import ReporteVentas
from src.servicios.stock_service import StockService as StockServiceReal
from src.servicios.ventas_service import PagoSolicitado, VentasService


class StockServicePrueba:
    """Doble de inventario que permite observar egresos y reingresos solicitados."""

    def __init__(self, disponible: int = 10) -> None:
        self.disponibles: dict[tuple[int, int], int] = {}
        self.disponible_por_defecto = disponible
        self.egresos: list[tuple[int, int, int, str]] = []
        self.reingresos: list[tuple[int, int, int, str]] = []

    def stock_disponible(self, ubicacion_id: int, producto_id: int) -> int:
        return self.disponibles.get((ubicacion_id, producto_id), self.disponible_por_defecto)

    def egresar(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: str) -> None:
        if self.stock_disponible(ubicacion_id, producto_id) < cantidad:
            raise ValidacionError("Stock insuficiente en el doble de prueba.")
        clave = (ubicacion_id, producto_id)
        self.disponibles[clave] = self.stock_disponible(*clave) - cantidad
        self.egresos.append((ubicacion_id, producto_id, cantidad, ref))

    def reingresar(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: str) -> None:
        clave = (ubicacion_id, producto_id)
        self.disponibles[clave] = self.stock_disponible(*clave) + cantidad
        self.reingresos.append((ubicacion_id, producto_id, cantidad, ref))


@pytest.fixture
def local(db):
    """Un local (id 1, punto de venta 10) y un producto (id 1) de $10 con costo $6."""
    db.ejecutar(
        "INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('SUCURSAL', 'LOC-1', 'Local 1', 10)"
    )
    db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Almacén')")
    db.ejecutar(
        "INSERT INTO producto (sku, nombre, unidad_medida, categoria_id, costo_actual, precio_venta_actual) "
        "VALUES ('SKU-1', 'Producto 1', 'UN', 1, ?, ?)",
        (Decimal("6.00"), Decimal("10.00")),
    )
    return db


@pytest.fixture
def stock(local):
    return StockServicePrueba()


@pytest.fixture
def servicio(local, stock):
    """VentasService con el doble de stock y la caja del local abierta con $50."""
    ventas = VentasService(local, stock)
    ventas.abrir_caja(1, Decimal("50.00"))
    return ventas


def efectivo(monto: str) -> PagoSolicitado:
    return PagoSolicitado("EFECTIVO", Decimal(monto))


def contar(db, tabla: str) -> int:
    return db.consultar_uno(f"SELECT COUNT(*) AS n FROM {tabla}")["n"]


def detalle_de(db, venta_id: int) -> int:
    return int(db.consultar_uno("SELECT id FROM detalle_venta WHERE venta_id = ?", (venta_id,))["id"])


# --- Venta y cobro (P7, V3, Strategy) --------------------------------------------------------


def test_venta_mixta_egresa_stock_emite_ticket_y_actualiza_caja(db, servicio, stock):
    venta_id = servicio.registrar_venta(
        1,
        {1: 2},
        [efectivo("10.00"), PagoSolicitado("CREDITO", Decimal("10.00"), {"autorizacion": "AUT-1"}, cuotas=2)],
        vendedor="Vinchi",
    )

    venta = db.consultar_uno("SELECT * FROM venta WHERE id = ?", (venta_id,))
    recibo = db.consultar_uno("SELECT * FROM comprobante WHERE venta_id = ?", (venta_id,))
    cobros = db.consultar("SELECT * FROM cobro WHERE venta_id = ?", (venta_id,))
    assert venta["total"] == Decimal("20.30")
    assert recibo["tipo"] == "TICKET"
    assert recibo["numero"] == 1
    assert len(cobros) == 2
    assert cobros[1]["recargo"] == Decimal("0.30")
    assert stock.egresos == [(1, 1, 2, f"VENTA:{venta_id}")]
    assert servicio.saldo_caja_abierta(1) == Decimal("70.30")


def test_stock_insuficiente_no_registra_venta(db, servicio, stock):
    stock.disponibles[(1, 1)] = 1

    with pytest.raises(ValidacionError, match="Stock disponible insuficiente"):
        servicio.registrar_venta(1, {1: 2}, [efectivo("20.00")], vendedor="Vinchi")

    assert contar(db, "venta") == 0
    assert stock.egresos == []


def test_pago_mixto_debe_cubrir_una_vez_el_total_base(db, servicio):
    with pytest.raises(ValidacionError, match="deben sumar 20.00"):
        servicio.registrar_venta(1, {1: 2}, [efectivo("19.99")], vendedor="Vinchi")

    assert contar(db, "venta") == 0


def test_tarjeta_a_cuotas_calcula_recargo_por_strategy():
    strategy = TarjetaCredito(cuotas=4)
    assert strategy.calcular_recargo(Decimal("100.00")) == Decimal("9.00")


# --- Devoluciones (V5) -----------------------------------------------------------------------


def test_devolucion_parcial_reingresa_stock_emite_nota_y_egresa_caja(db, servicio, stock):
    venta_id = servicio.registrar_venta(1, {1: 2}, [efectivo("20.00")], vendedor="Vinchi")

    devolucion_id = servicio.registrar_devolucion(
        venta_id, [DetalleDevolucion(detalle_de(db, venta_id), 1)], "Producto sin uso"
    )

    devolucion = db.consultar_uno("SELECT * FROM devolucion WHERE id = ?", (devolucion_id,))
    nota = db.consultar_uno("SELECT * FROM comprobante WHERE devolucion_id = ?", (devolucion_id,))
    assert devolucion["total_reintegrar"] == Decimal("10.00")
    assert nota["tipo"] == "NOTA_CREDITO"
    assert nota["numero"] == 1
    assert stock.reingresos == [(1, 1, 1, f"DEVOLUCION:{devolucion_id}")]
    assert servicio.saldo_caja_abierta(1) == Decimal("60.00")


def test_no_devuelve_mas_unidades_de_las_vendidas(db, servicio):
    venta_id = servicio.registrar_venta(1, {1: 1}, [efectivo("10.00")], vendedor="Vinchi")

    with pytest.raises(ValidacionError, match="unidades restantes"):
        servicio.registrar_devolucion(venta_id, [DetalleDevolucion(detalle_de(db, venta_id), 2)], "Excede la venta")

    assert contar(db, "devolucion") == 0


def test_no_devuelve_un_detalle_que_pertenece_a_otra_venta(db, servicio):
    primera = servicio.registrar_venta(1, {1: 1}, [efectivo("10.00")], vendedor="Vinchi")
    segunda = servicio.registrar_venta(1, {1: 1}, [efectivo("10.00")], vendedor="Vinchi")

    with pytest.raises(ValidacionError, match="pertenecer a la venta"):
        servicio.registrar_devolucion(segunda, [DetalleDevolucion(detalle_de(db, primera), 1)], "Venta incorrecta")


def test_no_acepta_devoluciones_fuera_del_plazo(db, servicio):
    fecha_venta = datetime.now() - timedelta(days=31)
    venta_id = servicio.registrar_venta(1, {1: 1}, [efectivo("10.00")], vendedor="Vinchi", fecha_hora=fecha_venta)

    with pytest.raises(ValidacionError, match="plazo de devolución"):
        servicio.registrar_devolucion(venta_id, [DetalleDevolucion(detalle_de(db, venta_id), 1)], "Fuera de plazo")


def test_devoluciones_parciales_acumuladas_no_superan_cantidad_vendida(db, servicio):
    venta_id = servicio.registrar_venta(1, {1: 2}, [efectivo("20.00")], vendedor="Vinchi")
    detalle_id = detalle_de(db, venta_id)
    servicio.registrar_devolucion(venta_id, [DetalleDevolucion(detalle_id, 1)], "Primera unidad")
    servicio.registrar_devolucion(venta_id, [DetalleDevolucion(detalle_id, 1)], "Segunda unidad")

    with pytest.raises(ValidacionError, match="unidades restantes"):
        servicio.registrar_devolucion(venta_id, [DetalleDevolucion(detalle_id, 1)], "Unidad inexistente")

    importes = db.consultar("SELECT total_reintegrar FROM devolucion WHERE venta_id = ? ORDER BY id", (venta_id,))
    assert [fila["total_reintegrar"] for fila in importes] == [Decimal("10.00"), Decimal("10.00")]


def test_devolucion_puede_no_reingresar_stock(db, servicio, stock):
    venta_id = servicio.registrar_venta(1, {1: 1}, [efectivo("10.00")], vendedor="Vinchi")

    servicio.registrar_devolucion(
        venta_id, [DetalleDevolucion(detalle_de(db, venta_id), 1, reingresa_stock=False)], "Producto dañado"
    )

    assert stock.reingresos == []
    renglon = db.consultar_uno("SELECT reingresa_stock FROM detalle_devolucion")
    assert not renglon["reingresa_stock"]


def test_devolucion_de_producto_gratuito_no_crea_egreso_de_caja(db, servicio):
    db.ejecutar(
        "INSERT INTO producto (sku, nombre, unidad_medida, categoria_id, costo_actual, precio_venta_actual) "
        "VALUES ('SKU-GRATIS', 'Muestra', 'UN', 1, ?, ?)",
        (Decimal("1.00"), Decimal("0.00")),
    )
    venta_id = servicio.registrar_venta(1, {1: 1, 2: 1}, [efectivo("10.00")], vendedor="Vinchi")
    detalle = db.consultar_uno(
        "SELECT id FROM detalle_venta WHERE venta_id = ? AND producto_id = 2", (venta_id,)
    )
    movimientos_antes = contar(db, "movimiento_caja")

    servicio.registrar_devolucion(venta_id, [DetalleDevolucion(int(detalle["id"]), 1)], "Muestra sin cargo")

    devolucion = db.consultar_uno("SELECT total_reintegrar FROM devolucion")
    assert devolucion["total_reintegrar"] == Decimal("0.00")
    assert contar(db, "movimiento_caja") == movimientos_antes


# --- Comprobantes (Factory) y clientes -------------------------------------------------------


@pytest.mark.parametrize(
    "documento, condicion, tipo_esperado",
    [
        ("20123456789", CondicionIva.RESPONSABLE_INSCRIPTO, "FACTURA_A"),
        ("27123456789", CondicionIva.EXENTO, "FACTURA_B"),
    ],
)
def test_tipo_de_factura_segun_condicion_de_iva(db, servicio, documento, condicion, tipo_esperado):
    cliente = servicio.registrar_cliente(Cliente(documento, "Cliente", condicion))

    venta_id = servicio.registrar_venta(1, {1: 1}, [efectivo("10.00")], cliente_id=cliente.id, vendedor="Vinchi")

    factura = db.consultar_uno("SELECT tipo FROM comprobante WHERE venta_id = ?", (venta_id,))
    assert factura["tipo"] == tipo_esperado


def test_documento_de_cliente_no_se_duplica(servicio):
    servicio.registrar_cliente(Cliente("20123456789", "Cliente 1"))
    with pytest.raises(EntidadDuplicadaError):
        servicio.registrar_cliente(Cliente("20123456789", "Cliente 2"))


def test_numeracion_de_venta_es_correlativa_por_sucursal(db, servicio):
    for _ in range(2):
        servicio.registrar_venta(1, {1: 1}, [efectivo("10.00")], vendedor="Vinchi")

    numeros = db.consultar("SELECT numero FROM venta ORDER BY numero")
    assert [fila["numero"] for fila in numeros] == [1, 2]


# --- Reporte R6 ------------------------------------------------------------------------------


def test_reporte_r6_agrupa_por_medio_sin_duplicar_ventas_mixtas(db, servicio):
    servicio.registrar_venta(
        1,
        {1: 2},
        [efectivo("10.00"), PagoSolicitado("TRANSFERENCIA", Decimal("10.00"), {"referencia": "TRX-1"})],
        vendedor="Vinchi",
    )

    filas = ReporteVentas(db).consultar(date.today(), date.today(), 1)

    assert {fila.medio_pago for fila in filas} == {"EFECTIVO", "TRANSFERENCIA"}
    assert [fila.cantidad_ventas for fila in filas] == [1, 1]
    assert sum((fila.total_cobrado for fila in filas), Decimal("0.00")) == Decimal("20.00")


# --- Caja ------------------------------------------------------------------------------------


def test_no_habilita_dos_cajas_abiertas_en_la_misma_sucursal(servicio):
    with pytest.raises(ValidacionError, match="Ya existe una caja abierta"):
        servicio.abrir_caja(1, Decimal("0.00"))


def test_cerrar_caja_devuelve_saldo_final(servicio):
    servicio.registrar_venta(1, {1: 1}, [efectivo("10.00")], vendedor="Vinchi")

    saldo = servicio.cerrar_caja(1)

    assert saldo == Decimal("60.00")
    assert servicio.saldo_caja_abierta(1) is None


# --- Integración con el StockService real (pohlsi) -------------------------------------------


def test_integracion_real_venta_y_devolucion_actualiza_stock_y_movimientos(db, servicio):
    stock_real = StockServiceReal(db)
    stock_real.ingresar_pendiente(1, 1, 5, Referencia("REMITO", 25))
    stock_real.confirmar_disponible(1, 1, 5, Referencia("REMITO", 25))
    ventas = VentasService(db, stock_real)

    venta_id = ventas.registrar_venta(1, {1: 2}, [efectivo("20.00")], vendedor="Vinchi")
    assert stock_real.stock_disponible(1, 1) == 3

    devolucion_id = ventas.registrar_devolucion(
        venta_id, [DetalleDevolucion(detalle_de(db, venta_id), 1)], "Reintegro integrado"
    )

    assert stock_real.stock_disponible(1, 1) == 4
    movimientos = db.consultar("SELECT tipo, tipo_documento, documento_id FROM movimiento_stock ORDER BY id")
    assert [movimiento["tipo"] for movimiento in movimientos] == [
        "INGRESO_PENDIENTE", "CONFIRMACION_VERIFICADO", "EGRESO_VENTA", "REINGRESO_DEVOLUCION",
    ]
    assert (movimientos[2]["tipo_documento"], movimientos[2]["documento_id"]) == ("VENTA", venta_id)
    assert (movimientos[3]["tipo_documento"], movimientos[3]["documento_id"]) == ("DEVOLUCION", devolucion_id)


def test_error_del_stock_service_real_revierte_venta_cobros_y_movimientos(db, servicio):
    class StockQueFallaAlEgresar(StockServiceReal):
        def egresar(self, ubicacion_id, producto_id, cantidad, ref, tipo=None):
            super().egresar(ubicacion_id, producto_id, cantidad, ref, **({} if tipo is None else {"tipo": tipo}))
            raise RuntimeError("falló la confirmación externa")

    stock_real = StockQueFallaAlEgresar(db)
    stock_real.ingresar_pendiente(1, 1, 3, Referencia("REMITO", 26))
    stock_real.confirmar_disponible(1, 1, 3, Referencia("REMITO", 26))
    ventas = VentasService(db, stock_real)

    with pytest.raises(RuntimeError, match="falló la confirmación externa"):
        ventas.registrar_venta(1, {1: 1}, [efectivo("10.00")], vendedor="Vinchi")

    assert stock_real.stock_disponible(1, 1) == 3
    assert contar(db, "venta") == 0
    assert contar(db, "cobro") == 0
    tipos = [fila["tipo"] for fila in db.consultar("SELECT tipo FROM movimiento_stock ORDER BY id")]
    assert tipos == ["INGRESO_PENDIENTE", "CONFIRMACION_VERIFICADO"]
