"""Reporte no trivial R5 de Logística (turco):
Bultos rechazados y mermas por rotura o adulteración de precinto logístico.

Analiza para un período `[desde, hasta]` (filtrable opcionalmente por sucursal destino,
categoría de producto y tipo de anomalía de precinto):
1. El detalle de cada bulto rechazado en la recepción (remito, orden, sucursal, fecha,
   receptor, precinto colocado vs. precinto leído, integridad, tipo de anomalía,
   motivo de rechazo, unidades afectadas y valorización de la merma al costo).
2. El desglose de mermas valorizadas por producto y sucursal.
3. El resumen comparativo por sucursal destino (total de bultos evaluados en el período,
   bultos verificados, bultos rechazados, porcentaje de rechazo, unidades en merma y
   valor total perdido por rechazos logísticos).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from src.dominio.logistica.modelos import CodigoEstadoBulto
from src.dominio.maestros.modelos import a_dinero
from src.excepciones import ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.reportes.inventario_reporte import validar_periodo


class TipoAnomaliaPrecinto(StrEnum):
    TODOS = "TODOS"
    PRECINTO_ROTO = "PRECINTO_ROTO"
    PRECINTO_NO_COINCIDE = "PRECINTO_NO_COINCIDE"
    ROTO_Y_NO_COINCIDE = "ROTO_Y_NO_COINCIDE"


NOMBRE_ANOMALIA: dict[str, str] = {
    TipoAnomaliaPrecinto.PRECINTO_ROTO.value: "Precinto roto/violado",
    TipoAnomaliaPrecinto.PRECINTO_NO_COINCIDE.value: "Precinto no coincide",
    TipoAnomaliaPrecinto.ROTO_Y_NO_COINCIDE.value: "Roto y no coincide",
}


def clasificar_anomalia(precinto_integro: bool, coincide_precinto: bool) -> str:
    """Devuelve el código de anomalía según la integridad física y coincidencia del precinto."""
    if not precinto_integro and not coincide_precinto:
        return TipoAnomaliaPrecinto.ROTO_Y_NO_COINCIDE.value
    if not precinto_integro:
        return TipoAnomaliaPrecinto.PRECINTO_ROTO.value
    if not coincide_precinto:
        return TipoAnomaliaPrecinto.PRECINTO_NO_COINCIDE.value
    return "OTRO"


def descripcion_anomalia(precinto_integro: bool, coincide_precinto: bool) -> str:
    codigo = clasificar_anomalia(precinto_integro, coincide_precinto)
    return NOMBRE_ANOMALIA.get(codigo, "Rechazo logístico")


@dataclass(frozen=True)
class FilaBultoRechazado:
    bulto_id: int
    codigo_bulto: str
    remito_id: int
    numero_remito: str
    orden_numero: int
    sucursal_id: int
    sucursal: str
    fecha_rechazo: datetime
    recibido_por: str
    precinto_colocado: str
    precinto_leido: str
    precinto_integro: bool
    coincide_precinto: bool
    codigo_anomalia: str
    tipo_anomalia: str
    motivo_rechazo: str
    unidades_totales: int
    valor_merma: Decimal


@dataclass(frozen=True)
class FilaDetalleMermaProducto:
    producto_id: int
    sku: str
    producto: str
    categoria_id: int
    categoria: str
    sucursal_id: int
    sucursal: str
    bultos_afectados: int
    unidades_merma: int
    costo_unitario: Decimal
    valor_merma: Decimal


@dataclass(frozen=True)
class ResumenRechazosSucursal:
    sucursal_id: int
    sucursal: str
    total_bultos_recibidos: int
    bultos_verificados: int
    bultos_rechazados: int
    porcentaje_rechazo: Decimal
    unidades_merma: int
    valor_merma: Decimal


@dataclass(frozen=True)
class ResumenReporteRechazos:
    bultos_rechazados: list[FilaBultoRechazado]
    mermas_por_producto: list[FilaDetalleMermaProducto]
    por_sucursal: list[ResumenRechazosSucursal]
    total_bultos_evaluados: int = 0

    @property
    def total_bultos_rechazados(self) -> int:
        return len(self.bultos_rechazados)

    @property
    def total_unidades_merma(self) -> int:
        return sum(f.unidades_totales for f in self.bultos_rechazados)

    @property
    def total_valor_merma(self) -> Decimal:
        return a_dinero(sum((f.valor_merma for f in self.bultos_rechazados), Decimal("0")))

    @property
    def tasa_rechazo_global(self) -> Decimal:
        if self.total_bultos_evaluados <= 0:
            return Decimal("0.00")
        return a_dinero(
            (Decimal(self.total_bultos_rechazados) * Decimal("100"))
            / Decimal(self.total_bultos_evaluados)
        )


class ReporteBultosRechazados:
    """R5: Bultos rechazados y mermas valorizadas por rotura/adulteración de precinto logístico."""

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def consultar(
        self,
        desde: date,
        hasta: date,
        sucursal_id: int | None = None,
        categoria_id: int | None = None,
        tipo_anomalia: str | TipoAnomaliaPrecinto | None = None,
    ) -> ResumenReporteRechazos:
        inicio, fin = validar_periodo(desde, hasta)
        filtro_anomalia = self._normalizar_filtro_anomalia(tipo_anomalia)

        costos_merma = self._costos_merma_por_remito_y_producto()
        bultos_controlados = self._consultar_bultos_controlados(inicio, fin, sucursal_id)

        filas_bultos: list[FilaBultoRechazado] = []
        acumulado_productos: dict[tuple[int, int], dict[str, Any]] = {}
        stats_sucursal: dict[int, dict[str, Any]] = {}

        for b in bultos_controlados:
            renglones = self._renglones_de_bulto(b["bulto_id"], categoria_id)
            if categoria_id is not None and not renglones:
                continue

            suc_id = b["sucursal_id"]
            info_suc = stats_sucursal.setdefault(
                suc_id,
                {
                    "sucursal_id": suc_id,
                    "sucursal": b["sucursal"],
                    "total_bultos_recibidos": 0,
                    "bultos_verificados": 0,
                    "bultos_rechazados": 0,
                    "unidades_merma": 0,
                    "valor_merma": Decimal("0"),
                },
            )

            es_rechazado = b["estado_bulto"] == CodigoEstadoBulto.RECHAZADO.value
            cod_anomalia = clasificar_anomalia(
                bool(b["precinto_integro"]), bool(b["coincide_precinto"])
            )

            if es_rechazado and not self._coincide_filtro_anomalia(
                cod_anomalia, bool(b["precinto_integro"]), bool(b["coincide_precinto"]), filtro_anomalia
            ):
                continue

            info_suc["total_bultos_recibidos"] += 1
            if not es_rechazado:
                info_suc["bultos_verificados"] += 1
                continue

            unidades_bulto = 0
            valor_bulto = Decimal("0")
            for renglon in renglones:
                prod_id = renglon["producto_id"]
                cant = int(renglon["cantidad"])
                costo_unit = costos_merma.get(
                    (b["remito_id"], prod_id), Decimal(renglon["costo_actual"])
                )
                subtotal = a_dinero(costo_unit * cant)
                unidades_bulto += cant
                valor_bulto += subtotal

                clave_prod = (suc_id, prod_id)
                item_prod = acumulado_productos.setdefault(
                    clave_prod,
                    {
                        "producto_id": prod_id,
                        "sku": renglon["sku"],
                        "producto": renglon["producto"],
                        "categoria_id": renglon["categoria_id"],
                        "categoria": renglon["categoria"],
                        "sucursal_id": suc_id,
                        "sucursal": b["sucursal"],
                        "bultos_ids": set(),
                        "unidades_merma": 0,
                        "costo_unitario": a_dinero(costo_unit),
                        "valor_merma": Decimal("0"),
                    },
                )
                item_prod["bultos_ids"].add(b["bulto_id"])
                item_prod["unidades_merma"] += cant
                item_prod["valor_merma"] = a_dinero(item_prod["valor_merma"] + subtotal)

            valor_bulto = a_dinero(valor_bulto)
            info_suc["bultos_rechazados"] += 1
            info_suc["unidades_merma"] += unidades_bulto
            info_suc["valor_merma"] = a_dinero(info_suc["valor_merma"] + valor_bulto)

            filas_bultos.append(
                FilaBultoRechazado(
                    bulto_id=b["bulto_id"],
                    codigo_bulto=b["codigo_bulto"],
                    remito_id=b["remito_id"],
                    numero_remito=b["numero_remito"],
                    orden_numero=b["orden_numero"],
                    sucursal_id=suc_id,
                    sucursal=b["sucursal"],
                    fecha_rechazo=b["fecha_control"],
                    recibido_por=b["recibido_por"],
                    precinto_colocado=b["precinto_colocado"] or "SIN PRECINTO",
                    precinto_leido=b["numero_precinto_leido"],
                    precinto_integro=bool(b["precinto_integro"]),
                    coincide_precinto=bool(b["coincide_precinto"]),
                    codigo_anomalia=cod_anomalia,
                    tipo_anomalia=descripcion_anomalia(
                        bool(b["precinto_integro"]), bool(b["coincide_precinto"])
                    ),
                    motivo_rechazo=b["motivo_rechazo"] or b["observacion_control"] or "",
                    unidades_totales=unidades_bulto,
                    valor_merma=valor_bulto,
                )
            )

        mermas_por_producto = [
            FilaDetalleMermaProducto(
                producto_id=d["producto_id"],
                sku=d["sku"],
                producto=d["producto"],
                categoria_id=d["categoria_id"],
                categoria=d["categoria"],
                sucursal_id=d["sucursal_id"],
                sucursal=d["sucursal"],
                bultos_afectados=len(d["bultos_ids"]),
                unidades_merma=d["unidades_merma"],
                costo_unitario=d["costo_unitario"],
                valor_merma=d["valor_merma"],
            )
            for d in sorted(
                acumulado_productos.values(),
                key=lambda x: (x["valor_merma"], x["unidades_merma"]),
                reverse=True,
            )
        ]

        por_sucursal: list[ResumenRechazosSucursal] = []
        for s in stats_sucursal.values():
            total_rec = s["total_bultos_recibidos"]
            rech = s["bultos_rechazados"]
            porcentaje = (
                a_dinero((Decimal(rech) * Decimal("100")) / Decimal(total_rec))
                if total_rec > 0
                else Decimal("0.00")
            )
            por_sucursal.append(
                ResumenRechazosSucursal(
                    sucursal_id=s["sucursal_id"],
                    sucursal=s["sucursal"],
                    total_bultos_recibidos=total_rec,
                    bultos_verificados=s["bultos_verificados"],
                    bultos_rechazados=rech,
                    porcentaje_rechazo=porcentaje,
                    unidades_merma=s["unidades_merma"],
                    valor_merma=a_dinero(s["valor_merma"]),
                )
            )
        por_sucursal.sort(key=lambda item: (item.valor_merma, item.bultos_rechazados), reverse=True)

        total_evaluados = sum(s.total_bultos_recibidos for s in por_sucursal)
        return ResumenReporteRechazos(
            bultos_rechazados=filas_bultos,
            mermas_por_producto=mermas_por_producto,
            por_sucursal=por_sucursal,
            total_bultos_evaluados=total_evaluados,
        )

    # --- Consultas SQL internas -----------------------------------------------------------------

    def _consultar_bultos_controlados(
        self, inicio: datetime, fin: datetime, sucursal_id: int | None
    ) -> list[ Any ]:
        sql = (
            "SELECT "
            "  b.id AS bulto_id, "
            "  b.codigo AS codigo_bulto, "
            "  b.estado AS estado_bulto, "
            "  b.motivo_rechazo AS motivo_rechazo, "
            "  r.id AS remito_id, "
            "  r.numero AS numero_remito, "
            "  o.numero AS orden_numero, "
            "  u.id AS sucursal_id, "
            "  u.nombre AS sucursal, "
            "  cb.fecha_hora_control AS fecha_control, "
            "  rec.recibido_por AS recibido_por, "
            "  pr.numero AS precinto_colocado, "
            "  cb.numero_precinto_leido AS numero_precinto_leido, "
            "  cb.precinto_integro AS precinto_integro, "
            "  cb.coincide_precinto AS coincide_precinto, "
            "  cb.observacion AS observacion_control "
            "FROM control_bulto cb "
            "JOIN recepcion rec ON rec.id = cb.recepcion_id "
            "JOIN bulto b ON b.id = cb.bulto_id "
            "JOIN remito r ON r.id = b.remito_id "
            "JOIN orden_reposicion o ON o.id = r.orden_reposicion_id "
            "JOIN ubicacion u ON u.id = r.destino_id "
            "LEFT JOIN precinto pr ON pr.bulto_id = b.id "
            "WHERE cb.fecha_hora_control >= ? AND cb.fecha_hora_control < ? "
            "  AND rec.cerrada = 1"
        )
        parametros: list[Any] = [inicio, fin]
        if sucursal_id is not None:
            sql += " AND r.destino_id = ?"
            parametros.append(sucursal_id)
        sql += " ORDER BY cb.fecha_hora_control DESC, b.id DESC"
        return self.db.consultar(sql, parametros)

    def _renglones_de_bulto(self, bulto_id: int, categoria_id: int | None) -> list[Any]:
        sql = (
            "SELECT db.producto_id, db.cantidad, p.sku, p.nombre AS producto, "
            "       p.costo_actual, c.id AS categoria_id, c.nombre AS categoria "
            "FROM detalle_bulto db "
            "JOIN producto p ON p.id = db.producto_id "
            "JOIN categoria c ON c.id = p.categoria_id "
            "WHERE db.bulto_id = ?"
        )
        parametros: list[Any] = [bulto_id]
        if categoria_id is not None:
            sql += " AND p.categoria_id = ?"
            parametros.append(categoria_id)
        sql += " ORDER BY p.nombre"
        return self.db.consultar(sql, parametros)

    def _costos_merma_por_remito_y_producto(self) -> dict[tuple[int, int], Decimal]:
        filas = self.db.consultar(
            "SELECT m.documento_id AS remito_id, s.producto_id, m.costo_unitario "
            "FROM movimiento_stock m "
            "JOIN stock s ON s.id = m.stock_id "
            "WHERE m.tipo_documento = 'REMITO' AND m.tipo = 'MERMA_RECHAZO' "
            "  AND m.documento_id IS NOT NULL"
        )
        return {
            (int(f["remito_id"]), int(f["producto_id"])): Decimal(f["costo_unitario"])
            for f in filas
        }

    @staticmethod
    def _normalizar_filtro_anomalia(valor: str | TipoAnomaliaPrecinto | None) -> str:
        if valor is None or not str(valor).strip():
            return TipoAnomaliaPrecinto.TODOS.value
        limpio = str(valor).strip().upper()
        validos = {e.value for e in TipoAnomaliaPrecinto}
        if limpio not in validos:
            raise ValidacionError(f"Tipo de anomalía inválido: «{valor}».")
        return limpio

    @staticmethod
    def _coincide_filtro_anomalia(
        cod_anomalia: str,
        precinto_integro: bool,
        coincide_precinto: bool,
        filtro: str,
    ) -> bool:
        if filtro == TipoAnomaliaPrecinto.TODOS.value:
            return True
        if filtro == TipoAnomaliaPrecinto.PRECINTO_ROTO.value:
            return not precinto_integro
        if filtro == TipoAnomaliaPrecinto.PRECINTO_NO_COINCIDE.value:
            return not coincide_precinto
        if filtro == TipoAnomaliaPrecinto.ROTO_Y_NO_COINCIDE.value:
            return cod_anomalia == TipoAnomaliaPrecinto.ROTO_Y_NO_COINCIDE.value
        return True
