"""Reporte R2: productos más vendidos y margen de ganancia/pérdida estimado (brache).

Usa el precio y el costo que `detalle_venta` guardó en el momento de cada venta,
así el margen no cambia si después se actualizan los precios del producto.
Las unidades devueltas se descuentan. Los recargos financieros de los medios de
pago (cuotas) no se cuentan como margen del producto.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.dominio.maestros.modelos import a_dinero
from src.excepciones import ValidacionError
from src.persistencia.conexion import BaseDeDatos


@dataclass(frozen=True)
class FilaProductoVendido:
    producto_id: int
    sku: str
    producto: str
    categoria: str
    unidades: int
    ingresos: Decimal
    costo: Decimal

    @property
    def margen(self) -> Decimal:
        return a_dinero(self.ingresos - self.costo)

    @property
    def margen_porcentual(self) -> Decimal | None:
        """Margen sobre las ventas, en porcentaje. None si no hubo ingresos."""
        return a_dinero(self.margen * 100 / self.ingresos) if self.ingresos else None

    @property
    def es_perdida(self) -> bool:
        return self.margen < 0


@dataclass(frozen=True)
class ResumenProductosVendidos:
    filas: list[FilaProductoVendido]

    @property
    def total_unidades(self) -> int:
        return sum(fila.unidades for fila in self.filas)

    @property
    def total_ingresos(self) -> Decimal:
        return a_dinero(sum((fila.ingresos for fila in self.filas), Decimal("0")))

    @property
    def total_margen(self) -> Decimal:
        return a_dinero(sum((fila.margen for fila in self.filas), Decimal("0")))

    @property
    def margen_porcentual(self) -> Decimal | None:
        return a_dinero(self.total_margen * 100 / self.total_ingresos) if self.total_ingresos else None

    def top(self, cantidad: int) -> list[FilaProductoVendido]:
        """Los `cantidad` productos más vendidos (las filas ya vienen ordenadas)."""
        return self.filas[:cantidad]


class ReporteProductosVendidos:
    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def consultar(
        self,
        desde: date,
        hasta: date,
        ubicacion_id: int | None = None,
        categoria_id: int | None = None,
    ) -> ResumenProductosVendidos:
        """Ventas confirmadas entre `desde` y `hasta` (inclusive), de mayor a menor cantidad vendida."""
        if desde > hasta:
            raise ValidacionError("La fecha «desde» no puede ser posterior a la fecha «hasta».")
        filtros = ["v.estado = 'CONFIRMADA'", "date(v.fecha_hora) BETWEEN ? AND ?"]
        parametros: list = [desde.isoformat(), hasta.isoformat()]
        if ubicacion_id is not None:
            filtros.append("v.ubicacion_id = ?")
            parametros.append(ubicacion_id)
        if categoria_id is not None:
            filtros.append("p.categoria_id = ?")
            parametros.append(categoria_id)
        renglones = self.db.consultar(
            "SELECT p.id AS producto_id, p.sku, p.nombre AS producto, c.nombre AS categoria, "
            "d.cantidad - d.cantidad_devuelta AS unidades, d.precio_unitario, d.costo_unitario "
            "FROM detalle_venta d JOIN venta v ON v.id = d.venta_id "
            "JOIN producto p ON p.id = d.producto_id JOIN categoria c ON c.id = p.categoria_id "
            "WHERE " + " AND ".join(filtros),
            parametros,
        )

        # Se acumula en Python para sumar Decimal exactos (SUM de SQLite usa coma flotante).
        acumulado: dict[int, dict] = defaultdict(
            lambda: {"unidades": 0, "ingresos": Decimal("0"), "costo": Decimal("0")}
        )
        datos: dict[int, tuple[str, str, str]] = {}
        for r in renglones:
            unidades = int(r["unidades"])
            item = acumulado[r["producto_id"]]
            item["unidades"] += unidades
            item["ingresos"] += r["precio_unitario"] * unidades
            item["costo"] += r["costo_unitario"] * unidades
            datos[r["producto_id"]] = (r["sku"], r["producto"], r["categoria"])

        filas = [
            FilaProductoVendido(
                producto_id=producto_id,
                sku=datos[producto_id][0],
                producto=datos[producto_id][1],
                categoria=datos[producto_id][2],
                unidades=item["unidades"],
                ingresos=a_dinero(item["ingresos"]),
                costo=a_dinero(item["costo"]),
            )
            for producto_id, item in acumulado.items()
            if item["unidades"] > 0  # si se devolvió todo, no cuenta como vendido
        ]
        filas.sort(key=lambda f: (-f.unidades, -f.ingresos, f.sku))
        return ResumenProductosVendidos(filas)
