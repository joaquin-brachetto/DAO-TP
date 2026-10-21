"""Ventana principal: menú de navegación hacia las pantallas de cada módulo."""

import tkinter as tk
from tkinter import ttk

from src import config
from src.datos_prueba import cargar_datos_de_prueba
from src.persistencia.conexion import BaseDeDatos
from src.servicios.inventario_app import crear_stock_service, describir_alerta
from src.servicios.observadores_stock import AlertaStock
from src.servicios.ventas_service import VentasService
from src.ui.componentes import confirmar, ejecutar_con_manejo_de_errores, mostrar_info
from src.ui.menu import OPCIONES_MENU, AbrirPantalla


class VentanaPrincipal(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(config.TITULO_APP)
        self.geometry("900x600")
        self.minsize(640, 400)
        # Inventario (pohlsi): un único StockService para toda la aplicación. Las pantallas lo toman
        # como `padre.stock_service`; sus observadores avisan el stock mínimo en la barra de abajo.
        self.db = BaseDeDatos()
        self.stock_service, self.alertas_stock = crear_stock_service(
            self.db, al_alertar=self._avisar_stock_minimo
        )
        self.ventas_service = VentasService(self.db, self.stock_service)
        self._armar_menu()
        self._armar_contenido()

    def _armar_menu(self) -> None:
        barra = tk.Menu(self)

        archivo = tk.Menu(barra, tearoff=False)
        archivo.add_command(label="Cargar datos de prueba", command=self._cargar_datos_de_prueba)
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.destroy)
        barra.add_cascade(label="Archivo", menu=archivo)

        for titulo, opciones in OPCIONES_MENU.items():
            submenu = tk.Menu(barra, tearoff=False)
            for etiqueta, abrir in opciones:
                submenu.add_command(label=etiqueta, command=self._accion(etiqueta, abrir))
            barra.add_cascade(label=titulo, menu=submenu)

        self.config(menu=barra)

    def _accion(self, etiqueta: str, abrir: AbrirPantalla | None):
        if abrir is None:
            return lambda: mostrar_info(f"«{etiqueta}» todavía está en construcción.", "En construcción", self)
        return lambda: abrir(self)

    def _cargar_datos_de_prueba(self) -> None:
        if not confirmar("¿Cargar sucursales, productos, proveedores y clientes de ejemplo?", padre=self):
            return
        cantidades = ejecutar_con_manejo_de_errores(cargar_datos_de_prueba, self)
        if cantidades is not None:
            detalle = "\n".join(f"{cantidad} {tipo}" for tipo, cantidad in cantidades.items())
            mostrar_info(f"Se cargaron los datos de prueba:\n\n{detalle}", "Datos de prueba", self)

    def _armar_contenido(self) -> None:
        contenido = ttk.Frame(self, padding=32)
        contenido.pack(fill="both", expand=True)
        ttk.Label(contenido, text=config.TITULO_APP, font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(
            contenido,
            text="Centro de Distribución y locales. Elegí una opción del menú para empezar.",
        ).pack(anchor="w", pady=(8, 0))

        estado = ttk.Label(self, text=f"Base de datos: {BaseDeDatos().ruta}", relief="sunken", padding=(8, 2))
        estado.pack(side="bottom", fill="x")
        self._aviso_stock = ttk.Label(self, text="", foreground="#d03b3b", padding=(8, 2))
        self._aviso_stock.pack(side="bottom", fill="x")

    def _avisar_stock_minimo(self, alerta: AlertaStock) -> None:
        """Observer de inventario: muestra la última alerta de stock mínimo en la barra de estado."""
        if hasattr(self, "_aviso_stock"):
            self._aviso_stock.configure(text=describir_alerta(alerta))
