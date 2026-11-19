"""Pruebas de la sección 1 migrada desde Colab, sin cambiar el UML."""

from datetime import date

import pytest

from citydelivery.modelos.cliente import Cliente, ClientePremium, ClienteStandard
from citydelivery.modelos.zona import Zona

FECHA = date(2026, 11, 10)


def test_premium_vigente_prioridad_y_vencimiento():
    zona = Zona("Z-03", "Residencial Premium Norte", 14.0, False)
    cliente = ClientePremium(
        "CLI-001",
        "Laura",
        "Calle 92",
        zona,
        fecha_compra_suscripcion=date(2026, 11, 1),
        duracion_suscripcion_dias=30,
    )
    assert cliente.calcular_vencimiento() == date(2026, 12, 1)
    assert cliente.tiene_suscripcion_activa(FECHA)
    assert cliente.obtener_prioridad(FECHA) == 1


def test_premium_vencido_pasa_a_prioridad_normal():
    zona = Zona("Z-03", "Residencial Premium Norte", 14.0, False)
    cliente = ClientePremium(
        "CLI-003",
        "Camila",
        "Calle 10",
        zona,
        fecha_compra_suscripcion=date(2026, 9, 1),
        duracion_suscripcion_dias=30,
    )
    assert not cliente.tiene_suscripcion_activa(FECHA)
    assert cliente.obtener_prioridad(FECHA) == 2


def test_standard_nunca_tiene_suscripcion():
    zona = Zona("Z-01", "Chapinero", 8.5, True)
    cliente = ClienteStandard("CLI-002", "Andres", "Carrera 13", zona)
    assert not cliente.tiene_suscripcion_activa(FECHA)
    assert cliente.obtener_prioridad(FECHA) == 2


def test_regla_camion_confirmada_por_profesor():
    restringida = Zona("Z-03", "Residencial Premium Norte", 14.0, False)
    libre = Zona("Z-02", "Centro", 11.0, True)
    premium = ClientePremium(
        "CLI-001",
        "Laura",
        "Calle 92",
        restringida,
        fecha_compra_suscripcion=date(2026, 11, 1),
        duracion_suscripcion_dias=30,
    )
    estandar = ClienteStandard("CLI-002", "Andres", "Carrera 13", restringida)
    assert not restringida.permite_camion_pesado(premium, FECHA)
    assert restringida.permite_camion_pesado(estandar, FECHA)
    assert libre.permite_camion_pesado(premium, FECHA)


def test_json_original_fallback_de_suscripcion():
    zona = Zona("Z-03", "Residencial Premium Norte", 14.0, False)
    cliente = ClientePremium(
        "CLI-001", "Laura", "Calle 92", zona, suscripcion_activa_declarada=True
    )
    assert cliente.tiene_suscripcion_activa(FECHA)
    assert cliente.obtener_prioridad(FECHA) == 1


def test_parametros_invalidos_no_se_aceptan():
    with pytest.raises(ValueError):
        Zona("Z-99", "Zona incorrecta", -2, True)
    with pytest.raises(ValueError):
        Zona("Z-99", "Zona incorrecta", 2, "si")
    zona = Zona("Z-01", "Chapinero", 8.5, True)
    with pytest.raises(ValueError):
        ClientePremium(
            "CLI-99", "N", "D", zona, fecha_compra_suscripcion=date(2026, 11, 1)
        )
    with pytest.raises(ValueError):
        ClienteStandard("CLI-99", "N", "D", "Z-01")


def test_cliente_padre_es_abstracto():
    zona = Zona("Z-01", "Chapinero", 8.5, True)
    with pytest.raises(TypeError):
        Cliente("CLI-99", "N", "D", zona)
