"""Pantallas de inventario (pohlsi).

Menú Inventario:  stock por ubicación (con las alertas del Observer), compras a
                  proveedores, necesidades de reposición y órdenes de reposición (P3).
Menú Reportes:    R3 – movimientos y valorización del inventario
                  R4 – tiempo promedio de tránsito CD → locales

Usan los componentes comunes de brache (`Grilla`, `Formulario`, `GraficoBarras`,
`ejecutar_con_manejo_de_errores`) y toman el `StockService` de la ventana principal
(`padre.stock_service`), que es el que tiene suscriptos los observadores.
"""

import tkinter as tk
from datetime import date
from decimal import Decimal
from tkinter import ttk
from typing import Any

from src.datos_prueba_inventario import cargar_stock_de_prueba
from src.dominio.inventario.modelos import (
    EstadoNecesidad,
    EstadoOrdenCompra,
    EstadoOrdenReposicion,
    NecesidadReposicion,
    OrdenCompra,
    OrdenReposicion,
    TipoMovimiento,
    nombre_estado,
)
from src.excepciones import ValidacionError
from src.persistencia.repositorio_inventario import MovimientoStockRepositorio
from src.reportes.inventario_reporte import (
    NOMBRE_TIPO,
    ReporteMovimientos,
    ReporteTransito,
    ResumenMovimientos,
    ResumenTransito,
    formato_duracion,
)
from src.servicios.compras_service import ComprasService
from src.servicios.maestros_service import (
    CategoriaService,
    ProductoService,
    ProveedorService,
    StockMinimoService,
    UbicacionService,
)
from src.servicios.reposicion_service import ReposicionService
from src.servicios.stock_service import StockService
from src.ui.abm import a_decimal, a_entero, formato_dinero
from src.ui.componentes import (
    Formulario,
    Grilla,
    confirmar,
    ejecutar_con_manejo_de_errores,
    mostrar_error,
    mostrar_info,
)
from src.ui.graficos import Barra, GraficoBarras

TODAS = "Todas"
TODOS = "Todos"



# --- Auxiliares ------------------------------------------------------------------------------------


def _stock_service(padre: tk.Misc) -> StockService:
    """El StockService de la ventana principal (con sus observadores); si no hay, uno nuevo."""
    return getattr(padre, "stock_service", None) or StockService()


def _a_fecha(texto: str, campo: str) -> date:
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        raise ValidacionError(f"«{campo}» debe tener el formato AAAA-MM-DD (ej. 2026-10-01).") from None


def _estado(valor: Any) -> str:
    return nombre_estado(valor)


class _Catalogo:
    """Nombres de productos, ubicaciones y proveedores para mostrar en las grillas (lee maestros)."""

    def __init__(self) -> None:
        self.productos = {p.id: p for p in ProductoService().listar(incluir_inactivos=True)}
        self.ubicaciones = {u.id: u for u in UbicacionService().listar(incluir_inactivas=True)}
        self.proveedores = {p.id: p for p in ProveedorService().listar(incluir_inactivos=True)}

    def producto(self, producto_id: int) -> str:
        p = self.productos.get(producto_id)
        return f"{p.sku} – {p.nombre}" if p else f"Producto {producto_id}"

    def ubicacion(self, ubicacion_id: int) -> str:
        u = self.ubicaciones.get(ubicacion_id)
        return f"{u.nombre} ({u.codigo})" if u else f"Ubicación {ubicacion_id}"

    def proveedor(self, proveedor_id: int) -> str:
        p = self.proveedores.get(proveedor_id)
        return p.razon_social if p else f"Proveedor {proveedor_id}"

    def opciones_productos(self, ids: list[int] | None = None) -> dict[str, int]:
        """{"SKU – nombre": id} de los productos activos (o de los ids indicados)."""
        elegidos = [p for p in self.productos.values() if p.activo and (ids is None or p.id in ids)]
        return {self.producto(p.id): p.id for p in sorted(elegidos, key=lambda p: p.nombre)}

    def opciones_ubicaciones(self, solo_sucursales: bool = False) -> dict[str, int]:
        elegidas = [
            u for u in self.ubicaciones.values()
            if u.activa and not (solo_sucursales and u.es_centro_distribucion())
        ]
        elegidas.sort(key=lambda u: (not u.es_centro_distribucion(), u.nombre))  # primero el CD
        return {self.ubicacion(u.id): u.id for u in elegidas}

    def centro_distribucion(self) -> int | None:
        return next((u.id for u in self.ubicaciones.values() if u.activa and u.es_centro_distribucion()), None)


def _combo(barra: tk.Misc, etiqueta: str, variable: tk.StringVar, opciones, ancho: int = 28) -> ttk.Combobox:
    ttk.Label(barra, text=etiqueta).pack(side="left")
    combo = ttk.Combobox(barra, textvariable=variable, values=list(opciones), state="readonly", width=ancho)
    combo.pack(side="left", padx=(4, 12))
    return combo


