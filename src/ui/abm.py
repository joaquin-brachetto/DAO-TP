"""Ventana genérica de ABM (alta, baja y modificación).

A la izquierda, la grilla con los registros; a la derecha, el formulario y los
botones Nuevo / Guardar / Dar de baja / Reactivar. Cada pantalla concreta
hereda de `VentanaABM`, define columnas y campos, y completa los métodos
marcados como "a redefinir" (ver `src/ui/pantallas/maestros.py`).
"""

import tkinter as tk
from decimal import Decimal, InvalidOperation
from tkinter import ttk
from typing import Any

from src.excepciones import ValidacionError
from src.ui.componentes import Formulario, Grilla, confirmar, ejecutar_con_manejo_de_errores, mostrar_info

# --- Conversión de lo que se escribe en el formulario -------------------------------------------


def a_decimal(texto: str, campo: str, opcional: bool = False) -> Decimal | None:
    """'1.234,50' o '1234.50' -> Decimal('1234.50')."""
    texto = texto.strip()
    if not texto:
        if opcional:
            return None
        raise ValidacionError(f"El campo «{campo}» es obligatorio.")
    if "," in texto:  # formato argentino: punto de miles y coma decimal
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        raise ValidacionError(f"«{campo}» debe ser un número.") from None


def a_entero(texto: str, campo: str, opcional: bool = False) -> int | None:
    texto = texto.strip()
    if not texto:
        if opcional:
            return None
        raise ValidacionError(f"El campo «{campo}» es obligatorio.")
    try:
        return int(texto)
    except ValueError:
        raise ValidacionError(f"«{campo}» debe ser un número entero.") from None


def a_real(texto: str, campo: str, opcional: bool = False) -> float | None:
    numero = a_decimal(texto, campo, opcional)
    return None if numero is None else float(numero)


def formato_dinero(valor: Decimal | None) -> str:
    """Decimal('-1234.5') -> '-$ 1.234,50'."""
    if valor is None:
        return ""
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if valor < 0 else ''}$ {texto}"


def formato_porcentaje(valor: Decimal | None) -> str:
    return "" if valor is None else f"{valor:.1f} %".replace(".", ",")


def formato_estado(activo: bool) -> str:
    return "Activo" if activo else "De baja"


# --- Ventana ---------------------------------------------------------------------------------------


