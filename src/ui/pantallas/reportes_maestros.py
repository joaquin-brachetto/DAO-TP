"""Pantallas de los reportes de brache: R1 (existencias y stock mínimo) y R2 (más vendidos y margen)."""

import tkinter as tk
from datetime import date
from tkinter import ttk

from src.excepciones import ValidacionError
from src.reportes.existencias_reporte import ReporteExistencias, ResumenExistencias
from src.reportes.productos_reporte import ReporteProductosVendidos, ResumenProductosVendidos
from src.servicios.maestros_service import CategoriaService, UbicacionService
from src.ui.abm import formato_dinero, formato_porcentaje
from src.ui.componentes import Grilla, ejecutar_con_manejo_de_errores
from src.ui.graficos import Barra, GraficoBarras

TODAS = "Todas"


def _a_fecha(texto: str, campo: str) -> date:
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        raise ValidacionError(f"«{campo}» debe tener el formato AAAA-MM-DD (ej. 2026-10-01).") from None


class _FiltrosComunes:
    """Combos de ubicación y categoría con la opción "Todas"."""

    def _armar_combos(self, barra: ttk.Frame, solo_sucursales: bool) -> None:
        servicio = UbicacionService()
        ubicaciones = servicio.listar_sucursales() if solo_sucursales else servicio.listar()
        self._ubicaciones = {TODAS: None} | {u.nombre: u.id for u in ubicaciones}
        self._categorias = {TODAS: None} | {c.nombre: c.id for c in CategoriaService().listar()}
        self.ubicacion = tk.StringVar(value=TODAS)
        self.categoria = tk.StringVar(value=TODAS)
        etiqueta = "Sucursal:" if solo_sucursales else "Ubicación:"
        ttk.Label(barra, text=etiqueta).pack(side="left")
        ttk.Combobox(barra, textvariable=self.ubicacion, values=list(self._ubicaciones), state="readonly",
                     width=28).pack(side="left", padx=(4, 12))
        ttk.Label(barra, text="Categoría:").pack(side="left")
        ttk.Combobox(barra, textvariable=self.categoria, values=list(self._categorias), state="readonly",
                     width=16).pack(side="left", padx=(4, 12))


# --- R1 ------------------------------------------------------------------------------------------------