class _EditorRenglones(ttk.Frame):
    """Producto + cantidad (+ costo opcional) con su grilla de renglones; lo usan compras y necesidades."""

    def __init__(self, padre: tk.Misc, catalogo: _Catalogo, con_costo: bool) -> None:
        super().__init__(padre)
        self.catalogo = catalogo
        self.con_costo = con_costo
        self.renglones: dict[int, tuple[int, Decimal | None]] = {}
        campos: list[tuple] = [("producto", "Producto", []), ("cantidad", "Cantidad")]
        if con_costo:
            campos.append(("costo", "Costo unitario"))
        self.formulario = Formulario(self, campos, ancho=36)
        self.formulario.pack(fill="x")
        botones = ttk.Frame(self)
        botones.pack(fill="x", pady=(6, 4))
        ttk.Button(botones, text="Agregar renglón", command=self._agregar).pack(side="left")
        ttk.Button(botones, text="Quitar renglón", command=self._quitar).pack(side="left", padx=4)
        columnas = [("producto", "Producto", 230), ("cantidad", "Cant.", 55)]
        if con_costo:
            columnas += [("costo", "Costo", 85), ("subtotal", "Subtotal", 95)]
        self.grilla = Grilla(self, columnas, alto=7)
        self.grilla.pack(fill="both", expand=True)
        self.total = ttk.Label(self, text="", font=("TkDefaultFont", 10, "bold"))
        self.total.pack(anchor="e", pady=(4, 0))
        self.opciones: dict[str, int] = {}
        self.cambiar_productos(catalogo.opciones_productos())

    def cambiar_productos(self, opciones: dict[str, int]) -> None:
        self.opciones = opciones
        self.formulario.actualizar_opciones("producto", list(opciones))
        self.formulario.cargar({"producto": ""})

    def _agregar(self) -> None:
        def agregar() -> bool:
            v = self.formulario.valores()
            if v["producto"] not in self.opciones:
                raise ValidacionError("Elegí un producto de la lista.")
            cantidad = a_entero(v["cantidad"], "Cantidad")
            if cantidad <= 0:
                raise ValidacionError("La cantidad debe ser mayor a cero.")
            costo = a_decimal(v["costo"], "Costo unitario") if self.con_costo else None
            if costo is not None and costo < 0:
                raise ValidacionError("El costo no puede ser negativo.")
            producto_id = self.opciones[v["producto"]]
            anterior = self.renglones.get(producto_id, (0, None))[0]
            self.renglones[producto_id] = (anterior + cantidad, costo)
            return True

        if ejecutar_con_manejo_de_errores(agregar, self):
            self.formulario.cargar({"cantidad": "", "costo": ""})
            self.refrescar()

    def _quitar(self) -> None:
        clave = self.grilla.seleccionado()
        if clave is None:
            mostrar_error("Elegí un renglón de la lista.", padre=self)
            return
        self.renglones.pop(int(clave), None)
        self.refrescar()

    def cargar(self, renglones: list[tuple]) -> None:
        """Reemplaza los renglones con una sugerencia: (producto, cantidad) o (producto, cantidad, costo)."""
        self.renglones = {r[0]: (r[1], r[2] if len(r) > 2 else None) for r in renglones}
        self.refrescar()

    def limpiar(self) -> None:
        self.renglones.clear()
        self.formulario.limpiar()
        self.refrescar()

    def refrescar(self) -> None:
        def fila(par):
            producto_id, (cantidad, costo) = par
            valores = [self.catalogo.producto(producto_id), cantidad]
            if self.con_costo:
                valores += [formato_dinero(costo), formato_dinero(costo * cantidad)]
            return valores

        self.grilla.cargar(self.renglones.items(), fila, clave=lambda par: par[0])
        unidades = sum(c for c, _ in self.renglones.values())
        texto = f"{len(self.renglones)} productos · {unidades} unidades"
        if self.con_costo:
            total = sum((c * (costo or 0) for c, costo in self.renglones.values()), Decimal("0"))
            texto += f" · Total {formato_dinero(total)}"
        self.total.configure(text=texto)

    def con_cantidades(self) -> list[tuple[int, int]]:
        return [(producto_id, cantidad) for producto_id, (cantidad, _) in self.renglones.items()]

    def con_costos(self) -> list[tuple[int, int, Decimal]]:
        return [(producto_id, cantidad, costo) for producto_id, (cantidad, costo) in self.renglones.items()]


# === Stock por ubicación =========================================================================


