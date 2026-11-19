from datetime import date

import pytest

from citydelivery.logistica.citydelivery import CityDelivery
from citydelivery.logistica.ruta import Ruta
from citydelivery.modelos.bodega import Bodega
from citydelivery.modelos.cliente import ClientePremium, ClienteStandard
from citydelivery.modelos.paquete import Paquete
from citydelivery.modelos.vehiculo import CamionPesado, Motocicleta, VanReparto
from citydelivery.modelos.zona import Zona

FECHA = date(2026, 11, 10)


@pytest.fixture
def central():
    bodega = Bodega("Bodega Central", 1000, 20)
    sistema = CityDelivery(bodega)
    zona = Zona("Z-01", "Centro", 11, True)
    zona_premium = Zona("Z-02", "Residencial", 14, False)
    assert sistema.registrar_zona(zona)
    assert sistema.registrar_zona(zona_premium)
    cliente = ClienteStandard("C-01", "Empresa", "Calle 1", zona)
    premium = ClientePremium(
        "C-02",
        "Laura",
        "Calle 2",
        zona_premium,
        fecha_compra_suscripcion=date(2026, 11, 1),
        duracion_suscripcion_dias=30,
    )
    assert sistema.registrar_cliente(cliente)
    assert sistema.registrar_cliente(premium)
    van = VanReparto("VAN-01", 500, 4, 120)
    moto = Motocicleta("MOTO-01", 25, 0.12, 900)
    camion = CamionPesado("CAM-01", 1500, 10, 180000, 35000)
    inhabilitada = VanReparto("VAN-02", 500, 4, 120, habilitado=False)
    for vehiculo in (van, moto, camion, inhabilitada):
        assert sistema.registrar_vehiculo(vehiculo)
    return (
        sistema,
        zona,
        zona_premium,
        cliente,
        premium,
        van,
        moto,
        camion,
        inhabilitada,
    )


def test_exige_bodega_valida():
    with pytest.raises(TypeError):
        CityDelivery("Bodega falsa")


def test_cinco_atributos_centrales(central):
    sistema, *_ = central
    assert vars(sistema).keys() == {"bodega", "clientes", "vehiculos", "zonas", "rutas"}
    assert isinstance(sistema.bodega, Bodega)


def test_registro_de_zonas_sin_duplicados(central):
    sistema, zona, *_ = central
    assert not sistema.registrar_zona(zona)
    assert not sistema.registrar_zona(Zona("Z-01", "Otra", 5, True))
    assert not sistema.registrar_zona("Zona")
    assert len(sistema.zonas) == 2
    assert sistema.registrar_zona(Zona("Z-03", "Suba", 17.5, True))


def test_clientes_zona_ya_registrada_y_ids_unicos(central):
    sistema, zona, _, cliente, *_ = central
    assert not sistema.registrar_cliente(cliente)
    assert not sistema.registrar_cliente(ClienteStandard("C-01", "Doble", "A", zona))
    assert not sistema.registrar_cliente("C-03")
    desconocida = Zona("Z-XX", "No registrada", 11, True)
    assert not sistema.registrar_cliente(
        ClienteStandard("C-03", "Nuevo", "B", desconocida)
    )
    assert len(sistema.clientes) == 2
    assert sistema.registrar_cliente(ClienteStandard("C-04", "Nuevo", "B", zona))


def test_zona_mismo_id_pero_instancia_ajena_no_aceptada(central):
    sistema, *_ = central
    clon = Zona("Z-01", "Centro", 11, True)
    assert not sistema.registrar_cliente(ClienteStandard("C-99", "Clon", "A", clon))


def test_registro_de_flota_valida_y_sin_duplicados(central):
    sistema, _, _, _, _, van, *_ = central
    assert not sistema.registrar_vehiculo(van)
    assert not sistema.registrar_vehiculo(VanReparto("VAN-01", 500, 4, 120))
    assert not sistema.registrar_vehiculo("VAN")
    assert len(sistema.vehiculos) == 4


def test_no_registra_vehiculo_previamente_cargado(central):
    sistema, _, _, cliente, *_ = central
    otra_van = VanReparto("VAN-99", 500, 4, 120)
    paquete = Paquete("P-99", 2, 0.02, cliente)
    assert otra_van.cargar_paquete(paquete, FECHA)
    assert not sistema.registrar_vehiculo(otra_van)


