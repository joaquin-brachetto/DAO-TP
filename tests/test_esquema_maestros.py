"""Tests del esquema de maestros (brache): restricciones de la base, entre ellas V4."""

import sqlite3

import pytest


@pytest.fixture
def base(db):
    db.ejecutar("INSERT INTO categoria (id, nombre) VALUES (1, 'Bebidas')")
    return db


def insertar_producto(db, sku: str, codigo_barras: str | None = None, costo: str = "10") -> None:
    db.ejecutar(
        "INSERT INTO producto (sku, codigo_barras, nombre, categoria_id, costo_actual, precio_venta_actual) "
        "VALUES (?, ?, 'Producto', 1, ?, 20)",
        (sku, codigo_barras, costo),
    )


def insertar_proveedor(db, cuit: str) -> None:
    db.ejecutar("INSERT INTO proveedor (cuit, razon_social) VALUES (?, 'Proveedor SA')", (cuit,))


def test_se_crean_todas_las_tablas_de_maestros(base):
    tablas = {fila["name"] for fila in base.consultar("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"ubicacion", "categoria", "producto", "historial_precio", "proveedor", "producto_proveedor"} <= tablas


def test_inicializar_dos_veces_no_falla(base):
    base.inicializar_esquema()


# --- V4: productos ---------------------------------------------------------------------------


def test_no_permite_sku_duplicado_aunque_cambien_mayusculas(base):
    insertar_producto(base, "ABC-1")
    with pytest.raises(sqlite3.IntegrityError):
        insertar_producto(base, "abc-1")


def test_no_permite_codigo_de_barras_duplicado(base):
    insertar_producto(base, "A", "7790001")
    with pytest.raises(sqlite3.IntegrityError):
        insertar_producto(base, "B", "7790001")


def test_varios_productos_pueden_no_tener_codigo_de_barras(base):
    insertar_producto(base, "A")
    insertar_producto(base, "B")


def test_no_permite_costo_negativo(base):
    with pytest.raises(sqlite3.IntegrityError):
        insertar_producto(base, "A", costo="-1")


def test_producto_exige_categoria_existente(base):
    with pytest.raises(sqlite3.IntegrityError):
        base.ejecutar(
            "INSERT INTO producto (sku, nombre, categoria_id, costo_actual, precio_venta_actual) "
            "VALUES ('X', 'X', 99, 1, 1)"
        )


# --- V4: proveedores -------------------------------------------------------------------------


def test_no_permite_cuit_duplicado(base):
    insertar_proveedor(base, "20123456789")
    with pytest.raises(sqlite3.IntegrityError):
        insertar_proveedor(base, "20123456789")


@pytest.mark.parametrize("cuit_invalido", ["2012345678", "20-12345678-9", "2012345678A"])
def test_cuit_debe_tener_11_digitos(base, cuit_invalido):
    with pytest.raises(sqlite3.IntegrityError):
        insertar_proveedor(base, cuit_invalido)


# --- Ubicaciones -----------------------------------------------------------------------------


def test_tipo_de_ubicacion_valido(base):
    with pytest.raises(sqlite3.IntegrityError):
        base.ejecutar("INSERT INTO ubicacion (tipo, codigo, nombre) VALUES ('DEPOSITO', 'X', 'X')")


def test_el_cd_no_tiene_punto_de_venta(base):
    with pytest.raises(sqlite3.IntegrityError):
        base.ejecutar("INSERT INTO ubicacion (tipo, codigo, nombre, punto_venta) VALUES ('CD', 'CD1', 'Central', 1)")
