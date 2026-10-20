"""Reporte R1: existencias actuales y productos en stock mínimo (brache).

El stock disponible lo informa inventario (pohlsi) a través del contrato
`StockService.stock_disponible`; el mínimo sale de la tabla `stock_minimo` de maestros.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from src.dominio.maestros.modelos import a_dinero
from src.persistencia.conexion import BaseDeDatos


class ConsultaStock(Protocol):
    """La parte del StockService de inventario que necesita este reporte."""

    def stock_disponible(self, ubicacion_id: int, producto_id: int) -> int: ...


@dataclass(frozen=True)
class FilaExistencia:
    ubicacion_id: int
    ubicacion: str
    codigo_ubicacion: str
    es_centro_distribucion: bool
    producto_id: int
    sku: str
    producto: str
    categoria: str
    disponible: int
    minimo: int
    costo_unitario: Decimal

    @property
    def en_minimo(self) -> bool:
        """El disponible llegó al mínimo o está por debajo (solo si hay un mínimo definido)."""
        return self.minimo > 0 and self.disponible <= self.minimo

    @property
    def faltante(self) -> int:
        """Unidades que faltan para volver a superar el mínimo."""
        return max(self.minimo - self.disponible, 0) if self.en_minimo else 0

    @property
    def valorizado(self) -> Decimal:
        """Disponible valorizado al costo actual del producto."""
        return a_dinero(self.costo_unitario * self.disponible)

    @property
    def cobertura(self) -> float | None:
        """Disponible / mínimo (1.0 = justo en el mínimo). None si no hay mínimo."""
        return self.disponible / self.minimo if self.minimo > 0 else None


@dataclass(frozen=True)
class ResumenExistencias:
    filas: list[FilaExistencia]

    @property
    def total_unidades(self) -> int:
        return sum(fila.disponible for fila in self.filas)

    @property
    def total_valorizado(self) -> Decimal:
        return a_dinero(sum((fila.valorizado for fila in self.filas), Decimal("0")))

    @property
    def cantidad_en_minimo(self) -> int:
        return sum(1 for fila in self.filas if fila.en_minimo)

    def menor_cobertura(self, limite: int = 10) -> list[FilaExistencia]:
        """Las filas con mínimo definido que están más cerca (o más por debajo) de él."""
        con_minimo = [fila for fila in self.filas if fila.cobertura is not None]
        return sorted(con_minimo, key=lambda fila: (fila.cobertura, fila.producto))[:limite]


class ReporteExistencias:
    def __init__(self, stock: ConsultaStock, db: BaseDeDatos | None = None) -> None:
        self.stock = stock
        self.db = db or BaseDeDatos()

    def consultar(
        self,
        ubicacion_id: int | None = None,
        categoria_id: int | None = None,
        solo_en_minimo: bool = False,
    ) -> ResumenExistencias:
        """Una fila por producto activo y ubicación activa. Primero los que están en stock mínimo."""
        filtros = ["p.activo = 1", "u.activa = 1"]
        parametros: list = []
        if ubicacion_id is not None:
            filtros.append("u.id = ?")
            parametros.append(ubicacion_id)
        if categoria_id is not None:
            filtros.append("p.categoria_id = ?")
            parametros.append(categoria_id)
        filas_bd = self.db.consultar(
            "SELECT u.id AS ubicacion_id, u.nombre AS ubicacion, u.codigo AS codigo_ubicacion, u.tipo, p.id AS producto_id, p.sku, "
            "p.nombre AS producto, c.nombre AS categoria, p.costo_actual, "
            "COALESCE(sm.cantidad_minima, 0) AS minimo "
            "FROM producto p CROSS JOIN ubicacion u "
            "JOIN categoria c ON c.id = p.categoria_id "
            "LEFT JOIN stock_minimo sm ON sm.producto_id = p.id AND sm.ubicacion_id = u.id "
            "WHERE " + " AND ".join(filtros),
            parametros,
        )
        filas = [
            FilaExistencia(
                ubicacion_id=fila["ubicacion_id"],
                ubicacion=fila["ubicacion"],
                codigo_ubicacion=fila["codigo_ubicacion"],
                es_centro_distribucion=fila["tipo"] == "CD",
                producto_id=fila["producto_id"],
                sku=fila["sku"],
                producto=fila["producto"],
                categoria=fila["categoria"],
                disponible=int(self.stock.stock_disponible(fila["ubicacion_id"], fila["producto_id"])),
                minimo=int(fila["minimo"]),
                costo_unitario=fila["costo_actual"],
            )
            for fila in filas_bd
        ]
        if solo_en_minimo:
            filas = [fila for fila in filas if fila.en_minimo]
        filas.sort(key=lambda f: (not f.en_minimo, not f.es_centro_distribucion, f.ubicacion, f.producto))
        return ResumenExistencias(filas)
