"""Datos de prueba (seed) para usar y mostrar la aplicación.

Carga el Centro de Distribución, tres sucursales, categorías, proveedores,
productos (con historial de precios), sus proveedores, el stock mínimo de cada
producto por ubicación y algunos clientes. Todo pasa por los servicios, así que
se aplican las mismas validaciones que en las pantallas.

Uso:
    python -m src.datos_prueba

También está en el menú Archivo → "Cargar datos de prueba". Solo se carga sobre
una base sin productos; para empezar de cero, borrar `datos/ventas.db`.

El stock y las ventas no se cargan acá: el stock lo maneja inventario (pohlsi)
y sin stock no se puede vender.
"""

import copy
from datetime import datetime, timedelta
from decimal import Decimal

from src.dominio.maestros.modelos import (
    Categoria,
    CentroDistribucion,
    Producto,
    ProductoProveedor,
    Proveedor,
    StockMinimo,
    Sucursal,
)
from src.dominio.ventas.modelos import Cliente, CondicionIva
from src.excepciones import ValidacionError
from src.persistencia.conexion import BaseDeDatos
from src.servicios.maestros_service import (
    CategoriaService,
    ProductoService,
    ProveedorService,
    StockMinimoService,
    UbicacionService,
)
from src.servicios.ventas_service import VentasService

UBICACIONES = [
    CentroDistribucion(codigo="CD-CBA", nombre="Centro de Distribución Córdoba",
                       direccion="Ruta 9 Km 695, Córdoba", telefono="351 400-1000", capacidad_m3=2500),
    Sucursal(codigo="SUC01", nombre="Sucursal Centro", direccion="27 de Abril 250",
             telefono="351 400-1001", punto_venta=1),
    Sucursal(codigo="SUC02", nombre="Sucursal Nueva Córdoba", direccion="Av. Hipólito Yrigoyen 480",
             telefono="351 400-1002", punto_venta=2),
    Sucursal(codigo="SUC03", nombre="Sucursal Cerro de las Rosas", direccion="Av. Rafael Núñez 4100",
             telefono="351 400-1003", punto_venta=3),
]

CATEGORIAS = [
    ("Almacén", "Secos y no perecederos"),
    ("Bebidas", "Con y sin alcohol"),
    ("Lácteos", "Requieren frío"),
    ("Limpieza", "Limpieza del hogar"),
    ("Perfumería", "Higiene personal"),
]

# clave: (CUIT, razón social, email, teléfono)
PROVEEDORES = {
    "mediterranea": ("30715643215", "Distribuidora Mediterránea SA", "ventas@mediterranea.com.ar", "351 455-2000"),
    "bebidas": ("30698745122", "Bebidas del Centro SRL", "pedidos@bebidasdelcentro.com.ar", "351 466-3000"),
    "serranita": ("30710023456", "Lácteos La Serranita SA", "comercial@laserranita.com.ar", "3547 42-1100"),
    "limpieza": ("20334455662", "Pérez Juan Carlos (Limpieza Total)", "limpiezatotal@gmail.com", "351 15 555-0101"),
}

# (SKU, nombre, categoría, unidad, costo, precio, proveedores, mínimo por sucursal)
PRODUCTOS = [
    ("YER-1K", "Yerba mate 1 kg", "Almacén", "UN", "3200", "4590", ["mediterranea"], 12),
    ("ARR-1K", "Arroz largo fino 1 kg", "Almacén", "UN", "1100", "1650", ["mediterranea"], 10),
    ("FID-500", "Fideos spaghetti 500 g", "Almacén", "UN", "850", "1290", ["mediterranea"], 15),
    ("ACE-900", "Aceite de girasol 900 ml", "Almacén", "UN", "2100", "2990", ["mediterranea"], 8),
    ("AZU-1K", "Azúcar 1 kg", "Almacén", "UN", "1050", "1490", ["mediterranea"], 10),
    ("HAR-1K", "Harina 000 1 kg", "Almacén", "UN", "700", "1050", ["mediterranea"], 10),
    ("CAF-250", "Café molido 250 g", "Almacén", "UN", "3900", "5600", ["mediterranea"], 5),
    ("PAN-DUL", "Pan dulce 500 g (liquidación)", "Almacén", "UN", "4200", "3900", ["mediterranea"], 0),
    ("AGU-1500", "Agua mineral 1,5 L", "Bebidas", "UN", "600", "990", ["bebidas"], 24),
    ("GAS-2250", "Gaseosa cola 2,25 L", "Bebidas", "UN", "1900", "2790", ["bebidas"], 18),
    ("JUG-1L", "Jugo de naranja 1 L", "Bebidas", "UN", "1300", "1950", ["bebidas"], 8),
    ("CER-473", "Cerveza rubia lata 473 ml", "Bebidas", "UN", "1150", "1690", ["bebidas"], 24),
    ("VIN-750", "Vino tinto malbec 750 ml", "Bebidas", "UN", "3500", "5200", ["bebidas"], 6),
    ("LEC-1L", "Leche entera 1 L", "Lácteos", "UN", "950", "1390", ["serranita"], 20),
    ("YOG-1K", "Yogur bebible frutilla 1 kg", "Lácteos", "UN", "1600", "2390", ["serranita"], 8),
    ("QUE-CRE", "Queso cremoso", "Lácteos", "KG", "6800", "9500", ["serranita"], 4),
    ("MAN-200", "Manteca 200 g", "Lácteos", "UN", "1700", "2450", ["serranita", "mediterranea"], 6),
    ("DET-750", "Detergente 750 ml", "Limpieza", "UN", "1250", "1890", ["limpieza"], 8),
    ("LAV-1L", "Lavandina 1 L", "Limpieza", "UN", "700", "1090", ["limpieza"], 10),
    ("JAB-3K", "Jabón en polvo 3 kg", "Limpieza", "UN", "5800", "8200", ["limpieza"], 4),
    ("SHA-400", "Shampoo 400 ml", "Perfumería", "UN", "2600", "3790", ["mediterranea"], 5),
    ("PAS-90", "Pasta dental 90 g", "Perfumería", "UN", "1100", "1690", ["mediterranea"], 8),
    ("PAP-4", "Papel higiénico x4", "Perfumería", "UN", "1500", "2190", ["mediterranea", "limpieza"], 10),
]

