"""Pruebas de Paquete y Bodega (migración 02)."""

from datetime import date

import pytest

from citydelivery.modelos.bodega import Bodega
from citydelivery.modelos.cliente import ClientePremium, ClienteStandard
from citydelivery.modelos.paquete import Paquete
from citydelivery.modelos.zona import Zona

FECHA = date(2026, 11, 10)


@pytest.fixture
def clientes():
    zona = Zona("Z-01", "Centro", 8, True)
    premium = ClientePremium(
        "CLI-01",
        "Laura",
        "Calle 1",
        zona,
        fecha_compra_suscripcion=date(2026, 11, 1),
        duracion_suscripcion_dias=30,
    )
    estandar = ClienteStandard("CLI-02", "Andrés", "Calle 2", zona)
    return premium, estandar


def test_paquete_se_crea_pendiente_y_con_prioridad(clientes):
    premium, estandar = clientes
    p = Paquete("PK-01", 2, 0.02, premium)
    q = Paquete("PK-02", 3, 0.03, estandar)
    assert p.estado == "PENDIENTE"
    assert p.esta_pendiente() and not p.esta_asignado()
    assert p.obtener_prioridad(FECHA) == 1
    assert q.obtener_prioridad(FECHA) == 2


def test_paquete_rechaza_datos_invalidos(clientes):
    premium, _ = clientes
    with pytest.raises(ValueError):
        Paquete("", 2, 0.1, premium)
    with pytest.raises(ValueError):
        Paquete("PK", 0, 0.1, premium)
    with pytest.raises(ValueError):
        Paquete("PK", float("nan"), 0.1, premium)
    with pytest.raises(ValueError):
        Paquete("PK", 2, -0.1, premium)
    with pytest.raises(ValueError):
        Paquete("PK", True, 0.1, premium)
    with pytest.raises(ValueError):
        Paquete("PK", 2, 0.1, "CLI-01")


def test_estados_no_permiten_saltos_ilegales(clientes):
    p = Paquete("PK-01", 3, 0.02, clientes[0])
    assert not p.cambiar_estado("ENTREGADO")
    assert p.cambiar_estado("ASIGNADO")
    assert p.esta_asignado()
    assert p.cambiar_estado("EN_RUTA")
    assert p.cambiar_estado("ENTREGADO")
    assert not p.cambiar_estado("PENDIENTE")


def test_paquete_pendiente_puede_conservar_motivo_sin_ser_rechazado(clientes):
    p = Paquete("PK-01", 3, 0.02, clientes[0])
    assert p.registrar_incidencia("PENDIENTE", "No hay vehículo compatible")
    assert p.estado == "PENDIENTE"
    assert "vehículo" in p.motivo_incidencia


def test_bodega_acepta_dentro_de_capacidad_y_calcula_totales(clientes):
    b = Bodega("Bodega Central", 10, 0.1)
    p1 = Paquete("PK-01", 3, 0.035, clientes[0])
    p2 = Paquete("PK-02", 5, 0.040, clientes[1])
    assert b.agregar_paquete(p1)
    assert b.agregar_paquete(p2)
    assert b.calcular_peso_ocupado() == 8
    assert b.calcular_volumen_ocupado() == pytest.approx(0.075)
    assert [p.codigo for p in b.consultar_inventario()] == ["PK-01", "PK-02"]


def test_bodega_rechaza_exceso_de_peso_y_conserva_inventario(clientes):
    b = Bodega("Bodega Central", 10, 0.1)
    assert b.agregar_paquete(Paquete("PK-01", 8, 0.035, clientes[0]))
    extra = Paquete("PK-02", 3, 0.01, clientes[1])
    assert not b.agregar_paquete(extra)
    assert extra.estado == "RECHAZADO"
    assert extra.motivo_incidencia
    assert b.calcular_peso_ocupado() == 8


def test_bodega_rechaza_exceso_de_volumen(clientes):
    b = Bodega("Bodega Central", 100, 0.1)
    assert b.agregar_paquete(Paquete("PK-01", 2, 0.08, clientes[0]))
    extra = Paquete("PK-02", 1, 0.03, clientes[1])
    assert not b.agregar_paquete(extra)
    assert extra.estado == "RECHAZADO"
    assert b.calcular_volumen_ocupado() == pytest.approx(0.08)


def test_bodega_rechaza_codigo_duplicado(clientes):
    b = Bodega("Bodega Central", 20, 0.2)
    p1 = Paquete("PK-01", 1, 0.01, clientes[0])
    p2 = Paquete("PK-01", 2, 0.02, clientes[1])
    assert b.agregar_paquete(p1)
    assert not b.agregar_paquete(p2)
    assert p2.estado == "RECHAZADO"
    assert len(b.consultar_inventario()) == 1
    assert not b.agregar_paquete(p1)
    assert p1.estado == "PENDIENTE"


def test_retirar_paquete_y_proteger_lista_inventario(clientes):
    b = Bodega("Bodega Central", 20, 0.2)
    p = Paquete("PK-01", 1, 0.01, clientes[0])
    assert b.agregar_paquete(p)
    copia = b.consultar_inventario()
    copia.clear()
    assert len(b.consultar_inventario()) == 1
    assert b.retirar_paquete(p)
    assert not b.retirar_paquete(p)
    assert b.calcular_peso_ocupado() == 0


def test_capacidades_invalidas_y_tipo_incorrecto(clientes):
    with pytest.raises(ValueError):
        Bodega("", 10, 1)
    with pytest.raises(ValueError):
        Bodega("Central", -1, 1)
    with pytest.raises(ValueError):
        Bodega("Central", 1, 0)
    b = Bodega("Central", 10, 1)
    with pytest.raises(TypeError):
        b.agregar_paquete({"codigo": "PK"})
