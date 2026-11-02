"""Tests de la carga de datos de prueba de maestros (brache)."""

import pytest

from src.datos_prueba import CLIENTES, PRODUCTOS, UBICACIONES, cargar_datos_de_prueba
from src.excepciones import ValidacionError
from src.persistencia.conexion import BaseDeDatos


def contar(db, tabla: str) -> int:
    return db.consultar_uno(f"SELECT COUNT(*) AS n FROM {tabla}")["n"]


def test_carga_todo_pasando_por_las_validaciones(db):
    cantidades = cargar_datos_de_prueba(db)

    assert contar(db, "ubicacion") == len(UBICACIONES)
    assert contar(db, "producto") == len(PRODUCTOS)
    assert contar(db, "cliente") == len(CLIENTES)
    assert contar(db, "stock_minimo") == cantidades["stock mínimos"]
    assert contar(db, "ubicacion WHERE tipo = 'CD'") == 1
    # cada producto tiene su precio inicial y los que aumentaron tienen dos registros
    assert contar(db, "historial_precio") > len(PRODUCTOS)


def test_no_se_carga_dos_veces(db):
    cargar_datos_de_prueba(db)

    with pytest.raises(ValidacionError):
        cargar_datos_de_prueba(db)
    assert contar(db, "producto") == len(PRODUCTOS)


def test_se_puede_cargar_en_otra_base_en_el_mismo_proceso(db):
    cargar_datos_de_prueba(db)
    BaseDeDatos.reiniciar()
    otra = BaseDeDatos(":memory:")
    otra.inicializar_esquema()

    cargar_datos_de_prueba(otra)

    assert contar(otra, "producto") == len(PRODUCTOS)
