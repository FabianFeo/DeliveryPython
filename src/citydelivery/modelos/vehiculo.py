"""Jerarquía de vehículos de CityDelivery, según el UML de 13 clases.

Los estados de reserva se consultan a las rutas, sin duplicar listas de flota.
"""
from abc import ABC, abstractmethod
from datetime import date
from math import isfinite

from .cliente import Cliente
from .paquete import Paquete


class Vehiculo(ABC):
    def __init__(self, identificador: str, capacidad_max_peso: float,
                 capacidad_max_volumen: float, habilitado: bool = True):
        if not isinstance(identificador, str) or not identificador.strip():
            raise ValueError('El vehiculo necesita un identificador valido.')
        for nombre, valor in (('peso', capacidad_max_peso),
                              ('volumen', capacidad_max_volumen)):
            if (isinstance(valor, bool) or not isinstance(valor, (int, float))
                    or not isfinite(valor) or valor <= 0):
                raise ValueError(f'La capacidad de {nombre} debe ser positiva.')
        if not isinstance(habilitado, bool):
            raise ValueError('habilitado debe ser True o False.')

        self.identificador = identificador.strip()
        self.capacidad_max_peso = float(capacidad_max_peso)
        self.capacidad_max_volumen = float(capacidad_max_volumen)
        self.carga_actual: list[Paquete] = []
        self.habilitado = habilitado

    def esta_disponible(self, rutas: list) -> bool:
        # Ruta se implementa en la siguiente seccion.
        # Una ruta PLANEADA reserva el vehiculo; EN_RUTA lo mantiene ocupado.
        return self.habilitado and not any(
            ruta.vehiculo is self and ruta.estado in ('PLANEADA', 'EN_RUTA')
            for ruta in rutas
        )

    def verificar_capacidad(self, paquete: Paquete) -> bool:
        if not isinstance(paquete, Paquete):
            raise TypeError('Se esperaba un objeto Paquete.')
        return (
            self.calcular_peso_actual() + paquete.peso
            <= self.capacidad_max_peso + 1e-9
            and self.calcular_volumen_actual() + paquete.volumen
            <= self.capacidad_max_volumen + 1e-9
        )

    def puede_cargar(self, paquete: Paquete) -> bool:
        # Regla heredada por vans y camiones; la motocicleta la especializa.
        return isinstance(paquete, Paquete)

    def puede_entregar(self, cliente: Cliente, fecha_consulta: date) -> bool:
        # La restriccion territorial especial solo corresponde a CamionPesado.
        return isinstance(cliente, Cliente)

    def cargar_paquete(self, paquete: Paquete, fecha_consulta: date) -> bool:
        # Sin clases ni metodos extra: se valida en los metodos del UML.
        if not isinstance(paquete, Paquete) or not self.habilitado:
            return False
        if not paquete.esta_pendiente():
            return False
        if any(p is paquete or p.codigo == paquete.codigo
               for p in self.carga_actual):
            return False
        if not self.puede_cargar(paquete):
            return False
        if not self.verificar_capacidad(paquete):
            return False
        if not self.puede_entregar(paquete.cliente_destino, fecha_consulta):
            return False
        if not paquete.cambiar_estado('ASIGNADO'):
            return False
        self.carga_actual.append(paquete)
        return True

    def descargar_paquete(self, paquete: Paquete) -> bool:
        # Se descarga al completar la entrega o despues de cancelar
        # una asignacion (Paquete debe estar de nuevo PENDIENTE).
        if paquete not in self.carga_actual:
            return False
        if paquete.estado not in ('ENTREGADO', 'PENDIENTE'):
            return False
        self.carga_actual.remove(paquete)
        return True

    def calcular_peso_actual(self) -> float:
        return sum(paquete.peso for paquete in self.carga_actual)

    def calcular_volumen_actual(self) -> float:
        return sum(paquete.volumen for paquete in self.carga_actual)

    @abstractmethod
    def calcular_costo(self, km: float) -> float:
        pass


