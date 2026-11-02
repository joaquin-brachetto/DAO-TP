"""Tests de los reportes de brache: R1 (existencias y stock mínimo) y R2 (más vendidos y margen)."""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

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


@pytest.fixture
def maestros(db):
    """Dos sucursales, el CD, dos categorías y tres productos (el pan se vende a pérdida)."""
    ubicaciones = UbicacionService()
    categorias = CategoriaService()
    productos = ProductoService()
    bebidas = categorias.guardar(Categoria("Bebidas"))
    almacen = categorias.guardar(Categoria("Almacén"))
    return SimpleNamespace(
        centro=ubicaciones.guardar(Sucursal(codigo="SUC01", nombre="Centro", punto_venta=1)),
        norte=ubicaciones.guardar(Sucursal(codigo="SUC02", nombre="Norte", punto_venta=2)),
        cd=ubicaciones.guardar(CentroDistribucion(codigo="CD", nombre="Central")),
        bebidas=bebidas,
        almacen=almacen,
        agua=productos.guardar(Producto("AGU", "Agua", bebidas.id, Decimal("600"), Decimal("1000"))),
        yerba=productos.guardar(Producto("YER", "Yerba", almacen.id, Decimal("3000"), Decimal("4500"))),
        pan=productos.guardar(Producto("PAN", "Pan dulce", almacen.id, Decimal("4200"), Decimal("3900"))),
    )


# --- R1: existencias y stock mínimo ----------------------------------------------------------


@pytest.fixture
def reporte_existencias(maestros):
    m = maestros
    minimos = StockMinimoService()
    minimos.definir(StockMinimo(m.agua.id, m.centro.id, 10))
    minimos.definir(StockMinimo(m.yerba.id, m.centro.id, 5))
    minimos.definir(StockMinimo(m.agua.id, m.cd.id, 60))
    stock = StockFalso({
        (m.centro.id, m.agua.id): 4,     # en mínimo, faltan 6
        (m.centro.id, m.yerba.id): 5,    # justo en el mínimo
        (m.cd.id, m.agua.id): 100,       # por encima del mínimo
        (m.norte.id, m.pan.id): 7,       # sin mínimo definido
    })
    return ReporteExistencias(stock)


def fila_de(resumen, ubicacion, producto):
    return next(f for f in resumen.filas if f.ubicacion_id == ubicacion.id and f.producto_id == producto.id)


def test_una_fila_por_producto_y_ubicacion_activos(maestros, reporte_existencias):
    assert len(reporte_existencias.consultar().filas) == 3 * 3

    ProductoService().dar_de_baja(maestros.pan.id)
    UbicacionService().dar_de_baja(maestros.norte.id)

    assert len(reporte_existencias.consultar().filas) == 2 * 2


def test_calculos_de_cada_fila(maestros, reporte_existencias):
    m = maestros
    resumen = reporte_existencias.consultar()

    agua_centro = fila_de(resumen, m.centro, m.agua)
    assert agua_centro.en_minimo
    assert agua_centro.faltante == 6
    assert agua_centro.valorizado == Decimal("2400.00")
    assert fila_de(resumen, m.centro, m.yerba).en_minimo
    assert not fila_de(resumen, m.cd, m.agua).en_minimo
    pan_norte = fila_de(resumen, m.norte, m.pan)
    assert not pan_norte.en_minimo
    assert pan_norte.cobertura is None


def test_totales_y_orden(reporte_existencias):
    resumen = reporte_existencias.consultar()

    assert resumen.cantidad_en_minimo == 2
    assert resumen.total_unidades == 4 + 5 + 100 + 7
    assert resumen.total_valorizado == Decimal("2400") + Decimal("15000") + Decimal("60000") + Decimal("29400")
    assert all(f.en_minimo for f in resumen.filas[:2])
    assert [(f.sku, f.ubicacion) for f in resumen.menor_cobertura(2)] == [("AGU", "Centro"), ("YER", "Centro")]


def test_filtros_de_existencias(maestros, reporte_existencias):
    m = maestros
    assert len(reporte_existencias.consultar(solo_en_minimo=True).filas) == 2
    assert {f.producto_id for f in reporte_existencias.consultar(categoria_id=m.almacen.id).filas} == {
        m.yerba.id, m.pan.id
    }
    assert {f.ubicacion_id for f in reporte_existencias.consultar(ubicacion_id=m.cd.id).filas} == {m.cd.id}


# --- R2: productos más vendidos y margen -----------------------------------------------------


@pytest.fixture
def ventas(maestros):
    servicio = VentasService(stock_service=StockFalso(por_defecto=1000))
    servicio.abrir_caja(maestros.centro.id)
    servicio.abrir_caja(maestros.norte.id)
    return servicio


