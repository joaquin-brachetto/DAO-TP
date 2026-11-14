"""Tests de la API web: las rutas llaman a los servicios y devuelven los errores de negocio como 400."""

import pytest

from src.web.app import crear_app


@pytest.fixture
def cliente(db):
    app = crear_app(db)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def con_datos(cliente):
    """Carga los datos de prueba completos, en el mismo orden que la pantalla de Inicio."""
    for paso in ("maestros", "stock", "logistica"):
        respuesta = cliente.post(f"/api/datos-prueba/{paso}")
        assert respuesta.status_code == 200, respuesta.get_json()
    return cliente


def ids(catalogo, clave, **filtros):
    return [x["id"] for x in catalogo[clave] if all(x[k] == v for k, v in filtros.items())]


def test_pagina_principal_y_catalogo_vacio(cliente):
    assert cliente.get("/").status_code == 200
    catalogo = cliente.get("/api/catalogo").get_json()
    assert catalogo["productos"] == []
    assert catalogo["datos"] == {"maestros": False, "stock": False, "logistica": False}


def test_datos_de_prueba_en_orden(cliente):
    respuesta = cliente.post("/api/datos-prueba/stock")
    assert respuesta.status_code == 400
    assert "Primero" in respuesta.get_json()["error"]


def test_catalogo_con_datos(con_datos):
    catalogo = con_datos.get("/api/catalogo").get_json()
    assert len(catalogo["productos"]) == 23
    assert len(ids(catalogo, "ubicaciones", tipo="CD")) == 1
    assert catalogo["datos"] == {"maestros": True, "stock": True, "logistica": True}


def test_alta_de_producto_con_sku_repetido_responde_400(con_datos):
    catalogo = con_datos.get("/api/catalogo").get_json()
    respuesta = con_datos.post("/api/productos", json={
        "sku": "yer-1k", "nombre": "Otra yerba", "categoria_id": catalogo["categorias"][0]["id"],
        "costo": 100, "precio": 150,
    })
    assert respuesta.status_code == 400
    assert "SKU" in respuesta.get_json()["error"]


def test_alta_de_producto_con_proveedor_y_minimo(con_datos):
    catalogo = con_datos.get("/api/catalogo").get_json()
    sucursal = ids(catalogo, "ubicaciones", tipo="SUCURSAL")[0]
    proveedor = catalogo["proveedores"][0]["id"]
    respuesta = con_datos.post("/api/productos", json={
        "sku": "GAL-200", "nombre": "Galletitas", "categoria_id": catalogo["categorias"][0]["id"],
        "costo": 500, "precio": 850, "proveedores": [proveedor], "minimos": {str(sucursal): 3},
    })
    assert respuesta.status_code == 200
    producto_id = respuesta.get_json()["id"]
    detalle = con_datos.get(f"/api/productos/{producto_id}").get_json()
    assert detalle["minimos"] == {str(sucursal): 3}
    assert len(detalle["historial"]) == 1


def test_baja_y_reactivacion_de_proveedor(con_datos):
    proveedor = con_datos.get("/api/catalogo").get_json()["proveedores"][0]["id"]
    assert con_datos.post(f"/api/proveedores/{proveedor}/baja").status_code == 200
    activos = {p["id"]: p["activo"] for p in con_datos.get("/api/catalogo").get_json()["proveedores"]}
    assert activos[proveedor] is False
    assert con_datos.post(f"/api/proveedores/{proveedor}/reactivar").status_code == 200


@pytest.mark.parametrize("clave", ["r1", "r2", "r3", "r4", "r5", "r6"])
def test_reportes_y_exportacion(con_datos, clave):
    reporte = con_datos.get(f"/api/reportes/{clave}").get_json()
    assert reporte["titulo"].startswith(clave.upper())
    assert reporte["secciones"]
    for formato, tipo in (("pdf", "application/pdf"), ("csv", "text/csv")):
        archivo = con_datos.get(f"/api/reportes/{clave}/exportar?formato={formato}")
        assert archivo.status_code == 200
        assert archivo.mimetype == tipo
        assert "attachment" in archivo.headers["Content-Disposition"]


