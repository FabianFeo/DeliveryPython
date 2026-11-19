"""Paquete y transiciones de estado definidos en el UML de CityDelivery."""

from datetime import date
from math import isfinite

from .cliente import Cliente


class Paquete:
    """Mercancia con destinatario, estado y motivo de incidencia."""

    TRANSICIONES = {
        'PENDIENTE': {'ASIGNADO', 'RECHAZADO'},
        'ASIGNADO': {'PENDIENTE', 'EN_RUTA'},
        'EN_RUTA': {'ENTREGADO'},
        'ENTREGADO': set(),
        'RECHAZADO': set(),
    }

    def __init__(self, codigo: str, peso: float, volumen: float,
                 cliente_destino: Cliente):
        if not isinstance(codigo, str) or not codigo.strip():
            raise ValueError('El paquete necesita un código válido.')
        for nombre, valor in (('peso', peso), ('volumen', volumen)):
            if (isinstance(valor, bool)
                    or not isinstance(valor, (int, float))
                    or not isfinite(valor)
                    or valor <= 0):
                raise ValueError(f'El {nombre} del paquete debe ser mayor que cero.')
        if not isinstance(cliente_destino, Cliente):
            raise ValueError('El destinatario debe ser un objeto Cliente.')

        self.codigo = codigo.strip()
        self.peso = float(peso)
        self.volumen = float(volumen)
        self.cliente_destino = cliente_destino
        self.estado = 'PENDIENTE'
        self.motivo_incidencia = ''

    def cambiar_estado(self, nuevo_estado: str) -> bool:
        """Impide saltos invalidos, p. ej. PENDIENTE -> ENTREGADO."""
        if nuevo_estado not in self.TRANSICIONES.get(self.estado, set()):
            return False
        self.estado = nuevo_estado
        self.motivo_incidencia = ''
        return True

    def esta_asignado(self) -> bool:
        return self.estado in ('ASIGNADO', 'EN_RUTA', 'ENTREGADO')

    def esta_pendiente(self) -> bool:
        return self.estado == 'PENDIENTE'

    def registrar_incidencia(self, estado: str, motivo: str) -> bool:
        """Guarda motivo de rechazo o de paquete pendiente sin vehículo."""
        if not isinstance(motivo, str) or not motivo.strip():
            raise ValueError('Debe indicar el motivo de la incidencia.')
        if estado == 'PENDIENTE' and self.estado == 'PENDIENTE':
            self.motivo_incidencia = motivo.strip()
            return True
        if estado == 'RECHAZADO' and self.cambiar_estado('RECHAZADO'):
            self.motivo_incidencia = motivo.strip()
            return True
        return False

    def obtener_prioridad(self, fecha_consulta: date) -> int:
        return self.cliente_destino.obtener_prioridad(fecha_consulta)
