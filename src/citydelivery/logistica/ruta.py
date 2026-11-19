from datetime import date
from math import isfinite

from ..modelos.paquete import Paquete
from ..modelos.vehiculo import VanReparto, Vehiculo
from ..modelos.zona import Zona


class Ruta:
    def __init__(
        self, id_ruta: str, vehiculo: Vehiculo, zona: Zona, distancia_km: float
    ):
        if not isinstance(id_ruta, str) or not id_ruta.strip():
            raise ValueError("La ruta necesita un ID.")
        if not isinstance(vehiculo, Vehiculo):
            raise TypeError("Se esperaba un Vehiculo.")
        if not isinstance(zona, Zona):
            raise TypeError("Se esperaba una Zona.")
        if (
            isinstance(distancia_km, bool)
            or not isinstance(distancia_km, (int, float))
            or not isfinite(distancia_km)
            or distancia_km < 0
        ):
            raise ValueError("Distancia de ruta invalida.")

        self.id = id_ruta.strip()
        self.vehiculo = vehiculo
        self.zona = zona
        self.paquetes: list[Paquete] = []
        self.distancia_km = float(distancia_km)
        self.estado = "PLANEADA"

    def agregar_paquete(self, paquete: Paquete, fecha_consulta: date) -> bool:
        if self.estado != "PLANEADA" or not isinstance(paquete, Paquete):
            return False
        if paquete.cliente_destino.zona is not self.zona:
            return False
        if any(p is paquete or p.codigo == paquete.codigo for p in self.paquetes):
            return False
        if not self.vehiculo.cargar_paquete(paquete, fecha_consulta):
            return False
        self.paquetes.append(paquete)
        return True

    def validar_ruta(self, fecha_consulta: date) -> bool:
        if self.estado not in ("PLANEADA", "EN_RUTA") or not self.paquetes:
            return False
        if not self.vehiculo.habilitado:
            return False
        if len({p.codigo for p in self.paquetes}) != len(self.paquetes):
            return False
        if sum(p.peso for p in self.paquetes) > self.vehiculo.capacidad_max_peso + 1e-9:
            return False
        if (
            sum(p.volumen for p in self.paquetes)
            > self.vehiculo.capacidad_max_volumen + 1e-9
        ):
            return False
        esperado = "ASIGNADO" if self.estado == "PLANEADA" else "EN_RUTA"
        return all(
            p.estado == esperado
            and p in self.vehiculo.carga_actual
            and p.cliente_destino.zona is self.zona
            and self.vehiculo.puede_cargar(p)
            and self.vehiculo.puede_entregar(p.cliente_destino, fecha_consulta)
            for p in self.paquetes
        )

    def esta_activa(self) -> bool:
        return self.estado == "EN_RUTA"

    def ocupa_vehiculo(self) -> bool:
        return self.estado in ("PLANEADA", "EN_RUTA")

    def iniciar_ruta(self) -> bool:
        # Antes de iniciar, GestorDespachos debe llamar a validar_ruta(fecha).
        if self.estado != "PLANEADA" or not self.paquetes:
            return False
        if any(
            p.estado != "ASIGNADO" or p not in self.vehiculo.carga_actual
            for p in self.paquetes
        ):
            return False
        for p in self.paquetes:
            if not p.cambiar_estado("EN_RUTA"):
                return False
        self.estado = "EN_RUTA"
        return True

    def finalizar_ruta(self) -> bool:
        if self.estado != "EN_RUTA" or not self.paquetes:
            return False
        if any(
            p.estado != "EN_RUTA" or p not in self.vehiculo.carga_actual
            for p in self.paquetes
        ):
            return False
        for p in self.paquetes:
            if not p.cambiar_estado("ENTREGADO"):
                return False
            if not self.vehiculo.descargar_paquete(p):
                return False
        self.estado = "FINALIZADA"
        return True

    def calcular_costo(self) -> float:
        # La van calcula costo con el peso HISTORICO de esta ruta,
        # no con la carga del vehiculo (que se vacia al finalizar).
        if isinstance(self.vehiculo, VanReparto):
            return (
                sum(p.peso for p in self.paquetes)
                * self.distancia_km
                * self.vehiculo.costo_por_kg_km
            )
        return self.vehiculo.calcular_costo(self.distancia_km)

    def obtener_entregas(self) -> list[Paquete]:
        return list(self.paquetes)
