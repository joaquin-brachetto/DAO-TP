"""Pantallas de maestros (brache): sucursales y CD, categorías, productos y proveedores."""

import tkinter as tk
from tkinter import ttk
from typing import Any

from src.dominio.maestros.modelos import (
    Categoria,
    CentroDistribucion,
    Producto,
    ProductoProveedor,
    Proveedor,
    StockMinimo,
    Sucursal,
    TipoUbicacion,
    Ubicacion,
    formatear_cuit,
)
from src.excepciones import ValidacionError
from src.servicios.maestros_service import (
    CategoriaService,
    ProductoService,
    ProveedorService,
    StockMinimoService,
    UbicacionService,
)
from src.ui.abm import (
    VentanaABM,
    a_decimal,
    a_entero,
    a_real,
    formato_dinero,
    formato_estado,
    formato_porcentaje,
)
from src.ui.componentes import Formulario, Grilla, confirmar, ejecutar_con_manejo_de_errores, mostrar_error

# --- P1: sucursales y Centro de Distribución ---------------------------------------------------------

TIPOS_UBICACION = {"Sucursal": TipoUbicacion.SUCURSAL, "Centro de Distribución": TipoUbicacion.CD}


class PantallaUbicaciones(VentanaABM):
    titulo = "Sucursales y Centro de Distribución"
    columnas = [
        ("tipo", "Tipo", 150),
        ("codigo", "Código", 80),
        ("nombre", "Nombre", 200),
        ("punto_venta", "Pto. venta", 80),
        ("direccion", "Dirección", 200),
        ("estado", "Estado", 70),
    ]
    campos = [
        ("tipo", "Tipo", list(TIPOS_UBICACION)),
        ("codigo", "Código"),
        ("nombre", "Nombre"),
        ("direccion", "Dirección"),
        ("telefono", "Teléfono"),
        ("punto_venta", "Punto de venta"),
        ("capacidad_m3", "Capacidad (m³)"),
    ]

    def __init__(self, padre: tk.Misc) -> None:
        self.servicio = UbicacionService()
        super().__init__(padre)
        self.formulario.al_cambiar("tipo", self._al_cambiar_tipo)

    def _al_cambiar_tipo(self, texto: str) -> None:
        tipo = TIPOS_UBICACION.get(texto)
        self.formulario.habilitar("punto_venta", tipo != TipoUbicacion.CD)
        self.formulario.habilitar("capacidad_m3", tipo != TipoUbicacion.SUCURSAL)

    def nuevo(self) -> None:
        super().nuevo()
        self.formulario.cargar({"tipo": "Sucursal"})

    def obtener_registros(self, incluir_inactivos: bool, texto: str) -> list[Ubicacion]:
        return self.servicio.listar(incluir_inactivos)

    def valores_fila(self, u: Ubicacion) -> tuple:
        tipo = "Centro de Distribución" if u.es_centro_distribucion() else "Sucursal"
        return (tipo, u.codigo, u.nombre, getattr(u, "punto_venta", "") or "", u.direccion or "", formato_estado(u.activa))

    def a_formulario(self, u: Ubicacion) -> dict[str, Any]:
        return {
            "tipo": "Centro de Distribución" if u.es_centro_distribucion() else "Sucursal",
            "codigo": u.codigo,
            "nombre": u.nombre,
            "direccion": u.direccion,
            "telefono": u.telefono,
            "punto_venta": getattr(u, "punto_venta", None),
            "capacidad_m3": getattr(u, "capacidad_m3", None),
        }

    def desde_formulario(self, v: dict[str, str], actual: Ubicacion | None) -> Ubicacion:
        tipo = TIPOS_UBICACION.get(v["tipo"])
        comunes = dict(
            codigo=v["codigo"],
            nombre=v["nombre"],
            direccion=v["direccion"],
            telefono=v["telefono"],
            activa=actual.activa if actual else True,
            id=actual.id if actual else None,
        )
        if tipo == TipoUbicacion.SUCURSAL:
            return Sucursal(punto_venta=a_entero(v["punto_venta"], "Punto de venta"), **comunes)
        if tipo == TipoUbicacion.CD:
            return CentroDistribucion(capacidad_m3=a_real(v["capacidad_m3"], "Capacidad", opcional=True), **comunes)
        raise ValidacionError("Elegí el tipo de ubicación.")

    def guardar_registro(self, u: Ubicacion) -> Ubicacion:
        return self.servicio.guardar(u)

    def dar_de_baja_registro(self, u: Ubicacion) -> None:
        self.servicio.dar_de_baja(u.id)

    def reactivar_registro(self, u: Ubicacion) -> None:
        self.servicio.reactivar(u.id)