class VentanaABM(tk.Toplevel):
    titulo = "ABM"
    columnas: list[tuple[str, str, int]] = []
    campos: list[tuple] = []

    con_baja_logica = True
    """Si es False (por ejemplo, categorías) el botón borra el registro y no hay "Reactivar"."""

    con_busqueda = False
    """Muestra un cuadro de búsqueda arriba de la grilla."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.title(self.titulo)
        self.geometry("1100x580")
        self.minsize(820, 420)
        self._registros: dict[str, Any] = {}
        self.actual: Any | None = None
        self._armar()
        self.refrescar()
        self.nuevo()

    # --- A redefinir en cada pantalla -----------------------------------------------------------

    def obtener_registros(self, incluir_inactivos: bool, texto: str) -> list[Any]:
        raise NotImplementedError

    def valores_fila(self, registro: Any) -> tuple:
        raise NotImplementedError

    def a_formulario(self, registro: Any) -> dict[str, Any]:
        raise NotImplementedError

    def desde_formulario(self, valores: dict[str, str], actual: Any | None) -> Any:
        """Arma una entidad NUEVA con lo escrito (con el id de `actual` si se está modificando).

        No hay que modificar `actual`: si el guardado falla, la grilla tiene que seguir
        mostrando los datos que están en la base.
        """
        raise NotImplementedError

    def guardar_registro(self, entidad: Any) -> Any:
        raise NotImplementedError

    def dar_de_baja_registro(self, registro: Any) -> None:
        raise NotImplementedError

    def reactivar_registro(self, registro: Any) -> None:
        raise NotImplementedError

    def esta_activo(self, registro: Any) -> bool:
        return getattr(registro, "activo", getattr(registro, "activa", True))

    def descripcion(self, registro: Any) -> str:
        """Texto corto para los mensajes de confirmación."""
        return getattr(registro, "nombre", str(registro.id))

    # --- Armado -------------------------------------------------------------------------------------

    def _armar(self) -> None:
        izquierda = ttk.Frame(self, padding=(12, 12, 6, 12))
        izquierda.pack(side="left", fill="both", expand=True)
        derecha = ttk.LabelFrame(self, text="Datos", padding=12)
        derecha.pack(side="right", fill="y", padx=(6, 12), pady=12)

        filtros = ttk.Frame(izquierda)
        filtros.pack(fill="x", pady=(0, 8))
        self._texto = tk.StringVar()
        if self.con_busqueda:
            ttk.Label(filtros, text="Buscar:").pack(side="left")
            buscador = ttk.Entry(filtros, textvariable=self._texto, width=30)
            buscador.pack(side="left", padx=(4, 12))
            buscador.bind("<KeyRelease>", lambda _e: self.refrescar())
        self._mostrar_inactivos = tk.BooleanVar(value=False)
        if self.con_baja_logica:
            ttk.Checkbutton(
                filtros, text="Mostrar dados de baja", variable=self._mostrar_inactivos, command=self.refrescar
            ).pack(side="left")

        self.grilla = Grilla(izquierda, self.columnas, alto=18)
        self.grilla.pack(fill="both", expand=True)
        self.grilla.al_seleccionar(self._al_seleccionar)

        self.formulario = Formulario(derecha, self.campos)
        self.formulario.pack(fill="x")

        botones = ttk.Frame(derecha)
        botones.pack(fill="x", pady=(12, 0))
        botones.columnconfigure((0, 1), weight=1, uniform="botones")
        ttk.Button(botones, text="Nuevo", command=self.nuevo).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        ttk.Button(botones, text="Guardar", command=self._guardar).grid(row=0, column=1, sticky="ew", padx=(2, 0))
        texto_baja = "Dar de baja" if self.con_baja_logica else "Eliminar"
        self._boton_baja = ttk.Button(botones, text=texto_baja, command=self._dar_de_baja)
        self._boton_baja.grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=(4, 0))
        self._boton_reactivar = ttk.Button(botones, text="Reactivar", command=self._reactivar)
        if self.con_baja_logica:
            self._boton_reactivar.grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=(4, 0))

        self.acciones_extra = ttk.Frame(derecha)
        """Lugar para botones propios de cada pantalla (ej. "Historial de precios")."""
        self.acciones_extra.pack(fill="x", pady=(12, 0))

        self.estado = ttk.Label(derecha, text="", foreground="gray30", wraplength=280)
        self.estado.pack(fill="x", pady=(12, 0))

    # --- Acciones ------------------------------------------------------------------------------------

    def refrescar(self, seleccionar: Any | None = None) -> None:
        registros = self.obtener_registros(self._mostrar_inactivos.get(), self._texto.get().strip())
        self._registros = {str(r.id): r for r in registros}
        self.grilla.cargar(registros, self.valores_fila, atenuar=lambda r: not self.esta_activo(r))
        if seleccionar is not None:
            self.grilla.seleccionar(seleccionar)

    def nuevo(self) -> None:
        self.actual = None
        self.grilla.deseleccionar()
        self.formulario.limpiar()
        self._actualizar_botones()
        self.estado.configure(text="Completá los datos y presioná Guardar para dar de alta.")

    def _al_seleccionar(self, clave: str) -> None:
        self.actual = self._registros.get(clave)
        if self.actual is None:
            return
        self.formulario.cargar(self.a_formulario(self.actual))
        self._actualizar_botones()
        estado = "" if self.esta_activo(self.actual) else " (dado de baja)"
        self.estado.configure(text=f"Modificando: {self.descripcion(self.actual)}{estado}")

    def _actualizar_botones(self) -> None:
        hay = self.actual is not None
        activo = hay and self.esta_activo(self.actual)
        self._boton_baja.configure(state="normal" if activo or (hay and not self.con_baja_logica) else "disabled")
        self._boton_reactivar.configure(state="normal" if hay and not activo else "disabled")

    def _guardar(self) -> None:
        def guardar() -> Any:
            entidad = self.desde_formulario(self.formulario.valores(), self.actual)
            return self.guardar_registro(entidad)

        es_alta = self.actual is None
        guardado = ejecutar_con_manejo_de_errores(guardar, self)
        if guardado is None:
            return  # el error ya se mostró; el formulario conserva lo escrito para corregirlo
        self.refrescar(seleccionar=guardado.id)
        self._al_seleccionar(str(guardado.id))
        mostrar_info("Se dio de alta correctamente." if es_alta else "Se guardaron los cambios.", "Listo", self)

    def _dar_de_baja(self) -> None:
        if self.actual is None:
            return
        accion = "dar de baja" if self.con_baja_logica else "eliminar"
        if not confirmar(f"¿Seguro que querés {accion} «{self.descripcion(self.actual)}»?", padre=self):
            return
        registro = self.actual
        if ejecutar_con_manejo_de_errores(lambda: self.dar_de_baja_registro(registro) or True, self):
            self.refrescar(seleccionar=registro.id)
            if self.con_baja_logica and self.grilla.seleccionado() == str(registro.id):
                self._al_seleccionar(str(registro.id))
            else:
                self.nuevo()

    def _reactivar(self) -> None:
        if self.actual is None:
            return
        registro = self.actual
        if ejecutar_con_manejo_de_errores(lambda: self.reactivar_registro(registro) or True, self):
            self.refrescar(seleccionar=registro.id)
            self._al_seleccionar(str(registro.id))
