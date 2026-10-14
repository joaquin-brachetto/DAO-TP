"""Pruebas del módulo de vinchi con un doble del contrato de StockService."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from src.dominio.ventas.modelos import (
    Cliente,
    CondicionIva,
    DetalleDevolucion,
    TarjetaCredito,
)
from src.excepciones import EntidadDuplicadaError, ValidacionError
from src.reportes.ventas_reporte import ReporteVentas
from src.servicios.ventas_service import PagoSolicitado, VentasService
from tests.utilidades import TestConBaseEnMemoria


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


class VentasTests(TestConBaseEnMemoria):
    def setUp(self) -> None:
        super().setUp()
        self.db.ejecutar(
            "INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('SUCURSAL', 'LOC-1', 'Local 1', 10)"
        )
        self.db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Almacén')")
        self.db.ejecutar(
            "INSERT INTO producto (sku, nombre, unidad_medida, categoria_id, costo_actual, precio_venta_actual) "
            "VALUES ('SKU-1', 'Producto 1', 'UN', 1, ?, ?)",
            (Decimal("6.00"), Decimal("10.00")),
        )
        self.stock = StockServicePrueba()
        self.service = VentasService(self.db, self.stock)
        self.caja = self.service.abrir_caja(1, Decimal("50.00"))

    def pago_efectivo(self, monto: str) -> PagoSolicitado:
        return PagoSolicitado("EFECTIVO", Decimal(monto))

    def test_venta_mixta_egresa_stock_emite_ticket_y_actualiza_caja(self) -> None:
        venta_id = self.service.registrar_venta(
            1,
            {1: 2},
            [self.pago_efectivo("10.00"), PagoSolicitado(
                "CREDITO", Decimal("10.00"), {"autorizacion": "AUT-1"}, cuotas=2
            )],
            vendedor="Vinchi",
        )

        venta = self.db.consultar_uno("SELECT * FROM venta WHERE id = ?", (venta_id,))
        recibo = self.db.consultar_uno("SELECT * FROM comprobante WHERE venta_id = ?", (venta_id,))
        cobros = self.db.consultar("SELECT * FROM cobro WHERE venta_id = ?", (venta_id,))
        self.assertEqual(venta["total"], Decimal("20.30"))
        self.assertEqual(recibo["tipo"], "TICKET")
        self.assertEqual(recibo["numero"], 1)
        self.assertEqual(len(cobros), 2)
        self.assertEqual(cobros[1]["recargo"], Decimal("0.30"))
        self.assertEqual(self.stock.egresos, [(1, 1, 2, f"VENTA:{venta_id}")])
        self.assertEqual(self.service.saldo_caja_abierta(1), Decimal("70.30"))

    def test_stock_insuficiente_no_registra_venta(self) -> None:
        self.stock.disponibles[(1, 1)] = 1

        with self.assertRaisesRegex(ValidacionError, "Stock disponible insuficiente"):
            self.service.registrar_venta(1, {1: 2}, [self.pago_efectivo("20.00")], vendedor="Vinchi")

        self.assertEqual(self.db.consultar_uno("SELECT COUNT(*) AS n FROM venta")["n"], 0)
        self.assertEqual(self.stock.egresos, [])

    def test_pago_mixto_debe_cubrir_una_vez_el_total_base(self) -> None:
        with self.assertRaisesRegex(ValidacionError, "deben sumar 20.00"):
            self.service.registrar_venta(
                1, {1: 2}, [self.pago_efectivo("19.99")], vendedor="Vinchi"
            )

        self.assertEqual(self.db.consultar_uno("SELECT COUNT(*) AS n FROM venta")["n"], 0)

    def test_tarjeta_a_cuotas_calcula_recargo_por_strategy(self) -> None:
        strategy = TarjetaCredito(cuotas=4)
        self.assertEqual(strategy.calcular_recargo(Decimal("100.00")), Decimal("9.00"))

    def test_devolucion_parcial_reingresa_stock_emite_nota_y_egresa_caja(self) -> None:
        venta_id = self.service.registrar_venta(
            1, {1: 2}, [self.pago_efectivo("20.00")], vendedor="Vinchi"
        )
        detalle = self.db.consultar_uno("SELECT id FROM detalle_venta WHERE venta_id = ?", (venta_id,))

        devolucion_id = self.service.registrar_devolucion(
            venta_id, [DetalleDevolucion(int(detalle["id"]), 1)], "Producto sin uso"
        )

        devolucion = self.db.consultar_uno("SELECT * FROM devolucion WHERE id = ?", (devolucion_id,))
        nota = self.db.consultar_uno("SELECT * FROM comprobante WHERE devolucion_id = ?", (devolucion_id,))
        self.assertEqual(devolucion["total_reintegrar"], Decimal("10.00"))
        self.assertEqual(nota["tipo"], "NOTA_CREDITO")
        self.assertEqual(nota["numero"], 1)
        self.assertEqual(self.stock.reingresos, [(1, 1, 1, f"DEVOLUCION:{devolucion_id}")])
        self.assertEqual(self.service.saldo_caja_abierta(1), Decimal("60.00"))

    def test_no_devuelve_mas_unidades_de_las_vendidas(self) -> None:
        venta_id = self.service.registrar_venta(
            1, {1: 1}, [self.pago_efectivo("10.00")], vendedor="Vinchi"
        )
        detalle = self.db.consultar_uno("SELECT id FROM detalle_venta WHERE venta_id = ?", (venta_id,))

        with self.assertRaisesRegex(ValidacionError, "unidades restantes"):
            self.service.registrar_devolucion(
                venta_id, [DetalleDevolucion(int(detalle["id"]), 2)], "Excede la venta"
            )

        self.assertEqual(self.db.consultar_uno("SELECT COUNT(*) AS n FROM devolucion")["n"], 0)

    def test_no_devuelve_un_detalle_que_pertenece_a_otra_venta(self) -> None:
        primera = self.service.registrar_venta(
            1, {1: 1}, [self.pago_efectivo("10.00")], vendedor="Vinchi"
        )
        segunda = self.service.registrar_venta(
            1, {1: 1}, [self.pago_efectivo("10.00")], vendedor="Vinchi"
        )
        detalle_primera = self.db.consultar_uno(
            "SELECT id FROM detalle_venta WHERE venta_id = ?", (primera,)
        )

        with self.assertRaisesRegex(ValidacionError, "pertenecer a la venta"):
            self.service.registrar_devolucion(
                segunda, [DetalleDevolucion(int(detalle_primera["id"]), 1)], "Venta incorrecta"
            )

    def test_no_acepta_devoluciones_fuera_del_plazo(self) -> None:
        fecha_venta = datetime.now() - timedelta(days=31)
        venta_id = self.service.registrar_venta(
            1, {1: 1}, [self.pago_efectivo("10.00")], vendedor="Vinchi", fecha_hora=fecha_venta
        )
        detalle = self.db.consultar_uno("SELECT id FROM detalle_venta WHERE venta_id = ?", (venta_id,))

        with self.assertRaisesRegex(ValidacionError, "plazo de devolución"):
            self.service.registrar_devolucion(
                venta_id, [DetalleDevolucion(int(detalle["id"]), 1)], "Fuera de plazo"
            )

    def test_devoluciones_parciales_acumuladas_no_superan_cantidad_vendida(self) -> None:
        venta_id = self.service.registrar_venta(
            1, {1: 2}, [self.pago_efectivo("20.00")], vendedor="Vinchi"
        )
        detalle = self.db.consultar_uno("SELECT id FROM detalle_venta WHERE venta_id = ?", (venta_id,))
        detalle_id = int(detalle["id"])
        self.service.registrar_devolucion(
            venta_id, [DetalleDevolucion(detalle_id, 1)], "Primera unidad"
        )
        self.service.registrar_devolucion(
            venta_id, [DetalleDevolucion(detalle_id, 1)], "Segunda unidad"
        )

        with self.assertRaisesRegex(ValidacionError, "unidades restantes"):
            self.service.registrar_devolucion(
                venta_id, [DetalleDevolucion(detalle_id, 1)], "Unidad inexistente"
            )
        importes = self.db.consultar(
            "SELECT total_reintegrar FROM devolucion WHERE venta_id = ? ORDER BY id", (venta_id,)
        )
        self.assertEqual([fila["total_reintegrar"] for fila in importes], [Decimal("10.00"), Decimal("10.00")])

    def test_devolucion_puede_no_reingresar_stock(self) -> None:
        venta_id = self.service.registrar_venta(
            1, {1: 1}, [self.pago_efectivo("10.00")], vendedor="Vinchi"
        )
        detalle = self.db.consultar_uno("SELECT id FROM detalle_venta WHERE venta_id = ?", (venta_id,))

        self.service.registrar_devolucion(
            venta_id, [DetalleDevolucion(int(detalle["id"]), 1, reingresa_stock=False)], "Producto dañado"
        )

        self.assertEqual(self.stock.reingresos, [])
        renglon = self.db.consultar_uno("SELECT reingresa_stock FROM detalle_devolucion")
        self.assertFalse(renglon["reingresa_stock"])

    def test_devolucion_de_producto_gratuito_no_crea_egreso_de_caja(self) -> None:
        self.db.ejecutar(
            "INSERT INTO producto (sku, nombre, unidad_medida, categoria_id, costo_actual, precio_venta_actual) "
            "VALUES ('SKU-GRATIS', 'Muestra', 'UN', 1, ?, ?)",
            (Decimal("1.00"), Decimal("0.00")),
        )
        venta_id = self.service.registrar_venta(
            1, {1: 1, 2: 1}, [self.pago_efectivo("10.00")], vendedor="Vinchi"
        )
        detalle = self.db.consultar_uno(
            "SELECT id FROM detalle_venta WHERE venta_id = ? AND producto_id = 2", (venta_id,)
        )
        movimientos_antes = self.db.consultar_uno("SELECT COUNT(*) AS n FROM movimiento_caja")["n"]

        self.service.registrar_devolucion(
            venta_id, [DetalleDevolucion(int(detalle["id"]), 1)], "Muestra sin cargo"
        )

        devolucion = self.db.consultar_uno("SELECT total_reintegrar FROM devolucion")
        movimientos_despues = self.db.consultar_uno("SELECT COUNT(*) AS n FROM movimiento_caja")["n"]
        self.assertEqual(devolucion["total_reintegrar"], Decimal("0.00"))
        self.assertEqual(movimientos_antes, movimientos_despues)

    def test_factura_a_para_responsable_inscripto(self) -> None:
        cliente = self.service.registrar_cliente(
            Cliente("20123456789", "Cliente RI", CondicionIva.RESPONSABLE_INSCRIPTO)
        )
        venta_id = self.service.registrar_venta(
            1, {1: 1}, [self.pago_efectivo("10.00")], cliente_id=cliente.id, vendedor="Vinchi"
        )
        factura = self.db.consultar_uno("SELECT tipo FROM comprobante WHERE venta_id = ?", (venta_id,))
        self.assertEqual(factura["tipo"], "FACTURA_A")

    def test_factura_b_para_cliente_exento(self) -> None:
        cliente = self.service.registrar_cliente(
            Cliente("27123456789", "Cliente exento", CondicionIva.EXENTO)
        )
        venta_id = self.service.registrar_venta(
            1, {1: 1}, [self.pago_efectivo("10.00")], cliente_id=cliente.id, vendedor="Vinchi"
        )
        factura = self.db.consultar_uno("SELECT tipo FROM comprobante WHERE venta_id = ?", (venta_id,))
        self.assertEqual(factura["tipo"], "FACTURA_B")

    def test_documento_de_cliente_no_se_duplica(self) -> None:
        self.service.registrar_cliente(Cliente("20123456789", "Cliente 1"))
        with self.assertRaises(EntidadDuplicadaError):
            self.service.registrar_cliente(Cliente("20123456789", "Cliente 2"))

    def test_reporte_r6_agrupa_por_medio_sin_duplicar_ventas_mixtas(self) -> None:
        self.service.registrar_venta(
            1,
            {1: 2},
            [
                self.pago_efectivo("10.00"),
                PagoSolicitado("TRANSFERENCIA", Decimal("10.00"), {"referencia": "TRX-1"}),
            ],
            vendedor="Vinchi",
        )

        filas = ReporteVentas(self.db).consultar(date.today(), date.today(), 1)

        self.assertEqual({fila.medio_pago for fila in filas}, {"EFECTIVO", "TRANSFERENCIA"})
        self.assertEqual([fila.cantidad_ventas for fila in filas], [1, 1])
        self.assertEqual(sum((fila.total_cobrado for fila in filas), Decimal("0.00")), Decimal("20.00"))

    def test_numeracion_de_venta_es_correlativa_por_sucursal(self) -> None:
        for _ in range(2):
            self.service.registrar_venta(
                1, {1: 1}, [self.pago_efectivo("10.00")], vendedor="Vinchi"
            )
        numeros = self.db.consultar("SELECT numero FROM venta ORDER BY numero")
        self.assertEqual([fila["numero"] for fila in numeros], [1, 2])

    def test_no_habilita_dos_cajas_abiertas_en_la_misma_sucursal(self) -> None:
        with self.assertRaisesRegex(ValidacionError, "Ya existe una caja abierta"):
            self.service.abrir_caja(1, Decimal("0.00"))

    def test_cerrar_caja_devuelve_saldo_final(self) -> None:
        self.service.registrar_venta(
            1, {1: 1}, [self.pago_efectivo("10.00")], vendedor="Vinchi"
        )
        saldo = self.service.cerrar_caja(1)
        self.assertEqual(saldo, Decimal("60.00"))
        self.assertIsNone(self.service.saldo_caja_abierta(1))