"""Repositorio genérico: guarda y lee entidades de una tabla.

Patrón **Repository**: el resto del sistema trabaja con objetos de dominio
(`Producto`, `Proveedor`, ...) y no escribe SQL. Cada repositorio concreto solo
dice qué tabla y qué clase usa:

    @dataclass
    class Categoria:
        nombre: str
        descripcion: str = ""
        id: int | None = None

    class CategoriaRepositorio(RepositorioBase[Categoria]):
        tabla = "categoria"
        entidad = Categoria

    repo = CategoriaRepositorio()
    bebidas = repo.guardar(Categoria("Bebidas"))   # INSERT, completa bebidas.id
    bebidas.descripcion = "Con y sin alcohol"
    repo.guardar(bebidas)                           # UPDATE
    repo.listar()

Por defecto, cada campo del dataclass se guarda en la columna del mismo nombre.
Si la tabla y la clase no coinciden (por ejemplo, una columna `categoria_id`
para un atributo `categoria: Categoria`), se redefinen `_a_entidad` y `_a_fila`.
"""

import sqlite3
from dataclasses import fields
from typing import Any, Generic, TypeVar

from src.excepciones import (
    EntidadDuplicadaError,
    EntidadEnUsoError,
    EntidadNoEncontradaError,
    ValidacionError,
)
from src.persistencia.conexion import BaseDeDatos

T = TypeVar("T")