def test_estados_iniciales_disponible_inhabilitado_y_sin_ruta(central):
    sistema, *_ = central
    assert sistema.obtener_estado_vehiculo("VAN-01") == "DISPONIBLE"
    assert sistema.obtener_estado_vehiculo("VAN-02") == "INHABILITADO"
    assert sistema.consultar_ruta_vehiculo("VAN-01") is None
    assert sistema.consultar_ruta_vehiculo("NO-EXISTE") is None
    assert [v.identificador for v in sistema.obtener_vehiculos_disponibles()] == [
        "VAN-01",
        "MOTO-01",
        "CAM-01",
    ]
    assert sistema.obtener_vehiculos_en_ruta() == []


def test_consulta_id_vehiculo_inexistente_es_explicita(central):
    sistema, *_ = central
    with pytest.raises(ValueError, match="no registrado"):
        sistema.obtener_estado_vehiculo("NO-EXISTE")


def test_registra_ruta_y_reserva_vehiculo(central):
    sistema, zona, _, cliente, _, van, *_ = central
    paquete = Paquete("P-01", 8, 0.04, cliente)
    assert sistema.bodega.agregar_paquete(paquete)
    ruta = Ruta("R-01", van, zona, 11)
    assert ruta.agregar_paquete(paquete, FECHA)
    assert ruta.validar_ruta(FECHA)
    assert sistema.registrar_ruta(ruta)
    assert sistema.obtener_estado_vehiculo("VAN-01") == "RESERVADO"
    assert sistema.consultar_ruta_vehiculo("VAN-01") is ruta
    assert sistema.obtener_vehiculos_en_ruta() == []
    assert [v.identificador for v in sistema.obtener_vehiculos_disponibles()] == [
        "MOTO-01",
        "CAM-01",
    ]


def test_ruta_vacia_no_se_registra(central):
    sistema, zona, _, _, _, van, *_ = central
    assert not sistema.registrar_ruta(Ruta("R-VACIA", van, zona, 11))
    assert not sistema.registrar_ruta("no es ruta")


def test_ruta_con_vehiculo_no_registrado_se_rechaza(central):
    sistema, zona, _, cliente, *_ = central
    van_ajena = VanReparto("VAN-AJENA", 500, 4, 120)
    paquete = Paquete("P-AJENA", 4, 0.02, cliente)
    assert sistema.bodega.agregar_paquete(paquete)
    ruta = Ruta("R-AJENA", van_ajena, zona, 11)
    assert ruta.agregar_paquete(paquete, FECHA)
    assert not sistema.registrar_ruta(ruta)


def test_ruta_con_zona_no_registrada_se_rechaza(central):
    sistema, _, _, cliente, _, van, *_ = central
    zona_ajena = Zona("Z-AJENA", "Extra", 2, True)
    cliente_ajeno = ClienteStandard("C-AJENO", "Persona", "A", zona_ajena)
    paquete = Paquete("P-AJENO", 4, 0.02, cliente_ajeno)
    assert sistema.bodega.agregar_paquete(paquete)
    ruta = Ruta("R-AJENA", van, zona_ajena, 2)
    assert ruta.agregar_paquete(paquete, FECHA)
    assert not sistema.registrar_ruta(ruta)


def test_paquete_no_almacenado_impide_registrar_ruta(central):
    sistema, zona, _, cliente, _, van, *_ = central
    paquete = Paquete("P-NO-BODEGA", 5, 0.1, cliente)
    ruta = Ruta("R-01", van, zona, 11)
    assert ruta.agregar_paquete(paquete, FECHA)
    assert not sistema.registrar_ruta(ruta)


def test_cliente_no_registrado_impide_registrar_ruta(central):
    sistema, zona, _, _, _, van, *_ = central
    cliente_externo = ClienteStandard("C-EXTERNO", "Persona", "A", zona)
    paquete = Paquete("P-EXTERNO", 5, 0.1, cliente_externo)
    assert sistema.bodega.agregar_paquete(paquete)
    ruta = Ruta("R-01", van, zona, 11)
    assert ruta.agregar_paquete(paquete, FECHA)
    assert not sistema.registrar_ruta(ruta)


def test_mismo_id_de_ruta_no_se_registra_dos_veces(central):
    sistema, zona, _, cliente, _, van, moto, *_ = central
    p1 = Paquete("P-R1", 2, 0.02, cliente)
    p2 = Paquete("P-R2", 2, 0.02, cliente)
    assert sistema.bodega.agregar_paquete(p1)
    assert sistema.bodega.agregar_paquete(p2)
    primera = Ruta("R-01", van, zona, 11)
    segunda = Ruta("R-01", moto, zona, 11)
    assert primera.agregar_paquete(p1, FECHA)
    assert segunda.agregar_paquete(p2, FECHA)
    assert sistema.registrar_ruta(primera)
    assert not sistema.registrar_ruta(segunda)


