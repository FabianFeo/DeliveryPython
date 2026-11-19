"""Clase Zona del UML de CityDelivery."""

from datetime import date
from math import isfinite


class Zona:
    def __init__(self, id_zona: str, nombre: str,
                 distancia_desde_bodega_km: float, acceso_camiones_pesados: bool):
        if not id_zona or not nombre:
            raise ValueError('La zona necesita ID y nombre.')
        if (not isinstance(distancia_desde_bodega_km, (int, float))
                or isinstance(distancia_desde_bodega_km, bool)
                or not isfinite(distancia_desde_bodega_km)
                or distancia_desde_bodega_km < 0):
            raise ValueError('La distancia de la zona debe ser no negativa.')
        if not isinstance(acceso_camiones_pesados, bool):
            raise ValueError('El acceso de camiones debe ser verdadero o falso.')
        self.id = id_zona
        self.nombre = nombre
        self.distancia_desde_bodega_km = float(distancia_desde_bodega_km)
        self.acceso_camiones_pesados = acceso_camiones_pesados

    def permite_camion_pesado(self, cliente, fecha_consulta: date) -> bool:
        # Regla confirmada con el profesor:
        # se prohíbe si la zona restringe Y la suscripción está vigente.
        return (self.acceso_camiones_pesados
                or not cliente.tiene_suscripcion_activa(fecha_consulta))
