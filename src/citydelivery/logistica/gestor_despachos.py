"""Planificación de despachos del UML CityDelivery (migración 06).

Se apoya en una única instancia de CityDelivery. No guarda copias de la
flota ni de las rutas. Dijkstra y TSP se ejecutan dentro de generar_rutas().

GRAFO_VIAL es una CONFIGURACIÓN DEL MÓDULO, no un atributo o método del UML.
Para utilizarlo desde el futuro lector JSON:

    import citydelivery.logistica.gestor_despachos as despacho_modulo
    despacho_modulo.GRAFO_VIAL = {
        "BODEGA": {"CLI-1": 6.0},
        "CLI-1": {"BODEGA": 6.0},
    }

Los nodos son "BODEGA" y los IDs de clientes. Cada ruta agrupa una sola zona
porque así está diseñada la clase Ruta del UML. No es un VRP global.
"""

from datetime import date
from heapq import heappop, heappush
from math import isfinite

from ..modelos.paquete import Paquete
from ..modelos.vehiculo import VanReparto, Vehiculo
from .citydelivery import CityDelivery
from .mejora_local import rescatar_pendientes
from .ruta import Ruta

# Información externa opcional. No forma parte de los 7 atributos del UML.
GRAFO_VIAL: dict | None = None


class GestorDespachos:
    def __init__(
        self,
        sistema: CityDelivery,
        fecha_operacion: date,
        hora_inicio_matutino: str = "06:00",
        hora_fin_matutino: str = "12:00",
        criterio_prioridad: list[str] | None = None,
    ):
        if not isinstance(sistema, CityDelivery):
            raise TypeError("sistema debe ser un objeto CityDelivery.")
        if not isinstance(fecha_operacion, date):
            raise TypeError("La fecha de operación debe ser de tipo date.")
        for valor in (hora_inicio_matutino, hora_fin_matutino):
            try:
                hora, minuto = map(int, valor.split(":"))
                if len(valor) != 5 or not (0 <= hora <= 23 and 0 <= minuto <= 59):
                    raise ValueError
            except (ValueError, AttributeError):
                raise ValueError("El horario debe tener el formato HH:MM.")
        if hora_inicio_matutino >= hora_fin_matutino:
            raise ValueError(
                "La hora de inicio debe ser anterior a la de finalización."
            )
        if criterio_prioridad is None:
            criterio_prioridad = ["PREMIUM", "ESTANDAR"]
        if not isinstance(criterio_prioridad, list) or not all(
            isinstance(x, str) for x in criterio_prioridad
        ):
            raise ValueError("Criterio de prioridad inválido.")

        self.sistema = sistema
        # Referencias a paquetes recibidos, incluso los rechazados por Bodega.
        # Cuando el menú/JSON agregue otros paquetes, añadirá también su referencia.
        self.paquetes_entrada: list[Paquete] = list(
            sistema.bodega.consultar_inventario()
        )
        self.alertas: list[str] = []
        self.hora_inicio_matutino = hora_inicio_matutino
        self.hora_fin_matutino = hora_fin_matutino
        self.criterio_prioridad = list(criterio_prioridad)
        self.fecha_operacion = fecha_operacion

    def obtener_paquetes_pendientes(self) -> list[Paquete]:
        return [
            p for p in self.sistema.bodega.consultar_inventario() if p.esta_pendiente()
        ]

    def obtener_vehiculos_disponibles(self) -> list[Vehiculo]:
        return self.sistema.obtener_vehiculos_disponibles()

    def ordenar_por_prioridad(self) -> list[Paquete]:
        # La prioridad Premium SOLO es alta con membresía vigente.
        # El orden original del inventario NO se altera.
        return sorted(
            self.obtener_paquetes_pendientes(),
            key=lambda p: (p.obtener_prioridad(self.fecha_operacion), p.codigo),
        )

    def verificar_vehiculo(self, vehiculo: Vehiculo, paquete: Paquete) -> bool:
        if not isinstance(vehiculo, Vehiculo) or not isinstance(paquete, Paquete):
            return False
        if not any(vehiculo is v for v in self.sistema.vehiculos):
            return False
        if paquete not in self.sistema.bodega.paquetes or not paquete.esta_pendiente():
            return False
        if not vehiculo.habilitado:
            return False
        if any(
            paquete.codigo == p.codigo for r in self.sistema.rutas for p in r.paquetes
        ):
            return False
        ruta_existente = self.sistema.consultar_ruta_vehiculo(vehiculo.identificador)
        if ruta_existente is None:
            if not vehiculo.esta_disponible(self.sistema.rutas):
                return False
        elif (
            ruta_existente.estado != "PLANEADA"
            or ruta_existente.zona is not paquete.cliente_destino.zona
        ):
            return False
        return (
            vehiculo.puede_cargar(paquete)
            and vehiculo.verificar_capacidad(paquete)
            and vehiculo.puede_entregar(paquete.cliente_destino, self.fecha_operacion)
        )

    def asignar_paquetes(self) -> None:
        # Método del UML para ejecutar la asignación. El detalle de la
        # creación y la optimización de recorridos está en generar_rutas().
        self.generar_rutas()

    def generar_rutas(self) -> list[Ruta]:
        """Asigna paquetes por prioridad, genera rutas por zona y vehículo.

        Si existe GRAFO_VIAL (dict: nodo -> {vecino: kilómetros}), utiliza
        Dijkstra entre los destinos y después TSP para minimizar el recorrido.
        Los nodos del grafo son 'BODEGA' y los ID de los clientes.
        El TSP retorna a BODEGA. Sin grafo o sin camino válido se usa la
        distancia de IDA a la zona, identificada como estimación, no como TSP.
        """
        nuevas = []
        # Primero Premium activos, después el resto. Dentro de cada nivel,
        # cargas grandes primero para dejar vehículos de menor capacidad libres.
        pendientes = self.ordenar_por_prioridad()
        prioridades = sorted(
            set(p.obtener_prioridad(self.fecha_operacion) for p in pendientes)
        )
        for prioridad in prioridades:
            grupo = [
                p
                for p in pendientes
                if p.obtener_prioridad(self.fecha_operacion) == prioridad
            ]
            for paquete in sorted(grupo, key=lambda p: (-p.volumen, -p.peso, p.codigo)):
                candidatos = []
                for vehiculo in self.sistema.vehiculos:
                    if not self.verificar_vehiculo(vehiculo, paquete):
                        continue
                    ruta = self.sistema.consultar_ruta_vehiculo(vehiculo.identificador)
                    km = paquete.cliente_destino.zona.distancia_desde_bodega_km
                    if ruta is not None:
                        # Ya hay un recorrido PLANEADO de la misma zona.
                        if isinstance(vehiculo, VanReparto):
                            incremento = paquete.peso * km * vehiculo.costo_por_kg_km
                        else:
                            incremento = 0.0  # viaje ya abierto: moto o camión
                    elif isinstance(vehiculo, VanReparto):
                        incremento = paquete.peso * km * vehiculo.costo_por_kg_km
                    else:
                        incremento = vehiculo.calcular_costo(km)
                    candidatos.append(
                        (
                            incremento,
                            0 if ruta is not None else 1,
                            vehiculo.identificador,
                            vehiculo,
                            ruta,
                        )
                    )

                if not candidatos:
                    motivo = "No existe vehículo compatible, libre o con capacidad suficiente"
                    paquete.registrar_incidencia("PENDIENTE", motivo)
                    aviso = f"Paquete {paquete.codigo}: {motivo}"
                    if aviso not in self.alertas:
                        self.alertas.append(aviso)
                    continue
                _, _, _, vehiculo, ruta = min(candidatos, key=lambda c: c[:3])
                if ruta is not None:
                    if not ruta.agregar_paquete(paquete, self.fecha_operacion):
                        paquete.registrar_incidencia(
                            "PENDIENTE", "No se pudo agregar a la ruta"
                        )
                    continue

                # Abrir una ruta solo después de comprobar que el vehículo está libre.
                consecutivo = len(self.sistema.rutas) + 1
                while any(r.id == f"R-{consecutivo:03d}" for r in self.sistema.rutas):
                    consecutivo += 1
                ruta = Ruta(
                    f"R-{consecutivo:03d}",
                    vehiculo,
                    paquete.cliente_destino.zona,
                    paquete.cliente_destino.zona.distancia_desde_bodega_km,
                )
                if not ruta.agregar_paquete(paquete, self.fecha_operacion):
                    paquete.registrar_incidencia(
                        "PENDIENTE", "La carga del paquete falló"
                    )
                    continue
                if not ruta.validar_ruta(
                    self.fecha_operacion
                ) or not self.sistema.registrar_ruta(ruta):
                    # Deshacer completamente la carga cuando no se pudo registrar la ruta.
                    paquete.cambiar_estado("PENDIENTE")
                    vehiculo.descargar_paquete(paquete)
                    paquete.registrar_incidencia("PENDIENTE", "Error al registrar ruta")
                    continue
                nuevas.append(ruta)

        # No cambia el UML: helper externo sin clases ni métodos adicionales.
        rescatar_pendientes(self, nuevas)

        # El grafo es CONFIGURACIÓN EXTERNA, NO un atributo nuevo del UML.
        # En la Sección 7 el lector JSON podrá asignar la variable GRAFO_VIAL.
        red = globals().get("GRAFO_VIAL", None)
        if red is None or red == {}:
            for ruta in self.sistema.rutas:
                if ruta.estado == "PLANEADA":
                    ruta.distancia_km = ruta.zona.distancia_desde_bodega_km
            aviso = (
                "Rutas: distancia aproximada de ida desde Bodega hasta Zona. "
                "No se aplicaron TSP ni Dijkstra porque falta un grafo de destinos."
            )
            if aviso not in self.alertas:
                self.alertas.append(aviso)
            return nuevas

        if not isinstance(red, dict) or "BODEGA" not in red:
            for ruta in self.sistema.rutas:
                if ruta.estado == "PLANEADA":
                    ruta.distancia_km = ruta.zona.distancia_desde_bodega_km
            aviso = (
                "GRAFO_VIAL inválido: se mantienen las distancias estimadas por zona."
            )
            if aviso not in self.alertas:
                self.alertas.append(aviso)
            return nuevas

        # Función LOCAL del algoritmo, NO método adicional de una clase.
        def dijkstra(inicio):
            distancias = {inicio: 0.0}
            cola = [(0.0, inicio)]
            while cola:
                costo, nodo = heappop(cola)
                if costo > distancias.get(nodo, float("inf")):
                    continue
                for vecino, peso in red.get(nodo, {}).items():
                    if (
                        isinstance(peso, bool)
                        or not isinstance(peso, (int, float))
                        or not isfinite(peso)
                        or peso < 0
                    ):
                        raise ValueError(
                            "Arista negativa, infinita o no numérica en GRAFO_VIAL"
                        )
                    nuevo = costo + peso
                    if nuevo < distancias.get(vecino, float("inf")):
                        distancias[vecino] = nuevo
                        heappush(cola, (nuevo, vecino))
            return distancias

        # El algoritmo exacto se limita a 9 destinos únicos para evitar
        # tiempos exponenciales. Para >9 se usa vecino cercano + 2-opt.
        for ruta in self.sistema.rutas:
            if ruta.estado != "PLANEADA":
                continue
            destinos = list(dict.fromkeys(p.cliente_destino.id for p in ruta.paquetes))
            nodos = ["BODEGA"] + destinos
            try:
                if any(
                    nodo not in red or not isinstance(red[nodo], dict) for nodo in nodos
                ):
                    raise ValueError("Grafo sin BODEGA o sin nodos de algunos clientes")
                caminos = {n: dijkstra(n) for n in nodos}
                if any(
                    destino not in caminos[origen]
                    for origen in nodos
                    for destino in nodos
                ):
                    raise ValueError(
                        "Grafo desconectado o sin recorrido de vuelta a BODEGA"
                    )
                distancia = lambda a, b: caminos[a][b]

                if len(destinos) <= 9:
                    # TSP exacto Held-Karp: recorrido cerrado BODEGA -> ... -> BODEGA.
                    n = len(destinos)
                    estados: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {
                        (1 << i, i): (distancia("BODEGA", destinos[i]), (i,))
                        for i in range(n)
                    }
                    for mascara in range(1, 1 << n):
                        for ultimo in range(n):
                            actual = estados.get((mascara, ultimo))
                            if actual is None:
                                continue
                            for sig in range(n):
                                if mascara & (1 << sig):
                                    continue
                                nuevo = actual[0] + distancia(
                                    destinos[ultimo], destinos[sig]
                                )
                                clave = (mascara | (1 << sig), sig)
                                if nuevo < estados.get(clave, (float("inf"), ()))[0]:
                                    estados[clave] = (nuevo, actual[1] + (sig,))
                    mejor = min(
                        (
                            estados[((1 << n) - 1, i)][0]
                            + distancia(destinos[i], "BODEGA"),
                            estados[((1 << n) - 1, i)][1],
                        )
                        for i in range(n)
                    )
                    total_km, secuencia = mejor
                    orden = [destinos[i] for i in secuencia]
                else:
                    # TSP heurístico: vecino más cercano + mejoras 2-opt.
                    sin_visitar = set(destinos)
                    orden = []
                    actual = "BODEGA"
                    while sin_visitar:
                        siguiente = min(
                            sin_visitar, key=lambda x: (distancia(actual, x), x)
                        )
                        orden.append(siguiente)
                        sin_visitar.remove(siguiente)
                        actual = siguiente

                    def coste(orden_actual):
                        ruta_nodos = ["BODEGA"] + orden_actual + ["BODEGA"]
                        return sum(
                            distancia(a, b) for a, b in zip(ruta_nodos, ruta_nodos[1:])
                        )

                    # Dos-opt sobre el orden, manteniendo BODEGA al inicio y al final.
                    for _ in range(30):
                        mejoro = False
                        for i in range(len(orden) - 1):
                            for j in range(i + 1, len(orden)):
                                candidato = (
                                    orden[:i]
                                    + list(reversed(orden[i : j + 1]))
                                    + orden[j + 1 :]
                                )
                                if coste(candidato) + 1e-9 < coste(orden):
                                    orden = candidato
                                    mejoro = True
                        if not mejoro:
                            break
                    total_km = coste(orden)

                # Solo después de completar el TSP actualizamos distancia y orden
                # de entrega, respetando los paquetes del mismo cliente.
                posicion = {cliente_id: i for i, cliente_id in enumerate(orden)}
                ruta.paquetes.sort(
                    key=lambda p: (posicion[p.cliente_destino.id], p.codigo)
                )
                ruta.distancia_km = round(total_km, 6)
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                ruta.distancia_km = ruta.zona.distancia_desde_bodega_km
                aviso = (
                    f"Ruta {ruta.id}: Dijkstra/TSP no aplicable ({exc}); "
                    "se usó la distancia de ida a la zona."
                )
                if aviso not in self.alertas:
                    self.alertas.append(aviso)
        return nuevas

    def obtener_paquetes_no_asignados(self) -> list[Paquete]:
        return [p for p in self.obtener_paquetes_pendientes()]

    def obtener_paquetes_rechazados(self) -> list[Paquete]:
        return [p for p in self.paquetes_entrada if p.estado == "RECHAZADO"]

    def calcular_costo_total(self) -> float:
        return sum(r.calcular_costo() for r in self.sistema.rutas)

    def generar_reporte(self) -> dict:
        # Métricas derivadas de los objetos del UML, sin nuevos atributos.
        todos = list(
            {
                id(p): p
                for p in (
                    self.paquetes_entrada
                    + self.sistema.bodega.consultar_inventario()
                    + [p for r in self.sistema.rutas for p in r.paquetes]
                )
            }.values()
        )
        rutas = list(self.sistema.rutas)
        usados = {r.vehiculo.identificador for r in rutas}
        asignados = [
            p for p in todos if p.estado in ("ASIGNADO", "EN_RUTA", "ENTREGADO")
        ]
        pendientes = self.obtener_paquetes_no_asignados()
        rechazados = [p for p in todos if p.estado == "RECHAZADO"]
        distancia_total = sum(r.distancia_km for r in rutas)
        costo_total = self.calcular_costo_total()
        # Comparación referencial SOLO válida para recorridos de ida por zona:
        # si cada paquete viajara por separado, sumaría la distancia de su zona.
        baseline_ida = sum(
            p.cliente_destino.zona.distancia_desde_bodega_km for p in asignados
        )
        grafo_activo = bool(globals().get("GRAFO_VIAL", None))
        eficiencia = None
        if not grafo_activo and baseline_ida > 0:
            eficiencia = round(100 * (baseline_ida - distancia_total) / baseline_ida, 2)

        # Con un grafo completo puede compararse TSP con un recorrido de
        # referencia: visitar clientes en orden de ID y regresar a BODEGA.
        # Esta es una MÉTRICA, no otro método añadido al UML.
        eficiencia_tsp = None
        grafo = globals().get("GRAFO_VIAL")
        if grafo_activo and isinstance(grafo, dict) and "BODEGA" in grafo:
            try:
                ref_total = 0.0
                optimizado_total = 0.0
                for ruta in rutas:
                    clientes_ordenados = sorted(
                        {p.cliente_destino.id for p in ruta.paquetes}
                    )
                    nodos_ref = ["BODEGA"] + clientes_ordenados + ["BODEGA"]
                    km_referencia = 0.0
                    for origen, destino in zip(nodos_ref, nodos_ref[1:]):
                        dist = {origen: 0.0}
                        cola = [(0.0, origen)]
                        while cola:
                            km, nodo = heappop(cola)
                            if km > dist.get(nodo, float("inf")):
                                continue
                            for vecino, peso in grafo.get(nodo, {}).items():
                                if (
                                    isinstance(peso, bool)
                                    or not isinstance(peso, (int, float))
                                    or not isfinite(peso)
                                    or peso < 0
                                ):
                                    raise ValueError("Arista inválida")
                                alternativo = km + peso
                                if alternativo < dist.get(vecino, float("inf")):
                                    dist[vecino] = alternativo
                                    heappush(cola, (alternativo, vecino))
                        if destino not in dist:
                            raise ValueError("Falta conexión en la ruta de referencia")
                        km_referencia += dist[destino]
                    ref_total += km_referencia
                    optimizado_total += ruta.distancia_km
                if (
                    ref_total > 0
                    and rutas
                    and not any(
                        ("Dijkstra/TSP no aplicable" in a) for a in self.alertas
                    )
                ):
                    eficiencia_tsp = round(
                        100 * (ref_total - optimizado_total) / ref_total, 2
                    )
            except (ValueError, TypeError, KeyError, OverflowError):
                pass
        return {
            "fechaOperacion": self.fecha_operacion.isoformat(),
            "totalPaquetes": len(todos),
            "asignados": len(asignados),
            "pendientes": [
                {"codigo": p.codigo, "motivo": p.motivo_incidencia} for p in pendientes
            ],
            "rechazados": [
                {"codigo": p.codigo, "motivo": p.motivo_incidencia} for p in rechazados
            ],
            "vehiculosDisponibles": [
                v.identificador for v in self.obtener_vehiculos_disponibles()
            ],
            "vehiculosEnRuta": [
                v.identificador for v in self.sistema.obtener_vehiculos_en_ruta()
            ],
            "vehiculosUtilizados": sorted(usados),
            "rutas": [
                {
                    "id": r.id,
                    "vehiculo": r.vehiculo.identificador,
                    "tipoVehiculo": type(r.vehiculo).__name__,
                    "zona": r.zona.nombre,
                    "estado": r.estado,
                    "destinos": [p.cliente_destino.direccion for p in r.paquetes],
                    "paquetes": [p.codigo for p in r.paquetes],
                    "distanciaKm": r.distancia_km,
                    "costoCOP": round(r.calcular_costo(), 2),
                    "ocupacionPesoPct": round(
                        100
                        * sum(p.peso for p in r.paquetes)
                        / r.vehiculo.capacidad_max_peso,
                        2,
                    ),
                    "ocupacionVolumenPct": round(
                        100
                        * sum(p.volumen for p in r.paquetes)
                        / r.vehiculo.capacidad_max_volumen,
                        2,
                    ),
                }
                for r in rutas
            ],
            "distanciaTotalKm": round(distancia_total, 3),
            "costoTotalCOP": round(costo_total, 2),
            "costoPromedioPorKmCOP": round(costo_total / distancia_total, 2)
            if distancia_total > 0
            else None,
            "porcentajeAsignado": round(100 * len(asignados) / len(todos), 2)
            if todos
            else 0.0,
            "eficienciaConsolidacionIdaPct": eficiencia,
            "eficienciaTSPvsOrdenCodigoPct": eficiencia_tsp,
            "metodoRutas": (
                "TSP + Dijkstra si existe grafo completo; "
                "estimación por zona cuando no lo hay"
            )
            if grafo_activo
            else "Estimación por distancia a zona (ida)",
            "alertas": list(self.alertas),
        }