# --- P2: categorías -------------------------------------------------------------------------------------


class PantallaCategorias(VentanaABM):
    titulo = "Categorías"
    con_baja_logica = False
    columnas = [("nombre", "Nombre", 220), ("descripcion", "Descripción", 380)]
    campos = [("nombre", "Nombre"), ("descripcion", "Descripción")]

    def __init__(self, padre: tk.Misc) -> None:
        self.servicio = CategoriaService()
        super().__init__(padre)

    def obtener_registros(self, incluir_inactivos: bool, texto: str) -> list[Categoria]:
        return self.servicio.listar()

    def valores_fila(self, c: Categoria) -> tuple:
        return (c.nombre, c.descripcion or "")

    def a_formulario(self, c: Categoria) -> dict[str, Any]:
        return {"nombre": c.nombre, "descripcion": c.descripcion}

    def desde_formulario(self, v: dict[str, str], actual: Categoria | None) -> Categoria:
        return Categoria(v["nombre"], v["descripcion"], id=actual.id if actual else None)

    def guardar_registro(self, c: Categoria) -> Categoria:
        return self.servicio.guardar(c)

    def dar_de_baja_registro(self, c: Categoria) -> None:
        self.servicio.eliminar(c.id)


# --- P2: productos y precios ---------------------------------------------------------------------------


