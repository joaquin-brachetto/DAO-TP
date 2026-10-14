"""Entidades de maestros (P1 y P2): ubicaciones, categorías, productos y proveedores.

Cada entidad sabe validar sus propios datos (`validar()`); las reglas que
necesitan consultar la base, como los duplicados de V4, están en
`src/servicios/maestros_service.py`.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from src.excepciones import ValidacionError

CENTAVO = Decimal("0.01")


def a_dinero(valor: Decimal | str | int) -> Decimal:
    """Normaliza un importe a centavos."""
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _texto_obligatorio(valor: str | None, campo: str) -> str:
    texto = (valor or "").strip()
    if not texto:
        raise ValidacionError(f"El campo «{campo}» es obligatorio.")
    return texto


def _texto_opcional(valor: str | None) -> str | None:
    texto = (valor or "").strip()
    return texto or None


# --- Ubicaciones (P1) ---------------------------------------------------------------


class TipoUbicacion(StrEnum):
    SUCURSAL = "SUCURSAL"
    CD = "CD"


@dataclass(kw_only=True)
class Ubicacion(ABC):
    """Lugar que tiene stock: una sucursal (local) o el Centro de Distribución."""

    codigo: str
    nombre: str
    direccion: str | None = None
    telefono: str | None = None
    activa: bool = True
    id: int | None = None

    @property
    @abstractmethod
    def tipo(self) -> TipoUbicacion: ...

    def es_centro_distribucion(self) -> bool:
        return self.tipo == TipoUbicacion.CD

    def validar(self) -> None:
        self.codigo = _texto_obligatorio(self.codigo, "Código").upper()
        self.nombre = _texto_obligatorio(self.nombre, "Nombre")
        self.direccion = _texto_opcional(self.direccion)
        self.telefono = _texto_opcional(self.telefono)


@dataclass(kw_only=True)
class Sucursal(Ubicacion):
    """Local que vende al público. El punto de venta numera sus comprobantes."""

    punto_venta: int

    @property
    def tipo(self) -> TipoUbicacion:
        return TipoUbicacion.SUCURSAL

    def validar(self) -> None:
        super().validar()
        if not isinstance(self.punto_venta, int) or self.punto_venta <= 0:
            raise ValidacionError("El punto de venta debe ser un número entero mayor a cero.")


@dataclass(kw_only=True)
class CentroDistribucion(Ubicacion):
    """Depósito central que abastece a las sucursales."""

    capacidad_m3: float | None = None

    @property
    def tipo(self) -> TipoUbicacion:
        return TipoUbicacion.CD

    def validar(self) -> None:
        super().validar()
        if self.capacidad_m3 is not None and self.capacidad_m3 <= 0:
            raise ValidacionError("La capacidad del Centro de Distribución debe ser mayor a cero.")


# --- Categorías y productos (P2) ----------------------------------------------------------


@dataclass
class Categoria:
    nombre: str
    descripcion: str | None = None
    id: int | None = None

    def validar(self) -> None:
        self.nombre = _texto_obligatorio(self.nombre, "Nombre")
        self.descripcion = _texto_opcional(self.descripcion)


@dataclass
class Producto:
    sku: str
    nombre: str
    categoria_id: int
    costo_actual: Decimal
    precio_venta_actual: Decimal
    codigo_barras: str | None = None
    descripcion: str | None = None
    unidad_medida: str = "UN"
    activo: bool = True
    id: int | None = None

    def validar(self) -> None:
        self.sku = _texto_obligatorio(self.sku, "SKU").upper()
        self.nombre = _texto_obligatorio(self.nombre, "Nombre")
        self.codigo_barras = _texto_opcional(self.codigo_barras)
        if self.codigo_barras is not None and not self.codigo_barras.isdigit():
            raise ValidacionError("El código de barras solo puede tener números.")
        self.descripcion = _texto_opcional(self.descripcion)
        self.unidad_medida = _texto_obligatorio(self.unidad_medida, "Unidad de medida").upper()
        if not self.categoria_id:
            raise ValidacionError("Hay que elegir una categoría.")
        self.costo_actual = a_dinero(self.costo_actual)
        self.precio_venta_actual = a_dinero(self.precio_venta_actual)
        if self.costo_actual < 0 or self.precio_venta_actual < 0:
            raise ValidacionError("El costo y el precio de venta no pueden ser negativos.")

    def margen_unitario(self) -> Decimal:
        """Ganancia por unidad al precio y costo actuales (negativa si se vende a pérdida)."""
        return a_dinero(self.precio_venta_actual - self.costo_actual)

    def margen_porcentual(self) -> Decimal | None:
        """Margen sobre el costo, en porcentaje. None si el costo es cero."""
        if self.costo_actual == 0:
            return None
        return a_dinero(self.margen_unitario() * 100 / self.costo_actual)


@dataclass
class HistorialPrecio:
    """Costo y precio de un producto durante un período. El vigente tiene `fecha_hasta` None."""

    producto_id: int
    costo: Decimal
    precio_venta: Decimal
    fecha_desde: datetime = field(default_factory=datetime.now)
    fecha_hasta: datetime | None = None
    id: int | None = None

    def esta_vigente(self) -> bool:
        return self.fecha_hasta is None


@dataclass
class StockMinimo:
    """Nivel mínimo de existencia de un producto en una ubicación (P2).

    Se considera que el producto está "en stock mínimo" cuando el disponible
    llega al mínimo o queda por debajo.
    """

    producto_id: int
    ubicacion_id: int
    cantidad_minima: int

    def validar(self) -> None:
        if not isinstance(self.cantidad_minima, int) or self.cantidad_minima < 0:
            raise ValidacionError("El stock mínimo debe ser un número entero mayor o igual a cero.")

    def esta_en_minimo(self, disponible: int) -> bool:
        return self.cantidad_minima > 0 and disponible <= self.cantidad_minima

    def faltante(self, disponible: int) -> int:
        """Unidades que faltan para volver a estar por encima del mínimo (0 si no falta nada)."""
        return max(self.cantidad_minima - disponible, 0)


# --- Proveedores (P2) ---------------------------------------------------------------------


def normalizar_cuit(cuit: str) -> str:
    """Deja solo los dígitos: '20-12345678-6' -> '20123456786'."""
    return re.sub(r"[\s-]", "", cuit or "")


def cuit_es_valido(cuit: str) -> bool:
    """Verifica que tenga 11 dígitos y que el dígito verificador sea correcto."""
    if len(cuit) != 11 or not cuit.isdigit():
        return False
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    resto = sum(int(digito) * peso for digito, peso in zip(cuit[:10], pesos)) % 11
    verificador = 0 if resto == 0 else 11 - resto
    return verificador != 10 and verificador == int(cuit[10])


def formatear_cuit(cuit: str) -> str:
    """'20123456786' -> '20-12345678-6'."""
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}" if len(cuit) == 11 else cuit


@dataclass
class Proveedor:
    cuit: str
    razon_social: str
    email: str | None = None
    telefono: str | None = None
    direccion: str | None = None
    activo: bool = True
    id: int | None = None

    def validar(self) -> None:
        self.cuit = normalizar_cuit(self.cuit)
        if not cuit_es_valido(self.cuit):
            raise ValidacionError("El CUIT no es válido: deben ser 11 dígitos con el verificador correcto.")
        self.razon_social = _texto_obligatorio(self.razon_social, "Razón social")
        self.email = _texto_opcional(self.email)
        if self.email is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.email):
            raise ValidacionError("El email no tiene un formato válido.")
        self.telefono = _texto_opcional(self.telefono)
        self.direccion = _texto_opcional(self.direccion)


@dataclass
class ProductoProveedor:
    """Un proveedor que vende un producto, con su código y condiciones."""

    producto_id: int
    proveedor_id: int
    codigo_en_proveedor: str | None = None
    costo_pactado: Decimal | None = None
    plazo_entrega_dias: int | None = None

    def validar(self) -> None:
        self.codigo_en_proveedor = _texto_opcional(self.codigo_en_proveedor)
        if self.costo_pactado is not None:
            self.costo_pactado = a_dinero(self.costo_pactado)
            if self.costo_pactado < 0:
                raise ValidacionError("El costo pactado no puede ser negativo.")
        if self.plazo_entrega_dias is not None and self.plazo_entrega_dias < 0:
            raise ValidacionError("El plazo de entrega no puede ser negativo.")
