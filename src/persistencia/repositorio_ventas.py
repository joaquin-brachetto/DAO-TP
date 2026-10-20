"""Persistencia de agregados de ventas que no caben en RepositorioBase."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.dominio.ventas.modelos import Cliente
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_base import RepositorioBase


class ClienteRepositorio(RepositorioBase[Cliente]):
    """Repository de compradores, reutiliza la infraestructura compartida."""

    tabla = "cliente"
    entidad = Cliente

    def _a_entidad(self, fila) -> Cliente:
        return Cliente(
            documento=fila["documento"],
            nombre=fila["nombre"],
            condicion_iva=fila["condicion_iva"],
            id=fila["id"],
        )


class VentasRepositorio:
    """Guarda y consulta agregados de ventas, cobros, caja y devoluciones."""

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def obtener_sucursal(self, ubicacion_id: int):
        """Devuelve datos fiscales de una sucursal, nunca de un CD."""
        return self.db.consultar_uno(
            "SELECT id, tipo, activa, punto_venta FROM ubicacion WHERE id = ?", (ubicacion_id,)
        )

    def obtener_producto(self, producto_id: int):
        """Carga nombre, precios y estado del maestro, sin modificar su módulo."""
        return self.db.consultar_uno(
            "SELECT id, nombre, costo_actual, precio_venta_actual, activo "
            "FROM producto WHERE id = ?", (producto_id,)
        )

    def existe_cliente(self, cliente_id: int) -> bool:
        return self.db.consultar_uno("SELECT 1 FROM cliente WHERE id = ?", (cliente_id,)) is not None

    def obtener_cliente(self, cliente_id: int | None):
        if cliente_id is None:
            return None
        return self.db.consultar_uno("SELECT * FROM cliente WHERE id = ?", (cliente_id,))

    def siguiente_numero_venta(self, ubicacion_id: int) -> int:
        fila = self.db.consultar_uno(
            "SELECT COALESCE(MAX(numero), 0) + 1 AS numero FROM venta WHERE ubicacion_id = ?",
            (ubicacion_id,),
        )
        return int(fila["numero"])

    def siguiente_numero_comprobante(self, punto_venta: int, tipo: str) -> int:
        fila = self.db.consultar_uno(
            "SELECT COALESCE(MAX(numero), 0) + 1 AS numero FROM comprobante "
            "WHERE punto_venta = ? AND tipo = ?", (punto_venta, tipo),
        )
        return int(fila["numero"])

    def crear_caja(self, ubicacion_id: int, fecha: datetime, saldo_inicial: Decimal) -> int:
        cursor = self.db.ejecutar(
            "INSERT INTO caja (ubicacion_id, fecha_apertura, saldo_inicial) VALUES (?, ?, ?)",
            (ubicacion_id, fecha, saldo_inicial),
        )
        return int(cursor.lastrowid)

    def caja_abierta(self, ubicacion_id: int):
        return self.db.consultar_uno(
            "SELECT * FROM caja WHERE ubicacion_id = ? AND fecha_cierre IS NULL", (ubicacion_id,)
        )

    def cerrar_caja(self, caja_id: int, fecha: datetime) -> None:
        self.db.ejecutar("UPDATE caja SET fecha_cierre = ? WHERE id = ? AND fecha_cierre IS NULL", (fecha, caja_id))

    def guardar_venta(
        self,
        *,
        ubicacion_id: int,
        cliente_id: int | None,
        numero: int,
        fecha_hora: datetime,
        vendedor: str,
        total: Decimal,
        detalles: list[dict[str, Any]],
        cobros: list[dict[str, Any]],
        caja_id: int,
        punto_venta: int,
        tipo_comprobante: str,
        comprobante_numero: int,
    ) -> tuple[int, int]:
        """Inserta el documento completo; el servicio envuelve todo en transacción."""
        cursor = self.db.ejecutar(
            "INSERT INTO venta (ubicacion_id, cliente_id, numero, fecha_hora, vendedor, estado, total) "
            "VALUES (?, ?, ?, ?, ?, 'CONFIRMADA', ?)",
            (ubicacion_id, cliente_id, numero, fecha_hora, vendedor, total),
        )
        venta_id = int(cursor.lastrowid)
        for detalle in detalles:
            self.db.ejecutar(
                "INSERT INTO detalle_venta (venta_id, producto_id, cantidad, precio_unitario, costo_unitario, "
                "recargo_asignado) VALUES (?, ?, ?, ?, ?, ?)",
                (venta_id, detalle["producto_id"], detalle["cantidad"], detalle["precio_unitario"],
                 detalle["costo_unitario"], detalle["recargo_asignado"]),
            )
        for cobro in cobros:
            pago_cursor = self.db.ejecutar(
                "INSERT INTO cobro (venta_id, fecha_hora, medio_pago, monto, recargo, cuotas, nro_autorizacion) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (venta_id, fecha_hora, cobro["medio_pago"], cobro["monto"], cobro["recargo"],
                 cobro["cuotas"], cobro["nro_autorizacion"]),
            )
            self.db.ejecutar(
                "INSERT INTO movimiento_caja (caja_id, fecha_hora, tipo, monto, medio_pago, concepto, cobro_id) "
                "VALUES (?, ?, 'INGRESO', ?, ?, ?, ?)",
                (caja_id, fecha_hora, cobro["monto"] + cobro["recargo"], cobro["medio_pago"],
                 f"Venta {numero}", int(pago_cursor.lastrowid)),
            )
        comprobante_cursor = self.db.ejecutar(
            "INSERT INTO comprobante (punto_venta, numero, tipo, fecha_emision, total, venta_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (punto_venta, comprobante_numero, tipo_comprobante, fecha_hora, total, venta_id),
        )
        return venta_id, int(comprobante_cursor.lastrowid)

    def obtener_venta(self, venta_id: int):
        return self.db.consultar_uno("SELECT * FROM venta WHERE id = ?", (venta_id,))

    def listar_detalles_venta(self, venta_id: int) -> list:
        return self.db.consultar(
            "SELECT * FROM detalle_venta WHERE venta_id = ? ORDER BY id", (venta_id,)
        )

    def listar_cobros(self, venta_id: int) -> list:
        return self.db.consultar("SELECT * FROM cobro WHERE venta_id = ? ORDER BY id", (venta_id,))

    def detalle_venta(self, detalle_id: int):
        return self.db.consultar_uno("SELECT * FROM detalle_venta WHERE id = ?", (detalle_id,))

    def crear_devolucion(
        self,
        *,
        venta_id: int,
        fecha_hora: datetime,
        motivo: str,
        total: Decimal,
        detalles: list[dict[str, Any]],
        caja_id: int,
        punto_venta: int,
        nota_credito,
    ) -> tuple[int, int]:
        cursor = self.db.ejecutar(
            "INSERT INTO devolucion (venta_id, fecha_hora, motivo, total_reintegrar) VALUES (?, ?, ?, ?)",
            (venta_id, fecha_hora, motivo, total),
        )
        devolucion_id = int(cursor.lastrowid)
        for detalle in detalles:
            self.db.ejecutar(
                "INSERT INTO detalle_devolucion (devolucion_id, detalle_venta_id, cantidad, reingresa_stock, "
                "monto_reintegrado) VALUES (?, ?, ?, ?, ?)",
                (devolucion_id, detalle["detalle_venta_id"], detalle["cantidad"],
                 detalle["reingresa_stock"], detalle["monto_reintegrado"]),
            )
            self.db.ejecutar(
                "UPDATE detalle_venta SET cantidad_devuelta = ?, monto_reintegrado = ? WHERE id = ?",
                (detalle["cantidad_devuelta_total"], detalle["monto_reintegrado_total"],
                 detalle["detalle_venta_id"]),
            )
        if total > 0:
            self.db.ejecutar(
                "INSERT INTO movimiento_caja (caja_id, fecha_hora, tipo, monto, medio_pago, concepto, devolucion_id) "
                "VALUES (?, ?, 'EGRESO', ?, 'REINTEGRO', ?, ?)",
                (caja_id, fecha_hora, total, f"Devolución de venta {venta_id}", devolucion_id),
            )
        nota_cursor = self.db.ejecutar(
            "INSERT INTO comprobante (punto_venta, numero, tipo, fecha_emision, total, devolucion_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (nota_credito.punto_venta, nota_credito.numero, nota_credito.tipo,
             nota_credito.fecha_emision, nota_credito.total, devolucion_id),
        )
        return devolucion_id, int(nota_cursor.lastrowid)

    def saldo_caja(self, caja_id: int) -> Decimal:
        caja = self.db.consultar_uno("SELECT saldo_inicial FROM caja WHERE id = ?", (caja_id,))
        saldo = Decimal(caja["saldo_inicial"])
        movimientos = self.db.consultar(
            "SELECT tipo, monto FROM movimiento_caja WHERE caja_id = ?", (caja_id,)
        )
        for movimiento in movimientos:
            importe = Decimal(movimiento["monto"])
            saldo += importe if movimiento["tipo"] == "INGRESO" else -importe
        return saldo.quantize(Decimal("0.01"))