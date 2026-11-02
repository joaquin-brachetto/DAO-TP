"""Tests de la conexión a SQLite (brache): patrón Singleton, transacciones y conversión de tipos."""

import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.persistencia.conexion import BaseDeDatos


# --- Singleton -------------------------------------------------------------------------------


def test_siempre_devuelve_la_misma_instancia(db):
    assert BaseDeDatos() is db
    assert BaseDeDatos(":memory:") is db


def test_no_permite_abrir_otra_base_en_paralelo(db):
    with pytest.raises(RuntimeError):
        BaseDeDatos("otra.db")


def test_reiniciar_crea_una_instancia_nueva(db):
    BaseDeDatos.reiniciar()
    assert BaseDeDatos(":memory:") is not db


# --- Transacciones ---------------------------------------------------------------------------


def cantidad_categorias(db) -> int:
    return db.consultar_uno("SELECT COUNT(*) AS n FROM categoria")["n"]


def test_si_algo_falla_se_deshace_todo(db):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion():
            db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Bebidas')")
            db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Bebidas')")  # duplicada
    assert cantidad_categorias(db) == 0


def test_las_transacciones_anidadas_confirman_al_final(db):
    with db.transaccion():
        db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Bebidas')")
        with db.transaccion():
            db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Almacén')")
        assert db._conexion.in_transaction
    assert not db._conexion.in_transaction
    assert cantidad_categorias(db) == 2


def test_un_error_interno_deshace_tambien_lo_externo(db):
    with pytest.raises(ValueError):
        with db.transaccion():
            db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Bebidas')")
            with db.transaccion():
                raise ValueError("falla adentro")
    assert cantidad_categorias(db) == 0


# --- Conversión de tipos ---------------------------------------------------------------------


@pytest.fixture
def tabla_prueba(db):
    db.ejecutar("CREATE TABLE prueba (dinero DECIMAL(12, 2), momento TIMESTAMP, dia DATE, activo BOOLEAN)")
    return db


def test_ida_y_vuelta(tabla_prueba):
    db = tabla_prueba
    momento = datetime(2026, 10, 13, 18, 30, 5)
    db.ejecutar("INSERT INTO prueba VALUES (?, ?, ?, ?)", (Decimal("1234.56"), momento, date(2026, 10, 13), True))

    fila = db.consultar_uno("SELECT * FROM prueba")

    assert fila["dinero"] == Decimal("1234.56")
    assert isinstance(fila["dinero"], Decimal)
    assert fila["momento"] == momento
    assert fila["dia"] == date(2026, 10, 13)
    assert fila["activo"] is True


def test_falso_se_lee_como_falso(tabla_prueba):
    tabla_prueba.ejecutar("INSERT INTO prueba (activo) VALUES (?)", (False,))
    assert tabla_prueba.consultar_uno("SELECT activo FROM prueba")["activo"] is False


def test_las_claves_foraneas_estan_activas(db):
    assert db.consultar_uno("PRAGMA foreign_keys")[0] == 1