class PantallaProductos(VentanaABM):
    titulo = "Productos y precios"
    con_busqueda = True
    columnas = [
        ("sku", "SKU", 90),
        ("nombre", "Nombre", 200),
        ("categoria", "Categoría", 110),
        ("costo", "Costo", 90),
        ("precio", "Precio venta", 90),
        ("margen", "Margen", 70),
        ("estado", "Estado", 70),
    ]
    campos = [
        ("sku", "SKU"),
        ("nombre", "Nombre"),
        ("categoria", "Categoría", []),
        ("costo", "Costo"),
        ("precio", "Precio de venta"),
        ("codigo_barras", "Código de barras"),
        ("unidad_medida", "Unidad de medida"),
        ("descripcion", "Descripción"),
    ]

    def __init__(self, padre: tk.Misc) -> None:
        self.servicio = ProductoService()
        self.categorias: dict[str, int] = {}
        super().__init__(padre)
        extra = self.acciones_extra
        extra.columnconfigure((0, 1), weight=1, uniform="extra")
        ttk.Button(extra, text="Historial de precios", command=self._ver_historial).grid(
            row=0, column=0, sticky="ew", padx=(0, 2)
        )
        ttk.Button(extra, text="Proveedores…", command=self._ver_proveedores).grid(
            row=0, column=1, sticky="ew", padx=(2, 0)
        )
        ttk.Button(extra, text="Stock mínimo…", command=self._ver_stock_minimo).grid(
            row=1, column=0, sticky="ew", padx=(0, 2), pady=(4, 0)
        )

    def _cargar_categorias(self) -> None:
        self.categorias = {c.nombre: c.id for c in CategoriaService().listar()}
        self.formulario.actualizar_opciones("categoria", list(self.categorias))

    def refrescar(self, seleccionar: Any | None = None) -> None:
        self._cargar_categorias()  # por si se agregaron categorías con la pantalla abierta
        super().refrescar(seleccionar)

    def nuevo(self) -> None:
        super().nuevo()
        self.formulario.cargar({"unidad_medida": "UN"})

    def _nombre_categoria(self, categoria_id: int) -> str:
        return next((nombre for nombre, id_ in self.categorias.items() if id_ == categoria_id), "")

    def obtener_registros(self, incluir_inactivos: bool, texto: str) -> list[Producto]:
        return self.servicio.buscar(texto, incluir_inactivos) if texto else self.servicio.listar(incluir_inactivos)

    def valores_fila(self, p: Producto) -> tuple:
        return (
            p.sku,
            p.nombre,
            self._nombre_categoria(p.categoria_id),
            formato_dinero(p.costo_actual),
            formato_dinero(p.precio_venta_actual),
            formato_porcentaje(p.margen_porcentual()),
            formato_estado(p.activo),
        )

    def a_formulario(self, p: Producto) -> dict[str, Any]:
        return {
            "sku": p.sku,
            "nombre": p.nombre,
            "categoria": self._nombre_categoria(p.categoria_id),
            "costo": p.costo_actual,
            "precio": p.precio_venta_actual,
            "codigo_barras": p.codigo_barras,
            "unidad_medida": p.unidad_medida,
            "descripcion": p.descripcion,
        }

    def desde_formulario(self, v: dict[str, str], actual: Producto | None) -> Producto:
        if v["categoria"] not in self.categorias:
            raise ValidacionError("Elegí una categoría (si no hay ninguna, primero cargala en Maestros → Categorías).")
        return Producto(
            sku=v["sku"],
            nombre=v["nombre"],
            categoria_id=self.categorias[v["categoria"]],
            costo_actual=a_decimal(v["costo"], "Costo"),
            precio_venta_actual=a_decimal(v["precio"], "Precio de venta"),
            codigo_barras=v["codigo_barras"],
            descripcion=v["descripcion"],
            unidad_medida=v["unidad_medida"] or "UN",
            activo=actual.activo if actual else True,
            id=actual.id if actual else None,
        )

    def guardar_registro(self, p: Producto) -> Producto:
        return self.servicio.guardar(p)

    def dar_de_baja_registro(self, p: Producto) -> None:
        self.servicio.dar_de_baja(p.id)

    def reactivar_registro(self, p: Producto) -> None:
        self.servicio.reactivar(p.id)

    def descripcion(self, p: Producto) -> str:
        return f"{p.sku} – {p.nombre}"

    def _ver_historial(self) -> None:
        if self.actual is None:
            mostrar_error("Primero elegí un producto de la lista.", padre=self)
            return
        VentanaHistorialPrecios(self, self.servicio, self.actual)

    def _ver_proveedores(self) -> None:
        if self.actual is None:
            mostrar_error("Primero elegí un producto de la lista.", padre=self)
            return
        VentanaProveedoresDeProducto(self, self.servicio, self.actual)


    def _ver_stock_minimo(self) -> None:
        if self.actual is None:
            mostrar_error("Primero elegí un producto de la lista.", padre=self)
            return
        VentanaStockMinimo(self, self.actual)


