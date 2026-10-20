"""Punto de entrada: `python main.py` desde la raíz del proyecto."""

from src.persistencia.conexion import BaseDeDatos
from src.ui.ventana_principal import VentanaPrincipal


def main() -> None:
    BaseDeDatos().inicializar_esquema()
    VentanaPrincipal().mainloop()


if __name__ == "__main__":
    main()
