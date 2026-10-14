"""Componentes de interfaz reutilizables por todas las pantallas."""

import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from tkinter import messagebox, ttk
from typing import Any

from src.excepciones import ErrorDeNegocio

# --- Mensajes ---------------------------------------------------------------------


def mostrar_info(mensaje: str, titulo: str = "Información", padre: tk.Misc | None = None) -> None:
    messagebox.showinfo(titulo, mensaje, parent=padre)


def mostrar_error(mensaje: str, titulo: str = "Error", padre: tk.Misc | None = None) -> None:
    messagebox.showerror(titulo, mensaje, parent=padre)


def confirmar(mensaje: str, titulo: str = "Confirmar", padre: tk.Misc | None = None) -> bool:
    return messagebox.askyesno(titulo, mensaje, parent=padre)


def ejecutar_con_manejo_de_errores(accion: Callable[[], Any], padre: tk.Misc | None = None) -> Any:
    """Ejecuta `accion` y, si lanza un ErrorDeNegocio, lo muestra en un cuadro de error.

    Pensado para los botones: `command=lambda: ejecutar_con_manejo_de_errores(self.guardar, self)`.
    Devuelve el resultado de la acción, o None si falló.
    """
    try:
        return accion()
    except ErrorDeNegocio as error:
        mostrar_error(str(error), padre=padre)
        return None


# --- Grilla -------------------------------------------------------------------------


class Grilla(ttk.Frame):
    """Tabla con barra de desplazamiento para listar registros.

        grilla = Grilla(frame, [("sku", "SKU", 100), ("nombre", "Nombre", 250)])
        grilla.cargar(productos, lambda p: (p.sku, p.nombre), clave=lambda p: p.id)
        id_elegido = grilla.seleccionado()
    """

    def __init__(self, padre: tk.Misc, columnas: Sequence[tuple[str, str, int]], alto: int = 12) -> None:
        super().__init__(padre)
        self._tabla = ttk.Treeview(
            self, columns=[c[0] for c in columnas], show="headings", height=alto, selectmode="browse"
        )
        for nombre, titulo, ancho in columnas:
            self._tabla.heading(nombre, text=titulo)
            self._tabla.column(nombre, width=ancho, anchor="w")
        barra = ttk.Scrollbar(self, orient="vertical", command=self._tabla.yview)
        self._tabla.configure(yscrollcommand=barra.set)
        self._tabla.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._tabla.tag_configure("atenuado", foreground="gray50")

    def cargar(
        self,
        registros: Iterable[Any],
        valores: Callable[[Any], Sequence[Any]],
        clave: Callable[[Any], Any] = lambda registro: registro.id,
        atenuar: Callable[[Any], bool] | None = None,
    ) -> None:
        """Reemplaza el contenido. `valores` arma la fila; `clave` identifica cada registro.

        `atenuar` (opcional) indica qué filas se muestran en gris, por ejemplo las dadas de baja.
        """
        self._tabla.delete(*self._tabla.get_children())
        for registro in registros:
            etiquetas = ("atenuado",) if atenuar is not None and atenuar(registro) else ()
            self._tabla.insert(
                "", "end", iid=str(clave(registro)), values=list(valores(registro)), tags=etiquetas
            )

    def seleccionar(self, clave: Any) -> None:
        """Selecciona y muestra la fila con esa clave, si existe."""
        if self._tabla.exists(str(clave)):
            self._tabla.selection_set(str(clave))
            self._tabla.see(str(clave))

    def deseleccionar(self) -> None:
        self._tabla.selection_remove(*self._tabla.selection())

    def seleccionado(self) -> str | None:
        """Clave del registro elegido (como texto), o None si no hay selección."""
        seleccion = self._tabla.selection()
        return seleccion[0] if seleccion else None

    def al_seleccionar(self, funcion: Callable[[str], None]) -> None:
        """Llama a `funcion(clave)` cada vez que el usuario elige una fila."""
        def manejar(_evento: tk.Event) -> None:
            clave = self.seleccionado()
            if clave is not None:
                funcion(clave)

        self._tabla.bind("<<TreeviewSelect>>", manejar)


# --- Formulario -------------------------------------------------------------------------


class Formulario(ttk.Frame):
    """Grupo de campos etiqueta + entrada, para los ABM.

        form = Formulario(frame, [("sku", "SKU"), ("nombre", "Nombre"), ("precio", "Precio")])
        form.cargar({"sku": "A-1", "nombre": "Yerba"})
        datos = form.valores()        # {"sku": "A-1", "nombre": "Yerba", "precio": ""}
        form.limpiar()

    Para un campo con opciones fijas, pasar la lista como tercer elemento:
        ("tipo", "Tipo", ["SUCURSAL", "CD"])
    """

    def __init__(self, padre: tk.Misc, campos: Sequence[tuple], ancho: int = 32) -> None:
        super().__init__(padre)
        self._variables: dict[str, tk.StringVar] = {}
        self._entradas: dict[str, ttk.Entry] = {}
        for fila, campo in enumerate(campos):
            nombre, etiqueta, *opciones = campo
            variable = tk.StringVar()
            ttk.Label(self, text=f"{etiqueta}:").grid(row=fila, column=0, sticky="w", padx=(0, 8), pady=2)
            if opciones:
                entrada = ttk.Combobox(
                    self, textvariable=variable, values=list(opciones[0]), state="readonly", width=ancho - 3
                )
            else:
                entrada = ttk.Entry(self, textvariable=variable, width=ancho)
            entrada.grid(row=fila, column=1, sticky="ew", pady=2)
            self._variables[nombre] = variable
            self._entradas[nombre] = entrada
        self.columnconfigure(1, weight=1)

    def valores(self) -> dict[str, str]:
        return {nombre: variable.get().strip() for nombre, variable in self._variables.items()}

    def cargar(self, datos: dict[str, Any]) -> None:
        for nombre, valor in datos.items():
            if nombre in self._variables:
                self._variables[nombre].set("" if valor is None else str(valor))

    def limpiar(self) -> None:
        for variable in self._variables.values():
            variable.set("")

    def actualizar_opciones(self, nombre: str, opciones: Sequence[str]) -> None:
        """Cambia la lista de un campo con opciones (por ejemplo, al agregar una categoría)."""
        self._entradas[nombre].configure(values=list(opciones))

    def habilitar(self, nombre: str, habilitado: bool = True) -> None:
        """Habilita o deshabilita un campo. Al deshabilitarlo se borra su valor."""
        entrada = self._entradas[nombre]
        if isinstance(entrada, ttk.Combobox):
            entrada.configure(state="readonly" if habilitado else "disabled")
        else:
            entrada.configure(state="normal" if habilitado else "disabled")
        if not habilitado:
            self._variables[nombre].set("")

    def al_cambiar(self, nombre: str, funcion: Callable[[str], None]) -> None:
        """Llama a `funcion(valor)` cada vez que cambia el valor de un campo."""
        variable = self._variables[nombre]
        variable.trace_add("write", lambda *_: funcion(variable.get()))
