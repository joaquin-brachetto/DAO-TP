"""Gráfico de barras horizontales sobre un Canvas de Tk (sin dependencias externas).

    grafico = GraficoBarras(frame, titulo="Unidades vendidas")
    grafico.dibujar([
        Barra("Yerba 1 kg", 120, "120 u."),
        Barra("Pan dulce", 15, "15 u.", alerta="pérdida"),
    ])

Una sola serie, de un solo color. Las barras en alerta (ej. "en stock mínimo",
"pérdida") van en rojo y siempre con un texto al lado: el color nunca es la
única pista. Cada barra puede tener un marcador vertical (ej. el stock mínimo).
"""

import tkinter as tk
from dataclasses import dataclass

COLOR_SUPERFICIE = "#fcfcfb"
COLOR_BARRA = "#2a78d6"
COLOR_ALERTA = "#d03b3b"
COLOR_MARCADOR = "#0b0b0b"
COLOR_TEXTO = "#0b0b0b"
COLOR_TEXTO_SECUNDARIO = "#52514e"
COLOR_LINEA_BASE = "#c3c2b7"

ALTO_FILA = 26
GROSOR_BARRA = 14
ANCHO_ETIQUETAS = 260
MARGEN = 12


@dataclass(frozen=True)
class Barra:
    etiqueta: str
    valor: float
    texto_valor: str
    marcador: float | None = None
    alerta: str | None = None
    """Si tiene texto, la barra se pinta en rojo y el texto se muestra al lado del valor."""


class GraficoBarras(tk.Canvas):
    def __init__(self, padre: tk.Misc, titulo: str = "", leyenda: str = "", filas_maximas: int = 10) -> None:
        alto = MARGEN * 2 + 22 + ALTO_FILA * filas_maximas + (18 if leyenda else 0)
        super().__init__(padre, height=alto, background=COLOR_SUPERFICIE, highlightthickness=0)
        self.titulo = titulo
        self.leyenda = leyenda
        self._barras: list[Barra] = []
        self.bind("<Configure>", lambda _evento: self._redibujar())

    def dibujar(self, barras: list[Barra]) -> None:
        self._barras = list(barras)
        self._redibujar()

    def _redibujar(self) -> None:
        self.delete("all")
        ancho = max(self.winfo_width(), 400)
        self.create_text(MARGEN, MARGEN, text=self.titulo, anchor="nw", fill=COLOR_TEXTO,
                         font=("TkDefaultFont", 10, "bold"))
        y_inicio = MARGEN + 26
        if not self._barras:
            self.create_text(MARGEN, y_inicio, text="Sin datos para el filtro elegido.", anchor="nw",
                             fill=COLOR_TEXTO_SECUNDARIO)
            return

        maximo = max(max(b.valor, b.marcador or 0) for b in self._barras) or 1
        x0 = MARGEN + ANCHO_ETIQUETAS
        largo_disponible = ancho - x0 - 230  # lugar a la derecha para el valor y la alerta
        escala = largo_disponible / maximo

        for indice, barra in enumerate(self._barras):
            y = y_inicio + indice * ALTO_FILA
            centro = y + ALTO_FILA / 2
            etiqueta = barra.etiqueta if len(barra.etiqueta) <= 38 else barra.etiqueta[:37] + "…"
            self.create_text(x0 - 8, centro, text=etiqueta, anchor="e", fill=COLOR_TEXTO)
            largo = max(barra.valor * escala, 2 if barra.valor > 0 else 0)
            color = COLOR_ALERTA if barra.alerta else COLOR_BARRA
            if largo:
                self.create_rectangle(x0, centro - GROSOR_BARRA / 2, x0 + largo, centro + GROSOR_BARRA / 2,
                                      fill=color, width=0)
            if barra.marcador is not None:
                xm = x0 + barra.marcador * escala
                self.create_line(xm, centro - GROSOR_BARRA / 2 - 3, xm, centro + GROSOR_BARRA / 2 + 3,
                                 fill=COLOR_MARCADOR, width=2)
            fin = x0 + max(largo, (barra.marcador or 0) * escala)
            texto = barra.texto_valor + (f"  ⚠ {barra.alerta}" if barra.alerta else "")
            self.create_text(fin + 8, centro, text=texto, anchor="w", fill=COLOR_TEXTO_SECUNDARIO)

        y_base = y_inicio + len(self._barras) * ALTO_FILA
        self.create_line(x0, y_inicio, x0, y_base, fill=COLOR_LINEA_BASE)
        if self.leyenda:
            self.create_text(MARGEN, y_base + 8, text=self.leyenda, anchor="nw", fill=COLOR_TEXTO_SECUNDARIO)
