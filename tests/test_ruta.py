from datetime import date

import pytest

from citydelivery.logistica.ruta import Ruta
from citydelivery.modelos.cliente import ClientePremium, ClienteStandard
from citydelivery.modelos.paquete import Paquete
from citydelivery.modelos.vehiculo import CamionPesado, Motocicleta, VanReparto
from citydelivery.modelos.zona import Zona

FECHA = date(2026, 11, 10)


@pytest.fixture
def contexto():
    zona = Zona("ZR-04", "Centro", 11, True)
    otra_zona = Zona("ZOT-04", "Suba", 17.5, True)
    cliente = ClienteStandard("C-R04", "Cliente", "Calle 5", zona)
    otro = ClienteStandard("C-OT04", "Cliente otro", "Calle 6", otra_zona)
    van = VanReparto("V-R04", 500, 4, 120)
    return zona, otra_zona, cliente, otro, van


def test_crear_ruta_planeada(contexto):
    zona, _, _, _, van = contexto
    ruta = Ruta("R-01", van, zona, 11)
    assert ruta.id == "R-01"
    assert ruta.zona is zona
    assert ruta.vehiculo is van
    assert ruta.distancia_km == 11.0
    assert ruta.estado == "PLANEADA"
    assert ruta.ocupa_vehiculo()
    assert not ruta.esta_activa()
    assert ruta.obtener_entregas() == []
    assert not ruta.validar_ruta(FECHA)
    assert not ruta.iniciar_ruta()


