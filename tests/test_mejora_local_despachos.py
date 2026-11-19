"""Validación de mejora local por reasignación sin modificar el UML."""
from datetime import date

import pytest

import citydelivery.logistica.gestor_despachos as despacho
from citydelivery.logistica.citydelivery import CityDelivery
from citydelivery.logistica.gestor_despachos import GestorDespachos
from citydelivery.modelos.bodega import Bodega
from citydelivery.modelos.cliente import ClientePremium, ClienteStandard
from citydelivery.modelos.paquete import Paquete
from citydelivery.modelos.vehiculo import VanReparto, Motocicleta, CamionPesado
from citydelivery.modelos.zona import Zona

FECHA = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def no_grafo(monkeypatch):
    monkeypatch.setattr(despacho, 'GRAFO_VIAL', None)


def escenario():
    sistema = CityDelivery(Bodega('Bodega', 500, 30))
    norte = Zona('Z-A', 'A', 11, True)
    sur = Zona('Z-B', 'B', 14, True)
    for zona in (norte, sur):
        assert sistema.registrar_zona(zona)
    premium = ClientePremium('VIP', 'Cliente VIP', 'Calle A', norte,
                             fecha_compra_suscripcion=date(2026, 11, 1),
                             duracion_suscripcion_dias=30)
    normal = ClienteStandard('STD', 'Cliente normal', 'Calle B', sur)
    for c in (premium, normal):
        assert sistema.registrar_cliente(c)
    van = VanReparto('VAN', 100, 4, 1)
    moto = Motocicleta('MOTO', 25, .12, 1000)
    for v in (van, moto):
        assert sistema.registrar_vehiculo(v)
    vip = Paquete('PK-VIP', 2, .02, premium)
    pesado = Paquete('PK-PES', 30, .2, normal)
    for p in (vip, pesado):
        assert sistema.bodega.agregar_paquete(p)
    gestor = GestorDespachos(sistema, FECHA)
    return sistema, gestor, van, moto, vip, pesado


def test_rescata_paquete_pendiente_y_no_pierde_premium():
    sistema, gestor, van, moto, vip, pesado = escenario()
    nuevas = gestor.generar_rutas()
    assert len(nuevas) == 2
    assert len(sistema.rutas) == 2
    assert vip.estado == pesado.estado == 'ASIGNADO'
    assert next(r for r in sistema.rutas if vip in r.paquetes).vehiculo is moto
    assert next(r for r in sistema.rutas if pesado in r.paquetes).vehiculo is van
    assert any('Mejora local:' in a for a in gestor.alertas)
    assert not gestor.obtener_paquetes_no_asignados()
    assert sum(len(r.paquetes) for r in sistema.rutas) == 2


def test_reporta_costos_y_distancia_estimados_sin_grafo():
    sistema, gestor, van, moto, vip, pesado = escenario()
    gestor.asignar_paquetes()
    reporte = gestor.generar_reporte()
    assert reporte['asignados'] == 2
    assert reporte['distanciaTotalKm'] == 25
    assert reporte['costoTotalCOP'] == (11 * 1000 + 30 * 14)
    assert reporte['eficienciaTSPvsOrdenCodigoPct'] is None
    assert 'estimación' in reporte['metodoRutas'].lower()


def test_idempotencia_de_despacho_mejorado():
    sistema, gestor, van, moto, vip, pesado = escenario()
    gestor.asignar_paquetes()
    gestor.asignar_paquetes()
    assert len(sistema.rutas) == 2
    assert sum(len(r.paquetes) for r in sistema.rutas) == 2
    assert len({p.codigo for r in sistema.rutas for p in r.paquetes}) == 2


def test_nunca_mueve_ruta_en_curso():
    sistema, gestor, van, moto, vip, pesado = escenario()
    # Primero crear solo la ruta VIP, iniciarla y agregar el paquete difícil.
    sistema.bodega.retirar_paquete(pesado)
    gestor.asignar_paquetes()
    ruta = sistema.rutas[0]
    assert ruta.vehiculo is van
    assert ruta.iniciar_ruta()
    assert sistema.bodega.agregar_paquete(pesado)
    gestor.asignar_paquetes()
    assert ruta.vehiculo is van
    assert ruta.estado == 'EN_RUTA'
    assert pesado.estado == 'PENDIENTE'


def test_no_mueve_una_ruta_si_el_sustituto_no_cabe():
    sistema, gestor, van, moto, vip, pesado = escenario()
    vip.peso = 5.0
    gestor.asignar_paquetes()
    assert len(sistema.rutas) == 1
    assert sistema.rutas[0].vehiculo is van
    assert vip.estado == 'ASIGNADO'
    assert pesado.estado == 'PENDIENTE'