class PantallaStock(tk.Toplevel):
    """Stock de cada producto en una ubicación (disponible / pendiente / merma) y alertas del Observer."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("Stock por ubicación")
        self.geometry("1150x680")
        self.stock = _stock_service(padre)
        self.alertas = getattr(padre, "alertas_stock", None)
        self.catalogo = _Catalogo()
        self.minimos = StockMinimoService()

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        barra = ttk.Frame(marco)
        barra.pack(fill="x")
        self._ubicaciones = self.catalogo.opciones_ubicaciones()
        self.ubicacion = tk.StringVar(value=next(iter(self._ubicaciones), ""))
        combo = _combo(barra, "Ubicación:", self.ubicacion, self._ubicaciones, ancho=36)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        ttk.Button(barra, text="Actualizar", command=self.refrescar).pack(side="left")
        ttk.Button(barra, text="Ver movimientos del producto", command=self._ver_movimientos).pack(side="left", padx=8)

        ttk.Label(
            marco,
            text="Pendiente: llegó o viene en camino sin verificar (no se puede vender).   "
            "Disponible: verificado, se puede vender.   Merma: rechazado.",
            foreground="gray30",
        ).pack(anchor="w", pady=(8, 4))
        self.resumen = ttk.Label(marco, text="", font=("TkDefaultFont", 10, "bold"))
        self.resumen.pack(anchor="w")
        self.grilla = Grilla(
            marco,
            [("producto", "Producto", 280), ("disponible", "Disponible", 85), ("pendiente", "Pendiente", 85),
             ("merma", "Merma", 70), ("minimo", "Mínimo", 70), ("estado", "Estado", 140),
             ("valorizado", "Disponible valorizado", 150)],
            alto=12,
        )
        self.grilla.pack(fill="both", expand=True, pady=(4, 0))

        alertas = ttk.LabelFrame(marco, text="Alertas de stock mínimo (Observer)", padding=8)
        alertas.pack(fill="x", pady=(10, 0))
        self.grilla_alertas = Grilla(
            alertas,
            [("hora", "Hora", 70), ("ubicacion", "Ubicación", 230), ("producto", "Producto", 260),
             ("disponible", "Disponible", 80), ("minimo", "Mínimo", 70), ("faltante", "Faltante", 70)],
            alto=4,
        )
        self.grilla_alertas.pack(fill="x")
        botones = ttk.Frame(alertas)
        botones.pack(fill="x", pady=(6, 0))
        ttk.Button(botones, text="Descartar alerta", command=self._descartar).pack(side="left")
        ttk.Label(
            botones,
            text="Cuando una venta o un despacho deja un producto en su mínimo, aparece acá y, si es una "
            "sucursal, se crea sola una necesidad de reposición.",
            foreground="gray30",
        ).pack(side="left", padx=8)
        self.refrescar()

    def _ubicacion_id(self) -> int | None:
        return self._ubicaciones.get(self.ubicacion.get())

    def refrescar(self) -> None:
        ubicacion_id = self._ubicacion_id()
        if ubicacion_id is None:
            self.resumen.configure(text="No hay ubicaciones activas. Cargalas desde Maestros.")
            return
        stocks = {s.producto_id: s for s in self.stock.listar_ubicacion(ubicacion_id)}
        minimos = self.minimos.de_ubicacion(ubicacion_id)
        filas = []
        for producto_id in sorted(set(stocks) | set(minimos), key=self.catalogo.producto):
            s = stocks.get(producto_id)
            disponible = s.cantidad_disponible if s else 0
            minimo = minimos.get(producto_id, 0)
            producto = self.catalogo.productos.get(producto_id)
            costo = producto.costo_actual if producto else Decimal("0")
            filas.append({
                "producto_id": producto_id, "disponible": disponible,
                "pendiente": s.cantidad_pendiente if s else 0, "merma": s.cantidad_merma if s else 0,
                "minimo": minimo, "en_minimo": minimo > 0 and disponible <= minimo,
                "valorizado": costo * disponible,
            })
        self.grilla.cargar(
            filas,
            lambda f: (self.catalogo.producto(f["producto_id"]), f["disponible"], f["pendiente"], f["merma"],
                       f["minimo"] or "", "⚠ En stock mínimo" if f["en_minimo"] else "OK",
                       formato_dinero(f["valorizado"])),
            clave=lambda f: f["producto_id"],
        )
        total = sum((f["valorizado"] for f in filas), Decimal("0"))
        self.resumen.configure(
            text=f"{len(filas)} productos · {sum(f['disponible'] for f in filas)} disponibles · "
            f"{sum(f['pendiente'] for f in filas)} pendientes de verificación · "
            f"{sum(1 for f in filas if f['en_minimo'])} en stock mínimo · Valorizado: {formato_dinero(total)}"
        )
        self._refrescar_alertas()

    def _refrescar_alertas(self) -> None:
        lista = self.alertas.alertas() if self.alertas is not None else []
        self.grilla_alertas.cargar(
            lista,
            lambda a: (a.fecha_hora.strftime("%H:%M"), self.catalogo.ubicacion(a.ubicacion_id),
                       self.catalogo.producto(a.producto_id), a.disponible, a.minimo, a.faltante),
            clave=lambda a: f"{a.producto_id}-{a.ubicacion_id}",
        )

    def _descartar(self) -> None:
        clave = self.grilla_alertas.seleccionado()
        if clave is None or self.alertas is None:
            mostrar_error("Elegí una alerta de la lista.", padre=self)
            return
        producto_id, ubicacion_id = (int(x) for x in clave.split("-"))
        self.alertas.descartar(producto_id, ubicacion_id)
        self._refrescar_alertas()

    def _ver_movimientos(self) -> None:
        clave = self.grilla.seleccionado()
        if clave is None:
            mostrar_error("Elegí un producto de la lista.", padre=self)
            return
        VentanaMovimientosProducto(self, self.stock, self.catalogo, self._ubicacion_id(), int(clave))


class VentanaMovimientosProducto(tk.Toplevel):
    """Libro de movimientos (inmutable) de un producto en una ubicación."""

    def __init__(self, padre: tk.Misc, stock: StockService, catalogo: _Catalogo, ubicacion_id: int,
                 producto_id: int) -> None:
        super().__init__(padre)
        self.title(f"Movimientos – {catalogo.producto(producto_id)}")
        self.geometry("900x420")
        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text=f"{catalogo.producto(producto_id)} en {catalogo.ubicacion(ubicacion_id)}",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        grilla = Grilla(
            marco,
            [("fecha", "Fecha y hora", 140), ("tipo", "Movimiento", 230), ("cantidad", "Cantidad", 70),
             ("costo", "Costo unit.", 90), ("documento", "Documento", 140), ("usuario", "Usuario", 110)],
            alto=14,
        )
        grilla.pack(fill="both", expand=True, pady=8)
        registro = stock.stock_de(ubicacion_id, producto_id)
        movimientos = MovimientoStockRepositorio(stock.db).de_stock(registro.id) if registro.id else []
        grilla.cargar(
            movimientos,
            lambda m: (m.fecha_hora.strftime("%Y-%m-%d %H:%M"), NOMBRE_TIPO[m.tipo], m.cantidad,
                       formato_dinero(m.costo_unitario),
                       m.tipo_documento if m.documento_id is None else f"{m.tipo_documento} {m.documento_id}",
                       m.usuario),
        )
        ttk.Label(marco, text="Los movimientos no se pueden modificar ni borrar.", foreground="gray30").pack(anchor="w")


# === Compras a proveedores ==========================================================================


class PantallaCompras(tk.Toplevel):
    """Órdenes de compra al Centro de Distribución: crear, recibir (ingresa stock) y anular."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("Compras a proveedores")
        self.geometry("1250x680")
        self.catalogo = _Catalogo()
        self.servicio = ComprasService(stock_service=_stock_service(padre))
        self.proveedores_servicio = ProveedorService()
        self._ordenes: dict[str, OrdenCompra] = {}

        izquierda = ttk.Frame(self, padding=(12, 12, 6, 12))
        izquierda.pack(side="left", fill="both", expand=True)
        derecha = ttk.LabelFrame(self, text="Nueva orden de compra", padding=12)
        derecha.pack(side="right", fill="y", padx=(6, 12), pady=12)

        barra = ttk.Frame(izquierda)
        barra.pack(fill="x")
        self.filtro = tk.StringVar(value=TODOS)
        combo = _combo(barra, "Estado:", self.filtro, [TODOS] + [_estado(e) for e in EstadoOrdenCompra], ancho=14)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        self.grilla = Grilla(
            izquierda,
            [("numero", "N°", 45), ("fecha", "Fecha", 85), ("proveedor", "Proveedor", 230),
             ("destino", "Destino", 190), ("estado", "Estado", 90), ("total", "Total", 110)],
            alto=10,
        )
        self.grilla.pack(fill="both", expand=True, pady=(8, 0))
        self.grilla.al_seleccionar(self._mostrar_detalle)
        ttk.Label(izquierda, text="Detalle de la orden elegida").pack(anchor="w", pady=(10, 2))
        self.detalle = Grilla(
            izquierda,
            [("producto", "Producto", 300), ("cantidad", "Cantidad", 80), ("costo", "Costo unit.", 100),
             ("subtotal", "Subtotal", 110)],
            alto=6,
        )
        self.detalle.pack(fill="x")
        botones = ttk.Frame(izquierda)
        botones.pack(fill="x", pady=(8, 0))
        ttk.Button(botones, text="Recibir en el CD (ingresa stock)", command=self._recibir).pack(side="left")
        ttk.Button(botones, text="Anular orden", command=self._anular).pack(side="left", padx=6)

        self.cd_id = self.catalogo.centro_distribucion()
        destino = self.catalogo.ubicacion(self.cd_id) if self.cd_id else "— no hay un CD activo —"
        ttk.Label(derecha, text=f"Destino: {destino}", foreground="gray30").pack(anchor="w")
        cabecera = ttk.Frame(derecha)
        cabecera.pack(fill="x", pady=(6, 6))
        self._proveedores = {
            p.razon_social: p.id for p in sorted(self.catalogo.proveedores.values(), key=lambda p: p.razon_social)
            if p.activo
        }
        self.proveedor = tk.StringVar()
        ttk.Label(cabecera, text="Proveedor:").pack(side="left")
        combo = ttk.Combobox(cabecera, textvariable=self.proveedor, values=list(self._proveedores),
                             state="readonly", width=36)
        combo.pack(side="left", padx=(4, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._al_cambiar_proveedor())
        ttk.Button(derecha, text="Sugerir según faltantes del CD", command=self._sugerir).pack(fill="x", pady=(0, 6))
        self.renglones = _EditorRenglones(derecha, self.catalogo, con_costo=True)
        self.renglones.pack(fill="both", expand=True)
        self.renglones.formulario.al_cambiar("producto", self._sugerir_costo)
        self._costos_pactados: dict[int, Decimal] = {}
        ttk.Button(derecha, text="Crear orden de compra", command=self._crear).pack(fill="x", pady=(8, 0))
        self.refrescar()

    # --- Lista y detalle -------------------------------------------------------------------------

    def refrescar(self, seleccionar: int | None = None) -> None:
        estado = next((e for e in EstadoOrdenCompra if _estado(e) == self.filtro.get()), None)
        ordenes = self.servicio.listar(estado)
        self._ordenes = {str(o.id): o for o in ordenes}
        self.grilla.cargar(
            ordenes,
            lambda o: (o.numero, o.fecha_emision.isoformat(), self.catalogo.proveedor(o.proveedor_id),
                       self.catalogo.ubicacion(o.destino_id), _estado(o.estado), formato_dinero(o.total())),
            atenuar=lambda o: o.estado == EstadoOrdenCompra.ANULADA,
        )
        self.detalle.cargar([], lambda d: ())
        if seleccionar is not None:
            self.grilla.seleccionar(seleccionar)
            self._mostrar_detalle(str(seleccionar))

    def _mostrar_detalle(self, clave: str) -> None:
        orden = self._ordenes.get(clave)
        if orden is None:
            return
        self.detalle.cargar(
            orden.detalles,
            lambda d: (self.catalogo.producto(d.producto_id), d.cantidad, formato_dinero(d.costo_unitario),
                       formato_dinero(d.subtotal())),
        )

    def _orden_elegida(self) -> OrdenCompra | None:
        orden = self._ordenes.get(self.grilla.seleccionado() or "")
        if orden is None:
            mostrar_error("Elegí una orden de la lista.", padre=self)
        return orden

    def _recibir(self) -> None:
        orden = self._orden_elegida()
        if orden is None:
            return
        if not confirmar(f"¿Registrar que llegó la orden {orden.numero}? Se suma su mercadería al stock del CD.",
                         padre=self):
            return
        if ejecutar_con_manejo_de_errores(lambda: self.servicio.recibir_orden(orden.id), self):
            self.refrescar(seleccionar=orden.id)
            mostrar_info(f"Orden {orden.numero} recibida: el stock del CD ya está disponible.", "Listo", self)

    def _anular(self) -> None:
        orden = self._orden_elegida()
        if orden is None or not confirmar(f"¿Anular la orden de compra {orden.numero}?", padre=self):
            return
        if ejecutar_con_manejo_de_errores(lambda: self.servicio.anular_orden(orden.id), self):
            self.refrescar(seleccionar=orden.id)

    # --- Nueva orden ---------------------------------------------------------------------------

    def _al_cambiar_proveedor(self) -> None:
        proveedor_id = self._proveedores.get(self.proveedor.get())
        if proveedor_id is None:
            return
        relaciones = self.proveedores_servicio.productos_de(proveedor_id)
        self._costos_pactados = {r.producto_id: r.costo_pactado for r in relaciones if r.costo_pactado is not None}
        ids = [r.producto_id for r in relaciones]
        # Si el proveedor no tiene productos asignados en maestros, se ofrecen todos.
        self.renglones.cambiar_productos(self.catalogo.opciones_productos(ids or None))
        self.renglones.limpiar()

    def _sugerir(self) -> None:
        """Carga en la nueva orden lo que le falta al CD de este proveedor (o del primero que tenga faltantes)."""
        sugerencia = ejecutar_con_manejo_de_errores(self.servicio.sugerir_compras, self)
        if sugerencia is None:
            return
        if sugerencia.vacia():
            mostrar_info("Ningún producto del CD está en su stock mínimo (contando lo ya pedido en órdenes "
                         "pendientes).", "Sin faltantes", self)
            return
        proveedor_id = self._proveedores.get(self.proveedor.get())
        if proveedor_id not in sugerencia.por_proveedor and sugerencia.por_proveedor:
            proveedor_id = next(iter(sugerencia.por_proveedor))
            self.proveedor.set(self.catalogo.proveedor(proveedor_id))
            self._al_cambiar_proveedor()
        if proveedor_id in sugerencia.por_proveedor:
            self.renglones.cargar(sugerencia.por_proveedor[proveedor_id])
        otros = [self.catalogo.proveedor(p) for p in sugerencia.por_proveedor if p != proveedor_id]
        avisos = []
        if otros:
            avisos.append("También hay faltantes para: " + ", ".join(otros) + ". Elegilos y volvé a sugerir.")
        if sugerencia.sin_proveedor:
            nombres = ", ".join(self.catalogo.producto(p) for p, _ in sugerencia.sin_proveedor)
            avisos.append(f"Sin proveedor asignado en maestros (no se pueden comprar): {nombres}.")
        if avisos:
            mostrar_info("\n\n".join(avisos), "Sugerencia de compra", self)

    def _sugerir_costo(self, texto: str) -> None:
        producto_id = self.renglones.opciones.get(texto)
        if producto_id is None:
            return
        producto = self.catalogo.productos[producto_id]
        costo = self._costos_pactados.get(producto_id, producto.costo_actual)
        self.renglones.formulario.cargar({"costo": f"{costo:.2f}"})

    def _crear(self) -> None:
        def crear() -> OrdenCompra:
            if self.proveedor.get() not in self._proveedores:
                raise ValidacionError("Elegí un proveedor.")
            if self.cd_id is None:
                raise ValidacionError("No hay un Centro de Distribución activo para recibir la compra.")
            return self.servicio.crear_orden(self._proveedores[self.proveedor.get()], self.cd_id,
                                             self.renglones.con_costos())

        orden = ejecutar_con_manejo_de_errores(crear, self)
        if orden is not None:
            self.renglones.limpiar()
            self.filtro.set(TODOS)
            self.refrescar(seleccionar=orden.id)
            mostrar_info(f"Se creó la orden de compra {orden.numero} por {formato_dinero(orden.total())}.\n"
                         "Cuando llegue la mercadería, usá «Recibir en el CD».", "Listo", self)


# === Necesidades de reposición =======================================================================


class PantallaNecesidades(tk.Toplevel):
    """Necesidades de cada sucursal (manuales o automáticas) y su consolidación en una orden (P3)."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("Necesidades de reposición")
        self.geometry("1250x680")
        self.catalogo = _Catalogo()
        self.servicio = ReposicionService()
        self._necesidades: dict[str, NecesidadReposicion] = {}
        self._sucursales = self.catalogo.opciones_ubicaciones(solo_sucursales=True)

        izquierda = ttk.Frame(self, padding=(12, 12, 6, 12))
        izquierda.pack(side="left", fill="both", expand=True)
        derecha = ttk.LabelFrame(self, text="Nueva necesidad (manual)", padding=12)
        derecha.pack(side="right", fill="y", padx=(6, 12), pady=12)

        barra = ttk.Frame(izquierda)
        barra.pack(fill="x")
        self.filtro_sucursal = tk.StringVar(value=TODAS)
        self.filtro_estado = tk.StringVar(value=_estado(EstadoNecesidad.PENDIENTE))
        for combo in (
            _combo(barra, "Sucursal:", self.filtro_sucursal, [TODAS] + list(self._sucursales), ancho=30),
            _combo(barra, "Estado:", self.filtro_estado, [TODOS] + [_estado(e) for e in EstadoNecesidad], ancho=12),
        ):
            combo.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        self.grilla = Grilla(
            izquierda,
            [("id", "N°", 45), ("fecha", "Fecha", 85), ("sucursal", "Sucursal", 220), ("origen", "Origen", 95),
             ("estado", "Estado", 95), ("orden", "Orden de rep.", 95), ("contenido", "Contenido", 150)],
            alto=10,
        )
        self.grilla.pack(fill="both", expand=True, pady=(8, 0))
        self.grilla.al_seleccionar(self._mostrar_detalle)
        ttk.Label(izquierda, text="Productos de la necesidad elegida").pack(anchor="w", pady=(10, 2))
        self.detalle = Grilla(izquierda, [("producto", "Producto", 340), ("cantidad", "Cantidad", 90)], alto=6)
        self.detalle.pack(fill="x")
        botones = ttk.Frame(izquierda)
        botones.pack(fill="x", pady=(8, 0))
        ttk.Button(botones, text="Consolidar pendientes de la sucursal en una orden",
                   command=self._consolidar).pack(side="left")
        ttk.Button(botones, text="Anular necesidad", command=self._anular).pack(side="left", padx=6)
        ttk.Label(
            izquierda,
            text="Consolidar junta todas las necesidades pendientes de la sucursal elegida en el filtro en UNA "
            "orden de reposición (origen: CD, destino: la sucursal), sumando las cantidades por producto.",
            foreground="gray30", wraplength=700,
        ).pack(anchor="w", pady=(6, 0))

        cabecera = ttk.Frame(derecha)
        cabecera.pack(fill="x", pady=(0, 6))
        self.sucursal = tk.StringVar()
        ttk.Label(cabecera, text="Sucursal:").pack(side="left")
        ttk.Combobox(cabecera, textvariable=self.sucursal, values=list(self._sucursales), state="readonly",
                     width=34).pack(side="left", padx=(4, 0))
        ttk.Button(derecha, text="Sugerir según stock mínimo", command=self._sugerir).pack(fill="x", pady=(0, 6))
        self.renglones = _EditorRenglones(derecha, self.catalogo, con_costo=False)
        self.renglones.pack(fill="both", expand=True)
        ttk.Button(derecha, text="Registrar necesidad", command=self._crear).pack(fill="x", pady=(8, 0))
        self.refrescar()

    def refrescar(self, seleccionar: int | None = None) -> None:
        estado = next((e for e in EstadoNecesidad if _estado(e) == self.filtro_estado.get()), None)
        necesidades = self.servicio.listar_necesidades(estado, self._sucursales.get(self.filtro_sucursal.get()))
        numeros = {o.id: o.numero for o in self.servicio.listar()}
        self._necesidades = {str(n.id): n for n in necesidades}
        self.grilla.cargar(
            necesidades,
            lambda n: (n.id, n.fecha.isoformat(), self.catalogo.ubicacion(n.ubicacion_id),
                       "Automática" if n.origen == "AUTOMATICA" else "Manual", _estado(n.estado),
                       numeros.get(n.orden_reposicion_id, ""),
                       f"{len(n.detalles)} prod. · {sum(d.cantidad_solicitada for d in n.detalles)} u."),
            atenuar=lambda n: n.estado == EstadoNecesidad.ANULADA,
        )
        self.detalle.cargar([], lambda d: ())
        if seleccionar is not None:
            self.grilla.seleccionar(seleccionar)
            self._mostrar_detalle(str(seleccionar))

    def _mostrar_detalle(self, clave: str) -> None:
        necesidad = self._necesidades.get(clave)
        if necesidad is not None:
            self.detalle.cargar(
                necesidad.detalles,
                lambda d: (self.catalogo.producto(d.producto_id), d.cantidad_solicitada),
            )

    def _sucursal_nueva(self) -> int:
        if self.sucursal.get() not in self._sucursales:
            raise ValidacionError("Elegí la sucursal que necesita la mercadería.")
        return self._sucursales[self.sucursal.get()]

    def _sugerir(self) -> None:
        sugerencia = ejecutar_con_manejo_de_errores(lambda: self.servicio.sugerir_necesidad(self._sucursal_nueva()),
                                                    self)
        if sugerencia is None:
            return
        if not sugerencia:
            mostrar_info("Ningún producto de esa sucursal está en su stock mínimo (contando lo que ya viene en "
                         "camino).", "Sin faltantes", self)
            return
        self.renglones.cargar(sugerencia)

    def _crear(self) -> None:
        necesidad = ejecutar_con_manejo_de_errores(
            lambda: self.servicio.crear_necesidad(self._sucursal_nueva(), self.renglones.con_cantidades()), self
        )
        if necesidad is not None:
            self.renglones.limpiar()
            self.filtro_estado.set(_estado(EstadoNecesidad.PENDIENTE))
            self.refrescar(seleccionar=necesidad.id)

    def _anular(self) -> None:
        necesidad = self._necesidades.get(self.grilla.seleccionado() or "")
        if necesidad is None:
            mostrar_error("Elegí una necesidad de la lista.", padre=self)
            return
        if confirmar(f"¿Anular la necesidad {necesidad.id}?", padre=self):
            if ejecutar_con_manejo_de_errores(lambda: self.servicio.anular_necesidad(necesidad.id), self):
                self.refrescar()

    def _consolidar(self) -> None:
        sucursal_id = self._sucursales.get(self.filtro_sucursal.get())
        if sucursal_id is None:
            mostrar_error("Primero elegí una sucursal en el filtro de arriba.", padre=self)
            return
        pendientes = self.servicio.listar_necesidades(EstadoNecesidad.PENDIENTE, sucursal_id)
        if not pendientes:
            mostrar_info("Esa sucursal no tiene necesidades pendientes.", "Nada para consolidar", self)
            return
        if not confirmar(f"¿Consolidar {len(pendientes)} necesidades pendientes de "
                         f"{self.filtro_sucursal.get()} en una orden de reposición?", padre=self):
            return
        orden = ejecutar_con_manejo_de_errores(lambda: self.servicio.consolidar([n.id for n in pendientes]), self)
        if orden is not None:
            self.refrescar()
            mostrar_info(f"Se creó la orden de reposición {orden.numero} con {len(orden.detalles)} productos.\n"
                         "La ves en Inventario → Órdenes de reposición.", "Listo", self)


# === Órdenes de reposición ===========================================================================


class PantallaOrdenesReposicion(tk.Toplevel):
    """Órdenes CD → sucursal, su detalle (solicitado / preparado / recibido) y sus estados."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("Órdenes de reposición")
        self.geometry("1100x660")
        self.catalogo = _Catalogo()
        self.servicio = ReposicionService()
        self._ordenes: dict[str, OrdenReposicion] = {}

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        barra = ttk.Frame(marco)
        barra.pack(fill="x")
        self.filtro = tk.StringVar(value=TODOS)
        combo = _combo(barra, "Estado:", self.filtro, [TODOS] + [_estado(e) for e in EstadoOrdenReposicion], ancho=20)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        self.grilla = Grilla(
            marco,
            [("numero", "N°", 45), ("fecha", "Emitida", 120), ("origen", "Origen", 220),
             ("destino", "Destino", 220), ("estado", "Estado", 140),
             ("avance", "Solicitado / preparado / recibido", 210)],
            alto=10,
        )
        self.grilla.pack(fill="both", expand=True, pady=(8, 0))
        self.grilla.al_seleccionar(self._mostrar_detalle)
        self.necesidades = ttk.Label(marco, text="", foreground="gray30")
        self.necesidades.pack(anchor="w", pady=(10, 2))
        self.detalle = Grilla(
            marco,
            [("producto", "Producto", 320), ("solicitada", "Solicitada", 90), ("preparada", "Preparada", 90),
             ("recibida", "Recibida", 90), ("faltante", "Faltante", 90)],
            alto=6,
        )
        self.detalle.pack(fill="x")
        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=(8, 0))
        ttk.Button(botones, text="Iniciar preparación", command=self._iniciar).pack(side="left")
        ttk.Button(botones, text="Cerrar orden", command=self._cerrar).pack(side="left", padx=6)
        ttk.Label(
            marco,
            text="Pendiente → En preparación → Despachada → Cerrada completa / con faltantes.  "
            "El armado de bultos, el despacho y la recepción los registra Logística; "
            "al cerrar, si se recibió menos de lo pedido, la orden queda «con faltantes».",
            foreground="gray30", wraplength=1050,
        ).pack(anchor="w", pady=(6, 0))
        self.refrescar()

    def refrescar(self, seleccionar: int | None = None) -> None:
        estado = next((e for e in EstadoOrdenReposicion if _estado(e) == self.filtro.get()), None)
        ordenes = self.servicio.listar(estado)
        self._ordenes = {str(o.id): o for o in ordenes}

        def avance(o: OrdenReposicion) -> str:
            return " / ".join(str(sum(getattr(d, campo) for d in o.detalles))
                              for campo in ("cantidad_solicitada", "cantidad_preparada", "cantidad_recibida"))

        self.grilla.cargar(
            ordenes,
            lambda o: (o.numero, o.fecha_emision.strftime("%Y-%m-%d %H:%M"), self.catalogo.ubicacion(o.origen_id),
                       self.catalogo.ubicacion(o.destino_id), _estado(o.estado), avance(o)),
            atenuar=lambda o: o.estado in (EstadoOrdenReposicion.CERRADA_COMPLETA,
                                           EstadoOrdenReposicion.CERRADA_CON_FALTANTES),
        )
        self.detalle.cargar([], lambda d: ())
        self.necesidades.configure(text="")
        if seleccionar is not None:
            self.grilla.seleccionar(seleccionar)
            self._mostrar_detalle(str(seleccionar))

    def _mostrar_detalle(self, clave: str) -> None:
        orden = self._ordenes.get(clave)
        if orden is None:
            return
        self.detalle.cargar(
            orden.detalles,
            lambda d: (self.catalogo.producto(d.producto_id), d.cantidad_solicitada, d.cantidad_preparada,
                       d.cantidad_recibida, d.faltante() or ""),
        )
        consolidadas = [n.id for n in self.servicio.listar_necesidades(EstadoNecesidad.CONSOLIDADA)
                        if n.orden_reposicion_id == orden.id]
        self.necesidades.configure(
            text=f"Orden {orden.numero}: consolida las necesidades N° {', '.join(map(str, consolidadas)) or '—'}"
        )

    def _orden_elegida(self) -> OrdenReposicion | None:
        orden = self._ordenes.get(self.grilla.seleccionado() or "")
        if orden is None:
            mostrar_error("Elegí una orden de la lista.", padre=self)
        return orden

    def _iniciar(self) -> None:
        orden = self._orden_elegida()
        if orden is not None and ejecutar_con_manejo_de_errores(
            lambda: self.servicio.iniciar_preparacion(orden.id), self
        ):
            self.refrescar(seleccionar=orden.id)

    def _cerrar(self) -> None:
        orden = self._orden_elegida()
        if orden is None or not confirmar(f"¿Cerrar la orden de reposición {orden.numero}?", padre=self):
            return
        cerrada = ejecutar_con_manejo_de_errores(lambda: self.servicio.cerrar(orden.id), self)
        if cerrada is not None:
            self.refrescar(seleccionar=orden.id)
            mostrar_info(f"La orden {cerrada.numero} quedó «{_estado(cerrada.estado)}».", "Listo", self)