def test_no_permite_dos_rutas_activas_mismo_vehiculo(central):
    sistema, zona, _, cliente, _, van, *_ = central
    p1 = Paquete("P-01", 4, 0.02, cliente)
    p2 = Paquete("P-02", 5, 0.02, cliente)
    assert sistema.bodega.agregar_paquete(p1)
    assert sistema.bodega.agregar_paquete(p2)
    primera = Ruta("R-01", van, zona, 11)
    segunda = Ruta("R-02", van, zona, 11)
    assert primera.agregar_paquete(p1, FECHA)
    assert segunda.agregar_paquete(p2, FECHA)
    assert sistema.registrar_ruta(primera)
    assert not sistema.registrar_ruta(segunda)
    assert len(sistema.rutas) == 1


def test_ciclo_planear_iniciar_finalizar_libera_vehiculo(central):
    sistema, zona, _, cliente, _, van, *_ = central
    paquete = Paquete("P-01", 8, 0.04, cliente)
    assert sistema.bodega.agregar_paquete(paquete)
    ruta = Ruta("R-01", van, zona, 11)
    assert ruta.agregar_paquete(paquete, FECHA)
    assert sistema.registrar_ruta(ruta)
    assert not sistema.finalizar_ruta("R-01")  # Aún PLANEADA
    assert ruta.iniciar_ruta()
    assert sistema.obtener_estado_vehiculo("VAN-01") == "EN_RUTA"
    assert sistema.obtener_vehiculos_en_ruta() == [van]
    assert sistema.finalizar_ruta("R-01")
    assert paquete.estado == "ENTREGADO"
    assert paquete not in sistema.bodega.paquetes
    assert van.carga_actual == []
    assert ruta.estado == "FINALIZADA"
    assert sistema.consultar_ruta_vehiculo("VAN-01") is None
    assert sistema.obtener_estado_vehiculo("VAN-01") == "DISPONIBLE"
    assert sistema.obtener_vehiculos_en_ruta() == []
    assert not sistema.finalizar_ruta("R-01")
    assert not sistema.finalizar_ruta("R-INEXISTENTE")
    assert ruta.calcular_costo() == 8 * 11 * 120


def test_vehiculo_puede_reutilizarse_tras_finalizar(central):
    sistema, zona, _, cliente, _, van, *_ = central
    primero = Paquete("P-01", 8, 0.04, cliente)
    segundo = Paquete("P-02", 5, 0.03, cliente)
    assert sistema.bodega.agregar_paquete(primero)
    assert sistema.bodega.agregar_paquete(segundo)
    ruta1 = Ruta("R-01", van, zona, 11)
    assert ruta1.agregar_paquete(primero, FECHA)
    assert sistema.registrar_ruta(ruta1)
    assert ruta1.iniciar_ruta()
    assert sistema.finalizar_ruta("R-01")
    ruta2 = Ruta("R-02", van, zona, 11)
    assert ruta2.agregar_paquete(segundo, FECHA)
    assert sistema.registrar_ruta(ruta2)
    assert sistema.obtener_estado_vehiculo("VAN-01") == "RESERVADO"
    assert len(sistema.rutas) == 2
    assert ruta1.calcular_costo() == 8 * 11 * 120


def test_un_vehiculo_inhabilitado_no_queda_disponible(central):
    sistema, _, _, _, _, van, *_ = central
    van.habilitado = False
    assert van not in sistema.obtener_vehiculos_disponibles()
    assert sistema.obtener_estado_vehiculo("VAN-01") == "INHABILITADO"


def test_paquete_de_ruta_historica_no_puede_reasignarse(central):
    sistema, zona, _, cliente, _, van, *_ = central
    paquete = Paquete("P-HIST", 8, 0.04, cliente)
    assert sistema.bodega.agregar_paquete(paquete)
    ruta = Ruta("R-01", van, zona, 11)
    assert ruta.agregar_paquete(paquete, FECHA)
    assert sistema.registrar_ruta(ruta)
    assert ruta.iniciar_ruta()
    assert sistema.finalizar_ruta("R-01")
    assert not ruta.agregar_paquete(paquete, FECHA)
    assert paquete.estado == "ENTREGADO"