class RepositorioBase(Generic[T]):
    tabla: str
    """Nombre de la tabla en la base."""

    entidad: type
    """Dataclass que representa una fila. Debe tener un atributo `id`."""

    campo_activo: str | None = None
    """Si se indica (por ejemplo "activo"), `eliminar` hace una baja lógica y
    `listar` no devuelve los registros dados de baja."""

    orden: str = "id"
    """Columna por la que se ordena `listar`."""

    def __init__(self, db: BaseDeDatos | None = None) -> None:
        self.db = db or BaseDeDatos()
        self._columnas_tabla: set[str] | None = None

    # --- Conversión fila <-> objeto (redefinir si hace falta) ----------------

    def _a_entidad(self, fila: sqlite3.Row) -> T:
        columnas = fila.keys()
        datos = {campo.name: fila[campo.name] for campo in fields(self.entidad) if campo.name in columnas}
        return self.entidad(**datos)

    def _a_fila(self, entidad: T) -> dict[str, Any]:
        """Columnas a guardar (sin el id)."""
        return {campo.name: getattr(entidad, campo.name) for campo in fields(self.entidad) if campo.name != "id"}

    # --- Lectura -----------------------------------------------------------------

    def obtener_por_id(self, id_: int) -> T | None:
        fila = self.db.consultar_uno(f"SELECT * FROM {self.tabla} WHERE id = ?", (id_,))
        return self._a_entidad(fila) if fila else None

    def obtener(self, id_: int) -> T:
        """Como `obtener_por_id`, pero lanza un error si no existe."""
        entidad = self.obtener_por_id(id_)
        if entidad is None:
            raise EntidadNoEncontradaError(f"No existe un registro de {self.tabla} con id {id_}.")
        return entidad

    def listar(self, incluir_inactivos: bool = False) -> list[T]:
        sql = f"SELECT * FROM {self.tabla}"
        if self.campo_activo and not incluir_inactivos:
            sql += f" WHERE {self.campo_activo} = 1"
        sql += f" ORDER BY {self.orden}"
        return [self._a_entidad(fila) for fila in self.db.consultar(sql)]

    def buscar_por(self, **filtros: Any) -> list[T]:
        """Busca por igualdad de columnas: `repo.buscar_por(categoria_id=3, activo=True)`.

        Un valor None busca los registros con esa columna vacía (IS NULL).
        """
        where, parametros = self._armar_where(filtros)
        filas = self.db.consultar(f"SELECT * FROM {self.tabla}{where} ORDER BY {self.orden}", parametros)
        return [self._a_entidad(fila) for fila in filas]

    def buscar_uno_por(self, **filtros: Any) -> T | None:
        resultados = self.buscar_por(**filtros)
        return resultados[0] if resultados else None

    def existe(self, excluir_id: int | None = None, **filtros: Any) -> bool:
        """¿Hay algún registro con esos valores? Sirve para validar duplicados.

        `excluir_id` deja afuera al propio registro cuando se está modificando:
            repo.existe(sku="ABC-1", excluir_id=producto.id)
        """
        where, parametros = self._armar_where(filtros)
        if excluir_id is not None:
            where += " AND id <> ?" if where else " WHERE id <> ?"
            parametros.append(excluir_id)
        return self.db.consultar_uno(f"SELECT 1 FROM {self.tabla}{where} LIMIT 1", parametros) is not None

    # --- Escritura ---------------------------------------------------------------

    def guardar(self, entidad: T) -> T:
        """Inserta si la entidad no tiene id; si lo tiene, la actualiza. Devuelve la misma entidad."""
        datos = self._a_fila(entidad)
        try:
            if getattr(entidad, "id", None) is None:
                columnas = ", ".join(datos)
                marcadores = ", ".join("?" for _ in datos)
                cursor = self.db.ejecutar(
                    f"INSERT INTO {self.tabla} ({columnas}) VALUES ({marcadores})", list(datos.values())
                )
                entidad.id = cursor.lastrowid
            else:
                asignaciones = ", ".join(f"{columna} = ?" for columna in datos)
                cursor = self.db.ejecutar(
                    f"UPDATE {self.tabla} SET {asignaciones} WHERE id = ?", [*datos.values(), entidad.id]
                )
                if cursor.rowcount == 0:
                    raise EntidadNoEncontradaError(f"No existe un registro de {self.tabla} con id {entidad.id}.")
        except sqlite3.IntegrityError as error:
            raise self._traducir_error(error) from error
        return entidad

    def eliminar(self, id_: int) -> None:
        """Baja lógica si la tabla tiene `campo_activo`; si no, borra la fila."""
        try:
            if self.campo_activo:
                cursor = self.db.ejecutar(f"UPDATE {self.tabla} SET {self.campo_activo} = 0 WHERE id = ?", (id_,))
            else:
                cursor = self.db.ejecutar(f"DELETE FROM {self.tabla} WHERE id = ?", (id_,))
        except sqlite3.IntegrityError as error:
            raise self._traducir_error(error) from error
        if cursor.rowcount == 0:
            raise EntidadNoEncontradaError(f"No existe un registro de {self.tabla} con id {id_}.")

    # --- Auxiliares ----------------------------------------------------------------

    def _armar_where(self, filtros: dict[str, Any]) -> tuple[str, list[Any]]:
        if not filtros:
            return "", []
        columnas_validas = self._columnas()
        for columna in filtros:
            if columna not in columnas_validas:
                raise ValueError(f"La tabla {self.tabla} no tiene la columna '{columna}'.")
        # `columna = NULL` nunca es verdadero en SQL: para buscar vacíos se usa IS NULL.
        condiciones = [
            f"{columna} IS NULL" if valor is None else f"{columna} = ?" for columna, valor in filtros.items()
        ]
        parametros = [valor for valor in filtros.values() if valor is not None]
        return " WHERE " + " AND ".join(condiciones), parametros

    def _columnas(self) -> set[str]:
        if self._columnas_tabla is None:
            filas = self.db.consultar(f"PRAGMA table_info({self.tabla})")
            self._columnas_tabla = {fila["name"] for fila in filas}
        return self._columnas_tabla

    def _traducir_error(self, error: sqlite3.IntegrityError) -> Exception:
        mensaje = str(error)
        if mensaje.startswith("UNIQUE constraint failed"):
            columnas = ", ".join(
                columna.split(".")[-1] for columna in mensaje.split(":", 1)[1].split(",")
            )
            return EntidadDuplicadaError(f"Ya existe un registro de {self.tabla} con el mismo valor de: {columnas}.")
        if mensaje.startswith("FOREIGN KEY constraint failed"):
            return EntidadEnUsoError(
                f"No se puede completar la operación sobre {self.tabla}: "
                "hay registros relacionados o el registro referenciado no existe."
            )
        return ValidacionError(f"Datos inválidos para {self.tabla}: {mensaje}")