def test_venta_sin_caja_abierta_responde_400(con_datos):
    catalogo = con_datos.get("/api/catalogo").get_json()
    sucursal = ids(catalogo, "ubicaciones", tipo="SUCURSAL")[0]
    producto = catalogo["productos"][0]
    respuesta = con_datos.post("/api/ventas", json={
        "sucursal_id": sucursal, "vendedor": "Ana", "items": [{"producto_id": producto["id"], "cantidad": 1}],
        "pagos": [{"medio": "EFECTIVO", "monto": producto["precio"]}],
    })
    assert respuesta.status_code == 400
    assert "caja" in respuesta.get_json()["error"].lower()


def test_venta_y_devolucion(con_datos):
    catalogo = con_datos.get("/api/catalogo").get_json()
    sucursal = ids(catalogo, "ubicaciones", tipo="SUCURSAL")[0]
    contexto = con_datos.get(f"/api/ventas/contexto?sucursal={sucursal}").get_json()
    producto = next(p for p in catalogo["productos"] if contexto["disponible"][str(p["id"])] > 0)
    assert con_datos.post("/api/caja/abrir", json={"sucursal_id": sucursal, "saldo_inicial": 1000}).status_code == 200

    venta = con_datos.post("/api/ventas", json={
        "sucursal_id": sucursal, "vendedor": "Ana", "items": [{"producto_id": producto["id"], "cantidad": 2}],
        "pagos": [{"medio": "EFECTIVO", "monto": producto["precio"] * 2}],
    }).get_json()
    assert venta["comprobante"].startswith("Ticket")
    despues = con_datos.get(f"/api/ventas/contexto?sucursal={sucursal}").get_json()
    assert despues["disponible"][str(producto["id"])] == contexto["disponible"][str(producto["id"])] - 2

    renglon = con_datos.get(f"/api/ventas/{venta['venta_id']}/renglones").get_json()[0]
    respuesta = con_datos.post("/api/devoluciones", json={
        "venta_id": venta["venta_id"], "motivo": "Vencido",
        "detalles": [{"detalle_venta_id": renglon["id"], "cantidad": 3}],
    })
    assert respuesta.status_code == 400  # V5: no se puede devolver más de lo vendido
    respuesta = con_datos.post("/api/devoluciones", json={
        "venta_id": venta["venta_id"], "motivo": "Vencido",
        "detalles": [{"detalle_venta_id": renglon["id"], "cantidad": 1}],
    })
    assert respuesta.status_code == 200
    assert len(con_datos.get(f"/api/devoluciones?sucursal={sucursal}").get_json()) == 1


def test_recepcion_del_remito_en_transito(con_datos):
    remito = next(r for r in con_datos.get("/api/logistica").get_json()["remitos"] if r["estado"] == "EN_TRANSITO")
    recepcion = con_datos.post(f"/api/remitos/{remito['id']}/recibir", json={"recibido_por": "Ana"}).get_json()["recepcion_id"]
    primero, *resto = remito["bultos"]
    controles = [(primero, primero["precinto"], True)] + [(b, b["precinto"], False) for b in resto]
    for bulto, leido, integro in controles:
        respuesta = con_datos.post(f"/api/recepciones/{recepcion}/controles",
                                   json={"bulto_id": bulto["id"], "precinto_leido": leido, "integro": integro})
        assert respuesta.status_code == 200
    cierre = con_datos.post(f"/api/recepciones/{recepcion}/cerrar").get_json()
    assert cierre["estado"] in ("Verificado", "Verificado con rechazos")
    historial = con_datos.get(f"/api/bultos/{primero['id']}/historial").get_json()
    assert [h["codigo"] for h in historial][-1] == "VERIFICADO"


def test_necesidad_una_por_una(con_datos):
    catalogo = con_datos.get("/api/catalogo").get_json()
    sucursal = ids(catalogo, "ubicaciones", tipo="SUCURSAL")[0]
    producto = catalogo["productos"][0]["id"]
    necesidad = con_datos.post("/api/necesidades", json={
        "sucursal_id": sucursal, "renglones": [{"producto_id": producto, "cantidad": 4}],
    }).get_json()["id"]
    orden = con_datos.post("/api/necesidades/consolidar", json={"ids": [necesidad]}).get_json()
    detalle = next(o for o in con_datos.get("/api/ordenes").get_json() if o["id"] == orden["id"])
    assert detalle["necesidades"] == [necesidad]
    assert detalle["items"][0]["solicitada"] == 4
