from datetime import date

import pytest

import citydelivery.logistica.gestor_despachos as modulo_gestor
from citydelivery.logistica.citydelivery import CityDelivery
from citydelivery.logistica.gestor_despachos import GestorDespachos
from citydelivery.modelos.bodega import Bodega
from citydelivery.modelos.cliente import ClientePremium, ClienteStandard
from citydelivery.modelos.paquete import Paquete
from citydelivery.modelos.vehiculo import CamionPesado, Motocicleta, VanReparto
from citydelivery.modelos.zona import Zona

FECHA = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def sin_grafo_entre_pruebas(monkeypatch):
    monkeypatch.setattr(modulo_gestor, "GRAFO_VIAL", None)


@pytest.fixture
def operacion():
    sistema = CityDelivery(Bodega("Central", 2000, 60))
    centro = Zona("Z-01", "Centro", 11, True)
    restringida = Zona("Z-02", "Residencial", 14, False)
    assert sistema.registrar_zona(centro)
    assert sistema.registrar_zona(restringida)
    normal = ClienteStandard("A", "Estándar", "Calle A", centro)
    vip = ClientePremium(
        "B",
        "Premium",
        "Calle B",
        restringida,
        fecha_compra_suscripcion=date(2026, 11, 1),
        duracion_suscripcion_dias=30,
    )
    vip_expirado = ClientePremium(
        "C",
        "Caducado",
        "Calle C",
        centro,
        fecha_compra_suscripcion=date(2026, 9, 1),
        duracion_suscripcion_dias=30,
    )
    for cliente in [normal, vip, vip_expirado]:
        assert sistema.registrar_cliente(cliente)
    return sistema, normal, vip, vip_expirado


def poner_paquete(sistema, codigo, cliente, peso=2, volumen=0.02):
    p = Paquete(codigo, peso, volumen, cliente)
    assert sistema.bodega.agregar_paquete(p)
    return p


def test_constructor_conserva_siete_atributos_del_uml(operacion):
    sistema, *_ = operacion
    gestor = GestorDespachos(sistema, FECHA)
    assert set(vars(gestor)) == {
        "sistema",
        "paquetes_entrada",
        "alertas",
        "hora_inicio_matutino",
        "hora_fin_matutino",
        "criterio_prioridad",
        "fecha_operacion",
    }


def test_no_agrega_metodos_fuera_del_uml():
    nombres = {
        n
        for n, obj in GestorDespachos.__dict__.items()
        if callable(obj) and not n.startswith("__")
    }
    assert nombres == {
        "obtener_paquetes_pendientes",
        "obtener_vehiculos_disponibles",
        "ordenar_por_prioridad",
        "verificar_vehiculo",
        "asignar_paquetes",
        "generar_rutas",
        "obtener_paquetes_no_asignados",
        "obtener_paquetes_rechazados",
        "calcular_costo_total",
        "generar_reporte",
    }


def test_valida_sistema_fecha_y_horarios(operacion):
    sistema, *_ = operacion
    with pytest.raises(TypeError):
        GestorDespachos("no es sistema", FECHA)
    with pytest.raises(TypeError):
        GestorDespachos(sistema, "2026-11-10")
    with pytest.raises(ValueError):
        GestorDespachos(sistema, FECHA, "12:00", "06:00")
    with pytest.raises(ValueError):
        GestorDespachos(sistema, FECHA, "AA:00", "15:00")
    with pytest.raises(ValueError):
        GestorDespachos(sistema, FECHA, criterio_prioridad=[1, 2])


def test_prioridad_vigente_antes_de_estandar_y_premium_vencido(operacion):
    sistema, standard, vip, vencido = operacion
    poner_paquete(sistema, "PK-01", standard)
    poner_paquete(sistema, "PK-02", vencido)
    poner_paquete(sistema, "PK-03", vip)
    original = [p.codigo for p in sistema.bodega.paquetes]
    gestor = GestorDespachos(sistema, FECHA)
    assert [p.codigo for p in gestor.ordenar_por_prioridad()] == [
        "PK-03",
        "PK-01",
        "PK-02",
    ]
    assert [p.codigo for p in sistema.bodega.paquetes] == original


