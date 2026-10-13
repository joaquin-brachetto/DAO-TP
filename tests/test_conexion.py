import sqlite3
from datetime import date, datetime
from decimal import Decimal

from src.persistencia.conexion import BaseDeDatos
from tests.utilidades import TestConBaseEnMemoria


class TestSingleton(TestConBaseEnMemoria):
    def test_siempre_devuelve_la_misma_instancia(self):
        self.assertIs(BaseDeDatos(), self.db)
        self.assertIs(BaseDeDatos(":memory:"), self.db)

    def test_no_permite_abrir_otra_base_en_paralelo(self):
        with self.assertRaises(RuntimeError):
            BaseDeDatos("otra.db")

    def test_reiniciar_crea_una_instancia_nueva(self):
        BaseDeDatos.reiniciar()
        self.assertIsNot(BaseDeDatos(":memory:"), self.db)


class TestTransacciones(TestConBaseEnMemoria):
    def _cantidad_categorias(self) -> int:
        return self.db.consultar_uno("SELECT COUNT(*) AS n FROM categoria")["n"]

    def test_si_algo_falla_se_deshace_todo(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaccion():
                self.db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Bebidas')")
                self.db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Bebidas')")  # duplicada
        self.assertEqual(self._cantidad_categorias(), 0)

    def test_las_transacciones_anidadas_confirman_al_final(self):
        with self.db.transaccion():
            self.db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Bebidas')")
            with self.db.transaccion():
                self.db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Almacén')")
            self.assertTrue(self.db._conexion.in_transaction)
        self.assertFalse(self.db._conexion.in_transaction)
        self.assertEqual(self._cantidad_categorias(), 2)

    def test_un_error_interno_deshace_tambien_lo_externo(self):
        with self.assertRaises(ValueError):
            with self.db.transaccion():
                self.db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Bebidas')")
                with self.db.transaccion():
                    raise ValueError("falla adentro")
        self.assertEqual(self._cantidad_categorias(), 0)


class TestConversionDeTipos(TestConBaseEnMemoria):
    def setUp(self):
        super().setUp()
        self.db.ejecutar(
            "CREATE TABLE prueba (dinero DECIMAL(12, 2), momento TIMESTAMP, dia DATE, activo BOOLEAN)"
        )

    def test_ida_y_vuelta(self):
        momento = datetime(2026, 10, 13, 18, 30, 5)
        self.db.ejecutar(
            "INSERT INTO prueba VALUES (?, ?, ?, ?)", (Decimal("1234.56"), momento, date(2026, 10, 13), True)
        )
        fila = self.db.consultar_uno("SELECT * FROM prueba")
        self.assertEqual(fila["dinero"], Decimal("1234.56"))
        self.assertIsInstance(fila["dinero"], Decimal)
        self.assertEqual(fila["momento"], momento)
        self.assertEqual(fila["dia"], date(2026, 10, 13))
        self.assertIs(fila["activo"], True)

    def test_falso_se_lee_como_falso(self):
        self.db.ejecutar("INSERT INTO prueba (activo) VALUES (?)", (False,))
        self.assertIs(self.db.consultar_uno("SELECT activo FROM prueba")["activo"], False)

    def test_las_claves_foraneas_estan_activas(self):
        self.assertEqual(self.db.consultar_uno("PRAGMA foreign_keys")[0], 1)
