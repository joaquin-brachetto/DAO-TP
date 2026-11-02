"""Repositorios de persistencia del módulo de logística (turco).

Heredan de `RepositorioBase` y traducen entre las filas de SQLite (`03_logistica.sql`)
y las entidades del dominio (`src/dominio/logistica/modelos.py`), incluyendo la
hidratación polimórfica del patrón State (`EstadoBulto`) en `BultoRepositorio`
y la protección de inmutabilidad en `CambioEstadoBultoRepositorio` (V2).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from src.dominio.logistica.modelos import (
    Bulto,
    CambioEstadoBulto,
    ControlBulto,
    Despacho,
    DetalleBulto,
    EstadoBulto,
    EstadoRemito,
    Precinto,
    Recepcion,
    Remito,
    estado_desde_nombre,
)
from src.excepciones import EntidadNoEncontradaError
from src.persistencia.conexion import BaseDeDatos
from src.persistencia.repositorio_base import RepositorioBase


class RemitoRepositorio(RepositorioBase[Remito]):
    """Persistencia de cabeceras de `Remito`."""

    tabla = "remito"
    entidad = Remito
    orden = "fecha_emision DESC, id DESC"

    def _a_entidad(self, fila: sqlite3.Row) -> Remito:
        return Remito(
            id=fila["id"],
            numero=fila["numero"],
            orden_reposicion_id=fila["orden_reposicion_id"],
            origen_id=fila["origen_id"],
            destino_id=fila["destino_id"],
            fecha_emision=fila["fecha_emision"],
            estado=EstadoRemito(fila["estado"]),
            despacho_id=fila["despacho_id"] if "despacho_id" in fila.keys() else None,
        )

    def _a_fila(self, remito: Remito) -> dict[str, Any]:
        return {
            "numero": remito.numero.strip().upper(),
            "orden_reposicion_id": remito.orden_reposicion_id,
            "origen_id": remito.origen_id,
            "destino_id": remito.destino_id,
            "fecha_emision": remito.fecha_emision,
            "estado": str(remito.estado),
            "despacho_id": remito.despacho_id,
        }

    def por_numero(self, numero: str) -> Remito | None:
        fila = self.db.consultar_uno(
            "SELECT * FROM remito WHERE UPPER(numero) = UPPER(?)",
            (numero.strip(),),
        )
        return self._a_entidad(fila) if fila else None

    def de_orden(self, orden_reposicion_id: int) -> list[Remito]:
        return self.buscar_por(orden_reposicion_id=orden_reposicion_id)

    def de_destino(
        self, destino_id: int, estado: EstadoRemito | str | None = None
    ) -> list[Remito]:
        if estado is not None:
            return self.buscar_por(destino_id=destino_id, estado=str(estado))
        return self.buscar_por(destino_id=destino_id)

    def proximo_numero(self) -> str:
        """Genera el siguiente número correlativo con formato REM-0001."""
        fila = self.db.consultar_uno("SELECT COALESCE(MAX(id), 0) + 1 AS proximo FROM remito")
        correlativo = int(fila["proximo"]) if fila else 1
        while True:
            candidato = f"REM-{correlativo:04d}"
            if not self.existe(numero=candidato):
                return candidato
            correlativo += 1


class BultoRepositorio(RepositorioBase[Bulto]):
    """Persistencia de `Bulto`, reconstruyendo su objeto `EstadoBulto` (Patrón State)."""

    tabla = "bulto"
    entidad = Bulto
    orden = "id"

    def _a_entidad(self, fila: sqlite3.Row) -> Bulto:
        return Bulto(
            id=fila["id"],
            codigo=fila["codigo"],
            remito_id=fila["remito_id"],
            fecha_creacion=fila["fecha_creacion"],
            peso_kg=fila["peso_kg"],
            estado=estado_desde_nombre(fila["estado"]),
            motivo_rechazo=fila["motivo_rechazo"],
        )

    def _a_fila(self, bulto: Bulto) -> dict[str, Any]:
        estado_str = (
            bulto.estado.nombre()
            if isinstance(bulto.estado, EstadoBulto)
            else str(bulto.estado)
        )
        return {
            "codigo": bulto.codigo.strip().upper(),
            "remito_id": bulto.remito_id,
            "fecha_creacion": bulto.fecha_creacion,
            "peso_kg": bulto.peso_kg,
            "estado": estado_str,
            "motivo_rechazo": bulto.motivo_rechazo,
        }

    def de_remito(self, remito_id: int) -> list[Bulto]:
        return self.buscar_por(remito_id=remito_id)

    def por_codigo(self, codigo: str) -> Bulto | None:
        fila = self.db.consultar_uno(
            "SELECT * FROM bulto WHERE UPPER(codigo) = UPPER(?)",
            (codigo.strip(),),
        )
        return self._a_entidad(fila) if fila else None

    def proximo_codigo(self) -> str:
        """Genera el siguiente código correlativo de bulto con formato BUL-0001."""
        fila = self.db.consultar_uno("SELECT COALESCE(MAX(id), 0) + 1 AS proximo FROM bulto")
        correlativo = int(fila["proximo"]) if fila else 1
        while True:
            candidato = f"BUL-{correlativo:04d}"
            if not self.existe(codigo=candidato):
                return candidato
            correlativo += 1


class DetalleBultoRepositorio(RepositorioBase[DetalleBulto]):
    """Renglones de productos contenidos en cada bulto."""

    tabla = "detalle_bulto"
    entidad = DetalleBulto
    orden = "id"

    def de_bulto(self, bulto_id: int) -> list[DetalleBulto]:
        return self.buscar_por(bulto_id=bulto_id)


class PrecintoRepositorio(RepositorioBase[Precinto]):
    """Precintos de seguridad con número único por bulto."""

    tabla = "precinto"
    entidad = Precinto
    orden = "id"

    def de_bulto(self, bulto_id: int) -> Precinto | None:
        return self.buscar_uno_por(bulto_id=bulto_id)

    def por_numero(self, numero: str) -> Precinto | None:
        fila = self.db.consultar_uno(
            "SELECT * FROM precinto WHERE UPPER(numero) = UPPER(?)",
            (numero.strip(),),
        )
        return self._a_entidad(fila) if fila else None


class CambioEstadoBultoRepositorio(RepositorioBase[CambioEstadoBulto]):
    """Historial inmutable de estados del bulto (V2).

    Solo permite insertar nuevos eventos y consultar la línea de tiempo.
    Cualquier intento de UPDATE o DELETE dispara los triggers de inmutabilidad en SQLite.
    """

    tabla = "cambio_estado_bulto"
    entidad = CambioEstadoBulto
    orden = "fecha_hora, id"

    def guardar(self, entidad: CambioEstadoBulto) -> CambioEstadoBulto:
        datos = self._a_fila(entidad)
        try:
            if getattr(entidad, "id", None) is None:
                columnas = ", ".join(datos)
                marcadores = ", ".join("?" for _ in datos)
                cursor = self.db.ejecutar(
                    f"INSERT INTO {self.tabla} ({columnas}) VALUES ({marcadores})",
                    list(datos.values()),
                )
                object.__setattr__(entidad, "id", cursor.lastrowid)
            else:
                asignaciones = ", ".join(f"{columna} = ?" for columna in datos)
                cursor = self.db.ejecutar(
                    f"UPDATE {self.tabla} SET {asignaciones} WHERE id = ?",
                    [*datos.values(), entidad.id],
                )
                if cursor.rowcount == 0:
                    raise EntidadNoEncontradaError(
                        f"No existe un registro de {self.tabla} con id {entidad.id}."
                    )
        except sqlite3.IntegrityError as error:
            raise self._traducir_error(error) from error
        return entidad

    def de_bulto(self, bulto_id: int) -> list[CambioEstadoBulto]:
        filas = self.db.consultar(
            "SELECT * FROM cambio_estado_bulto WHERE bulto_id = ? ORDER BY fecha_hora ASC, id ASC",
            (bulto_id,),
        )
        return [self._a_entidad(fila) for fila in filas]


class DespachoRepositorio(RepositorioBase[Despacho]):
    """Persistencia de `Despacho` y su asociación con uno o más remitos (`despacho_remito`)."""

    tabla = "despacho"
    entidad = Despacho
    orden = "fecha_hora_salida DESC, id DESC"

    def _a_entidad(self, fila: sqlite3.Row) -> Despacho:
        despacho_id = fila["id"]
        remitos_filas = self.db.consultar(
            "SELECT remito_id FROM despacho_remito WHERE despacho_id = ? ORDER BY id",
            (despacho_id,),
        )
        remito_ids = [r["remito_id"] for r in remitos_filas]
        if not remito_ids:
            remitos_fk = self.db.consultar(
                "SELECT id FROM remito WHERE despacho_id = ? ORDER BY id",
                (despacho_id,),
            )
            remito_ids = [r["id"] for r in remitos_fk]
        return Despacho(
            id=despacho_id,
            fecha_hora_salida=fila["fecha_hora_salida"],
            transportista=fila["transportista"],
            patente=fila["patente"],
            usuario=fila["usuario"],
            observaciones=fila["observaciones"],
            remito_ids=remito_ids,
        )

    def _a_fila(self, despacho: Despacho) -> dict[str, Any]:
        return {
            "fecha_hora_salida": despacho.fecha_hora_salida,
            "transportista": despacho.transportista,
            "patente": despacho.patente,
            "usuario": despacho.usuario,
            "observaciones": despacho.observaciones,
        }

    def guardar(self, entidad: Despacho) -> Despacho:
        with self.db.transaccion():
            super().guardar(entidad)
            if entidad.id is not None and entidad.remito_ids:
                for remito_id in entidad.remito_ids:
                    existe_rel = self.db.consultar_uno(
                        "SELECT id FROM despacho_remito WHERE remito_id = ?",
                        (remito_id,),
                    )
                    if existe_rel is None:
                        try:
                            self.db.ejecutar(
                                "INSERT INTO despacho_remito (despacho_id, remito_id) VALUES (?, ?)",
                                (entidad.id, remito_id),
                            )
                        except sqlite3.IntegrityError as error:
                            raise self._traducir_error(error) from error
                    self.db.ejecutar(
                        "UPDATE remito SET despacho_id = ? WHERE id = ?",
                        (entidad.id, remito_id),
                    )
        return entidad


class RecepcionRepositorio(RepositorioBase[Recepcion]):
    """Persistencia de actas de `Recepcion` de remitos en sucursal."""

    tabla = "recepcion"
    entidad = Recepcion
    orden = "fecha_hora_llegada DESC, id DESC"

    def _a_entidad(self, fila: sqlite3.Row) -> Recepcion:
        return Recepcion(
            id=fila["id"],
            remito_id=fila["remito_id"],
            fecha_hora_llegada=fila["fecha_hora_llegada"],
            recibido_por=fila["recibido_por"],
            observaciones=fila["observaciones"],
            cerrada=bool(fila["cerrada"]),
        )

    def _a_fila(self, recepcion: Recepcion) -> dict[str, Any]:
        return {
            "remito_id": recepcion.remito_id,
            "fecha_hora_llegada": recepcion.fecha_hora_llegada,
            "recibido_por": recepcion.recibido_por,
            "observaciones": recepcion.observaciones,
            "cerrada": bool(recepcion.cerrada),
        }

    def de_remito(self, remito_id: int) -> Recepcion | None:
        return self.buscar_uno_por(remito_id=remito_id)


class ControlBultoRepositorio(RepositorioBase[ControlBulto]):
    """Persistencia del control de precinto por cada bulto recibido."""

    tabla = "control_bulto"
    entidad = ControlBulto
    orden = "fecha_hora_control, id"

    def _a_entidad(self, fila: sqlite3.Row) -> ControlBulto:
        return ControlBulto(
            id=fila["id"],
            recepcion_id=fila["recepcion_id"],
            bulto_id=fila["bulto_id"],
            numero_precinto_leido=fila["numero_precinto_leido"],
            precinto_integro=bool(fila["precinto_integro"]),
            coincide_precinto=bool(fila["coincide_precinto"]),
            resultado=fila["resultado"],
            observacion=fila["observacion"],
            fecha_hora_control=fila["fecha_hora_control"],
        )

    def _a_fila(self, control: ControlBulto) -> dict[str, Any]:
        return {
            "recepcion_id": control.recepcion_id,
            "bulto_id": control.bulto_id,
            "numero_precinto_leido": control.numero_precinto_leido.strip().upper(),
            "precinto_integro": bool(control.precinto_integro),
            "coincide_precinto": bool(control.coincide_precinto),
            "resultado": control.resultado,
            "observacion": control.observacion,
            "fecha_hora_control": control.fecha_hora_control,
        }

    def de_recepcion(self, recepcion_id: int) -> list[ControlBulto]:
        return self.buscar_por(recepcion_id=recepcion_id)

    def de_bulto(self, bulto_id: int) -> ControlBulto | None:
        return self.buscar_uno_por(bulto_id=bulto_id)