def test_solo_recibe_vehiculos_del_sistema_y_sin_duplicar(operacion):
    sistema, standard, *_ = operacion
    paquete = poner_paquete(sistema, "PK", standard)
    externa = VanReparto("VAN-EXT", 500, 4, 120)
    gestor = GestorDespachos(sistema, FECHA)
    assert not gestor.verificar_vehiculo(externa, paquete)
    assert sistema.registrar_vehiculo(externa)
    assert gestor.verificar_vehiculo(externa, paquete)
    assert gestor.obtener_vehiculos_disponibles() == [externa]


def test_asigna_paquete_solo_una_vez_e_idempotencia(operacion):
    sistema, standard, *_ = operacion
    van = VanReparto("VAN-1", 500, 4, 120)
    assert sistema.registrar_vehiculo(van)
    paquete = poner_paquete(sistema, "PK-01", standard)
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    assert len(sistema.rutas) == 1
    assert paquete.estado == "ASIGNADO"
    assert sistema.obtener_estado_vehiculo("VAN-1") == "RESERVADO"
    gestor.asignar_paquetes()
    assert len(sistema.rutas) == 1
    assert van.carga_actual.count(paquete) == 1


def test_agrupa_paquetes_de_una_misma_zona_y_costo_van(operacion):
    sistema, std, _, vencido = operacion
    van = VanReparto("VAN-1", 500, 4, 120)
    sistema.registrar_vehiculo(van)
    p1 = poner_paquete(sistema, "PK-01", std, 3, 0.03)
    p2 = poner_paquete(sistema, "PK-02", vencido, 5, 0.05)
    gestor = GestorDespachos(sistema, FECHA)
    rutas = gestor.generar_rutas()
    assert len(rutas) == 1
    assert set(rutas[0].paquetes) == {p1, p2}
    assert rutas[0].distancia_km == 11
    assert rutas[0].calcular_costo() == (3 + 5) * 11 * 120
    assert gestor.calcular_costo_total() == (3 + 5) * 11 * 120


def test_zona_distinta_no_se_mezcla_en_la_misma_ruta(operacion):
    sistema, std, vip, _ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    sistema.registrar_vehiculo(VanReparto("VAN-2", 500, 4, 120))
    poner_paquete(sistema, "PK-A", std)
    poner_paquete(sistema, "PK-B", vip)
    gestor = GestorDespachos(sistema, FECHA)
    assert len(gestor.generar_rutas()) == 2
    assert len({r.zona.id for r in sistema.rutas}) == 2


def test_van_ocupada_deja_paquete_distinto_pendiente(operacion):
    sistema, std, vip, _ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    p_normal = poner_paquete(sistema, "PK-A", std)
    p_vip = poner_paquete(sistema, "PK-B", vip)
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    assert p_vip.estado == "ASIGNADO"
    assert p_normal.estado == "PENDIENTE"
    assert len(gestor.obtener_paquetes_no_asignados()) == 1
    assert p_normal.motivo_incidencia


def test_camion_restringido_para_premium_activo(operacion):
    sistema, _, vip, _ = operacion
    camion = CamionPesado("CAM-1", 1500, 10, 180000, 35000)
    sistema.registrar_vehiculo(camion)
    paquete = poner_paquete(sistema, "PK-VIP", vip, 200, 1)
    gestor = GestorDespachos(sistema, FECHA)
    assert not gestor.verificar_vehiculo(camion, paquete)
    gestor.asignar_paquetes()
    assert paquete.estado == "PENDIENTE"
    assert not sistema.rutas


def test_camion_permitido_para_estandar_en_zona_restringida(operacion):
    sistema, _, _, _ = operacion
    restringida = sistema.zonas[1]
    std_r = ClienteStandard("D", "Standard", "Calle D", restringida)
    sistema.registrar_cliente(std_r)
    camion = CamionPesado("CAM-1", 1500, 10, 180000, 35000)
    sistema.registrar_vehiculo(camion)
    paquete = poner_paquete(sistema, "PK", std_r, 200, 1)
    GestorDespachos(sistema, FECHA).asignar_paquetes()
    assert paquete.estado == "ASIGNADO"
    assert sistema.rutas[0].calcular_costo() == 215000


