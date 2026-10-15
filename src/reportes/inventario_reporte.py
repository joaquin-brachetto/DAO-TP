"""Reportes de inventario (pohlsi).

R3 – Movimientos y valorización del inventario
    Entradas y salidas de stock en un período (por tipo de movimiento, ubicación y
    categoría) y el stock actual de cada ubicación valorizado al costo.

R4 – Tiempo promedio de tránsito CD → locales
    Para cada remito: cuánto tardó desde que salió del CD hasta que el local lo
    verificó (o rechazó). Promedio, mínimo y máximo por sucursal.

Los dos salen del libro `movimiento_stock`, que es inmutable. R4 no lee tablas de
logística: usa los movimientos que logística (turco) registra con la referencia
`Referencia("REMITO", remito_id)`:

    despacho  -> EGRESO_DESPACHO en el CD           (sale del CD)
                 INGRESO_PENDIENTE en el local       (queda en tránsito, sin verificar)
    recepción -> CONFIRMACION_VERIFICADO o MERMA_RECHAZO en el local (se verificó o rechazó)
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum

from src.dominio.inventario.modelos import TipoMovimiento
from src.dominio.maestros.modelos import a_dinero
from src.excepciones import ValidacionError
from src.persistencia.conexion import BaseDeDatos

T = TipoMovimiento

DOCUMENTO_REMITO = "REMITO"
"""Tipo de documento con el que logística referencia sus movimientos (contrato con turco)."""


class Sentido(StrEnum):
    ENTRADA = "Entrada"
    SALIDA = "Salida"
    INTERNO = "Interno"  # cambia de balde dentro de la misma ubicación


SENTIDO_POR_TIPO: dict[TipoMovimiento, Sentido] = {
    T.INGRESO_COMPRA: Sentido.ENTRADA,
    T.INGRESO_PENDIENTE: Sentido.ENTRADA,
    T.REINGRESO_DEVOLUCION: Sentido.ENTRADA,
    T.EGRESO_VENTA: Sentido.SALIDA,
    T.EGRESO_DESPACHO: Sentido.SALIDA,
    T.MERMA_RECHAZO: Sentido.SALIDA,  # deja de ser stock utilizable: es una pérdida
    T.CONFIRMACION_VERIFICADO: Sentido.INTERNO,  # pendiente -> disponible
    T.AJUSTE: Sentido.INTERNO,
}

NOMBRE_TIPO: dict[TipoMovimiento, str] = {
    T.INGRESO_COMPRA: "Compra a proveedor",
    T.EGRESO_DESPACHO: "Despacho a sucursal",
    T.INGRESO_PENDIENTE: "Ingreso pendiente de verificación",
    T.CONFIRMACION_VERIFICADO: "Verificado (pasa a disponible)",
    T.MERMA_RECHAZO: "Merma por rechazo",
    T.EGRESO_VENTA: "Venta",
    T.REINGRESO_DEVOLUCION: "Devolución de cliente",
    T.AJUSTE: "Ajuste",
}


def validar_periodo(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """Rango [desde 00:00, hasta+1 00:00) para comparar con fechas y horas."""
    if desde > hasta:
        raise ValidacionError("La fecha «Desde» no puede ser posterior a «Hasta».")
    return datetime.combine(desde, time.min), datetime.combine(hasta + timedelta(days=1), time.min)


# === R3: movimientos y valorización =============================================================


@dataclass(frozen=True)
class FilaMovimiento:
    fecha_hora: datetime
    ubicacion_id: int
    ubicacion: str
    producto_id: int
    sku: str
    producto: str
    categoria: str
    tipo: TipoMovimiento
    cantidad: int
    costo_unitario: Decimal
    tipo_documento: str
    documento_id: int | None
    usuario: str

    @property
    def sentido(self) -> Sentido:
        return SENTIDO_POR_TIPO[self.tipo]

    @property
    def valor(self) -> Decimal:
        return a_dinero(self.costo_unitario * self.cantidad)

    @property
    def documento(self) -> str:
        return self.tipo_documento if self.documento_id is None else f"{self.tipo_documento} {self.documento_id}"


@dataclass(frozen=True)
class TotalPorTipo:
    tipo: TipoMovimiento
    movimientos: int
    unidades: int
    valor: Decimal

    @property
    def sentido(self) -> Sentido:
        return SENTIDO_POR_TIPO[self.tipo]

    @property
    def nombre(self) -> str:
        return NOMBRE_TIPO[self.tipo]


@dataclass(frozen=True)
class FilaValorizacion:
    ubicacion_id: int
    ubicacion: str
    codigo: str
    es_centro_distribucion: bool
    disponible: int
    pendiente: int
    merma: int
    valor_disponible: Decimal
    valor_pendiente: Decimal
    valor_merma: Decimal

    @property
    def valor_total(self) -> Decimal:
        """Disponible + pendiente (lo que la empresa tiene). La merma se informa aparte."""
        return a_dinero(self.valor_disponible + self.valor_pendiente)


@dataclass(frozen=True)
class ResumenMovimientos:
    movimientos: list[FilaMovimiento]
    valorizacion: list[FilaValorizacion]

    def por_tipo(self) -> list[TotalPorTipo]:
        """Totales por tipo de movimiento, en el orden del enum (entradas primero)."""
        totales = []
        for tipo in TipoMovimiento:
            del_tipo = [m for m in self.movimientos if m.tipo == tipo]
            if del_tipo:
                totales.append(TotalPorTipo(
                    tipo=tipo,
                    movimientos=len(del_tipo),
                    unidades=sum(m.cantidad for m in del_tipo),
                    valor=a_dinero(sum((m.valor for m in del_tipo), Decimal("0"))),
                ))
        return sorted(totales, key=lambda t: list(Sentido).index(t.sentido))

    def _total(self, sentido: Sentido) -> tuple[int, Decimal]:
        filas = [m for m in self.movimientos if m.sentido == sentido]
        return sum(m.cantidad for m in filas), a_dinero(sum((m.valor for m in filas), Decimal("0")))

    @property
    def entradas(self) -> tuple[int, Decimal]:
        """(unidades, valor) que entraron en el período."""
        return self._total(Sentido.ENTRADA)

    @property
    def salidas(self) -> tuple[int, Decimal]:
        """(unidades, valor) que salieron en el período (ventas, despachos y mermas)."""
        return self._total(Sentido.SALIDA)

    @property
    def total_valorizado(self) -> Decimal:
        return a_dinero(sum((fila.valor_total for fila in self.valorizacion), Decimal("0")))


class ReporteMovimientos:
    """R3: movimientos de stock de un período y stock actual valorizado al costo."""

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def consultar(
        self,
        desde: date,
        hasta: date,
        ubicacion_id: int | None = None,
        categoria_id: int | None = None,
        tipo: TipoMovimiento | None = None,
    ) -> ResumenMovimientos:
        inicio, fin = validar_periodo(desde, hasta)
        return ResumenMovimientos(
            movimientos=self._movimientos(inicio, fin, ubicacion_id, categoria_id, tipo),
            valorizacion=self._valorizacion(ubicacion_id, categoria_id),
        )

    def _movimientos(self, inicio, fin, ubicacion_id, categoria_id, tipo) -> list[FilaMovimiento]:
        sql = (
            "SELECT m.fecha_hora, m.tipo, m.cantidad, m.costo_unitario, m.tipo_documento, m.documento_id, "
            "m.usuario, s.ubicacion_id, u.nombre AS ubicacion, s.producto_id, p.sku, p.nombre AS producto, "
            "c.nombre AS categoria "
            "FROM movimiento_stock m "
            "JOIN stock s ON s.id = m.stock_id "
            "JOIN ubicacion u ON u.id = s.ubicacion_id "
            "JOIN producto p ON p.id = s.producto_id "
            "JOIN categoria c ON c.id = p.categoria_id "
            "WHERE m.fecha_hora >= ? AND m.fecha_hora < ?"
        )
        parametros: list = [inicio, fin]
        if ubicacion_id is not None:
            sql += " AND s.ubicacion_id = ?"
            parametros.append(ubicacion_id)
        if categoria_id is not None:
            sql += " AND p.categoria_id = ?"
            parametros.append(categoria_id)
        if tipo is not None:
            sql += " AND m.tipo = ?"
            parametros.append(str(tipo))
        filas = self.db.consultar(sql + " ORDER BY m.fecha_hora, m.id", parametros)
        return [
            FilaMovimiento(
                fecha_hora=f["fecha_hora"],
                ubicacion_id=f["ubicacion_id"],
                ubicacion=f["ubicacion"],
                producto_id=f["producto_id"],
                sku=f["sku"],
                producto=f["producto"],
                categoria=f["categoria"],
                tipo=TipoMovimiento(f["tipo"]),
                cantidad=f["cantidad"],
                costo_unitario=f["costo_unitario"],
                tipo_documento=f["tipo_documento"],
                documento_id=f["documento_id"],
                usuario=f["usuario"],
            )
            for f in filas
        ]

    def _valorizacion(self, ubicacion_id, categoria_id) -> list[FilaValorizacion]:
        """Stock actual por ubicación, valorizado al costo actual de cada producto."""
        sql = (
            "SELECT u.id, u.nombre, u.codigo, u.tipo, s.cantidad_disponible, s.cantidad_pendiente, "
            "s.cantidad_merma, p.costo_actual "
            "FROM stock s JOIN ubicacion u ON u.id = s.ubicacion_id JOIN producto p ON p.id = s.producto_id "
            "WHERE 1 = 1"
        )
        parametros: list = []
        if ubicacion_id is not None:
            sql += " AND u.id = ?"
            parametros.append(ubicacion_id)
        if categoria_id is not None:
            sql += " AND p.categoria_id = ?"
            parametros.append(categoria_id)
        acumulado: dict[int, dict] = {}
        for f in self.db.consultar(sql + " ORDER BY u.tipo, u.nombre", parametros):
            fila = acumulado.setdefault(f["id"], {
                "ubicacion_id": f["id"], "ubicacion": f["nombre"], "codigo": f["codigo"],
                "es_centro_distribucion": f["tipo"] == "CD",
                "disponible": 0, "pendiente": 0, "merma": 0,
                "valor_disponible": Decimal("0"), "valor_pendiente": Decimal("0"), "valor_merma": Decimal("0"),
            })
            costo = Decimal(f["costo_actual"])
            for balde in ("disponible", "pendiente", "merma"):
                cantidad = f[f"cantidad_{balde}"]
                fila[balde] += cantidad
                fila[f"valor_{balde}"] += costo * cantidad
        return [
            FilaValorizacion(**{**datos, **{k: a_dinero(v) for k, v in datos.items() if k.startswith("valor_")}})
            for datos in acumulado.values()
        ]


# === R4: tiempo de tránsito CD -> locales ========================================================


@dataclass(frozen=True)
class FilaTransito:
    remito_id: int
    origen: str
    destino_id: int
    destino: str
    despacho: datetime
    recepcion: datetime | None
    unidades: int
    con_rechazos: bool

    @property
    def en_transito(self) -> bool:
        return self.recepcion is None

    @property
    def horas(self) -> float | None:
        if self.recepcion is None:
            return None
        return (self.recepcion - self.despacho).total_seconds() / 3600


@dataclass(frozen=True)
class PromedioSucursal:
    destino_id: int
    destino: str
    remitos: int
    promedio_horas: float
    minimo_horas: float
    maximo_horas: float


@dataclass(frozen=True)
class ResumenTransito:
    filas: list[FilaTransito]

    @property
    def recibidos(self) -> list[FilaTransito]:
        return [f for f in self.filas if not f.en_transito]

    @property
    def cantidad_en_transito(self) -> int:
        return sum(1 for f in self.filas if f.en_transito)

    @property
    def promedio_horas(self) -> float | None:
        horas = [f.horas for f in self.recibidos]
        return sum(horas) / len(horas) if horas else None

    def por_sucursal(self) -> list[PromedioSucursal]:
        """Promedio, mínimo y máximo por sucursal (solo remitos ya recibidos), del más lento al más rápido."""
        grupos: dict[int, list[FilaTransito]] = {}
        for fila in self.recibidos:
            grupos.setdefault(fila.destino_id, []).append(fila)
        promedios = [
            PromedioSucursal(
                destino_id=destino_id,
                destino=filas[0].destino,
                remitos=len(filas),
                promedio_horas=sum(f.horas for f in filas) / len(filas),
                minimo_horas=min(f.horas for f in filas),
                maximo_horas=max(f.horas for f in filas),
            )
            for destino_id, filas in grupos.items()
        ]
        return sorted(promedios, key=lambda p: p.promedio_horas, reverse=True)


class ReporteTransito:
    """R4: tiempo entre el despacho en el CD y la verificación en el local, por remito."""

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()

    def consultar(self, desde: date, hasta: date, sucursal_id: int | None = None) -> ResumenTransito:
        """Remitos despachados en el período (por fecha de despacho)."""
        inicio, fin = validar_periodo(desde, hasta)
        filas = self.db.consultar(
            "SELECT m.documento_id AS remito, m.tipo, m.fecha_hora, m.cantidad, s.ubicacion_id, u.nombre "
            "FROM movimiento_stock m JOIN stock s ON s.id = m.stock_id JOIN ubicacion u ON u.id = s.ubicacion_id "
            "WHERE m.tipo_documento = ? AND m.documento_id IS NOT NULL AND m.tipo IN (?, ?, ?, ?) "
            "ORDER BY m.documento_id, m.fecha_hora",
            (DOCUMENTO_REMITO, str(T.EGRESO_DESPACHO), str(T.INGRESO_PENDIENTE),
             str(T.CONFIRMACION_VERIFICADO), str(T.MERMA_RECHAZO)),
        )
        remitos: dict[int, dict] = {}
        for f in filas:
            datos = remitos.setdefault(f["remito"], {
                "despacho": None, "origen": "", "destino_id": None, "destino": "",
                "recepcion": None, "unidades": 0, "con_rechazos": False,
            })
            tipo = TipoMovimiento(f["tipo"])
            if tipo == T.EGRESO_DESPACHO:
                if datos["despacho"] is None or f["fecha_hora"] < datos["despacho"]:
                    datos["despacho"], datos["origen"] = f["fecha_hora"], f["nombre"]
            elif tipo == T.INGRESO_PENDIENTE:
                datos["destino_id"], datos["destino"] = f["ubicacion_id"], f["nombre"]
                datos["unidades"] += f["cantidad"]
            else:  # verificado o rechazado en el local: la primera marca la recepción
                datos["destino_id"], datos["destino"] = f["ubicacion_id"], f["nombre"]
                if datos["recepcion"] is None or f["fecha_hora"] < datos["recepcion"]:
                    datos["recepcion"] = f["fecha_hora"]
                datos["con_rechazos"] |= tipo == T.MERMA_RECHAZO

        resultado = []
        for remito_id, datos in remitos.items():
            if datos["despacho"] is None or datos["destino_id"] is None:
                continue  # remito incompleto: sin salida del CD o sin destino
            if not inicio <= datos["despacho"] < fin:
                continue
            if sucursal_id is not None and datos["destino_id"] != sucursal_id:
                continue
            resultado.append(FilaTransito(remito_id=remito_id, **datos))
        return ResumenTransito(sorted(resultado, key=lambda f: f.despacho))


def formato_duracion(horas: float | None) -> str:
    """26.5 -> '1 d 2 h 30 min'; None -> 'En tránsito'."""
    if horas is None:
        return "En tránsito"
    minutos = round(horas * 60)
    dias, resto = divmod(minutos, 24 * 60)
    horas_enteras, minutos = divmod(resto, 60)
    partes = [f"{dias} d"] if dias else []
    if horas_enteras or dias:
        partes.append(f"{horas_enteras} h")
    partes.append(f"{minutos} min")
    return " ".join(partes)
