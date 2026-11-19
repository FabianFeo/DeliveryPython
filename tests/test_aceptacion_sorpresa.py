"""Pruebas adicionales de aceptación, independientes del UML y sin internet.

Ejecutar con: .\\.venv\\Scripts\\python.exe -m pytest tests\\test_aceptacion_sorpresa.py -v
"""
import copy
import json
from datetime import date
from math import isfinite
from pathlib import Path

import pytest

from citydelivery.logistica import gestor_despachos as modulo_gestor
from citydelivery.modelos.vehiculo import CamionPesado, Motocicleta, VanReparto
from citydelivery.servicios.lector_json import cargar_sistema_desde_json

DATA = Path(__file__).resolve().parents[1] / 'data'


@pytest.fixture(autouse=True)
def limpiar_grafo(monkeypatch):
    monkeypatch.setattr(modulo_gestor, 'GRAFO_VIAL', None)


@pytest.fixture
def datos_base():
    return json.loads((DATA / 'citydelivery_ejemplo.json').read_text(encoding='utf-8-sig'))


def cargar(datos):
    return cargar_sistema_desde_json(copy.deepcopy(datos))


def verificar_invariantes(sistema):
    """Reglas que deben mantenerse en todos los escenarios."""
    rutas = sistema.rutas
    codigos = [p.codigo for r in rutas for p in r.paquetes]
    assert len(codigos) == len(set(codigos)), 'Un paquete quedó en dos rutas'
    ids = [r.id for r in rutas]
    assert len(ids) == len(set(ids)), 'Rutas con identificador duplicado'
    for ruta in rutas:
        assert ruta.paquetes, 'Ruta sin paquetes'
        assert ruta.vehiculo in sistema.vehiculos
        assert ruta.zona in sistema.zonas
        assert all(p.cliente_destino.zona is ruta.zona for p in ruta.paquetes)
        assert sum(p.peso for p in ruta.paquetes) <= ruta.vehiculo.capacidad_max_peso + 1e-9
        assert sum(p.volumen for p in ruta.paquetes) <= ruta.vehiculo.capacidad_max_volumen + 1e-9
        assert all(ruta.vehiculo.puede_cargar(p) for p in ruta.paquetes)
        assert all(ruta.vehiculo.puede_entregar(p.cliente_destino, date(2026,11,10)) for p in ruta.paquetes)
        if isinstance(ruta.vehiculo, Motocicleta):
            assert all(p.peso < 5 for p in ruta.paquetes)
        assert isfinite(ruta.calcular_costo()) and ruta.calcular_costo() >= 0
        assert isfinite(ruta.distancia_km) and ruta.distancia_km >= 0
    for vehiculo in sistema.vehiculos:
        activas = [r for r in rutas if r.vehiculo is vehiculo and r.ocupa_vehiculo()]
        assert len(activas) <= 1, 'Un vehículo tiene más de una ruta activa'


def test_01_json_original_se_carga_y_se_planifica(datos_base):
    resultado = cargar(datos_base)
    s, g = resultado['sistema'], resultado['gestor']
    assert (len(s.zonas), len(s.clientes), len(s.vehiculos)) == (5, 6, 5)
    assert resultado['resumen']['paquetesRecibidos'] == 15
    g.asignar_paquetes()
    reporte = g.generar_reporte()
    assert (reporte['asignados'], len(reporte['pendientes']), len(s.rutas)) == (11, 4, 5)
    assert reporte['costoTotalCOP'] == pytest.approx(841220)
    assert reporte['distanciaTotalKm'] == pytest.approx(63.5)
    assert 'Estimación' in reporte['metodoRutas']
    verificar_invariantes(s)


def test_02_cero_vehiculos_conserva_todos_pendientes(datos_base):
    datos_base['vehiculos'] = []
    r = cargar(datos_base)
    s, g = r['sistema'], r['gestor']
    g.asignar_paquetes()
    rep = g.generar_reporte()
    assert len(s.rutas) == 0
    assert rep['asignados'] == 0
    assert len(rep['pendientes']) == 15
    assert rep['costoTotalCOP'] == 0


def test_03_solo_motocicletas_no_transporta_5kg_o_mas(datos_base):
    datos_base['vehiculos'] = [{'id':'MOTO-SORPRESA', 'tipo':'MOTOCICLETA','disponible':True}]
    r = cargar(datos_base)
    s, g = r['sistema'], r['gestor']
    g.asignar_paquetes()
    verificar_invariantes(s)
    assert s.rutas
    assert all(p.peso < 5 for ruta in s.rutas for p in ruta.paquetes)
    assert all(p.estado == 'PENDIENTE' for p in g.paquetes_entrada if p.peso >= 5)


