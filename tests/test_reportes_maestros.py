"""Pruebas de los reportes de brache: R1 (existencias y stock mínimo) y R2 (más vendidos y margen)."""

from datetime import date, datetime
from decimal import Decimal

from src.dominio.maestros.modelos import Categoria, CentroDistribucion, Producto, StockMinimo, Sucursal
from src.dominio.ventas.modelos import DetalleDevolucion
from src.excepciones import ValidacionError
from src.reportes.existencias_reporte import ReporteExistencias
from src.reportes.productos_reporte import ReporteProductosVendidos
from src.servicios.maestros_service import (
    CategoriaService,
    ProductoService,
    StockMinimoService,
    UbicacionService,
)
from src.servicios.ventas_service import PagoSolicitado, VentasService
from tests.utilidades import TestConBaseEnMemoria


class StockFalso:
    """Doble del StockService de inventario: stock fijo por (ubicación, producto)."""

    def __init__(self, disponibles: dict[tuple[int, int], int] | None = None, por_defecto: int = 0) -> None:
        self.disponibles = disponibles or {}
        self.por_defecto = por_defecto

    def stock_disponible(self, ubicacion_id: int, producto_id: int) -> int:
        return self.disponibles.get((ubicacion_id, producto_id), self.por_defecto)

    def egresar(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: str) -> None:
        clave = (ubicacion_id, producto_id)
        self.disponibles[clave] = self.stock_disponible(*clave) - cantidad

    def reingresar(self, ubicacion_id: int, producto_id: int, cantidad: int, ref: str) -> None:
        clave = (ubicacion_id, producto_id)
        self.disponibles[clave] = self.stock_disponible(*clave) + cantidad


class ConDatosDeMaestros(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        ubicaciones = UbicacionService()
        self.centro = ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1))
        self.norte = ubicaciones.guardar(Sucursal(codigo="SUC02", nombre="Norte", punto_venta=2))
        self.cd = ubicaciones.guardar(CentroDistribucion(codigo="CD", nombre="Central"))
        categorias = CategoriaService()
        self.bebidas = categorias.guardar(Categoria("Bebidas"))
        self.almacen = categorias.guardar(Categoria("Almacén"))
        productos = ProductoService()
        self.agua = productos.guardar(Producto("AGU", "Agua", self.bebidas.id, Decimal("600"), Decimal("1000")))
        self.yerba = productos.guardar(Producto("YER", "Yerba", self.almacen.id, Decimal("3000"), Decimal("4500")))
        self.pan = productos.guardar(Producto("PAN", "Pan dulce", self.almacen.id, Decimal("4200"), Decimal("3900")))


class TestReporteExistencias(ConDatosDeMaestros):
    def setUp(self):
        super().setUp()
        minimos = StockMinimoService()
        minimos.definir(StockMinimo(self.agua.id, self.centro.id, 10))
        minimos.definir(StockMinimo(self.yerba.id, self.centro.id, 5))
        minimos.definir(StockMinimo(self.agua.id, self.cd.id, 60))
        self.stock = StockFalso({
            (self.centro.id, self.agua.id): 4,     # en mínimo, faltan 6
            (self.centro.id, self.yerba.id): 5,    # justo en el mínimo
            (self.cd.id, self.agua.id): 100,       # por encima del mínimo
            (self.norte.id, self.pan.id): 7,       # sin mínimo definido
        })
        self.reporte = ReporteExistencias(self.stock)

    def _fila(self, resumen, ubicacion, producto):
        return next(f for f in resumen.filas if f.ubicacion_id == ubicacion.id and f.producto_id == producto.id)

    def test_una_fila_por_producto_y_ubicacion_activos(self):
        resumen = self.reporte.consultar()
        self.assertEqual(len(resumen.filas), 3 * 3)
        ProductoService().dar_de_baja(self.pan.id)
        UbicacionService().dar_de_baja(self.norte.id)
        self.assertEqual(len(self.reporte.consultar().filas), 2 * 2)

    def test_calculos_de_cada_fila(self):
        resumen = self.reporte.consultar()
        agua_centro = self._fila(resumen, self.centro, self.agua)
        self.assertTrue(agua_centro.en_minimo)
        self.assertEqual(agua_centro.faltante, 6)
        self.assertEqual(agua_centro.valorizado, Decimal("2400.00"))
        self.assertTrue(self._fila(resumen, self.centro, self.yerba).en_minimo)
        self.assertFalse(self._fila(resumen, self.cd, self.agua).en_minimo)
        pan_norte = self._fila(resumen, self.norte, self.pan)
        self.assertFalse(pan_norte.en_minimo)
        self.assertIsNone(pan_norte.cobertura)

    def test_totales_y_orden(self):
        resumen = self.reporte.consultar()
        self.assertEqual(resumen.cantidad_en_minimo, 2)
        self.assertEqual(resumen.total_unidades, 4 + 5 + 100 + 7)
        self.assertEqual(resumen.total_valorizado, Decimal("2400") + Decimal("15000") + Decimal("60000") + Decimal("29400"))
        self.assertTrue(all(f.en_minimo for f in resumen.filas[:2]))
        self.assertEqual([(f.sku, f.ubicacion) for f in resumen.menor_cobertura(2)], [("AGU", "Centro"), ("YER", "Centro")])

    def test_filtros(self):
        self.assertEqual(len(self.reporte.consultar(solo_en_minimo=True).filas), 2)
        self.assertEqual({f.producto_id for f in self.reporte.consultar(categoria_id=self.almacen.id).filas},
                         {self.yerba.id, self.pan.id})
        self.assertEqual({f.ubicacion_id for f in self.reporte.consultar(ubicacion_id=self.cd.id).filas}, {self.cd.id})