@pytest.fixture
def vender(maestros, ventas):
    """Devuelve una función que registra una venta en octubre de 2026 pagando el total exacto."""
    precios = {maestros.agua.id: Decimal("1000"), maestros.yerba.id: Decimal("4500"), maestros.pan.id: Decimal("3900")}

    def registrar(sucursal, items: dict, dia: int, medio: str = "EFECTIVO", cuotas: int = 1) -> int:
        total = sum(precios[p] * c for p, c in items.items())
        datos = {"autorizacion": "AUT-1"} if medio != "EFECTIVO" else {}
        return ventas.registrar_venta(
            sucursal.id, items, [PagoSolicitado(medio, total, datos, cuotas=cuotas)],
            vendedor="test", fecha_hora=datetime(2026, 10, dia, 12, 0),
        )

    return registrar


def consultar_octubre(**filtros):
    return ReporteProductosVendidos().consultar(date(2026, 10, 1), date(2026, 10, 31), **filtros)


def test_ranking_ingresos_costo_y_margen(maestros, vender):
    m = maestros
    vender(m.centro, {m.agua.id: 5, m.yerba.id: 1}, dia=3)
    vender(m.norte, {m.agua.id: 3, m.pan.id: 2}, dia=10)

    resumen = consultar_octubre()

    assert [f.sku for f in resumen.filas] == ["AGU", "PAN", "YER"]
    agua = resumen.filas[0]
    assert agua.unidades == 8
    assert agua.ingresos == Decimal("8000.00")
    assert agua.costo == Decimal("4800.00")
    assert agua.margen == Decimal("3200.00")
    assert agua.margen_porcentual == Decimal("40.00")
    pan = resumen.filas[1]
    assert pan.es_perdida
    assert pan.margen == Decimal("-600.00")
    assert resumen.total_unidades == 11
    assert resumen.total_margen == Decimal("3200") + Decimal("-600") + Decimal("1500")
    assert [f.sku for f in resumen.top(1)] == ["AGU"]


def test_usa_el_precio_y_costo_del_momento_de_la_venta(maestros, vender):
    agua = maestros.agua
    vender(maestros.centro, {agua.id: 2}, dia=3)
    agua.costo_actual, agua.precio_venta_actual = Decimal("900"), Decimal("1500")
    ProductoService().guardar(agua)

    [fila] = consultar_octubre().filas

    assert (fila.ingresos, fila.costo) == (Decimal("2000.00"), Decimal("1200.00"))


def test_descuenta_devoluciones(db, maestros, ventas, vender):
    m = maestros
    venta_id = vender(m.centro, {m.agua.id: 5, m.pan.id: 1}, dia=3)
    detalles = {
        r["producto_id"]: r["id"]
        for r in db.consultar("SELECT id, producto_id FROM detalle_venta WHERE venta_id = ?", (venta_id,))
    }
    ventas.registrar_devolucion(
        venta_id,
        [DetalleDevolucion(detalles[m.agua.id], 2), DetalleDevolucion(detalles[m.pan.id], 1)],
        "No le gustó", fecha_hora=datetime(2026, 10, 4, 10, 0),
    )

    resumen = consultar_octubre()

    assert [(f.sku, f.unidades) for f in resumen.filas] == [("AGU", 3)]  # el pan se devolvió entero


def test_no_cuenta_el_recargo_de_las_cuotas_como_margen(maestros, vender):
    vender(maestros.centro, {maestros.yerba.id: 1}, dia=3, medio="CREDITO", cuotas=6)

    [yerba] = consultar_octubre().filas

    assert yerba.ingresos == Decimal("4500.00")


def test_filtros_y_periodo(maestros, vender):
    m = maestros
    vender(m.centro, {m.agua.id: 1}, dia=3)
    vender(m.norte, {m.yerba.id: 1}, dia=31)
    vender(m.norte, {m.pan.id: 1}, dia=1)

    assert {f.sku for f in consultar_octubre(ubicacion_id=m.norte.id).filas} == {"YER", "PAN"}
    assert {f.sku for f in consultar_octubre(categoria_id=m.bebidas.id).filas} == {"AGU"}
    solo_dia_3 = ReporteProductosVendidos().consultar(date(2026, 10, 3), date(2026, 10, 3))
    assert [f.sku for f in solo_dia_3.filas] == ["AGU"]
    with pytest.raises(ValidacionError):
        ReporteProductosVendidos().consultar(date(2026, 10, 31), date(2026, 10, 1))


def test_sin_ventas(maestros):
    resumen = consultar_octubre()

    assert resumen.filas == []
    assert resumen.margen_porcentual is None
