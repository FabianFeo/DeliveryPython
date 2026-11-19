"""Mejora local de despachos sin clases adicionales al UML.

Esta función es un auxiliar del algoritmo, NO un método de CityDelivery
ni de GestorDespachos. Su objetivo es rescatar paquetes pendientes mediante
una reasignación segura de una ruta PLANEADA a un vehículo libre.
No altera rutas EN_RUTA/FINALIZADA y no necesita geocodificación.
"""
from typing import TYPE_CHECKING

from ..modelos.paquete import Paquete
from ..modelos.vehiculo import Vehiculo, VanReparto
from .ruta import Ruta

if TYPE_CHECKING:
    from .gestor_despachos import GestorDespachos


def rescatar_pendientes(gestor: "GestorDespachos", nuevas: list[Ruta]) -> None:
    """Prioriza aumentar paquetes asignados; minimiza costo solo entre rescates."""
    # MEJORA LOCAL SIN GRAFO NI MÉTODOS NUEVOS EN EL UML.
    # Si quedó un paquete pendiente, una ruta PLANEADA puede cambiar de
    # vehículo hacia uno libre y compatible; el vehículo liberado puede
    # atender la nueva zona. Solo se aplica si AUMENTA las entregas.
    # Nunca se modifica una ruta EN_RUTA o FINALIZADA.
    def costo_proyectado(vehiculo: Vehiculo, paquetes: list[Paquete], kilometros: float) -> float:
        if isinstance(vehiculo, VanReparto):
            return (sum(p.peso for p in paquetes)
                    * kilometros * vehiculo.costo_por_kg_km)
        return vehiculo.calcular_costo(kilometros)

    def admite_carga_completa(vehiculo: Vehiculo, paquetes: list[Paquete]) -> bool:
        return (
            vehiculo.habilitado
            and not vehiculo.carga_actual
            and sum(p.peso for p in paquetes) <= vehiculo.capacidad_max_peso + 1e-9
            and sum(p.volumen for p in paquetes) <= vehiculo.capacidad_max_volumen + 1e-9
            and all(
                vehiculo.puede_cargar(p)
                and vehiculo.puede_entregar(p.cliente_destino, gestor.fecha_operacion)
                for p in paquetes
            )
        )

    def trasladar_ruta_planeada(ruta: Ruta, vehiculo_nuevo: Vehiculo) -> bool:
        """Transfiere carga usando los métodos públicos, con reversión."""
        anterior = ruta.vehiculo
        paquetes_ruta = list(ruta.paquetes)
        if ruta.estado != 'PLANEADA' or not paquetes_ruta:
            return False
        if not vehiculo_nuevo.esta_disponible(gestor.sistema.rutas):
            return False
        if not admite_carga_completa(vehiculo_nuevo, paquetes_ruta):
            return False
        try:
            for p in paquetes_ruta:
                if not p.cambiar_estado('PENDIENTE'):
                    raise RuntimeError('No se pudo desbloquear un paquete.')
                if not anterior.descargar_paquete(p):
                    raise RuntimeError('No se pudo descargar un paquete.')
            for p in paquetes_ruta:
                if not vehiculo_nuevo.cargar_paquete(p, gestor.fecha_operacion):
                    raise RuntimeError('No se pudo transferir un paquete.')
            ruta.vehiculo = vehiculo_nuevo
            if not ruta.validar_ruta(gestor.fecha_operacion):
                raise RuntimeError('La ruta reasignada no es válida.')
            return True
        except (ValueError, RuntimeError):
            # Volver al estado previo ante cualquier fallo de la transferencia.
            ruta.vehiculo = anterior
            for p in paquetes_ruta:
                if p in vehiculo_nuevo.carga_actual:
                    if p.estado == 'ASIGNADO' and not p.cambiar_estado('PENDIENTE'):
                        raise RuntimeError('No se pudo revertir el estado de un paquete.')
                    if not vehiculo_nuevo.descargar_paquete(p):
                        raise RuntimeError('No se pudo revertir la carga del sustituto.')
            for p in paquetes_ruta:
                if p in anterior.carga_actual:
                    if p.estado == 'PENDIENTE' and not p.cambiar_estado('ASIGNADO'):
                        raise RuntimeError('No se pudo restaurar el paquete original.')
                else:
                    if p.estado == 'ASIGNADO' and not p.cambiar_estado('PENDIENTE'):
                        raise RuntimeError('No se pudo revertir el estado de un paquete.')
                    if not anterior.cargar_paquete(p, gestor.fecha_operacion):
                        raise RuntimeError('No fue posible restablecer la ruta original.')
            return False

    # Una sola reasignación puede liberar un vehículo para otro destino.
    # Costos se usan para ELEGIR entre mejoras factibles, no como garantía
    # de óptimo global. Se conserva la prioridad del paquete pendiente.
    pendientes_rescate = sorted(
        gestor.obtener_paquetes_pendientes(),
        key=lambda p: (p.obtener_prioridad(gestor.fecha_operacion),
                       -p.volumen, -p.peso, p.codigo)
    )
    for pendiente in pendientes_rescate:
        opciones = []
        for ruta_actual in gestor.sistema.rutas:
            if ruta_actual.estado != 'PLANEADA':
                continue
            vehiculo_liberado = ruta_actual.vehiculo
            if not (
                vehiculo_liberado.habilitado
                and pendiente.peso <= vehiculo_liberado.capacidad_max_peso + 1e-9
                and pendiente.volumen <= vehiculo_liberado.capacidad_max_volumen + 1e-9
                and vehiculo_liberado.puede_cargar(pendiente)
                and vehiculo_liberado.puede_entregar(
                    pendiente.cliente_destino, gestor.fecha_operacion
                )
            ):
                continue
            for sustituto in gestor.sistema.obtener_vehiculos_disponibles():
                if not admite_carga_completa(sustituto, ruta_actual.paquetes):
                    continue
                diferencia = (
                    costo_proyectado(sustituto, ruta_actual.paquetes,
                                    ruta_actual.distancia_km)
                    + costo_proyectado(vehiculo_liberado, [pendiente],
                                      pendiente.cliente_destino.zona.distancia_desde_bodega_km)
                    - ruta_actual.calcular_costo()
                )
                opciones.append((diferencia, ruta_actual.id,
                                sustituto.identificador, ruta_actual, sustituto))

        # Un sustituto puede fallar durante la transferencia; intentar
        # las otras alternativas seguras, ordenadas por costo incremental.
        for _, _, _, ruta_a_mover, vehiculo_nuevo in sorted(
            opciones, key=lambda opcion: opcion[:3]
        ):
            vehiculo_liberado = ruta_a_mover.vehiculo
            if not trasladar_ruta_planeada(ruta_a_mover, vehiculo_nuevo):
                continue
            if not gestor.verificar_vehiculo(vehiculo_liberado, pendiente):
                trasladar_ruta_planeada(ruta_a_mover, vehiculo_liberado)
                continue
            numero = len(gestor.sistema.rutas) + 1
            while any(r.id == f'R-{numero:03d}' for r in gestor.sistema.rutas):
                numero += 1
            nueva_ruta = Ruta(
                f'R-{numero:03d}', vehiculo_liberado,
                pendiente.cliente_destino.zona,
                pendiente.cliente_destino.zona.distancia_desde_bodega_km
            )
            creada = nueva_ruta.agregar_paquete(pendiente, gestor.fecha_operacion)
            if creada:
                creada = (nueva_ruta.validar_ruta(gestor.fecha_operacion)
                          and gestor.sistema.registrar_ruta(nueva_ruta))
            if not creada:
                if pendiente.estado == 'ASIGNADO':
                    pendiente.cambiar_estado('PENDIENTE')
                if pendiente in vehiculo_liberado.carga_actual:
                    vehiculo_liberado.descargar_paquete(pendiente)
                trasladar_ruta_planeada(ruta_a_mover, vehiculo_liberado)
                continue
            nuevas.append(nueva_ruta)
            gestor.alertas[:] = [a for a in gestor.alertas
                                 if not a.startswith(f'Paquete {pendiente.codigo}:')]
            gestor.alertas.append(
                f'Mejora local: la ruta {ruta_a_mover.id} pasó a '
                f'{vehiculo_nuevo.identificador}; '
                f'{vehiculo_liberado.identificador} pudo despachar {pendiente.codigo}.'
            )
            break