def test_no_mueve_una_ruta_si_sustituto_inhabilitado():
    sistema, gestor, van, moto, vip, pesado = escenario()
    moto.habilitado = False
    gestor.asignar_paquetes()
    assert len(sistema.rutas) == 1
    assert pesado.estado == 'PENDIENTE'
    assert sistema.rutas[0].vehiculo is van


def test_conserva_costos_tras_finalizar_rutas():
    sistema, gestor, van, moto, vip, pesado = escenario()
    gestor.asignar_paquetes()
    costo = gestor.calcular_costo_total()
    for ruta in list(sistema.rutas):
        assert ruta.validar_ruta(FECHA)
        assert ruta.iniciar_ruta()
        assert sistema.finalizar_ruta(ruta.id)
    assert gestor.calcular_costo_total() == costo
    assert sistema.obtener_estado_vehiculo(van.identificador) == 'DISPONIBLE'
    assert sistema.obtener_estado_vehiculo(moto.identificador) == 'DISPONIBLE'
    assert vip.estado == pesado.estado == 'ENTREGADO'


def test_regla_camion_premium_se_respeta_aun_en_rescate():
    sistema, gestor, van, moto, vip, pesado = escenario()
    vip.cliente_destino.zona.acceso_camiones_pesados = False
    # Vea el ejemplo inverso: el camión queda libre, pero NO puede llevar VIP.
    moto.habilitado = False
    camion = CamionPesado('CAM', 200, 4, 15000, 0)
    assert sistema.registrar_vehiculo(camion)
    # Normal puede viajar con CAM; no debe evitarse esta asignación.
    gestor.asignar_paquetes()
    assert vip.estado == 'ASIGNADO'
    assert pesado.estado == 'ASIGNADO'
    assert next(r for r in sistema.rutas if vip in r.paquetes).vehiculo is van
    assert next(r for r in sistema.rutas if pesado in r.paquetes).vehiculo is camion


def test_una_sola_bodega_central():
    sistema, gestor, *_ = escenario()
    assert isinstance(sistema.bodega, Bodega)
    assert not hasattr(gestor, 'bodega')


def test_cantidad_de_atributos_del_uml_inalterada():
    sistema, gestor, *_ = escenario()
    assert set(vars(gestor)) == {
        'sistema', 'paquetes_entrada', 'alertas',
        'hora_inicio_matutino', 'hora_fin_matutino',
        'criterio_prioridad', 'fecha_operacion'
    }


def test_transferencia_fallida_restaurada_sin_paquetes_duplicados(monkeypatch):
    sistema, gestor, van, moto, vip, pesado = escenario()
    # Inyectar un fallo real de carga durante la mejora; el dato previo
    # debe conservarse y el paquete pendiente no se pierde.
    monkeypatch.setattr(moto, 'cargar_paquete', lambda paquete, fecha: False)
    gestor.asignar_paquetes()
    assert len(sistema.rutas) == 1
    ruta = sistema.rutas[0]
    assert ruta.vehiculo is van
    assert ruta.paquetes == [vip]
    assert vip.estado == 'ASIGNADO'
    assert van.carga_actual == [vip]
    assert moto.carga_actual == []
    assert pesado.estado == 'PENDIENTE'
    assert ruta.validar_ruta(FECHA)


def test_rescate_no_genera_estado_ficticio_de_finalizado():
    sistema, gestor, van, moto, vip, pesado = escenario()
    gestor.asignar_paquetes()
    assert all(r.estado == 'PLANEADA' for r in sistema.rutas)
    assert sistema.obtener_estado_vehiculo('VAN') == 'RESERVADO'
    assert sistema.obtener_estado_vehiculo('MOTO') == 'RESERVADO'
    assert not sistema.obtener_vehiculos_disponibles()


def test_ubicaciones_parciales_no_son_requisito_para_planificar():
    sistema, gestor, van, moto, vip, pesado = escenario()
    # El gestor no conoce ni exige lat/lon de cada cliente.
    assert not hasattr(sistema, 'ubicaciones')
    gestor.asignar_paquetes()
    assert gestor.generar_reporte()['asignados'] == 2
    assert len(sistema.rutas) == 2


def test_hay_registro_de_mejora_sin_duplicar_alerta_pendiente():
    sistema, gestor, van, moto, vip, pesado = escenario()
    gestor.asignar_paquetes()
    assert any('Mejora local:' in texto for texto in gestor.alertas)
    assert not any(texto.startswith('Paquete PK-PES:') for texto in gestor.alertas)
    assert pesado.motivo_incidencia == ''
