"""Ventana principal: menú de navegación hacia las pantallas de cada módulo."""

import tkinter as tk
from tkinter import ttk

from src import config
from src.persistencia.conexion import BaseDeDatos
from src.ui.componentes import mostrar_info
from src.ui.menu import OPCIONES_MENU, AbrirPantalla


class VentanaPrincipal(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(config.TITULO_APP)
        self.geometry("900x600")
        self.minsize(640, 400)
        self._armar_menu()
        self._armar_contenido()

    def _armar_menu(self) -> None:
        barra = tk.Menu(self)

        archivo = tk.Menu(barra, tearoff=False)
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
