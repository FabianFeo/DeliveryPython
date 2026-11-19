"""Gestión de la capacidad e inventario de la Bodega Central."""

from math import isfinite

from .paquete import Paquete


class Bodega:
    """Representa la unica Bodega Central de CityDelivery."""

    def __init__(self, direccion: str, capacidad_max_peso: float,
                 capacidad_max_volumen: float):
        if not isinstance(direccion, str) or not direccion.strip():
            raise ValueError('La bodega necesita una dirección.')
        for nombre, valor in (('peso', capacidad_max_peso),
                              ('volumen', capacidad_max_volumen)):
            if (isinstance(valor, bool)
                    or not isinstance(valor, (int, float))
                    or not isfinite(valor)
                    or valor <= 0):
                raise ValueError(f'Capacidad máxima de {nombre} inválida.')

        self.direccion = direccion.strip()
        self.capacidad_max_peso = float(capacidad_max_peso)
        self.capacidad_max_volumen = float(capacidad_max_volumen)
        self.paquetes: list[Paquete] = []

    def calcular_peso_ocupado(self) -> float:
        return sum(paquete.peso for paquete in self.paquetes)

    def calcular_volumen_ocupado(self) -> float:
        return sum(paquete.volumen for paquete in self.paquetes)

    def puede_almacenar(self, paquete: Paquete) -> bool:
        if not isinstance(paquete, Paquete):
            raise TypeError('Se esperaba un objeto Paquete.')
        return (self.calcular_peso_ocupado() + paquete.peso
                <= self.capacidad_max_peso + 1e-9
                and self.calcular_volumen_ocupado() + paquete.volumen
                <= self.capacidad_max_volumen + 1e-9)

    def agregar_paquete(self, paquete: Paquete) -> bool:
        if not isinstance(paquete, Paquete):
            raise TypeError('Se esperaba un objeto Paquete.')

        # No modificar un paquete que ya está almacenado si lo registran dos veces.
        if any(guardado is paquete for guardado in self.paquetes):
            return False
        if any(guardado.codigo == paquete.codigo for guardado in self.paquetes):
            paquete.registrar_incidencia('RECHAZADO', 'Código de paquete duplicado')
            return False
        if not paquete.esta_pendiente():
            return False
        if not self.puede_almacenar(paquete):
            paquete.registrar_incidencia(
                'RECHAZADO', 'Excede el límite de peso o volumen de la bodega'
            )
            return False

        self.paquetes.append(paquete)
        return True

    def retirar_paquete(self, paquete: Paquete) -> bool:
        """Retira mercancía al salir a reparto; la ruta actualizará su estado."""
        if paquete not in self.paquetes:
            return False
        self.paquetes.remove(paquete)
        return True

    def consultar_inventario(self) -> list[Paquete]:
        """Devuelve una copia de la lista para proteger el inventario interno."""
        return list(self.paquetes)
