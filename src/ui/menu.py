"""Opciones del menú principal.

Cada módulo cuelga sus pantallas acá. Para enchufar una pantalla nueva,
reemplazar el `None` por la función que la abre. Esa función recibe la ventana
principal y abre su propia ventana (`tk.Toplevel`):

    from src.ui.pantallas.productos import abrir_productos
    ...
    ("Productos", abrir_productos),

Mientras quede en `None`, la opción muestra el aviso "En construcción".
Cada integrante toca solo el bloque de su módulo, así no hay conflictos.
"""

from collections.abc import Callable
from tkinter import Misc

from src.ui.pantallas.maestros import abrir_categorias, abrir_productos, abrir_proveedores, abrir_ubicaciones
from src.ui.pantallas.ventas import abrir_caja, abrir_devoluciones, abrir_reporte_ventas, abrir_ventas

AbrirPantalla = Callable[[Misc], None]

OPCIONES_MENU: dict[str, list[tuple[str, AbrirPantalla | None]]] = {
    # --- brache ---
    "Maestros": [
        ("Sucursales y Centro de Distribución", abrir_ubicaciones),
        ("Categorías", abrir_categorias),
        ("Productos y precios", abrir_productos),
        ("Proveedores", abrir_proveedores),
    ],
    # --- pohlsi ---
    "Inventario": [
        ("Stock por ubicación", None),
        ("Compras a proveedores", None),
        ("Necesidades de reposición", None),
        ("Órdenes de reposición", None),
    ],
    # --- turco ---
    "Logística": [
        ("Armado de bultos y remitos", None),
        ("Despacho", None),
        ("Recepción en sucursal", None),
        ("Trazabilidad de bultos", None),
    ],
    # --- vinchi ---
    "Ventas": [
        ("Nueva venta", abrir_ventas),
        ("Devoluciones", abrir_devoluciones),
        ("Caja", abrir_caja),
    ],
    # --- cada uno el suyo ---
    "Reportes": [
        ("Existencias y stock mínimo", None),                 # brache
        ("Productos más vendidos y margen", None),            # brache
        ("Movimientos y valorización del inventario", None),  # pohlsi
        ("Tiempo promedio de tránsito CD → locales", None),   # pohlsi
        ("Bultos rechazados y mermas", None),                 # turco
        ("Ventas por período, local y medio de pago", abrir_reporte_ventas),  # vinchi
    ],
}
