"""Regresiones de la presentación Rich y de importar JSON sin pérdida de datos."""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from citydelivery.logistica import gestor_despachos as modulo_gestor
from citydelivery.logistica.citydelivery import CityDelivery
from citydelivery.logistica.gestor_despachos import GestorDespachos
from citydelivery.modelos.bodega import Bodega
from citydelivery.modelos.cliente import ClienteStandard
from citydelivery.modelos.paquete import Paquete
from citydelivery.modelos.vehiculo import VanReparto
from citydelivery.modelos.zona import Zona
from citydelivery.presentacion.menu import iniciar_menu_interactivo

ROOT = Path(__file__).resolve().parents[1]
JSON_EJEMPLO = ROOT / 'data' / 'citydelivery_ejemplo.json'


@pytest.fixture(autouse=True)
def limpiar_grafo():
    modulo_gestor.GRAFO_VIAL = None
    yield
    modulo_gestor.GRAFO_VIAL = None


def ejecutar(monkeypatch, secuencia, estado=None):
    valores = iter(secuencia)
    monkeypatch.setattr('builtins.input', lambda *_: next(valores))
    return iniciar_menu_interactivo(estado)


def existente():
    sistema = CityDelivery(Bodega('Nuestra Bodega Central', 5000, 100))
    zona = Zona('EX-01', 'Barrio Único', 7, True)
    cliente = ClienteStandard('EX-CLI', 'Cliente propio', 'Av Principal', zona)
    van = VanReparto('VAN-EX', 500, 4.0, 100)
    assert sistema.registrar_zona(zona)
    assert sistema.registrar_cliente(cliente)
    assert sistema.registrar_vehiculo(van)
    gestor = GestorDespachos(sistema, date(2026, 11, 11))
    paquete = Paquete('EX-PK', 2, .01, cliente)
    assert sistema.bodega.agregar_paquete(paquete)
    gestor.paquetes_entrada.append(paquete)
    return {'sistema': sistema, 'gestor': gestor, 'grafo_vial': {}}


def test_opcion_2_se_llama_cargar_informacion_desde_json(monkeypatch, capsys):
    ejecutar(monkeypatch, ['0'])
    texto = capsys.readouterr().out
    assert 'Cargar información desde JSON' in texto
    assert 'Cargar / reemplazar sistema desde JSON' not in texto
    assert 'CARGAR JSON DEL PROFESOR' not in texto


def test_pantalla_de_importacion_tiene_titulo_exactamente_esperado(monkeypatch, capsys):
    final = ejecutar(monkeypatch, ['2', str(JSON_EJEMPLO), '0'])
    texto = capsys.readouterr().out
    assert 'CARGAR JSON DE INFORMACIÓN' in texto
    assert 'Archivo cargado' in texto
    assert 'CARGAR JSON DEL PROFESOR' not in texto
    assert len(final['sistema'].clientes) == 6


def test_opcion_11_da_resultados_visibles_y_tablas(monkeypatch, capsys):
    final = ejecutar(monkeypatch, ['2', str(JSON_EJEMPLO), '11', '0'])
    texto = capsys.readouterr().out
    assert 'RESULTADO DE PLANIFICACIÓN' in texto
    assert 'RUTAS DE LA OPERACIÓN' in texto
    assert 'PAQUETES POR ASIGNAR' in texto
    assert 'Sin grafo' in texto
    assert len(final['sistema'].rutas) == 5
    assert final['gestor'].generar_reporte()['asignados'] == 11


def test_opcion_11_sin_registros_explica_que_falta(monkeypatch, capsys):
    e = existente()
    e['sistema'].zonas.clear()
    ejecutar(monkeypatch, ['11', '0'], e)
    assert 'Faltan: zonas' in capsys.readouterr().out


def test_opcion_11_sin_paquetes_recomienda_paso(monkeypatch, capsys):
    e = existente()
    e['sistema'].bodega.paquetes.clear()
    e['gestor'].paquetes_entrada.clear()
    ejecutar(monkeypatch, ['11', '0'], e)
    assert 'No hay paquetes pendientes' in capsys.readouterr().out


def test_agregar_json_no_borra_bodega_clientes_ni_paquetes(monkeypatch, capsys):
    e = existente()
    bodega_original = e['sistema'].bodega
    final = ejecutar(monkeypatch, ['2', str(JSON_EJEMPLO), 'A', '0'], e)
    assert final['sistema'] is e['sistema']
    assert final['sistema'].bodega is bodega_original
    assert final['sistema'].bodega.direccion == 'Nuestra Bodega Central'
    assert final['gestor'].fecha_operacion == date(2026, 11, 11)
    assert len(final['sistema'].zonas) == 6
    assert len(final['sistema'].clientes) == 7
    assert len(final['sistema'].vehiculos) == 6
    assert len(final['gestor'].paquetes_entrada) == 16
    assert any(p.codigo == 'EX-PK' for p in final['sistema'].bodega.paquetes)
    assert all(p.cliente_destino in final['sistema'].clientes
               for p in final['sistema'].bodega.paquetes)
    assert 'información agregada' in capsys.readouterr().out


def test_reimportar_json_omite_duplicados(monkeypatch, capsys):
    final = ejecutar(monkeypatch, [
        '2', str(JSON_EJEMPLO), '2', str(JSON_EJEMPLO), 'A', '0'
    ])
    assert len(final['sistema'].zonas) == 5
    assert len(final['sistema'].clientes) == 6
    assert len(final['sistema'].vehiculos) == 5
    assert len(final['gestor'].paquetes_entrada) == 15
    assert 'omitieron IDs repetidos' in capsys.readouterr().out


def test_reemplazar_json_es_eleccion_explicita(monkeypatch, capsys):
    e = existente()
    final = ejecutar(monkeypatch, ['2', str(JSON_EJEMPLO), 'R', '0'], e)
    assert final['sistema'] is not e['sistema']
    assert len(final['sistema'].clientes) == 6
    assert all(c.id != 'EX-CLI' for c in final['sistema'].clientes)


def test_cancelar_importacion_preserva_estado_y_grafo(monkeypatch):
    e = existente()
    grafo = {'BODEGA': {'EX-CLI': 2}, 'EX-CLI': {'BODEGA': 2}}
    e['grafo_vial'] = grafo
    final = ejecutar(monkeypatch, ['2', str(JSON_EJEMPLO), 'C', '0'], e)
    assert final['sistema'] is e['sistema']
    assert modulo_gestor.GRAFO_VIAL == grafo


def test_primera_planificacion_con_json_en_proceso_real():
    final = subprocess.run(
        [sys.executable, 'main.py'],
        input=f'2\n{JSON_EJEMPLO}\n11\n0\n', text=True,
        capture_output=True, cwd=ROOT, timeout=30
    )
    assert final.returncode == 0, final.stderr
    assert 'RESULTADO DE PLANIFICACIÓN' in final.stdout
    assert 'CARGAR JSON DE INFORMACIÓN' in final.stdout
    assert 'Sesión terminada' in final.stdout


def test_metricas_visual_funciona_desde_json(monkeypatch, capsys):
    ejecutar(monkeypatch, ['2', str(JSON_EJEMPLO), '11', '14', '0'])
    s = capsys.readouterr().out
    assert 'MÉTRICAS DE OPERACIÓN' in s
    assert 'UTILIZACIÓN DE LA FLOTA' in s
    assert 'Paquetes recibidos: 15' in s