def test_validaciones_de_constructor(contexto):
    zona, _, _, _, van = contexto
    with pytest.raises(ValueError):
        Ruta(" ", van, zona, 11)
    with pytest.raises(TypeError):
        Ruta("R-01", "VAN-01", zona, 11)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Ruta("R-01", van, "Centro", 11)  # type: ignore[arg-type]
    for km in (-1, True, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            Ruta("R-02", van, zona, km)


def test_agregar_paquetes_y_evitar_duplicados(contexto):
    zona, _, cliente, _, van = contexto
    ruta = Ruta("R-03", van, zona, 11)
    p = Paquete("PK-R01", 8, 0.04, cliente)
    assert ruta.agregar_paquete(p, FECHA)
    assert p.estado == "ASIGNADO"
    assert not ruta.agregar_paquete(p, FECHA)
    assert not ruta.agregar_paquete(Paquete("PK-R01", 1, 0.01, cliente), FECHA)
    assert len(ruta.paquetes) == 1
    assert van.carga_actual == [p]
    assert ruta.validar_ruta(FECHA)


def test_prohibicion_de_mezclar_zonas(contexto):
    zona, _, _, otro, van = contexto
    ruta = Ruta("R-04", van, zona, 11)
    p = Paquete("PK-OTRA", 2, 0.01, otro)
    assert not ruta.agregar_paquete(p, FECHA)
    assert p.estado == "PENDIENTE"
    assert van.carga_actual == []


def test_validar_peso_y_volumen_acumulados(contexto):
    zona, _, cliente, _, _ = contexto
    van = VanReparto("V-PEQ", 10, 0.10, 120)
    ruta = Ruta("R-05", van, zona, 11)
    a = Paquete("P-A", 8, 0.08, cliente)
    b = Paquete("P-B", 3, 0.01, cliente)
    c = Paquete("P-C", 1, 0.03, cliente)
    assert ruta.agregar_paquete(a, FECHA)
    assert not ruta.agregar_paquete(b, FECHA)
    assert not ruta.agregar_paquete(c, FECHA)
    assert b.estado == c.estado == "PENDIENTE"
    assert ruta.validar_ruta(FECHA)


def test_reserva_y_estado_en_ruta(contexto):
    zona, _, cliente, _, van = contexto
    ruta = Ruta("R-06", van, zona, 11)
    p = Paquete("PK-06", 2, 0.01, cliente)
    assert ruta.agregar_paquete(p, FECHA)
    assert not van.esta_disponible([ruta])
    assert ruta.validar_ruta(FECHA)
    assert ruta.iniciar_ruta()
    assert ruta.estado == "EN_RUTA"
    assert ruta.esta_activa() and ruta.ocupa_vehiculo()
    assert p.estado == "EN_RUTA"
    assert ruta.validar_ruta(FECHA)
    assert not ruta.iniciar_ruta()
    assert not van.esta_disponible([ruta])


def test_finalizar_entrega_y_liberar_vehiculo(contexto):
    zona, _, cliente, _, van = contexto
    ruta = Ruta("R-07", van, zona, 11)
    p = Paquete("PK-07", 3, 0.01, cliente)
    assert ruta.agregar_paquete(p, FECHA)
    assert not ruta.finalizar_ruta()  # no se finaliza una ruta planeada
    assert ruta.iniciar_ruta()
    assert ruta.finalizar_ruta()
    assert ruta.estado == "FINALIZADA"
    assert p.estado == "ENTREGADO"
    assert van.carga_actual == []
    assert van.esta_disponible([ruta])
    assert not ruta.esta_activa() and not ruta.ocupa_vehiculo()
    assert not ruta.finalizar_ruta()
    assert not ruta.validar_ruta(FECHA)


def test_no_admite_paquetes_si_no_esta_planeada(contexto):
    zona, _, cliente, _, van = contexto
    ruta = Ruta("R-08", van, zona, 11)
    p = Paquete("PK-08", 2, 0.01, cliente)
    assert ruta.agregar_paquete(p, FECHA)
    assert ruta.iniciar_ruta()
    assert not ruta.agregar_paquete(Paquete("PK-N", 2, 0.01, cliente), FECHA)
    assert ruta.finalizar_ruta()
    assert not ruta.agregar_paquete(Paquete("PK-N2", 2, 0.01, cliente), FECHA)


def test_costo_van_historico_incluso_tras_descarga(contexto):
    zona, _, cliente, _, van = contexto
    ruta = Ruta("R-09", van, zona, 11)
    assert ruta.agregar_paquete(Paquete("PK-09", 8, 0.04, cliente), FECHA)
    assert ruta.agregar_paquete(Paquete("PK-10", 5, 0.03, cliente), FECHA)
    assert ruta.calcular_costo() == 17160  # 13 kg * 11 km * 120
    assert ruta.iniciar_ruta()
    assert ruta.finalizar_ruta()
    assert ruta.calcular_costo() == 17160
    # La misma van puede utilizarse para una ruta futura sin alterar el costo previo.
    ruta2 = Ruta("R-10", van, zona, 12)
    assert ruta2.agregar_paquete(Paquete("PK-11", 1, 0.01, cliente), FECHA)
    assert ruta.calcular_costo() == 17160
    assert ruta2.calcular_costo() == 1440


def test_costo_moto_y_camion(contexto):
    zona, _, cliente, _, _ = contexto
    moto = Motocicleta("MOTO-R04", 25, 0.12, 900, 4.99)
    ruta_moto = Ruta("R-MOTO", moto, zona, 11)
    assert ruta_moto.agregar_paquete(Paquete("PM-01", 2, 0.01, cliente), FECHA)
    assert ruta_moto.calcular_costo() == 9900
    camion = CamionPesado("CAM-R04", 1500, 10, 180000, 35000)
    ruta_camion = Ruta("R-CAM", camion, zona, 11)
    assert ruta_camion.agregar_paquete(Paquete("PC-01", 100, 0.5, cliente), FECHA)
    assert ruta_camion.calcular_costo() == 215000


def test_moto_no_admite_cinco_kg(contexto):
    zona, _, cliente, _, _ = contexto
    moto = Motocicleta("M-05", 25, 0.12, 900, 4.99)
    ruta = Ruta("R-11", moto, zona, 11)
    p = Paquete("P-5KG", 5.0, 0.01, cliente)
    assert not ruta.agregar_paquete(p, FECHA)
    assert p.estado == "PENDIENTE"


def test_camion_restringido_premium_activo():
    zona = Zona("Z-PR", "Residencial Premium", 14, False)
    premium = ClientePremium(
        "C-PRE",
        "Premium",
        "Calle 92",
        zona,
        fecha_compra_suscripcion=date(2026, 11, 1),
        duracion_suscripcion_dias=30,
    )
    camion = CamionPesado("C-PRE", 1500, 10, 180000, 35000)
    ruta = Ruta("R-12", camion, zona, 14)
    p = Paquete("PK-PRE", 100, 1.0, premium)
    assert not ruta.agregar_paquete(p, FECHA)
    assert p.estado == "PENDIENTE"


def test_camion_puede_entregar_a_standard_en_zona_restringida():
    zona = Zona("Z-PR2", "Residencial Premium", 14, False)
    estandar = ClienteStandard("C-STD", "Estándar", "Calle 9", zona)
    camion = CamionPesado("CAM-STD", 1500, 10, 180000, 35000)
    ruta = Ruta("R-13", camion, zona, 14)
    assert ruta.agregar_paquete(Paquete("PK-STD", 20, 0.1, estandar), FECHA)


def test_paquetes_obtener_entregas_devuelve_copia(contexto):
    zona, _, cliente, _, van = contexto
    ruta = Ruta("R-14", van, zona, 11)
    p = Paquete("PK-14", 2, 0.01, cliente)
    assert ruta.agregar_paquete(p, FECHA)
    entregas = ruta.obtener_entregas()
    entregas.clear()
    assert ruta.obtener_entregas() == [p]


def test_vehiculo_inhabilitado_impide_ruta(contexto):
    zona, _, cliente, _, _ = contexto
    van = VanReparto("V-OFF", 100, 4, 120, habilitado=False)
    ruta = Ruta("R-15", van, zona, 11)
    assert not ruta.agregar_paquete(Paquete("PK-OFF", 1, 0.01, cliente), FECHA)
    assert not ruta.validar_ruta(FECHA)
