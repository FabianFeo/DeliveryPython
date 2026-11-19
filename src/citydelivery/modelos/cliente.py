"""Jerarquía Cliente del UML de CityDelivery."""

from abc import ABC, abstractmethod
from datetime import date, timedelta
from .zona import Zona


class Cliente(ABC):
    def __init__(self, id_cliente: str, nombre: str, direccion: str, zona: Zona):
        if not id_cliente or not nombre or not direccion:
            raise ValueError('El cliente necesita ID, nombre y dirección.')
        if not isinstance(zona, Zona):
            raise ValueError('La zona del cliente debe ser un objeto Zona.')
        self.id = id_cliente
        self.nombre = nombre
        self.direccion = direccion
        self.zona = zona

    @abstractmethod
    def tiene_suscripcion_activa(self, fecha_consulta: date) -> bool:
        pass

    @abstractmethod
    def obtener_prioridad(self, fecha_consulta: date) -> int:
        pass


class ClientePremium(Cliente):
    def __init__(self, id_cliente: str, nombre: str, direccion: str, zona: Zona,
                 fecha_compra_suscripcion: date | None = None,
                 duracion_suscripcion_dias: int | None = None,
                 suscripcion_activa_declarada: bool | None = None):
        super().__init__(id_cliente, nombre, direccion, zona)
        if (fecha_compra_suscripcion is None) != (duracion_suscripcion_dias is None):
            raise ValueError('La fecha de compra y la duración deben venir juntas.')
        if fecha_compra_suscripcion is not None and not isinstance(fecha_compra_suscripcion, date):
            raise ValueError('La fecha de compra debe ser de tipo date.')
        if duracion_suscripcion_dias is not None and (
                type(duracion_suscripcion_dias) is not int or duracion_suscripcion_dias <= 0):
            raise ValueError('La duración debe ser un entero positivo en días.')
        if (suscripcion_activa_declarada is not None
                and not isinstance(suscripcion_activa_declarada, bool)):
            raise ValueError('suscripcionActiva debe ser verdadero o falso.')
        self.fecha_compra_suscripcion = fecha_compra_suscripcion
        self.duracion_suscripcion_dias = duracion_suscripcion_dias
        self.suscripcion_activa_declarada = suscripcion_activa_declarada

    def calcular_vencimiento(self) -> date | None:
        if self.fecha_compra_suscripcion is None:
            return None
        return self.fecha_compra_suscripcion + timedelta(days=self.duracion_suscripcion_dias)

    def tiene_suscripcion_activa(self, fecha_consulta: date) -> bool:
        vencimiento = self.calcular_vencimiento()
        if vencimiento is not None:
            return self.fecha_compra_suscripcion <= fecha_consulta < vencimiento
        # Compatibilidad con el JSON de ejemplo, que solo trae suscripcionActiva.
        return self.suscripcion_activa_declarada is True

    def obtener_prioridad(self, fecha_consulta: date) -> int:
        return 1 if self.tiene_suscripcion_activa(fecha_consulta) else 2


class ClienteStandard(Cliente):
    def tiene_suscripcion_activa(self, fecha_consulta: date) -> bool:
        return False

    def obtener_prioridad(self, fecha_consulta: date) -> int:
        return 2
