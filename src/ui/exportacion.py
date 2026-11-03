"""Botones «Exportar PDF» y «Exportar CSV» para las pantallas de reportes.

Cada pantalla de reporte agrega los botones con una sola llamada, indicando qué tablas
y qué gráfico exportar:

    agregar_botones_exportar(barra, self, "R3 – Movimientos y valorización",
                             tablas=[("Por tipo", self.grilla_tipos)], grafico=self.grafico,
                             resumen=self.resumen)

Se exporta exactamente lo que se está viendo: las filas cargadas en las grillas, los
filtros de la barra y el texto del resumen. La generación del archivo la hacen los
exportadores de `src/reportes/exportacion.py` (la interfaz solo junta los datos).
"""

import re
import tkinter as tk
from collections.abc import Callable, Sequence
from datetime import datetime
from tkinter import filedialog, ttk
from typing import Any

from src.reportes.exportacion import DocumentoReporte, GraficoReporte, SeccionReporte, exportador_para
from src.ui.componentes import contenido_de_tabla, ejecutar_con_manejo_de_errores, mostrar_error, mostrar_info
from src.ui.graficos import GraficoBarras

# Una tabla a exportar: su título y la Grilla (o el Treeview) que la muestra.
Tabla = tuple[str, Any]


def agregar_botones_exportar(
    barra: tk.Misc,
    ventana: tk.Misc,
    titulo: str,
    tablas: Sequence[Tabla],
    grafico: GraficoBarras | Callable[[], GraficoReporte | None] | None = None,
    resumen: ttk.Label | None = None,
    filtros: tk.Misc | None = None,
) -> None:
    """Agrega los dos botones al final de `barra`.

    `filtros` es el marco con los filtros del reporte (por defecto, la misma `barra`).
    `grafico` puede ser un `GraficoBarras` o una función que devuelva un `GraficoReporte`.
    """

    def armar_documento() -> DocumentoReporte:
        return DocumentoReporte(
            titulo=titulo,
            filtros=describir_filtros(filtros if filtros is not None else barra),
            resumen=str(resumen.cget("text")) if resumen is not None else "",
            secciones=[_seccion(nombre, tabla) for nombre, tabla in tablas],
            grafico=_grafico(grafico),
        )

    def exportar(formato: str) -> None:
        exportador = exportador_para(formato)
        ruta = filedialog.asksaveasfilename(
            parent=ventana,
            title=f"Exportar a {formato}",
            defaultextension=exportador.extension,
            initialfile=f"{_nombre_archivo(titulo)}_{datetime.now():%Y%m%d}{exportador.extension}",
            filetypes=[(f"Archivo {formato}", f"*{exportador.extension}")],
        )
        if not ruta:  # el usuario canceló
            return
        try:
            exportador.exportar(armar_documento(), ruta)
        except OSError as error:  # por ejemplo, el archivo está abierto en otro programa
            mostrar_error(f"No se pudo guardar el archivo:\n{error}", padre=ventana)
            return
        mostrar_info(f"Se exportó el reporte a:\n{ruta}", "Exportación", ventana)

    ttk.Button(barra, text="Exportar PDF",
               command=lambda: ejecutar_con_manejo_de_errores(lambda: exportar("PDF"), ventana)
               ).pack(side="left", padx=(12, 0))
    ttk.Button(barra, text="Exportar CSV",
               command=lambda: ejecutar_con_manejo_de_errores(lambda: exportar("CSV"), ventana)
               ).pack(side="left", padx=(6, 0))


def describir_filtros(marco: tk.Misc) -> str:
    """Arma «Desde: 2026-11-01 · Hasta: 2026-11-30 · Sucursal: Todas» con los controles del marco."""
    partes: list[str] = []
    etiqueta = ""
    for control in marco.winfo_children():
        if isinstance(control, ttk.Button):
            continue
        if isinstance(control, ttk.Label):
            etiqueta = str(control.cget("text")).strip().rstrip(":")
        elif isinstance(control, ttk.Checkbutton):
            if control.instate(["selected"]):
                partes.append(str(control.cget("text")))
            etiqueta = ""
        elif isinstance(control, ttk.Entry):  # incluye ttk.Combobox, que hereda de Entry
            valor = control.get().strip()
            if valor:
                partes.append(f"{etiqueta}: {valor}" if etiqueta else valor)
            etiqueta = ""
    return " · ".join(partes)


def _seccion(nombre: str, tabla) -> SeccionReporte:
    titulos, filas = tabla.contenido() if hasattr(tabla, "contenido") else contenido_de_tabla(tabla)
    return SeccionReporte(nombre, titulos, filas)


def _grafico(grafico) -> GraficoReporte | None:
    if grafico is None:
        return None
    if isinstance(grafico, GraficoBarras):
        barras = grafico.barras()
        return GraficoReporte(
            titulo=grafico.titulo,
            etiquetas=[barra.etiqueta for barra in barras],
            valores=[float(barra.valor) for barra in barras],
            alertas=[bool(barra.alerta) for barra in barras],
        )
    return grafico()


def _nombre_archivo(titulo: str) -> str:
    """«R3 – Movimientos y valorización» → «R3_Movimientos_y_valorizacion»."""
    sin_acentos = titulo.translate(str.maketrans("áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN"))
    return re.sub(r"[^A-Za-z0-9]+", "_", sin_acentos).strip("_")