class Motocicleta(Vehiculo):
    def __init__(self, identificador: str, capacidad_max_peso: float,
                 capacidad_max_volumen: float, costo_por_kilometro: float,
                 peso_maximo_por_paquete_kg: float = 4.99,
                 habilitado: bool = True):
        super().__init__(identificador, capacidad_max_peso,
                         capacidad_max_volumen, habilitado)
        if (isinstance(costo_por_kilometro, bool)
                or not isinstance(costo_por_kilometro, (int, float))
                or not isfinite(costo_por_kilometro)
                or costo_por_kilometro < 0):
            raise ValueError('Tarifa por kilometro invalida.')
        if (isinstance(peso_maximo_por_paquete_kg, bool)
                or not isinstance(peso_maximo_por_paquete_kg, (int, float))
                or not isfinite(peso_maximo_por_paquete_kg)
                or peso_maximo_por_paquete_kg <= 0):
            raise ValueError('Limite de peso individual invalido.')
        self.costo_por_kilometro = float(costo_por_kilometro)
        self.peso_maximo_por_paquete_kg = float(peso_maximo_por_paquete_kg)

    def puede_cargar(self, paquete: Paquete) -> bool:
        return (isinstance(paquete, Paquete)
                and paquete.peso < 5.0
                and paquete.peso <= self.peso_maximo_por_paquete_kg)

    def calcular_costo(self, km: float) -> float:
        if isinstance(km, bool) or not isinstance(km, (int, float)) or not isfinite(km) or km < 0:
            raise ValueError('Distancia invalida.')
        return float(km) * self.costo_por_kilometro


class VanReparto(Vehiculo):
    def __init__(self, identificador: str, capacidad_max_peso: float,
                 capacidad_max_volumen: float, costo_por_kg_km: float,
                 habilitado: bool = True):
        super().__init__(identificador, capacidad_max_peso,
                         capacidad_max_volumen, habilitado)
        if (isinstance(costo_por_kg_km, bool)
                or not isinstance(costo_por_kg_km, (int, float))
                or not isfinite(costo_por_kg_km)
                or costo_por_kg_km < 0):
            raise ValueError('Tarifa por kg-km invalida.')
        self.costo_por_kg_km = float(costo_por_kg_km)

    def calcular_costo(self, km: float) -> float:
        if isinstance(km, bool) or not isinstance(km, (int, float)) or not isfinite(km) or km < 0:
            raise ValueError('Distancia invalida.')
        # Cada vehiculo tendra solo una ruta reservada/activa a la vez.
        # Asi la carga_actual pertenece a esa ruta; no a otras rutas historicas.
        return self.calcular_peso_actual() * float(km) * self.costo_por_kg_km


class CamionPesado(Vehiculo):
    def __init__(self, identificador: str, capacidad_max_peso: float,
                 capacidad_max_volumen: float, tarifa_base: float,
                 impuesto_ambiental: float, habilitado: bool = True):
        super().__init__(identificador, capacidad_max_peso,
                         capacidad_max_volumen, habilitado)
        for nombre, valor in (('tarifa_base', tarifa_base),
                              ('impuesto_ambiental', impuesto_ambiental)):
            if (isinstance(valor, bool) or not isinstance(valor, (int, float))
                    or not isfinite(valor) or valor < 0):
                raise ValueError(f'{nombre}: valor invalido.')
        self.tarifa_base = float(tarifa_base)
        self.impuesto_ambiental = float(impuesto_ambiental)

    def puede_entregar(self, cliente: Cliente, fecha_consulta: date) -> bool:
        return (isinstance(cliente, Cliente)
                and cliente.zona.permite_camion_pesado(cliente, fecha_consulta))

    def calcular_costo(self, km: float) -> float:
        if isinstance(km, bool) or not isinstance(km, (int, float)) or not isfinite(km) or km < 0:
            raise ValueError('Distancia invalida.')
        # Cobro fijo por viaje, independientemente de los kilometros.
        return self.tarifa_base + self.impuesto_ambiental
