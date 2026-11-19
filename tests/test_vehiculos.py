from datetime import date
from types import SimpleNamespace

import pytest

from citydelivery.modelos.cliente import ClientePremium, ClienteStandard
from citydelivery.modelos.paquete import Paquete
from citydelivery.modelos.vehiculo import (
    CamionPesado,
    Motocicleta,
    VanReparto,
    Vehiculo,
)
from citydelivery.modelos.zona import Zona

FECHA = date(2026, 11, 10)


@pytest.fixture
def destinatarios():
    zona_restringida = Zona("Z-M03", "Residencial restringida", 14.0, False)
    zona_libre = Zona("Z-L03", "Centro", 11.0, True)
    premium_activo = ClientePremium(
        "CP-M03",
        "Premium activo",
        "Calle 1",
        zona_restringida,
        fecha_compra_suscripcion=date(2026, 11, 1),
        duracion_suscripcion_dias=30,
    )
    premium_vencido = ClientePremium(
        "CV-M03",
        "Premium vencido",
        "Calle 2",
        zona_restringida,
        fecha_compra_suscripcion=date(2026, 9, 1),
        duracion_suscripcion_dias=30,
    )
    estandar = ClienteStandard(
        "CE-M03",
        "Estándar",
        "Calle 3",
        zona_restringida,
    )
    premium_zona_libre = ClientePremium(
        "CL-M03",
        "Premium libre",
        "Calle 4",
        zona_libre,
        suscripcion_activa_declarada=True,
    )
    return premium_activo, premium_vencido, estandar, premium_zona_libre


def test_vehiculo_es_abstracto():
    with pytest.raises(TypeError):
        Vehiculo("V-01", 50, 2.0)


def test_motocicleta_puede_cargar_paquete_liviano(destinatarios):
    moto = Motocicleta("MOTO-T01", 25, 0.12, 900, 4.99)
    p = Paquete("PM01", 2, 0.015, destinatarios[0])
    assert moto.puede_cargar(p)
    assert moto.verificar_capacidad(p)
    assert moto.cargar_paquete(p, FECHA)
    assert p.estado == "ASIGNADO"
    assert moto.calcular_peso_actual() == 2
    assert moto.calcular_volumen_actual() == pytest.approx(0.015)


def test_motocicleta_rechaza_paquete_de_cinco_kilos(destinatarios):
    moto = Motocicleta("MOTO-T02", 25, 0.12, 900, 4.99)
    p = Paquete("PM02", 5.0, 0.015, destinatarios[2])
    assert not moto.puede_cargar(p)
    assert not moto.cargar_paquete(p, FECHA)
    assert p.estado == "PENDIENTE"
    assert moto.carga_actual == []


def test_motocicleta_respeta_limite_configurable(destinatarios):
    moto = Motocicleta("MOTO-T03", 25, 0.12, 900, 3.0)
    p = Paquete("PM03", 3.2, 0.015, destinatarios[2])
    assert not moto.puede_cargar(p)
    assert not moto.cargar_paquete(p, FECHA)


def test_vehiculo_valida_peso_acumulado(destinatarios):
    van = VanReparto("VAN-T01", 10.0, 1.0, 120)
    p1 = Paquete("PV01", 8.0, 0.02, destinatarios[2])
    p2 = Paquete("PV02", 3.0, 0.02, destinatarios[2])
    assert van.cargar_paquete(p1, FECHA)
    assert not van.verificar_capacidad(p2)
    assert not van.cargar_paquete(p2, FECHA)
    assert p2.estado == "PENDIENTE"
    assert van.calcular_peso_actual() == 8.0


def test_vehiculo_valida_volumen_acumulado(destinatarios):
    van = VanReparto("VAN-T02", 100, 0.1, 120)
    p1 = Paquete("PV03", 2.0, 0.08, destinatarios[2])
    p2 = Paquete("PV04", 2.0, 0.03, destinatarios[2])
    assert van.cargar_paquete(p1, FECHA)
    assert not van.verificar_capacidad(p2)
    assert not van.cargar_paquete(p2, FECHA)
    assert van.calcular_volumen_actual() == pytest.approx(0.08)


def test_mismo_paquete_no_puede_cargarse_dos_veces(destinatarios):
    moto = Motocicleta("MOTO-T04", 25, 0.12, 900)
    p = Paquete("PM04", 2.0, 0.02, destinatarios[2])
    assert moto.cargar_paquete(p, FECHA)
    assert not moto.cargar_paquete(p, FECHA)
    assert len(moto.carga_actual) == 1


def test_vehiculo_inhabilitado_no_acepta_paquetes(destinatarios):
    van = VanReparto("VAN-T03", 500, 4, 120, habilitado=False)
    p = Paquete("PV05", 8, 0.04, destinatarios[2])
    assert not van.esta_disponible([])
    assert not van.cargar_paquete(p, FECHA)
    assert p.estado == "PENDIENTE"