class VentanaStockMinimo(tk.Toplevel):
    """Stock mínimo del producto en cada sucursal y en el CD (P2)."""

    def __init__(self, padre: tk.Misc, producto: Producto) -> None:
        super().__init__(padre)
        self.servicio = StockMinimoService()
        self.producto = producto
        self.title(f"Stock mínimo – {producto.sku}")
        self.geometry("620x420")
        self.ubicaciones = {u.id: u for u in UbicacionService().listar(incluir_inactivas=True)}

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text=f"{producto.sku} – {producto.nombre}", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        ttk.Label(
            marco,
            text="Cuando el stock disponible llega a este valor, el producto aparece como «en stock mínimo».",
            foreground="gray30",
            wraplength=590,
        ).pack(anchor="w")
        self.grilla = Grilla(marco, [("ubicacion", "Ubicación", 280), ("tipo", "Tipo", 150), ("minimo", "Mínimo", 90)], alto=8)
        self.grilla.pack(fill="both", expand=True, pady=8)
        self.grilla.al_seleccionar(self._al_seleccionar)

        self.opciones = {
            f"{u.nombre} ({u.codigo})": u.id for u in self.ubicaciones.values() if u.activa
        }
        self.formulario = Formulario(marco, [("ubicacion", "Ubicación", list(self.opciones)), ("minimo", "Cantidad mínima")])
        self.formulario.pack(fill="x")
        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=(8, 0))
        ttk.Button(botones, text="Guardar", command=self._guardar).pack(side="left")
        ttk.Button(botones, text="Quitar", command=self._quitar).pack(side="left", padx=4)
        self._refrescar()

    def _etiqueta(self, ubicacion_id: int) -> str:
        u = self.ubicaciones[ubicacion_id]
        return f"{u.nombre} ({u.codigo})"

    def _refrescar(self) -> None:
        self.minimos = {str(m.ubicacion_id): m for m in self.servicio.de_producto(self.producto.id)}
        self.grilla.cargar(
            self.minimos.values(),
            lambda m: (
                self._etiqueta(m.ubicacion_id),
                "Centro de Distribución" if self.ubicaciones[m.ubicacion_id].es_centro_distribucion() else "Sucursal",
                m.cantidad_minima,
            ),
            clave=lambda m: m.ubicacion_id,
            atenuar=lambda m: not self.ubicaciones[m.ubicacion_id].activa,
        )

    def _al_seleccionar(self, clave: str) -> None:
        minimo = self.minimos[clave]
        self.formulario.cargar({"ubicacion": self._etiqueta(minimo.ubicacion_id), "minimo": minimo.cantidad_minima})

    def _guardar(self) -> None:
        def guardar() -> StockMinimo:
            v = self.formulario.valores()
            if v["ubicacion"] not in self.opciones:
                raise ValidacionError("Elegí una ubicación activa.")
            return self.servicio.definir(
                StockMinimo(self.producto.id, self.opciones[v["ubicacion"]], a_entero(v["minimo"], "Cantidad mínima"))
            )

        minimo = ejecutar_con_manejo_de_errores(guardar, self)
        if minimo is not None:
            self._refrescar()
            self.grilla.seleccionar(minimo.ubicacion_id)

    def _quitar(self) -> None:
        clave = self.grilla.seleccionado()
        if clave is None:
            mostrar_error("Elegí una ubicación de la lista.", padre=self)
            return
        if confirmar(f"¿Quitar el stock mínimo en {self._etiqueta(int(clave))}?", padre=self):
            if ejecutar_con_manejo_de_errores(lambda: self.servicio.quitar(self.producto.id, int(clave)) or True, self):
                self.formulario.limpiar()
                self._refrescar()


class VentanaHistorialPrecios(tk.Toplevel):
    def __init__(self, padre: tk.Misc, servicio: ProductoService, producto: Producto) -> None:
        super().__init__(padre)
        self.title(f"Historial de precios – {producto.sku}")
        self.geometry("640x320")
        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text=f"{producto.sku} – {producto.nombre}", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        grilla = Grilla(
            marco,
            [("desde", "Desde", 140), ("hasta", "Hasta", 140), ("costo", "Costo", 100),
             ("precio", "Precio venta", 100), ("margen", "Margen", 100)],
        )
        grilla.pack(fill="both", expand=True, pady=(8, 0))
        grilla.cargar(
            servicio.historial_precios(producto.id),
            lambda h: (
                h.fecha_desde.strftime("%d/%m/%Y %H:%M"),
                h.fecha_hasta.strftime("%d/%m/%Y %H:%M") if h.fecha_hasta else "vigente",
                formato_dinero(h.costo),
                formato_dinero(h.precio_venta),
                formato_dinero(h.precio_venta - h.costo),
            ),
        )


