"""Fixtures compartidas de pytest.

`db` reemplaza a `TestConBaseEnMemoria` (unittest): cada test arranca con una
base vacía en memoria y el esquema completo creado.
`escenario` carga los maestros mínimos para probar inventario.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.persistencia.conexion import BaseDeDatos


@pytest.fixture
def db():
    BaseDeDatos.reiniciar()
    base = BaseDeDatos(":memory:")
    base.inicializar_esquema()
    yield base
    BaseDeDatos.reiniciar()


@pytest.fixture
def escenario(db):
    """CD, dos sucursales, dos productos (costo $100 y $50) y un proveedor, con sus ids."""
    cd = db.ejecutar("INSERT INTO ubicacion (tipo, codigo, nombre) VALUES ('CD', 'CD1', 'Centro')").lastrowid
    sucursal = db.ejecutar(
        "INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('SUCURSAL', 'S1', 'Local 1', 1)"
    ).lastrowid
    otra_sucursal = db.ejecutar(
        "INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('SUCURSAL', 'S2', 'Local 2', 2)"
    ).lastrowid
    categoria = db.ejecutar("INSERT INTO categoria (nombre) VALUES ('Varios')").lastrowid
    producto = db.ejecutar(
        "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) VALUES (?, ?, ?, ?, ?)",
        ("A-1", "Yerba", categoria, Decimal("100"), Decimal("150")),
    ).lastrowid
    otro_producto = db.ejecutar(
        "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) VALUES (?, ?, ?, ?, ?)",
        ("B-1", "Azúcar", categoria, Decimal("50"), Decimal("80")),
    ).lastrowid
    proveedor = db.ejecutar(
        "INSERT INTO proveedor (cuit, razon_social) VALUES ('30712345678', 'Distribuidora SA')"
    ).lastrowid
    return SimpleNamespace(
        cd=cd, sucursal=sucursal, otra_sucursal=otra_sucursal,
        producto=producto, otro_producto=otro_producto, proveedor=proveedor,
    )


@pytest.fixture
def definir_minimo(db):
    """Devuelve una función para cargar un stock mínimo (lo administra maestros)."""

    def definir(producto_id, ubicacion_id, cantidad):
        db.ejecutar(
            "INSERT INTO stock_minimo (producto_id, ubicacion_id, cantidad_minima) VALUES (?, ?, ?)",
            (producto_id, ubicacion_id, cantidad),
        )

    return definir
