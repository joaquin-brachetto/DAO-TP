"""Consultas de la pantalla de Inicio: totales del día, ventas de la semana y últimas ventas."""

from datetime import datetime

from src.persistencia.conexion import BaseDeDatos


class TableroRepositorio:
    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def cobrado_por_dia(self, desde: datetime, hasta: datetime) -> list:
        """Total cobrado (con recargos) por día de las ventas confirmadas en [desde, hasta)."""
        return self.db.consultar(
            "SELECT date(v.fecha_hora) AS dia, SUM(c.monto + c.recargo) AS total "
            "FROM venta v JOIN cobro c ON c.venta_id = v.id "
            "WHERE v.estado = 'CONFIRMADA' AND v.fecha_hora >= ? AND v.fecha_hora < ? "
            "GROUP BY date(v.fecha_hora) ORDER BY dia",
            (desde, hasta),
        )

    def cobrado_por_medio(self, desde: datetime, hasta: datetime) -> list:
        return self.db.consultar(
            "SELECT c.medio_pago, SUM(c.monto + c.recargo) AS total "
            "FROM venta v JOIN cobro c ON c.venta_id = v.id "
            "WHERE v.estado = 'CONFIRMADA' AND v.fecha_hora >= ? AND v.fecha_hora < ? "
            "GROUP BY c.medio_pago",
            (desde, hasta),
        )

    def cantidad_de_ventas(self, desde: datetime, hasta: datetime) -> int:
        fila = self.db.consultar_uno(
            "SELECT COUNT(*) AS cantidad FROM venta "
            "WHERE estado = 'CONFIRMADA' AND fecha_hora >= ? AND fecha_hora < ?",
            (desde, hasta),
        )
        return int(fila["cantidad"])

    def ultimas_ventas(self, limite: int) -> list:
        """Las últimas ventas con su sucursal, comprobante, cliente y medios de pago."""
        return self.db.consultar(
            "SELECT v.id, v.fecha_hora, v.total, u.nombre AS sucursal, "
            "cp.tipo, cp.punto_venta, cp.numero, cl.nombre AS cliente, "
            "(SELECT GROUP_CONCAT(medio_pago || CASE WHEN cuotas > 1 THEN ' en ' || cuotas || ' cuotas' ELSE '' END, ' + ') "
            " FROM cobro WHERE venta_id = v.id) AS medios "
            "FROM venta v JOIN ubicacion u ON u.id = v.ubicacion_id "
            "JOIN comprobante cp ON cp.venta_id = v.id "
            "LEFT JOIN cliente cl ON cl.id = v.cliente_id "
            "WHERE v.estado = 'CONFIRMADA' ORDER BY v.fecha_hora DESC, v.id DESC LIMIT ?",
            (limite,),
        )

    def datos_cargados(self) -> dict[str, bool]:
        """Qué datos de prueba ya están cargados (para ofrecer solo el paso que sigue)."""
        def hay(tabla: str) -> bool:
            return self.db.consultar_uno(f"SELECT 1 FROM {tabla} LIMIT 1") is not None

        return {"maestros": hay("producto"), "stock": hay("stock"), "logistica": hay("remito")}