class VentanaProveedoresDeProducto(tk.Toplevel):
    """Qué proveedores venden el producto, con su código, costo pactado y plazo de entrega."""

    def __init__(self, padre: tk.Misc, servicio: ProductoService, producto: Producto) -> None:
        super().__init__(padre)
        self.servicio = servicio
        self.producto = producto
        self.title(f"Proveedores – {producto.sku}")
        self.geometry("760x420")
        self.proveedores = {p.id: p for p in ProveedorService().listar(incluir_inactivos=True)}

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text=f"{producto.sku} – {producto.nombre}", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.grilla = Grilla(
            marco,
            [("proveedor", "Proveedor", 220), ("cuit", "CUIT", 120), ("codigo", "Código del proveedor", 140),
             ("costo", "Costo pactado", 100), ("plazo", "Plazo (días)", 80)],
            alto=8,
        )
        self.grilla.pack(fill="both", expand=True, pady=8)
        self.grilla.al_seleccionar(self._al_seleccionar)

        activos = {self._etiqueta(p): p.id for p in self.proveedores.values() if p.activo}
        self.opciones = activos
        self.formulario = Formulario(
            marco,
            [("proveedor", "Proveedor", list(activos)), ("codigo", "Código del proveedor"),
             ("costo", "Costo pactado"), ("plazo", "Plazo de entrega (días)")],
        )
        self.formulario.pack(fill="x")
        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=(8, 0))
        ttk.Button(botones, text="Asignar / actualizar", command=self._asignar).pack(side="left")
        ttk.Button(botones, text="Quitar", command=self._quitar).pack(side="left", padx=4)
        self._refrescar()

    def _etiqueta(self, proveedor: Proveedor) -> str:
        return f"{proveedor.razon_social} ({formatear_cuit(proveedor.cuit)})"

    def _refrescar(self) -> None:
        self.relaciones = {str(r.proveedor_id): r for r in self.servicio.proveedores_de(self.producto.id)}
        self.grilla.cargar(
            self.relaciones.values(),
            lambda r: (
                self.proveedores[r.proveedor_id].razon_social,
                formatear_cuit(self.proveedores[r.proveedor_id].cuit),
                r.codigo_en_proveedor or "",
                formato_dinero(r.costo_pactado),
                "" if r.plazo_entrega_dias is None else r.plazo_entrega_dias,
            ),
            clave=lambda r: r.proveedor_id,
            atenuar=lambda r: not self.proveedores[r.proveedor_id].activo,
        )

    def _al_seleccionar(self, clave: str) -> None:
        relacion = self.relaciones[clave]
        self.formulario.cargar(
            {
                "proveedor": self._etiqueta(self.proveedores[relacion.proveedor_id]),
                "codigo": relacion.codigo_en_proveedor,
                "costo": relacion.costo_pactado,
                "plazo": relacion.plazo_entrega_dias,
            }
        )

    def _asignar(self) -> None:
        def asignar() -> ProductoProveedor:
            v = self.formulario.valores()
            if v["proveedor"] not in self.opciones:
                raise ValidacionError("Elegí un proveedor activo.")
            return self.servicio.asignar_proveedor(
                ProductoProveedor(
                    producto_id=self.producto.id,
                    proveedor_id=self.opciones[v["proveedor"]],
                    codigo_en_proveedor=v["codigo"],
                    costo_pactado=a_decimal(v["costo"], "Costo pactado", opcional=True),
                    plazo_entrega_dias=a_entero(v["plazo"], "Plazo de entrega", opcional=True),
                )
            )

        relacion = ejecutar_con_manejo_de_errores(asignar, self)
        if relacion is not None:
            self._refrescar()
            self.grilla.seleccionar(relacion.proveedor_id)

    def _quitar(self) -> None:
        clave = self.grilla.seleccionado()
        if clave is None:
            mostrar_error("Elegí un proveedor de la lista.", padre=self)
            return
        nombre = self.proveedores[int(clave)].razon_social
        if confirmar(f"¿Quitar a {nombre} de los proveedores de este producto?", padre=self):
            if ejecutar_con_manejo_de_errores(
                lambda: self.servicio.quitar_proveedor(self.producto.id, int(clave)) or True, self
            ):
                self.formulario.limpiar()
                self._refrescar()