# === R3: movimientos y valorización ===================================================================


class PantallaMovimientos(tk.Toplevel):
    """R3: entradas y salidas del período y stock actual valorizado al costo por ubicación."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("R3 – Movimientos y valorización del inventario")
        self.geometry("1150x720")
        self.reporte = ReporteMovimientos()
        catalogo = _Catalogo()

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
        self._ubicaciones = {TODAS: None} | catalogo.opciones_ubicaciones()
        self._categorias = {TODAS: None} | {c.nombre: c.id for c in CategoriaService().listar()}
        self._tipos = {TODOS: None} | {NOMBRE_TIPO[t]: t for t in TipoMovimiento}
        self.ubicacion = tk.StringVar(value=TODAS)
        self.categoria = tk.StringVar(value=TODAS)
        self.tipo = tk.StringVar(value=TODOS)
        _combo(barra, "Ubicación:", self.ubicacion, self._ubicaciones, ancho=24)
        _combo(barra, "Categoría:", self.categoria, self._categorias, ancho=12)
        _combo(barra, "Tipo:", self.tipo, self._tipos, ancho=22)
        ttk.Button(barra, text="Consultar", command=self._consultar).pack(side="left")

        self.resumen = ttk.Label(marco, text="", font=("TkDefaultFont", 10, "bold"))
        self.resumen.pack(anchor="w", pady=(10, 4))
        pestañas = ttk.Notebook(marco)
        pestañas.pack(fill="both", expand=True)

        por_tipo = ttk.Frame(pestañas, padding=8)
        pestañas.add(por_tipo, text="Entradas y salidas por tipo")
        self.grilla_tipos = Grilla(
            por_tipo,
            [("sentido", "Sentido", 80), ("tipo", "Tipo de movimiento", 260), ("movimientos", "Movimientos", 95),
             ("unidades", "Unidades", 90), ("valor", "Valor (costo)", 140)],
            alto=8,
        )
        self.grilla_tipos.pack(fill="x")
        ttk.Label(
            por_tipo,
            text="«Interno» = cambia de balde dentro de la misma ubicación (por ejemplo, pendiente → disponible "
            "al verificar un bulto). No suma ni resta stock.",
            foreground="gray30",
        ).pack(anchor="w")

        valorizacion = ttk.Frame(pestañas, padding=8)
        pestañas.add(valorizacion, text="Stock valorizado por ubicación")
        self.grilla_valor = Grilla(
            valorizacion,
            [("ubicacion", "Ubicación", 250), ("disponible", "Disponible", 85), ("pendiente", "Pendiente", 85),
             ("merma", "Merma", 70), ("valor_disponible", "Valor disponible", 135),
             ("valor_pendiente", "Valor pendiente", 135), ("valor_total", "Total", 135),
             ("valor_merma", "Merma valorizada", 135)],
            alto=6,
        )
        self.grilla_valor.pack(fill="x")
        self.grafico = GraficoBarras(
            valorizacion,
            titulo="Stock valorizado al costo actual (disponible + pendiente)",
            leyenda="Valorizado con el costo actual de cada producto · la merma se informa aparte",
            filas_maximas=6,
        )
        self.grafico.pack(fill="x", pady=(10, 0))

        detalle = ttk.Frame(pestañas, padding=8)
        pestañas.add(detalle, text="Detalle de movimientos")
        self.grilla_detalle = Grilla(
            detalle,
            [("fecha", "Fecha y hora", 125), ("ubicacion", "Ubicación", 170), ("producto", "Producto", 200),
             ("tipo", "Movimiento", 200), ("sentido", "Sentido", 70), ("cantidad", "Cant.", 55),
             ("valor", "Valor", 105), ("documento", "Documento", 120)],
            alto=16,
        )
        self.grilla_detalle.pack(fill="both", expand=True)
        self._consultar()

    def _consultar(self) -> None:
        def consultar() -> ResumenMovimientos:
            return self.reporte.consultar(
                _a_fecha(self.desde.get(), "Desde"), _a_fecha(self.hasta.get(), "Hasta"),
                self._ubicaciones[self.ubicacion.get()], self._categorias[self.categoria.get()],
                self._tipos[self.tipo.get()],
            )

        resumen = ejecutar_con_manejo_de_errores(consultar, self)
        if resumen is not None:
            self._mostrar(resumen)

    def _mostrar(self, r: ResumenMovimientos) -> None:
        (u_ent, v_ent), (u_sal, v_sal) = r.entradas, r.salidas
        self.resumen.configure(
            text=f"{len(r.movimientos)} movimientos · Entradas: {u_ent} u. ({formato_dinero(v_ent)}) · "
            f"Salidas: {u_sal} u. ({formato_dinero(v_sal)}) · "
            f"Stock valorizado hoy: {formato_dinero(r.total_valorizado)}"
        )
        self.grilla_tipos.cargar(
            r.por_tipo(),
            lambda t: (str(t.sentido), t.nombre, t.movimientos, t.unidades, formato_dinero(t.valor)),
            clave=lambda t: str(t.tipo),
        )
        self.grilla_valor.cargar(
            r.valorizacion,
            lambda v: (f"{v.ubicacion} ({v.codigo})", v.disponible, v.pendiente, v.merma,
                       formato_dinero(v.valor_disponible), formato_dinero(v.valor_pendiente),
                       formato_dinero(v.valor_total), formato_dinero(v.valor_merma)),
            clave=lambda v: v.ubicacion_id,
        )
        self.grafico.dibujar([
            Barra(v.ubicacion, float(v.valor_total), formato_dinero(v.valor_total),
                  alerta="con merma" if v.merma else None)
            for v in sorted(r.valorizacion, key=lambda v: v.valor_total, reverse=True)
        ])
        self.grilla_detalle.cargar(
            enumerate(r.movimientos),
            lambda par: (par[1].fecha_hora.strftime("%Y-%m-%d %H:%M"), par[1].ubicacion,
                         f"{par[1].sku} – {par[1].producto}", NOMBRE_TIPO[par[1].tipo], str(par[1].sentido),
                         par[1].cantidad, formato_dinero(par[1].valor), par[1].documento),
            clave=lambda par: par[0],
        )


# === R4: tiempo de tránsito ===========================================================================


class PantallaTransito(tk.Toplevel):
    """R4: tiempo desde el despacho en el CD hasta la verificación en el local, por sucursal."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title("R4 – Tiempo promedio de tránsito CD → locales")
        self.geometry("1100x700")
        self.reporte = ReporteTransito()

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        barra = ttk.Frame(marco)
        barra.pack(fill="x")
        hoy = date.today()
        self.desde = tk.StringVar(value=hoy.replace(day=1).isoformat())
        self.hasta = tk.StringVar(value=hoy.isoformat())
        ttk.Label(barra, text="Despachados desde:").pack(side="left")
        ttk.Entry(barra, textvariable=self.desde, width=11).pack(side="left", padx=(4, 12))
        ttk.Label(barra, text="Hasta:").pack(side="left")
        ttk.Entry(barra, textvariable=self.hasta, width=11).pack(side="left", padx=(4, 12))
        self._sucursales = {TODAS: None} | _Catalogo().opciones_ubicaciones(solo_sucursales=True)
        self.sucursal = tk.StringVar(value=TODAS)
        _combo(barra, "Sucursal:", self.sucursal, self._sucursales, ancho=30)
        ttk.Button(barra, text="Consultar", command=self._consultar).pack(side="left")

        self.resumen = ttk.Label(marco, text="", font=("TkDefaultFont", 10, "bold"))
        self.resumen.pack(anchor="w", pady=(10, 4))
        ttk.Label(marco, text="Tiempo de tránsito = desde que el remito sale del CD hasta que la sucursal lo "
                  "verifica (o lo rechaza). Los remitos todavía no verificados figuran «En tránsito».",
                  foreground="gray30").pack(anchor="w")
        self.grilla_sucursales = Grilla(
            marco,
            [("sucursal", "Sucursal", 280), ("remitos", "Remitos recibidos", 120), ("promedio", "Promedio", 150),
             ("minimo", "Más rápido", 150), ("maximo", "Más lento", 150)],
            alto=5,
        )
        self.grilla_sucursales.pack(fill="x", pady=(6, 0))
        self.grafico = GraficoBarras(marco, titulo="Tiempo promedio de tránsito por sucursal (horas)",
                                     leyenda="Rojo con ⚠: hubo remitos con bultos rechazados", filas_maximas=5)
        self.grafico.pack(fill="x", pady=(10, 0))
        ttk.Label(marco, text="Remitos del período").pack(anchor="w", pady=(10, 2))
        self.grilla_remitos = Grilla(
            marco,
            [("remito", "Remito", 70), ("origen", "Origen", 190), ("destino", "Destino", 190),
             ("despacho", "Despacho", 130), ("recepcion", "Verificación", 130), ("tiempo", "Tránsito", 130),
             ("unidades", "Unidades", 75), ("rechazos", "Rechazos", 75)],
            alto=8,
        )
        self.grilla_remitos.pack(fill="both", expand=True)
        self._consultar()

    def _consultar(self) -> None:
        resumen = ejecutar_con_manejo_de_errores(
            lambda: self.reporte.consultar(_a_fecha(self.desde.get(), "Desde"), _a_fecha(self.hasta.get(), "Hasta"),
                                           self._sucursales[self.sucursal.get()]),
            self,
        )
        if resumen is not None:
            self._mostrar(resumen)

    def _mostrar(self, r: ResumenTransito) -> None:
        if not r.filas:
            self.resumen.configure(text="No hay remitos despachados en el período. Los genera Logística al "
                                   "despachar bultos desde el CD.")
        else:
            self.resumen.configure(
                text=f"{len(r.recibidos)} remitos verificados · {r.cantidad_en_transito} en tránsito · "
                f"Promedio general: {formato_duracion(r.promedio_horas) if r.recibidos else '—'}"
            )
        por_sucursal = r.por_sucursal()
        con_rechazos = {f.destino_id for f in r.recibidos if f.con_rechazos}
        self.grilla_sucursales.cargar(
            por_sucursal,
            lambda p: (p.destino, p.remitos, formato_duracion(p.promedio_horas), formato_duracion(p.minimo_horas),
                       formato_duracion(p.maximo_horas)),
            clave=lambda p: p.destino_id,
        )
        self.grafico.dibujar([
            Barra(p.destino, p.promedio_horas, f"{p.promedio_horas:.1f} h".replace(".", ","),
                  alerta="con rechazos" if p.destino_id in con_rechazos else None)
            for p in por_sucursal
        ])
        self.grilla_remitos.cargar(
            r.filas,
            lambda f: (f.remito_id, f.origen, f.destino, f.despacho.strftime("%Y-%m-%d %H:%M"),
                       f.recepcion.strftime("%Y-%m-%d %H:%M") if f.recepcion else "—",
                       formato_duracion(f.horas), f.unidades, "Sí" if f.con_rechazos else ""),
            clave=lambda f: f.remito_id,
        )