def test_moto_no_acepta_cinco_kg_y_no_queda_rechazado(operacion):
    sistema, std, *_ = operacion
    sistema.registrar_vehiculo(Motocicleta("MOTO-1", 25, 0.12, 900))
    paquete = poner_paquete(sistema, "PK", std, 5, 0.04)
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    assert paquete.estado == "PENDIENTE"
    assert len(gestor.obtener_paquetes_rechazados()) == 0
    assert len(gestor.obtener_paquetes_no_asignados()) == 1


def test_rechazo_de_bodega_se_reporta_si_se_registra_entrada(operacion):
    sistema, std, *_ = operacion
    gestor = GestorDespachos(sistema, FECHA)
    rechazado = Paquete("PK-GIGANTE", 3000, 50, std)
    assert not sistema.bodega.agregar_paquete(rechazado)
    gestor.paquetes_entrada.append(rechazado)
    reporte = gestor.generar_reporte()
    assert reporte["totalPaquetes"] == 1
    assert reporte["asignados"] == 0
    assert reporte["rechazados"][0]["codigo"] == "PK-GIGANTE"


def test_liberacion_del_vehiculo_y_conservacion_del_costo(operacion):
    sistema, std, *_ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    paquete = poner_paquete(sistema, "PK-1", std, 8, 0.1)
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    ruta = sistema.rutas[0]
    precio = gestor.calcular_costo_total()
    assert ruta.iniciar_ruta()
    assert sistema.obtener_estado_vehiculo("VAN-1") == "EN_RUTA"
    assert sistema.finalizar_ruta(ruta.id)
    assert paquete.estado == "ENTREGADO"
    assert sistema.obtener_estado_vehiculo("VAN-1") == "DISPONIBLE"
    assert gestor.calcular_costo_total() == precio
    reporte = gestor.generar_reporte()
    assert reporte["asignados"] == 1
    assert reporte["rutas"][0]["estado"] == "FINALIZADA"
    assert reporte["rutas"][0]["ocupacionPesoPct"] > 0


def test_reutiliza_el_vehiculo_en_una_segunda_ronda(operacion):
    sistema, std, *_ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    poner_paquete(sistema, "PK-1", std)
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    anterior = sistema.rutas[0]
    assert anterior.iniciar_ruta()
    assert sistema.finalizar_ruta(anterior.id)
    paquete2 = poner_paquete(sistema, "PK-2", std)
    gestor.asignar_paquetes()
    assert len(sistema.rutas) == 2
    assert paquete2.estado == "ASIGNADO"
    assert sistema.rutas[-1].id != anterior.id


def test_sin_grafo_no_afirma_optimizacion(operacion):
    sistema, std, *_ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    poner_paquete(sistema, "PK-1", std)
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    reporte = gestor.generar_reporte()
    assert reporte["distanciaTotalKm"] == 11
    assert "estimación" in reporte["metodoRutas"].lower()
    assert reporte["eficienciaTSPvsOrdenCodigoPct"] is None
    assert any("No se aplicaron TSP ni Dijkstra" in a for a in reporte["alertas"])


def test_dijkstra_elige_camino_indirecto_antes_de_tsp(operacion, monkeypatch):
    sistema, std, *_ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    poner_paquete(sistema, "PK-1", std, 3)
    # La distancia directa BODEGA -> A cuesta 20, pero pasando por X cuesta 5.
    monkeypatch.setattr(
        modulo_gestor,
        "GRAFO_VIAL",
        {
            "BODEGA": {"A": 20, "X": 3},
            "X": {"A": 2, "BODEGA": 3},
            "A": {"BODEGA": 4},
        },
    )
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    assert sistema.rutas[0].distancia_km == 9
    assert gestor.calcular_costo_total() == 9 * 3 * 120
    assert gestor.generar_reporte()["eficienciaTSPvsOrdenCodigoPct"] == 0


