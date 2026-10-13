"""Excepciones comunes a todos los módulos.

Los servicios lanzan estas excepciones y la interfaz las muestra al usuario
(ver `src/ui/componentes.py::mostrar_error`).
"""


class ErrorDeNegocio(Exception):
    """Base de todos los errores que se le muestran al usuario."""


class ValidacionError(ErrorDeNegocio):
    """Un dato ingresado no cumple una regla (campo vacío, número negativo, etc.)."""


class EntidadDuplicadaError(ErrorDeNegocio):
    """Se intentó guardar algo que ya existe (mismo SKU, mismo CUIT, etc.)."""


class EntidadNoEncontradaError(ErrorDeNegocio):
    """Se buscó por id algo que no existe."""


class EntidadEnUsoError(ErrorDeNegocio):
    """Se intentó borrar algo que otros registros siguen usando."""
