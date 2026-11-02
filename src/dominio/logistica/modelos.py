"""Clases de dominio de logística (turco): bultos, remitos, precintos, despachos,
recepciones y el patrón State para el ciclo de vida del bulto (P4, P5, P6, V1, V2).

El objeto `Bulto` mantiene en `self.estado` una instancia de una subclase concreta
de `EstadoBulto(ABC)` y delega en ella todas las operaciones dependientes del estado:
    Preparado -> Precintado -> EnTransito -> Recibido -> Verificado | Rechazado

Cada transición válida registra un `CambioEstadoBulto` inmutable (`frozen=True`).
Cualquier operación no permitida en el estado actual lanza `TransicionInvalidaError`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from src.excepciones import ValidacionError


class TransicionInvalidaError(ValidacionError):
    """Se intentó realizar una operación o transición de estado inválida para el bulto o remito."""


class CodigoEstadoBulto(StrEnum):
    PREPARADO = "PREPARADO"
    PRECINTADO = "PRECINTADO"
    EN_TRANSITO = "EN_TRANSITO"
    RECIBIDO = "RECIBIDO"
    VERIFICADO = "VERIFICADO"
    RECHAZADO = "RECHAZADO"


class EstadoRemito(StrEnum):
    EMITIDO = "EMITIDO"
    EN_TRANSITO = "EN_TRANSITO"
    RECIBIDO = "RECIBIDO"
    VERIFICADO = "VERIFICADO"
    VERIFICADO_CON_RECHAZOS = "VERIFICADO_CON_RECHAZOS"


class ResultadoControl(StrEnum):
    VERIFICADO = "VERIFICADO"
    RECHAZADO = "RECHAZADO"


NOMBRES_ESTADO_LOGISTICA: dict[str, str] = {
    "PREPARADO": "Preparado",
    "PRECINTADO": "Precintado",
    "EN_TRANSITO": "En tránsito",
    "RECIBIDO": "Recibido",
    "VERIFICADO": "Verificado",
    "RECHAZADO": "Rechazado",
    "EMITIDO": "Emitido",
    "VERIFICADO_CON_RECHAZOS": "Verificado con rechazos",
}


def nombre_estado_logistica(estado: EstadoBulto | StrEnum | str) -> str:
    """Nombre legible para mostrar en la interfaz de usuario."""
    clave = estado.nombre() if isinstance(estado, EstadoBulto) else str(estado)
    return NOMBRES_ESTADO_LOGISTICA.get(clave, clave)


def _entero_positivo(valor: int, campo: str = "cantidad") -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValidacionError(f"El campo «{campo}» debe ser un entero mayor a cero.")
    return valor


# === Patrón State (GoF): Ciclo de vida del Bulto ===============================================


class EstadoBulto(ABC):
    """Estado abstracto del ciclo de vida de un `Bulto`.

    Cada subclase concreta representa un estado del bulto y redefine únicamente
    las operaciones válidas desde ese estado. Las operaciones no permitidas
    heredan el comportamiento por defecto que lanza `TransicionInvalidaError`.
    """

    @abstractmethod
    def nombre(self) -> str:
        """Código canónico del estado (ej. 'PREPARADO', 'PRECINTADO', etc.)."""

    @abstractmethod
    def es_final(self) -> bool:
        """Indica si el estado es terminal (no admite nuevas transiciones)."""

    def agregar_producto(self, bulto: Bulto, producto_id: int, cantidad: int) -> None:
        raise TransicionInvalidaError(
            f"No se pueden agregar productos al bulto «{bulto.codigo}» porque está en estado "
            f"«{nombre_estado_logistica(self)}»."
        )

    def precintar(
        self,
        bulto: Bulto,
        precinto: Precinto,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        raise TransicionInvalidaError(
            f"No se puede precintar el bulto «{bulto.codigo}» desde el estado "
            f"«{nombre_estado_logistica(self)}»."
        )

    def despachar(
        self,
        bulto: Bulto,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        raise TransicionInvalidaError(
            f"No se puede despachar el bulto «{bulto.codigo}» desde el estado "
            f"«{nombre_estado_logistica(self)}» (debe estar Precintado)."
        )

    def recibir(
        self,
        bulto: Bulto,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        raise TransicionInvalidaError(
            f"No se puede recibir el bulto «{bulto.codigo}» desde el estado "
            f"«{nombre_estado_logistica(self)}» (debe estar En tránsito)."
        )

    def verificar(
        self,
        bulto: Bulto,
        usuario: str = "sistema",
        observacion: str = "",
        fecha_hora: datetime | None = None,
    ) -> None:
        raise TransicionInvalidaError(
            f"No se puede verificar el bulto «{bulto.codigo}» desde el estado "
            f"«{nombre_estado_logistica(self)}» (debe estar Recibido)."
        )

    def rechazar(
        self,
        bulto: Bulto,
        motivo: str,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        raise TransicionInvalidaError(
            f"No se puede rechazar el bulto «{bulto.codigo}» desde el estado "
            f"«{nombre_estado_logistica(self)}» (debe estar Recibido)."
        )

    def __eq__(self, otro: object) -> bool:
        if isinstance(otro, EstadoBulto):
            return self.nombre() == otro.nombre()
        if isinstance(otro, str):
            return self.nombre() == otro
        return False

    def __hash__(self) -> int:
        return hash(self.nombre())

    def __str__(self) -> str:
        return self.nombre()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class Preparado(EstadoBulto):
    """Estado inicial del bulto: admite cargar productos y colocar el precinto de seguridad."""

    def nombre(self) -> str:
        return CodigoEstadoBulto.PREPARADO.value

    def es_final(self) -> bool:
        return False

    def agregar_producto(self, bulto: Bulto, producto_id: int, cantidad: int) -> None:
        producto_id = _entero_positivo(producto_id, "producto_id")
        cantidad = _entero_positivo(cantidad, "cantidad")
        for detalle in bulto.detalles:
            if detalle.producto_id == producto_id:
                detalle.cantidad += cantidad
                return
        bulto.detalles.append(
            DetalleBulto(producto_id=producto_id, cantidad=cantidad, bulto_id=bulto.id)
        )

    def precintar(
        self,
        bulto: Bulto,
        precinto: Precinto,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        if not bulto.detalles:
            raise TransicionInvalidaError(
                f"No se puede precintar el bulto «{bulto.codigo}» porque no contiene productos."
            )
        if precinto is None or not isinstance(precinto, Precinto) or not precinto.numero.strip():
            raise ValidacionError("El bulto requiere un precinto de seguridad con número válido.")
        precinto.numero = precinto.numero.strip().upper()
        if bulto.id is not None:
            precinto.bulto_id = bulto.id
        bulto.precinto = precinto
        bulto._cambiar_estado(
            Precintado(),
            usuario=usuario,
            observacion=f"Precintado con N° {precinto.numero}",
            fecha_hora=fecha_hora or precinto.fecha_colocacion,
        )


class Precintado(EstadoBulto):
    """El bulto ya tiene su precinto colocado: está cerrado y listo para despachar desde el CD."""

    def nombre(self) -> str:
        return CodigoEstadoBulto.PRECINTADO.value

    def es_final(self) -> bool:
        return False

    def despachar(
        self,
        bulto: Bulto,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        if bulto.precinto is None or not bulto.precinto.numero.strip():
            raise TransicionInvalidaError(
                f"El bulto «{bulto.codigo}» no tiene un precinto asignado para despachar."
            )
        bulto._cambiar_estado(
            EnTransito(),
            usuario=usuario,
            observacion="Despachado desde CD",
            fecha_hora=fecha_hora,
        )


class EnTransito(EstadoBulto):
    """El bulto salió del CD y viaja hacia la sucursal destino."""

    def nombre(self) -> str:
        return CodigoEstadoBulto.EN_TRANSITO.value

    def es_final(self) -> bool:
        return False

    def recibir(
        self,
        bulto: Bulto,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        bulto._cambiar_estado(
            Recibido(),
            usuario=usuario,
            observacion="Recibido en sucursal destino",
            fecha_hora=fecha_hora,
        )


class Recibido(EstadoBulto):
    """El bulto llegó físicamente al local y aguarda la verificación de su precinto (P6, V1)."""

    def nombre(self) -> str:
        return CodigoEstadoBulto.RECIBIDO.value

    def es_final(self) -> bool:
        return False

    def verificar(
        self,
        bulto: Bulto,
        usuario: str = "sistema",
        observacion: str = "",
        fecha_hora: datetime | None = None,
    ) -> None:
        obs = observacion.strip() if observacion else "Precinto íntegro y verificado"
        bulto.motivo_rechazo = None
        bulto._cambiar_estado(
            Verificado(),
            usuario=usuario,
            observacion=obs,
            fecha_hora=fecha_hora,
        )

    def rechazar(
        self,
        bulto: Bulto,
        motivo: str,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        motivo_limpio = (motivo or "").strip()
        if not motivo_limpio:
            raise TransicionInvalidaError(
                f"Debe indicar el motivo de rechazo para el bulto «{bulto.codigo}»."
            )
        bulto.motivo_rechazo = motivo_limpio
        bulto._cambiar_estado(
            Rechazado(),
            usuario=usuario,
            observacion=motivo_limpio,
            fecha_hora=fecha_hora,
        )


class Verificado(EstadoBulto):
    """Estado final exitoso: el precinto estaba íntegro y coincidió; habilita el stock disponible (V1)."""

    def nombre(self) -> str:
        return CodigoEstadoBulto.VERIFICADO.value

    def es_final(self) -> bool:
        return True


class Rechazado(EstadoBulto):
    """Estado final de rechazo logístico: precinto violado o adulterado; va a merma y no habilita venta (V1)."""

    def nombre(self) -> str:
        return CodigoEstadoBulto.RECHAZADO.value

    def es_final(self) -> bool:
        return True


_CLASES_ESTADO_POR_NOMBRE: dict[str, type[EstadoBulto]] = {
    CodigoEstadoBulto.PREPARADO.value: Preparado,
    CodigoEstadoBulto.PRECINTADO.value: Precintado,
    CodigoEstadoBulto.EN_TRANSITO.value: EnTransito,
    CodigoEstadoBulto.RECIBIDO.value: Recibido,
    CodigoEstadoBulto.VERIFICADO.value: Verificado,
    CodigoEstadoBulto.RECHAZADO.value: Rechazado,
}


def estado_desde_nombre(valor: str | CodigoEstadoBulto | EstadoBulto) -> EstadoBulto:
    """Reconstruye la instancia de `EstadoBulto` correspondiente al código guardado en la base."""
    if isinstance(valor, EstadoBulto):
        return valor
    clave = str(valor).strip().upper()
    clase = _CLASES_ESTADO_POR_NOMBRE.get(clave)
    if clase is None:
        raise ValidacionError(f"Estado de bulto desconocido: «{valor}».")
    return clase()


# === Entidades de Dominio de Logística =========================================================


@dataclass
class DetalleBulto:
    producto_id: int
    cantidad: int
    id: int | None = None
    bulto_id: int | None = None

    def __post_init__(self) -> None:
        self.producto_id = _entero_positivo(self.producto_id, "producto_id")
        self.cantidad = _entero_positivo(self.cantidad, "cantidad")


@dataclass
class Precinto:
    numero: str
    fecha_colocacion: datetime = field(default_factory=datetime.now)
    usuario_colocacion: str = "sistema"
    id: int | None = None
    bulto_id: int | None = None

    def __post_init__(self) -> None:
        self.numero = (self.numero or "").strip().upper()
        if not self.numero:
            raise ValidacionError("El número de precinto no puede estar vacío.")
        self.usuario_colocacion = (self.usuario_colocacion or "sistema").strip() or "sistema"


@dataclass(frozen=True)
class CambioEstadoBulto:
    """Registro inmutable de una transición de estado de un bulto (V2)."""

    fecha_hora: datetime
    estado_anterior: str | None
    estado_nuevo: str
    usuario: str = "sistema"
    observacion: str = ""
    id: int | None = None
    bulto_id: int | None = None


@dataclass
class Bulto:
    """Contenedor físico armado en el CD que delega su comportamiento en `self.estado` (Patrón State)."""

    codigo: str
    remito_id: int | None = None
    fecha_creacion: datetime = field(default_factory=datetime.now)
    peso_kg: float | None = None
    estado: EstadoBulto = field(default_factory=Preparado)
    motivo_rechazo: str | None = None
    precinto: Precinto | None = None
    detalles: list[DetalleBulto] = field(default_factory=list)
    cambios_estado: list[CambioEstadoBulto] = field(default_factory=list)
    id: int | None = None

    def __post_init__(self) -> None:
        self.codigo = (self.codigo or "").strip().upper()
        if not self.codigo:
            raise ValidacionError("El código del bulto es obligatorio.")
        if self.peso_kg is not None and float(self.peso_kg) <= 0:
            raise ValidacionError("El peso del bulto debe ser mayor a cero.")
        if not isinstance(self.estado, EstadoBulto):
            self.estado = estado_desde_nombre(self.estado)

    @property
    def nombre_estado(self) -> str:
        return self.estado.nombre()

    @property
    def es_estado_final(self) -> bool:
        return self.estado.es_final()

    def total_unidades(self) -> int:
        return sum(detalle.cantidad for detalle in self.detalles)

    def historial(self) -> tuple[CambioEstadoBulto, ...]:
        """Devuelve una tupla inmutable con todos los cambios de estado del bulto (V2)."""
        return tuple(self.cambios_estado)

    # --- Operaciones delegadas al EstadoBulto actual (Patrón State) ---------------------------

    def agregar_producto(self, producto_id: int, cantidad: int) -> None:
        self.estado.agregar_producto(self, producto_id, cantidad)

    def precintar(
        self,
        precinto: Precinto,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        self.estado.precintar(self, precinto, usuario=usuario, fecha_hora=fecha_hora)

    def despachar(self, usuario: str = "sistema", fecha_hora: datetime | None = None) -> None:
        self.estado.despachar(self, usuario=usuario, fecha_hora=fecha_hora)

    def recibir(self, usuario: str = "sistema", fecha_hora: datetime | None = None) -> None:
        self.estado.recibir(self, usuario=usuario, fecha_hora=fecha_hora)

    def verificar(
        self,
        usuario: str = "sistema",
        observacion: str = "",
        fecha_hora: datetime | None = None,
    ) -> None:
        self.estado.verificar(self, usuario=usuario, observacion=observacion, fecha_hora=fecha_hora)

    def rechazar(
        self,
        motivo: str,
        usuario: str = "sistema",
        fecha_hora: datetime | None = None,
    ) -> None:
        self.estado.rechazar(self, motivo=motivo, usuario=usuario, fecha_hora=fecha_hora)

    def _cambiar_estado(
        self,
        nuevo_estado: EstadoBulto,
        usuario: str = "sistema",
        observacion: str = "",
        fecha_hora: datetime | None = None,
    ) -> CambioEstadoBulto:
        """Efectúa la transición de estado y agrega un registro inmutable al historial (V2)."""
        anterior = self.estado.nombre() if self.estado is not None else None
        cambio = CambioEstadoBulto(
            fecha_hora=fecha_hora or datetime.now(),
            estado_anterior=anterior,
            estado_nuevo=nuevo_estado.nombre(),
            usuario=(usuario or "sistema").strip() or "sistema",
            observacion=(observacion or "").strip(),
            bulto_id=self.id,
        )
        self.estado = nuevo_estado
        self.cambios_estado.append(cambio)
        return cambio


@dataclass
class Remito:
    """Documento de despacho que agrupa los bultos enviados desde el CD hacia una sucursal."""

    numero: str
    orden_reposicion_id: int
    origen_id: int
    destino_id: int
    fecha_emision: datetime = field(default_factory=datetime.now)
    estado: EstadoRemito = EstadoRemito.EMITIDO
    despacho_id: int | None = None
    bultos: list[Bulto] = field(default_factory=list)
    id: int | None = None

    def __post_init__(self) -> None:
        self.numero = (self.numero or "").strip().upper()
        if not self.numero:
            raise ValidacionError("El número de remito es obligatorio.")
        if self.origen_id == self.destino_id:
            raise ValidacionError("El origen y el destino del remito deben ser distintos.")
        if not isinstance(self.estado, EstadoRemito):
            self.estado = EstadoRemito(str(self.estado))

    def agregar_bulto(self, bulto: Bulto) -> None:
        if self.estado != EstadoRemito.EMITIDO:
            raise TransicionInvalidaError(
                f"No se pueden agregar bultos al remito «{self.numero}» en estado «{nombre_estado_logistica(self.estado)}»."
            )
        if self.id is not None:
            bulto.remito_id = self.id
        self.bultos.append(bulto)

    def cerrar_verificacion(self) -> EstadoRemito:
        """Cierra la verificación del remito cuando todos sus bultos están en estado final (V1)."""
        if not self.bultos:
            raise TransicionInvalidaError(
                f"El remito «{self.numero}» no tiene bultos cargados para verificar."
            )
        sin_procesar = [b.codigo for b in self.bultos if not b.es_estado_final]
        if sin_procesar:
            raise TransicionInvalidaError(
                f"No se puede cerrar el remito «{self.numero}»: faltan verificar o rechazar los bultos "
                f"{', '.join(sin_procesar)}."
            )
        hubo_rechazos = any(b.nombre_estado == CodigoEstadoBulto.RECHAZADO.value for b in self.bultos)
        self.estado = (
            EstadoRemito.VERIFICADO_CON_RECHAZOS if hubo_rechazos else EstadoRemito.VERIFICADO
        )
        return self.estado


@dataclass
class Despacho:
    """Salida física de uno o más remitos desde el Centro de Distribución (P5)."""

    fecha_hora_salida: datetime
    transportista: str
    patente: str
    usuario: str = "sistema"
    observaciones: str = ""
    remito_ids: list[int] = field(default_factory=list)
    id: int | None = None

    def __post_init__(self) -> None:
        self.transportista = (self.transportista or "").strip()
        self.patente = (self.patente or "").strip().upper()
        if not self.transportista:
            raise ValidacionError("El nombre del transportista es obligatorio.")
        if not self.patente:
            raise ValidacionError("La patente del vehículo es obligatoria.")
        self.usuario = (self.usuario or "sistema").strip() or "sistema"
        self.observaciones = (self.observaciones or "").strip()


@dataclass
class ControlBulto:
    """Resultado de inspeccionar el precinto de un bulto al recibirlo en la sucursal (P6, V1)."""

    bulto_id: int
    numero_precinto_leido: str
    precinto_integro: bool
    coincide_precinto: bool
    resultado: str
    observacion: str = ""
    fecha_hora_control: datetime = field(default_factory=datetime.now)
    id: int | None = None
    recepcion_id: int | None = None

    def __post_init__(self) -> None:
        self.numero_precinto_leido = (self.numero_precinto_leido or "").strip().upper()
        if not self.numero_precinto_leido:
            raise ValidacionError("Debe ingresar el número de precinto leído en la recepción.")
        self.precinto_integro = bool(self.precinto_integro)
        self.coincide_precinto = bool(self.coincide_precinto)
        self.resultado = str(self.resultado).strip().upper()
        if self.resultado not in (ResultadoControl.VERIFICADO.value, ResultadoControl.RECHAZADO.value):
            raise ValidacionError(f"Resultado de control inválido: «{self.resultado}».")
        self.observacion = (self.observacion or "").strip()

    def es_valido(self, precinto_esperado: str) -> bool:
        """Un bulto es válido únicamente si su precinto está íntegro y coincide con el colocado en el CD."""
        esperado = (precinto_esperado or "").strip().upper()
        return bool(self.precinto_integro) and bool(esperado) and self.numero_precinto_leido == esperado


@dataclass
class Recepcion:
    """Acta de recepción y verificación de un remito en la sucursal destino (P6, V1)."""

    remito_id: int
    fecha_hora_llegada: datetime
    recibido_por: str
    observaciones: str = ""
    cerrada: bool = False
    controles: list[ControlBulto] = field(default_factory=list)
    id: int | None = None

    def __post_init__(self) -> None:
        self.recibido_por = (self.recibido_por or "").strip()
        if not self.recibido_por:
            raise ValidacionError("Debe indicar quién recibió el remito en la sucursal.")
        self.observaciones = (self.observaciones or "").strip()
        self.cerrada = bool(self.cerrada)