# === Funciones que usa el menú =========================================================================


def abrir_stock(padre: tk.Misc) -> None:
    PantallaStock(padre)


def abrir_compras(padre: tk.Misc) -> None:
    PantallaCompras(padre)


def abrir_necesidades(padre: tk.Misc) -> None:
    PantallaNecesidades(padre)


def abrir_ordenes_reposicion(padre: tk.Misc) -> None:
    PantallaOrdenesReposicion(padre)


def abrir_movimientos(padre: tk.Misc) -> None:
    PantallaMovimientos(padre)


def abrir_transito(padre: tk.Misc) -> None:
    PantallaTransito(padre)


def abrir_cargar_stock_de_prueba(padre: tk.Misc) -> None:
    if not confirmar("¿Cargar stock de prueba? Se registran compras al CD y una carga inicial en cada sucursal.\n"
                     "Antes tienen que estar cargados los datos de prueba de maestros (Archivo).", padre=padre):
        return
    cantidades = ejecutar_con_manejo_de_errores(cargar_stock_de_prueba, padre)
    if cantidades is not None:
        detalle = "\n".join(f"{cantidad} {tipo}" for tipo, cantidad in cantidades.items())
        mostrar_info(f"Se cargó el stock de prueba:\n\n{detalle}", "Stock de prueba", padre)