# --- P2: proveedores -------------------------------------------------------------------------------------


class PantallaProveedores(VentanaABM):
    titulo = "Proveedores"
    con_busqueda = True
    columnas = [
        ("cuit", "CUIT", 110),
        ("razon_social", "Razón social", 220),
        ("email", "Email", 180),
        ("telefono", "Teléfono", 110),
        ("estado", "Estado", 70),
    ]
    campos = [
        ("cuit", "CUIT"),
        ("razon_social", "Razón social"),
        ("email", "Email"),
        ("telefono", "Teléfono"),
        ("direccion", "Dirección"),
    ]

    def __init__(self, padre: tk.Misc) -> None:
        self.servicio = ProveedorService()
        super().__init__(padre)
        ttk.Button(self.acciones_extra, text="Productos que provee", command=self._ver_productos).pack(side="left")

    def obtener_registros(self, incluir_inactivos: bool, texto: str) -> list[Proveedor]:
        proveedores = self.servicio.listar(incluir_inactivos)
        texto = texto.lower().replace("-", "")
        return [p for p in proveedores if texto in p.razon_social.lower() or texto in p.cuit] if texto else proveedores

    def valores_fila(self, p: Proveedor) -> tuple:
        return (formatear_cuit(p.cuit), p.razon_social, p.email or "", p.telefono or "", formato_estado(p.activo))

    def a_formulario(self, p: Proveedor) -> dict[str, Any]:
        return {
            "cuit": formatear_cuit(p.cuit),
            "razon_social": p.razon_social,
            "email": p.email,
            "telefono": p.telefono,
            "direccion": p.direccion,
        }

    def desde_formulario(self, v: dict[str, str], actual: Proveedor | None) -> Proveedor:
        return Proveedor(
            cuit=v["cuit"],
            razon_social=v["razon_social"],
            email=v["email"],
            telefono=v["telefono"],
            direccion=v["direccion"],
            activo=actual.activo if actual else True,
            id=actual.id if actual else None,
        )

    def guardar_registro(self, p: Proveedor) -> Proveedor:
        return self.servicio.guardar(p)

    def dar_de_baja_registro(self, p: Proveedor) -> None:
        self.servicio.dar_de_baja(p.id)

    def reactivar_registro(self, p: Proveedor) -> None:
        self.servicio.reactivar(p.id)

    def descripcion(self, p: Proveedor) -> str:
        return p.razon_social

    def _ver_productos(self) -> None:
        if self.actual is None:
            mostrar_error("Primero elegí un proveedor de la lista.", padre=self)
            return
        productos = ProductoService()
        ventana = tk.Toplevel(self)
        ventana.title(f"Productos de {self.actual.razon_social}")
        ventana.geometry("560x300")
        grilla = Grilla(
            ventana,
            [("sku", "SKU", 90), ("nombre", "Producto", 220), ("codigo", "Código del proveedor", 130),
             ("costo", "Costo pactado", 100)],
        )
        grilla.pack(fill="both", expand=True, padx=12, pady=12)
        relaciones = self.servicio.productos_de(self.actual.id)
        por_id = {p.id: p for p in productos.listar(incluir_inactivos=True)}
        grilla.cargar(
            relaciones,
            lambda r: (por_id[r.producto_id].sku, por_id[r.producto_id].nombre, r.codigo_en_proveedor or "",
                       formato_dinero(r.costo_pactado)),
            clave=lambda r: r.producto_id,
        )


# --- Funciones que usa el menú ---------------------------------------------------------------------------


def abrir_ubicaciones(padre: tk.Misc) -> None:
    PantallaUbicaciones(padre)


def abrir_categorias(padre: tk.Misc) -> None:
    PantallaCategorias(padre)


def abrir_productos(padre: tk.Misc) -> None:
    PantallaProductos(padre)


def abrir_proveedores(padre: tk.Misc) -> None:
    PantallaProveedores(padre)
