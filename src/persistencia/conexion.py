"""Conexión a la base de datos SQLite.

Patrón **Singleton**: toda la aplicación comparte una única conexión.
Cualquier `BaseDeDatos()` devuelve siempre la misma instancia, así no hace
falta pasar la conexión de un lado a otro.

Uso típico:

    db = BaseDeDatos()
    filas = db.consultar("SELECT * FROM producto WHERE activo = ?", (True,))

    with db.transaccion():          # todo o nada
        db.ejecutar("UPDATE ...")
        db.ejecutar("INSERT ...")
"""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src import config

# --- Conversión de tipos Python <-> SQLite ----------------------------------
# Según el tipo declarado de la columna en el CREATE TABLE:
#   DECIMAL(12,2) -> Decimal   (dinero: nunca usar float)
#   TIMESTAMP     -> datetime
#   DATE          -> date
#   BOOLEAN       -> bool
sqlite3.register_adapter(Decimal, str)
sqlite3.register_adapter(datetime, lambda valor: valor.isoformat(sep=" "))
sqlite3.register_adapter(date, lambda valor: valor.isoformat())
sqlite3.register_converter("DECIMAL", lambda valor: Decimal(valor.decode()))
sqlite3.register_converter("TIMESTAMP", lambda valor: datetime.fromisoformat(valor.decode()))
sqlite3.register_converter("DATE", lambda valor: date.fromisoformat(valor.decode()))
sqlite3.register_converter("BOOLEAN", lambda valor: valor not in (b"0", b""))


class BaseDeDatos:
    """Única conexión a la base de datos de la aplicación (Singleton)."""

    _instancia: "BaseDeDatos | None" = None

    def __new__(cls, ruta: str | Path | None = None) -> "BaseDeDatos":
        if cls._instancia is None:
            instancia = super().__new__(cls)
            instancia._conectar(str(ruta or config.RUTA_BD))
            cls._instancia = instancia
        elif ruta is not None and str(ruta) != cls._instancia.ruta:
            raise RuntimeError(
                f"La base de datos ya está abierta en {cls._instancia.ruta}; "
                "no se puede abrir otra en paralelo."
            )
        return cls._instancia

    def _conectar(self, ruta: str) -> None:
        if ruta != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.ruta = ruta
        self._conexion = sqlite3.connect(ruta, detect_types=sqlite3.PARSE_DECLTYPES)
        self._conexion.row_factory = sqlite3.Row
        self._conexion.execute("PRAGMA foreign_keys = ON")
        self._profundidad_transaccion = 0

    # --- Esquema --------------------------------------------------------------

    def inicializar_esquema(self, carpeta: str | Path | None = None) -> None:
        """Ejecuta todos los `.sql` de la carpeta del esquema, en orden alfabético.

        Los scripts usan `CREATE TABLE IF NOT EXISTS`, así que se puede llamar
        cada vez que arranca la aplicación.
        """
        carpeta = Path(carpeta or config.CARPETA_ESQUEMA)
        for script in sorted(carpeta.glob("*.sql")):
            self._conexion.executescript(script.read_text(encoding="utf-8"))
        self._conexion.commit()

    # --- Transacciones y consultas --------------------------------------------

    @contextmanager
    def transaccion(self):
        """Agrupa varias operaciones: si alguna falla, se deshacen todas.

        Se puede anidar: solo la transacción más externa hace el commit, así un
        servicio puede llamar a varios repositorios dentro de la misma transacción.
        """
        self._profundidad_transaccion += 1
        try:
            yield self
        except BaseException:
            self._profundidad_transaccion -= 1
            if self._profundidad_transaccion == 0:
                self._conexion.rollback()
            raise
        else:
            self._profundidad_transaccion -= 1
            if self._profundidad_transaccion == 0:
                self._conexion.commit()

    def ejecutar(self, sql: str, parametros=()) -> sqlite3.Cursor:
        """Ejecuta un INSERT / UPDATE / DELETE. Si no hay transacción abierta, abre una."""
        with self.transaccion():
            return self._conexion.execute(sql, parametros)

    def consultar(self, sql: str, parametros=()) -> list[sqlite3.Row]:
        """Ejecuta un SELECT y devuelve todas las filas (se accede por nombre: fila["nombre"])."""
        return self._conexion.execute(sql, parametros).fetchall()

    def consultar_uno(self, sql: str, parametros=()) -> sqlite3.Row | None:
        """Ejecuta un SELECT y devuelve la primera fila, o None si no hay resultados."""
        return self._conexion.execute(sql, parametros).fetchone()

    # --- Ciclo de vida ----------------------------------------------------------

    def cerrar(self) -> None:
        self._conexion.close()

    @classmethod
    def reiniciar(cls) -> None:
        """Cierra la conexión y olvida la instancia. Pensado para los tests."""
        if cls._instancia is not None:
            cls._instancia.cerrar()
            cls._instancia = None