def test_04_bodega_pequena_rechaza_paquetes_por_capacidad(datos_base):
    datos_base['configuracion']['bodega']['capacidadMaximaKg'] = 1
    r = cargar(datos_base)
    s, g = r['sistema'], r['gestor']
    assert not s.bodega.consultar_inventario()
    assert r['resumen']['paquetesRechazados'] == 15
    g.asignar_paquetes()
    assert g.generar_reporte()['asignados'] == 0
    assert len(g.generar_reporte()['rechazados']) == 15


def test_05_cliente_desconocido_es_omitido_con_alerta(datos_base):
    datos_base['paquetes'].append({'codigo':'PK-DESCONOCIDO', 'pesoKg':1,
                                   'volumenM3':0.01,'clienteId':'NO-EXISTE'})
    r = cargar(datos_base)
    assert r['resumen']['paquetesOmitidosPorDatosInvalidos'] == 1
    assert any('clienteId desconocido' in a for a in r['gestor'].alertas)
    assert len(r['gestor'].paquetes_entrada) == 15


def test_06_codigo_repetido_se_registra_como_rechazado(datos_base):
    datos_base['paquetes'].append(copy.deepcopy(datos_base['paquetes'][0]))
    r = cargar(datos_base)
    assert r['resumen']['paquetesRechazados'] == 1
    assert len(r['sistema'].bodega.consultar_inventario()) == 15
    assert len(r['gestor'].paquetes_entrada) == 16
    assert len(r['gestor'].obtener_paquetes_rechazados()) == 1


def test_07_premium_vencido_no_tiene_prioridad(datos_base):
    cliente = next(c for c in datos_base['clientes'] if c['id'] == 'CLI-001')
    cliente.update(fechaCompraSuscripcion='2026-01-01',
                   duracionSuscripcionDias=30, suscripcionActiva=True)
    r = cargar(datos_base)
    vip = next(c for c in r['sistema'].clientes if c.id == 'CLI-001')
    assert not vip.tiene_suscripcion_activa(date(2026, 11, 10))
    assert vip.obtener_prioridad(date(2026, 11, 10)) == 2


def test_08_camion_zona_restringida_distingue_premium_y_estandar(datos_base):
    datos_base['zonas'] = [{'id':'Z-R','nombre':'Zona restringida',
                              'distanciaDesdeBodegaKm':8.0,'accesoCamionesPesados':False}]
    datos_base['clientes'] = [
        {'id':'VIP','nombre':'Premium','categoria':'PREMIUM','direccion':'Calle X',
         'zonaId':'Z-R','suscripcionActiva':True},
        {'id':'STD','nombre':'Estandar','categoria':'ESTANDAR','direccion':'Calle Y',
         'zonaId':'Z-R','suscripcionActiva':False},
    ]
    datos_base['vehiculos'] = [{'id':'CAM-TEST','tipo':'CAMION_PESADO','disponible':True}]
    datos_base['paquetes'] = [
        {'codigo':'PK-VIP','pesoKg':100,'volumenM3':1,'clienteId':'VIP','estado':'PENDIENTE'},
        {'codigo':'PK-STD','pesoKg':100,'volumenM3':1,'clienteId':'STD','estado':'PENDIENTE'},
    ]
    r = cargar(datos_base)
    s,g = r['sistema'],r['gestor']
    g.asignar_paquetes()
    verificar_invariantes(s)
    assert len(s.rutas) == 1
    assert isinstance(s.rutas[0].vehiculo, CamionPesado)
    assert [p.codigo for p in s.rutas[0].paquetes] == ['PK-STD']
    assert {p.codigo for p in g.obtener_paquetes_no_asignados()} == {'PK-VIP'}


def test_09_varias_decenas_paquetes_sin_codigos_duplicados(datos_base):
    ejemplo = datos_base['paquetes'][0]
    for i in range(60):
        datos_base['paquetes'].append({**ejemplo, 'codigo':f'PK-EXTRA-{i:03d}',
                                       'pesoKg': 1.0, 'volumenM3':.002})
    r = cargar(datos_base)
    s,g = r['sistema'],r['gestor']
    assert r['resumen']['paquetesRecibidos'] == 75
    assert len(s.bodega.consultar_inventario()) == 75
    g.asignar_paquetes()
    verificar_invariantes(s)
    assert g.generar_reporte()['totalPaquetes'] == 75
    assert g.generar_reporte()['asignados'] + len(g.generar_reporte()['pendientes']) == 75