def test_tsp_elige_mejor_orden_en_dos_destinos(operacion, monkeypatch):
    sistema, std, _, _ = operacion
    extra = ClienteStandard("D", "Otro", "Calle B", std.zona)
    sistema.registrar_cliente(extra)
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    poner_paquete(sistema, "PK-A", std, 2)
    poner_paquete(sistema, "PK-B", extra, 3)
    monkeypatch.setattr(
        modulo_gestor,
        "GRAFO_VIAL",
        {
            "BODEGA": {"A": 7, "D": 2},
            "A": {"D": 7, "BODEGA": 3},
            "D": {"A": 3, "BODEGA": 2},
        },
    )
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    ruta = sistema.rutas[0]
    assert ruta.distancia_km == 8
    assert [p.cliente_destino.id for p in ruta.paquetes] == ["D", "A"]
    assert gestor.calcular_costo_total() == 8 * 5 * 120
    assert gestor.generar_reporte()["eficienciaTSPvsOrdenCodigoPct"] == 33.33


def test_grafo_incompleto_caida_controlada_a_estimacion(operacion, monkeypatch):
    sistema, std, *_ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    poner_paquete(sistema, "PK", std)
    monkeypatch.setattr(
        modulo_gestor, "GRAFO_VIAL", {"BODEGA": {"OTRO": 4}, "OTRO": {"BODEGA": 4}}
    )
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    assert sistema.rutas[0].distancia_km == 11
    assert any("Dijkstra/TSP no aplicable" in a for a in gestor.alertas)
    assert gestor.generar_reporte()["eficienciaTSPvsOrdenCodigoPct"] is None


def test_aristas_negativas_no_son_aceptadas(operacion, monkeypatch):
    sistema, std, *_ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    poner_paquete(sistema, "PK", std)
    monkeypatch.setattr(
        modulo_gestor, "GRAFO_VIAL", {"BODEGA": {"A": -1}, "A": {"BODEGA": 5}}
    )
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    assert sistema.rutas[0].distancia_km == 11
    assert any("Dijkstra/TSP no aplicable" in a for a in gestor.alertas)


def test_mas_de_nueve_destinos_usa_heuristica_eficiente(operacion, monkeypatch):
    sistema, std, *_ = operacion
    clientes = [std]
    for i in range(1, 10):
        cliente = ClienteStandard(f"C{i:02d}", f"Cliente {i}", f"Calle {i}", std.zona)
        sistema.registrar_cliente(cliente)
        clientes.append(cliente)
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    for i, cliente in enumerate(clientes):
        poner_paquete(sistema, f"PK-{i}", cliente, 1, 0.01)
    nodos = ["BODEGA"] + [c.id for c in clientes]
    monkeypatch.setattr(
        modulo_gestor,
        "GRAFO_VIAL",
        {a: {b: 1.0 if a != b else 0.0 for b in nodos if b != a} for a in nodos},
    )
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    assert sistema.rutas[0].distancia_km == 11
    assert len(sistema.rutas[0].paquetes) == 10


def test_reporte_contiene_metricas_acordadas(operacion):
    sistema, std, *_ = operacion
    sistema.registrar_vehiculo(VanReparto("VAN-1", 500, 4, 120))
    poner_paquete(sistema, "PK", std, 3, 0.06)
    gestor = GestorDespachos(sistema, FECHA)
    gestor.asignar_paquetes()
    reporte = gestor.generar_reporte()
    for campo in (
        "totalPaquetes",
        "asignados",
        "pendientes",
        "rechazados",
        "rutas",
        "distanciaTotalKm",
        "costoTotalCOP",
        "porcentajeAsignado",
        "eficienciaConsolidacionIdaPct",
        "eficienciaTSPvsOrdenCodigoPct",
    ):
        assert campo in reporte
    ruta = reporte["rutas"][0]
    assert ruta["ocupacionPesoPct"] == 0.6
    assert ruta["ocupacionVolumenPct"] == 1.5