class PantallaExistencias(tk.Toplevel, _FiltrosComunes):
    """R1: stock disponible por ubicación comparado con el stock mínimo."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("R1 – Existencias actuales y stock mínimo")
        self.geometry("1100x720")
        stock_service = getattr(padre, "stock_service", None)
        self.reporte = ReporteExistencias(stock_service) if stock_service is not None else None

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        barra = ttk.Frame(marco)
        barra.pack(fill="x")
        self._armar_combos(barra, solo_sucursales=False)
        self.solo_minimo = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra, text="Solo en stock mínimo", variable=self.solo_minimo).pack(side="left")
        self.boton = ttk.Button(barra, text="Consultar", command=self._consultar)
        self.boton.pack(side="left", padx=12)

        self.resumen = ttk.Label(marco, text="", font=("TkDefaultFont", 10, "bold"))
        self.resumen.pack(anchor="w", pady=(10, 4))
        self.grilla = Grilla(
            marco,
            [("ubicacion", "Ubicación", 228), ("sku", "SKU", 75), ("producto", "Producto", 185),
             ("categoria", "Categoría", 90), ("disponible", "Disponible", 80), ("minimo", "Mínimo", 62),
             ("faltante", "Faltante", 62), ("valorizado", "Valorizado (costo)", 135), ("estado", "Estado", 140)],
            alto=10,
        )
        self.grilla.pack(fill="both", expand=True)
        self.grafico = GraficoBarras(
            marco,
            titulo="Productos más cerca de su stock mínimo (disponible vs. mínimo)",
            leyenda="Barra: stock disponible   ·   Línea negra: stock mínimo   ·   Rojo con ⚠: en stock mínimo",
        )
        self.grafico.pack(fill="x", pady=(10, 0))

        if self.reporte is None:
            self.boton.configure(state="disabled")
            self.resumen.configure(
                text="⚠ Este reporte necesita el StockService de inventario (pohlsi), que todavía no está "
                "integrado en la aplicación.",
                foreground="#d03b3b",
            )
        else:
            self._consultar()

    def _consultar(self) -> None:
        resumen = ejecutar_con_manejo_de_errores(
            lambda: self.reporte.consultar(
                self._ubicaciones[self.ubicacion.get()], self._categorias[self.categoria.get()], self.solo_minimo.get()
            ),
            self,
        )
        if resumen is not None:
            self._mostrar(resumen)

    def _mostrar(self, resumen: ResumenExistencias) -> None:
        self.resumen.configure(
            text=f"{len(resumen.filas)} filas   ·   {resumen.cantidad_en_minimo} en stock mínimo   ·   "
            f"{resumen.total_unidades} unidades disponibles   ·   Valorizado: {formato_dinero(resumen.total_valorizado)}"
        )
        self.grilla.cargar(
            resumen.filas,
            lambda f: (f.ubicacion, f.sku, f.producto, f.categoria, f.disponible, f.minimo or "",
                       f.faltante or "", formato_dinero(f.valorizado), "⚠ En stock mínimo" if f.en_minimo else "OK"),
            clave=lambda f: f"{f.ubicacion_id}-{f.producto_id}",
        )
        self.grafico.dibujar([
            Barra(f"{f.producto} ({f.codigo_ubicacion})", f.disponible, f"{f.disponible} / mín. {f.minimo}",
                  marcador=f.minimo, alerta="en mínimo" if f.en_minimo else None)
            for f in resumen.menor_cobertura(10)
        ])


# --- R2 ------------------------------------------------------------------------------------------------


class PantallaProductosVendidos(tk.Toplevel, _FiltrosComunes):
    """R2: ranking de productos por unidades vendidas, con su margen estimado."""

    TOP = 10

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("R2 – Productos más vendidos y margen")
        self.geometry("1100x720")
        self.reporte = ReporteProductosVendidos()

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        barra = ttk.Frame(marco)
        barra.pack(fill="x")
        hoy = date.today()
        self.desde = tk.StringVar(value=hoy.replace(day=1).isoformat())
        self.hasta = tk.StringVar(value=hoy.isoformat())
        ttk.Label(barra, text="Desde:").pack(side="left")
        ttk.Entry(barra, textvariable=self.desde, width=11).pack(side="left", padx=(4, 12))
        ttk.Label(barra, text="Hasta:").pack(side="left")
        ttk.Entry(barra, textvariable=self.hasta, width=11).pack(side="left", padx=(4, 12))
        self._armar_combos(barra, solo_sucursales=True)
        ttk.Button(barra, text="Consultar", command=self._consultar).pack(side="left")

        self.resumen = ttk.Label(marco, text="", font=("TkDefaultFont", 10, "bold"))
        self.resumen.pack(anchor="w", pady=(10, 4))
        self.grilla = Grilla(
            marco,
            [("puesto", "#", 40), ("sku", "SKU", 80), ("producto", "Producto", 230), ("categoria", "Categoría", 100),
             ("unidades", "Unidades", 80), ("ingresos", "Ingresos", 120), ("costo", "Costo", 120),
             ("margen", "Margen", 120), ("porcentaje", "Margen %", 80)],
            alto=10,
        )
        self.grilla.pack(fill="both", expand=True)
        self.grafico = GraficoBarras(
            marco,
            titulo=f"Top {self.TOP}: unidades vendidas",
            leyenda="Rojo con ⚠: producto vendido a pérdida (margen negativo)",
        )
        self.grafico.pack(fill="x", pady=(10, 0))
        self._consultar()

    def _consultar(self) -> None:
        def consultar() -> ResumenProductosVendidos:
            return self.reporte.consultar(
                _a_fecha(self.desde.get(), "Desde"),
                _a_fecha(self.hasta.get(), "Hasta"),
                self._ubicaciones[self.ubicacion.get()],
                self._categorias[self.categoria.get()],
            )

        resumen = ejecutar_con_manejo_de_errores(consultar, self)
        if resumen is not None:
            self._mostrar(resumen)

    def _mostrar(self, resumen: ResumenProductosVendidos) -> None:
        self.resumen.configure(
            text=f"{len(resumen.filas)} productos vendidos   ·   {resumen.total_unidades} unidades   ·   "
            f"Ingresos: {formato_dinero(resumen.total_ingresos)}   ·   Margen: {formato_dinero(resumen.total_margen)}"
            f" ({formato_porcentaje(resumen.margen_porcentual) or '—'})"
        )
        self.grilla.cargar(
            enumerate(resumen.filas, start=1),
            lambda par: (par[0], par[1].sku, par[1].producto, par[1].categoria, par[1].unidades,
                         formato_dinero(par[1].ingresos), formato_dinero(par[1].costo),
                         formato_dinero(par[1].margen), formato_porcentaje(par[1].margen_porcentual)),
            clave=lambda par: par[1].producto_id,
        )
        self.grafico.dibujar([
            Barra(f.producto, f.unidades, f"{f.unidades} u.",
                  alerta="pérdida" if f.es_perdida else None)
            for f in resumen.top(self.TOP)
        ])


def abrir_existencias(padre: tk.Misc) -> None:
    PantallaExistencias(padre)


def abrir_productos_vendidos(padre: tk.Misc) -> None:
    PantallaProductosVendidos(padre)