def test_disponibilidad_se_deriva_de_las_rutas():
    van = VanReparto("VAN-T04", 500, 4, 120)
    otra = VanReparto("VAN-OTRA", 500, 4, 120)
    assert van.esta_disponible([])
    assert van.esta_disponible([SimpleNamespace(vehiculo=otra, estado="EN_RUTA")])
    assert not van.esta_disponible([SimpleNamespace(vehiculo=van, estado="PLANEADA")])
    assert not van.esta_disponible([SimpleNamespace(vehiculo=van, estado="EN_RUTA")])
    assert van.esta_disponible([SimpleNamespace(vehiculo=van, estado="FINALIZADA")])


def test_costo_de_motocicleta_por_km():
    moto = Motocicleta("MOTO-T05", 25, 0.12, 900)
    assert moto.calcular_costo(14.0) == 12600.0
    assert moto.calcular_costo(0.0) == 0.0


def test_costo_de_van_es_peso_por_km_por_tarifa(destinatarios):
    van = VanReparto("VAN-T05", 500, 4, 120)
    paquete = Paquete("PV06", 8.0, 0.04, destinatarios[0])
    assert van.cargar_paquete(paquete, FECHA)
    assert van.calcular_costo(14.0) == 13440.0


def test_camion_no_entra_a_zona_restringida_para_premium_activo(destinatarios):
    camion = CamionPesado("CAM-T01", 1500, 10, 180000, 35000)
    premium, _, _, _ = destinatarios
    p = Paquete("PC01", 50, 0.5, premium)
    assert not camion.puede_entregar(premium, FECHA)
    assert not camion.cargar_paquete(p, FECHA)
    assert p.estado == "PENDIENTE"


def test_camion_entra_a_zona_restringida_para_estandar_o_premium_vencido(destinatarios):
    camion = CamionPesado("CAM-T02", 1500, 10, 180000, 35000)
    _, vencido, estandar, _ = destinatarios
    assert camion.puede_entregar(vencido, FECHA)
    assert camion.puede_entregar(estandar, FECHA)
    assert camion.cargar_paquete(Paquete("PC02", 50, 0.5, estandar), FECHA)


def test_camion_entra_a_zona_no_restringida(destinatarios):
    camion = CamionPesado("CAM-T03", 1500, 10, 180000, 35000)
    premium_libre = destinatarios[3]
    assert camion.puede_entregar(premium_libre, FECHA)
    assert camion.cargar_paquete(Paquete("PC03", 50, 0.5, premium_libre), FECHA)


def test_camion_cobra_tarifa_fija_e_impuesto():
    camion = CamionPesado("CAM-T04", 1500, 10, 180000, 35000)
    assert camion.calcular_costo(0.0) == 215000.0
    assert camion.calcular_costo(14.0) == 215000.0


def test_descarga_solo_tras_entrega_o_reversion_a_pendiente(destinatarios):
    moto = Motocicleta("MOTO-T06", 25, 0.12, 900)
    p = Paquete("PM06", 2, 0.02, destinatarios[2])
    assert moto.cargar_paquete(p, FECHA)
    assert not moto.descargar_paquete(p)
    assert p.cambiar_estado("EN_RUTA")
    assert p.cambiar_estado("ENTREGADO")
    assert moto.descargar_paquete(p)
    assert moto.calcular_peso_actual() == 0
    assert not moto.descargar_paquete(p)


def test_descarga_si_paquete_retorna_a_pendiente(destinatarios):
    moto = Motocicleta("MOTO-T07", 25, 0.12, 900)
    p = Paquete("PM07", 2, 0.02, destinatarios[2])
    assert moto.cargar_paquete(p, FECHA)
    assert p.cambiar_estado("PENDIENTE")
    assert moto.descargar_paquete(p)


def test_valida_identificadores_capacidades_y_tarifas():
    with pytest.raises(ValueError):
        Motocicleta("", 25, 0.12, 900)
    with pytest.raises(ValueError):
        VanReparto("VAN-T06", -1, 4, 120)
    with pytest.raises(ValueError):
        VanReparto("VAN-T07", 500, 0, 120)
    with pytest.raises(ValueError):
        Motocicleta("MOTO-T08", 25, 0.12, -1)
    with pytest.raises(ValueError):
        VanReparto("VAN-T08", 500, 4, float("nan"))
    with pytest.raises(ValueError):
        CamionPesado("CAM-T05", 1500, 10, 180000, -2)
    with pytest.raises(ValueError):
        VanReparto("VAN-T09", 500, 4, 120, habilitado="si")


def test_costo_rechaza_distancias_invalidas():
    vehiculos = [
        Motocicleta("MOTO-T09", 25, 0.12, 900),
        VanReparto("VAN-T10", 500, 4, 120),
        CamionPesado("CAM-T06", 1500, 10, 180000, 35000),
    ]
    for vehiculo in vehiculos:
        with pytest.raises(ValueError):
            vehiculo.calcular_costo(-1)
        with pytest.raises(ValueError):
            vehiculo.calcular_costo(float("inf"))
        with pytest.raises(ValueError):
            vehiculo.calcular_costo(True)