class TestReporteProductosVendidos(ConDatosDeMaestros):
    def setUp(self):
        super().setUp()
        self.ventas = VentasService(stock_service=StockFalso(por_defecto=1000))
        self.ventas.abrir_caja(self.centro.id)
        self.ventas.abrir_caja(self.norte.id)
        self.reporte = ReporteProductosVendidos()

    def _vender(self, sucursal, items: dict, dia: int, medio: str = "EFECTIVO", cuotas: int = 1) -> int:
        precios = {self.agua.id: Decimal("1000"), self.yerba.id: Decimal("4500"), self.pan.id: Decimal("3900")}
        total = sum(precios[p] * c for p, c in items.items())
        datos = {"autorizacion": "AUT-1"} if medio != "EFECTIVO" else {}
        return self.ventas.registrar_venta(
            sucursal.id, items, [PagoSolicitado(medio, total, datos, cuotas=cuotas)],
            vendedor="test", fecha_hora=datetime(2026, 10, dia, 12, 0),
        )

    def _consultar(self, **filtros):
        return self.reporte.consultar(date(2026, 10, 1), date(2026, 10, 31), **filtros)

    def test_ranking_ingresos_costo_y_margen(self):
        self._vender(self.centro, {self.agua.id: 5, self.yerba.id: 1}, dia=3)
        self._vender(self.norte, {self.agua.id: 3, self.pan.id: 2}, dia=10)
        resumen = self._consultar()
        self.assertEqual([f.sku for f in resumen.filas], ["AGU", "PAN", "YER"])
        agua = resumen.filas[0]
        self.assertEqual(agua.unidades, 8)
        self.assertEqual(agua.ingresos, Decimal("8000.00"))
        self.assertEqual(agua.costo, Decimal("4800.00"))
        self.assertEqual(agua.margen, Decimal("3200.00"))
        self.assertEqual(agua.margen_porcentual, Decimal("40.00"))
        pan = resumen.filas[1]
        self.assertTrue(pan.es_perdida)
        self.assertEqual(pan.margen, Decimal("-600.00"))
        self.assertEqual(resumen.total_unidades, 11)
        self.assertEqual(resumen.total_margen, Decimal("3200") + Decimal("-600") + Decimal("1500"))
        self.assertEqual([f.sku for f in resumen.top(1)], ["AGU"])

    def test_usa_el_precio_y_costo_del_momento_de_la_venta(self):
        self._vender(self.centro, {self.agua.id: 2}, dia=3)
        self.agua.costo_actual, self.agua.precio_venta_actual = Decimal("900"), Decimal("1500")
        ProductoService().guardar(self.agua)
        [agua] = self._consultar().filas
        self.assertEqual((agua.ingresos, agua.costo), (Decimal("2000.00"), Decimal("1200.00")))

    def test_descuenta_devoluciones(self):
        venta_id = self._vender(self.centro, {self.agua.id: 5, self.pan.id: 1}, dia=3)
        detalles = {r["producto_id"]: r["id"] for r in self.db.consultar(
            "SELECT id, producto_id FROM detalle_venta WHERE venta_id = ?", (venta_id,))}
        self.ventas.registrar_devolucion(
            venta_id,
            [DetalleDevolucion(detalles[self.agua.id], 2), DetalleDevolucion(detalles[self.pan.id], 1)],
            "No le gustó", fecha_hora=datetime(2026, 10, 4, 10, 0),
        )
        resumen = self._consultar()
        self.assertEqual([(f.sku, f.unidades) for f in resumen.filas], [("AGU", 3)])  # el pan se devolvió entero

    def test_no_cuenta_el_recargo_de_las_cuotas_como_margen(self):
        self._vender(self.centro, {self.yerba.id: 1}, dia=3, medio="CREDITO", cuotas=6)
        [yerba] = self._consultar().filas
        self.assertEqual(yerba.ingresos, Decimal("4500.00"))

    def test_filtros_y_periodo(self):
        self._vender(self.centro, {self.agua.id: 1}, dia=3)
        self._vender(self.norte, {self.yerba.id: 1}, dia=31)
        self._vender(self.norte, {self.pan.id: 1}, dia=1)
        self.assertEqual({f.sku for f in self._consultar(ubicacion_id=self.norte.id).filas}, {"YER", "PAN"})
        self.assertEqual({f.sku for f in self._consultar(categoria_id=self.bebidas.id).filas}, {"AGU"})
        solo_dia_3 = self.reporte.consultar(date(2026, 10, 3), date(2026, 10, 3))
        self.assertEqual([f.sku for f in solo_dia_3.filas], ["AGU"])
        with self.assertRaises(ValidacionError):
            self.reporte.consultar(date(2026, 10, 31), date(2026, 10, 1))

    def test_sin_ventas(self):
        resumen = self._consultar()
        self.assertEqual(resumen.filas, [])
        self.assertIsNone(resumen.margen_porcentual)
