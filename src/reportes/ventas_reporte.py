"""Reporte R6: ventas e ingresos agrupados por período, local y medio de pago."""

from dataclasses import dataclass
from collections import defaultdict
from datetime import date
from decimal import Decimal

from src.persistencia.conexion import BaseDeDatos


@dataclass(frozen=True)
class FilaReporteVentas:
    """Totales cobrados y cantidad de ventas de un local y medio de pago."""

    ubicacion_id: int
    sucursal: str
    medio_pago: str
    cantidad_ventas: int
    total_cobrado: Decimal


class ReporteVentas:
    """Consulta los cobros registrados sin duplicar ventas con pago mixto."""

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def consultar(
        self, desde: date, hasta: date, ubicacion_id: int | None = None
    ) -> list[FilaReporteVentas]:
        """Agrupa el ingreso cobrado (incluidos recargos) en el rango inclusivo."""
        if desde > hasta:
            raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")
        filtros = ["date(v.fecha_hora) BETWEEN ? AND ?"]
        parametros: list = [desde.isoformat(), hasta.isoformat()]
        if ubicacion_id is not None:
            filtros.append("v.ubicacion_id = ?")
            parametros.append(ubicacion_id)
        filas = self.db.consultar(
            "SELECT u.id AS ubicacion_id, u.nombre AS sucursal, c.medio_pago, v.id AS venta_id, "
            "c.monto, c.recargo FROM cobro c JOIN venta v ON v.id = c.venta_id "
            "JOIN ubicacion u ON u.id = v.ubicacion_id WHERE " + " AND ".join(filtros),
            parametros,
        )
        agrupados: dict[tuple[int, str, str], dict] = defaultdict(
            lambda: {"ventas": set(), "total": Decimal("0.00")}
        )
        for fila in filas:
            clave = (int(fila["ubicacion_id"]), fila["sucursal"], fila["medio_pago"])
            agrupados[clave]["ventas"].add(int(fila["venta_id"]))
            agrupados[clave]["total"] += Decimal(fila["monto"]) + Decimal(fila["recargo"])
        return sorted(
            (
                FilaReporteVentas(
                    ubicacion_id=ubicacion_id,
                    sucursal=sucursal,
                    medio_pago=medio_pago,
                    cantidad_ventas=len(valores["ventas"]),
                    total_cobrado=valores["total"].quantize(Decimal("0.01")),
                )
                for (ubicacion_id, sucursal, medio_pago), valores in agrupados.items()
            ),
            key=lambda fila: (fila.sucursal, -fila.total_cobrado),
        )