def test_10_replanificar_sin_cambios_no_duplica_rutas(datos_base):
    r = cargar(datos_base)
    s,g = r['sistema'],r['gestor']
    g.asignar_paquetes()
    n_rutas = len(s.rutas)
    anterior = sorted(p.codigo for ruta in s.rutas for p in ruta.paquetes)
    g.asignar_paquetes()
    assert len(s.rutas) == n_rutas
    assert sorted(p.codigo for ruta in s.rutas for p in ruta.paquetes) == anterior
    verificar_invariantes(s)


def test_11_jornada_con_varias_rondas_y_costo_historico(datos_base):
    r = cargar(datos_base)
    s,g = r['sistema'],r['gestor']
    costo_anterior = 0
    for ronda in range(10):
        g.asignar_paquetes()
        verificar_invariantes(s)
        costo_total = g.calcular_costo_total()
        assert costo_total >= costo_anterior
        costo_anterior = costo_total
        activas = [ruta for ruta in s.rutas if ruta.estado == 'PLANEADA']
        if not activas:
            break
        for ruta in activas:
            assert ruta.validar_ruta(g.fecha_operacion)
            assert ruta.iniciar_ruta()
            assert s.finalizar_ruta(ruta.id)
        assert g.calcular_costo_total() == costo_total
    assert not g.obtener_paquetes_no_asignados(), 'Quedaron pendientes pese a cerrar varias rondas'
    assert all(p.estado == 'ENTREGADO' for p in g.paquetes_entrada)
    assert all(s.obtener_estado_vehiculo(v.identificador) == 'DISPONIBLE'
               for v in s.vehiculos if v.habilitado)
    assert not s.bodega.consultar_inventario()


def test_12_grafo_completo_ficticio_activa_dijkstra_y_tsp(datos_base):
    # Matriz sintética de distancias, NO distancias reales de Bogotá.
    nodos = ['BODEGA'] + [c['id'] for c in datos_base['clientes']]
    datos_base['grafoVial'] = {
        a: {b: float(1 + abs(i-j)) for j,b in enumerate(nodos) if a!=b}
        for i,a in enumerate(nodos)
    }
    r = cargar(datos_base)
    s,g = r['sistema'],r['gestor']
    assert r['resumen']['tieneGrafoVial']
    g.asignar_paquetes()
    assert s.rutas
    assert not any('no aplicable' in alerta for alerta in g.alertas)
    verificar_invariantes(s)
    assert all(ruta.distancia_km > 0 for ruta in s.rutas)


def test_13_no_reutiliza_grafo_de_otro_json(datos_base):
    nodos = ['BODEGA'] + [c['id'] for c in datos_base['clientes']]
    uno = copy.deepcopy(datos_base)
    uno['grafoVial'] = {a: {b: 2 for b in nodos if b != a} for a in nodos}
    assert cargar(uno)['resumen']['tieneGrafoVial']
    dos = cargar(datos_base)
    assert not dos['resumen']['tieneGrafoVial']
    assert modulo_gestor.GRAFO_VIAL is None
    dos['gestor'].asignar_paquetes()
    assert 'Estimación' in dos['gestor'].generar_reporte()['metodoRutas']


def test_14_json_malformado_no_se_carga():
    with pytest.raises(ValueError):
        cargar_sistema_desde_json('{"metadata":')


def test_15_suscripcion_no_puede_habilitar_camion_para_premium_activo_en_zona_restringida(datos_base):
    r = cargar(datos_base)
    s,g = r['sistema'],r['gestor']
    for cliente in s.clientes:
        if cliente.id == 'CLI-001':
            zona = cliente.zona
            camion = next(v for v in s.vehiculos if isinstance(v, CamionPesado))
            assert not camion.puede_entregar(cliente, g.fecha_operacion)
            assert not zona.permite_camion_pesado(cliente,g.fecha_operacion)


def test_16_reporte_no_inventa_distancias_viales_sin_grafo(datos_base):
    r = cargar(datos_base)
    g = r['gestor']
    g.asignar_paquetes()
    reporte = g.generar_reporte()
    assert reporte['eficienciaTSPvsOrdenCodigoPct'] is None
    assert 'Estimación' in reporte['metodoRutas']
    assert reporte['costoTotalCOP'] >= 0