# Productos que cambiaron de precio hace dos semanas (para que el historial tenga datos).
AUMENTOS = {"YER-1K": ("3450", "4990"), "GAS-2250": ("2050", "2990"), "LEC-1L": ("990", "1450")}

MINIMO_CD_POR_SUCURSAL = 6  # el CD guarda más: 6 veces el mínimo de una sucursal

CLIENTES = [
    ("28456789", "María González", CondicionIva.CONSUMIDOR_FINAL),
    ("30718887778", "Almacén Don Pepe SRL", CondicionIva.RESPONSABLE_INSCRIPTO),
    ("27298765433", "Laura Fernández", CondicionIva.MONOTRIBUTISTA),
]


def _ean13(numero: int) -> str:
    """Código de barras argentino (prefijo 779) con su dígito verificador."""
    base = f"779{numero:09d}"
    suma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(base))
    return base + str((10 - suma % 10) % 10)


class _Reloj:
    """Hora que usa ProductoService para fechar el historial de precios."""

    def __init__(self, momento: datetime) -> None:
        self.momento = momento

    def __call__(self) -> datetime:
        return self.momento


def cargar_datos_de_prueba(db: BaseDeDatos | None = None) -> dict[str, int]:
    """Carga los datos y devuelve cuántos registros se crearon de cada tipo."""
    db = db or BaseDeDatos()
    if db.consultar_uno("SELECT 1 FROM producto LIMIT 1") is not None:
        raise ValidacionError("La base ya tiene productos. Para recargar los datos de prueba, borrá datos/ventas.db.")

    ahora = datetime.now().replace(microsecond=0)
    reloj = _Reloj(ahora - timedelta(days=60))
    ubicaciones = UbicacionService(db)
    productos = ProductoService(db, ahora=reloj)
    minimos = StockMinimoService(db)

    with db.transaccion():
        creadas = [ubicaciones.guardar(u) for u in copy.deepcopy(UBICACIONES)]
        cd = next(u for u in creadas if u.es_centro_distribucion())
        sucursales = [u for u in creadas if not u.es_centro_distribucion()]

        servicio_categorias, servicio_proveedores = CategoriaService(db), ProveedorService(db)
        categorias = {
            nombre: servicio_categorias.guardar(Categoria(nombre, descripcion)).id for nombre, descripcion in CATEGORIAS
        }
        proveedores = {
            clave: servicio_proveedores.guardar(Proveedor(cuit, razon, email=email, telefono=telefono)).id
            for clave, (cuit, razon, email, telefono) in PROVEEDORES.items()
        }

        por_sku: dict[str, Producto] = {}
        for numero, (sku, nombre, categoria, unidad, costo, precio, provs, minimo) in enumerate(PRODUCTOS, start=1):
            producto = productos.guardar(
                Producto(sku, nombre, categorias[categoria], Decimal(costo), Decimal(precio),
                         codigo_barras=_ean13(numero), unidad_medida=unidad)
            )
            por_sku[sku] = producto
            for orden, clave in enumerate(provs):
                productos.asignar_proveedor(
                    ProductoProveedor(producto.id, proveedores[clave], codigo_en_proveedor=f"{clave[:3].upper()}-{numero:03d}",
                                      costo_pactado=Decimal(costo) * (1 + Decimal("0.03") * orden),
                                      plazo_entrega_dias=2 + orden * 3)
                )
            if minimo:
                for sucursal in sucursales:
                    minimos.definir(StockMinimo(producto.id, sucursal.id, minimo))
                minimos.definir(StockMinimo(producto.id, cd.id, minimo * MINIMO_CD_POR_SUCURSAL))

        reloj.momento = ahora - timedelta(days=14)
        for sku, (costo, precio) in AUMENTOS.items():
            producto = por_sku[sku]
            producto.costo_actual, producto.precio_venta_actual = Decimal(costo), Decimal(precio)
            productos.guardar(producto)

        ventas = VentasService(db)
        for documento, nombre, condicion in CLIENTES:
            ventas.registrar_cliente(Cliente(documento, nombre, condicion))

    return {
        "ubicaciones": len(UBICACIONES),
        "categorías": len(CATEGORIAS),
        "proveedores": len(PROVEEDORES),
        "productos": len(PRODUCTOS),
        "stock mínimos": sum(1 for p in PRODUCTOS if p[7]) * len(UBICACIONES),
        "clientes": len(CLIENTES),
    }


def main() -> None:
    db = BaseDeDatos()
    db.inicializar_esquema()
    try:
        cantidades = cargar_datos_de_prueba(db)
    except ValidacionError as error:
        print(error)
        return
    print(f"Datos de prueba cargados en {db.ruta}:")
    for tipo, cantidad in cantidades.items():
        print(f"  {cantidad:>3} {tipo}")


if __name__ == "__main__":
    main()
