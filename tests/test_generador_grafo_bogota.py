"""Pruebas totalmente offline del generador. No descargan mapas ni inventan direcciones."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generar_grafo_bogota.py"
spec = importlib.util.spec_from_file_location("generador_bogota", SCRIPT)
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)


@pytest.fixture
def operacion():
    return {
        "configuracion": {"bodega": {"direccion": "Dirección de prueba, Bogotá"}},
        "clientes": [
            {"id": "CLI-001", "direccion": "Dirección A"},
            {"id": "CLI-002", "direccion": "Dirección B"},
        ],
    }


@pytest.fixture
def puntos():
    return {"BODEGA": (4.60, -74.1), "CLI-001": (4.61, -74.09), "CLI-002": (4.62, -74.08)}


def test_crea_una_sola_bodega_y_clientes_sin_inventar_coordenadas(operacion):
    plantilla = modulo.ubicaciones_desde_operacion(operacion)
    assert set(plantilla["ubicaciones"]) == {"BODEGA", "CLI-001", "CLI-002"}
    assert all(v["lat"] is None and v["lon"] is None and not v["confirmado"] for v in plantilla["ubicaciones"].values())


def test_plantilla_rechaza_ids_repetidos_y_bodega_reservada(operacion):
    operacion["clientes"].append({"id": "CLI-001", "direccion": "Dirección C"})
    with pytest.raises(ValueError, match="duplicado"):
        modulo.ubicaciones_desde_operacion(operacion)
    operacion["clientes"][-1]["id"] = "BODEGA"
    with pytest.raises(ValueError, match="reservado"):
        modulo.ubicaciones_desde_operacion(operacion)


def test_no_acepta_coordenadas_no_confirmadas(operacion):
    data = modulo.ubicaciones_desde_operacion(operacion)
    with pytest.raises(ValueError, match="sin confirmar"):
        modulo.validar_ubicaciones(data)


def test_coordenadas_confirmadas_y_bounds(operacion, puntos):
    data = modulo.ubicaciones_desde_operacion(operacion)
    for key, (lat, lon) in puntos.items():
        data["ubicaciones"][key].update(lat=lat, lon=lon, confirmado=True)
    assert modulo.validar_ubicaciones(data) == puntos
    data["ubicaciones"]["CLI-002"]["lon"] = -70.0
    with pytest.raises(ValueError, match="fuera"):
        modulo.validar_ubicaciones(data)


@pytest.mark.parametrize("valor", [None, float("nan"), float("inf"), "4.65", True])
def test_rechaza_latitud_invalida(operacion, puntos, valor):
    data = modulo.ubicaciones_desde_operacion(operacion)
    for key, (lat, lon) in puntos.items():
        data["ubicaciones"][key].update(lat=lat, lon=lon, confirmado=True)
    data["ubicaciones"]["CLI-001"]["lat"] = valor
    with pytest.raises(ValueError, match="lat"):
        modulo.validar_ubicaciones(data)


def test_valida_ids_exactos(operacion):
    data = modulo.ubicaciones_desde_operacion(operacion)
    del data["ubicaciones"]["CLI-001"]
    with pytest.raises(ValueError, match="Faltan"):
        modulo.validar_contra_operacion(data, operacion)


def test_bbox_contiene_todos_los_puntos_y_suma_margen(puntos):
    oeste, sur, este, norte, area = modulo.caja_geografica(puntos, 1.5)
    assert oeste < min(lon for _, lon in puntos.values())
    assert este > max(lon for _, lon in puntos.values())
    assert sur < min(lat for lat, _ in puntos.values())
    assert norte > max(lat for lat, _ in puntos.values())
    assert 0 < area < 850


def test_dijkstra_dirigido_no_simetrico():
    # Red sintética para prueba: A->B cuesta 2 km pero B->A cuesta 5 km.
    grafo = nx.DiGraph()
    grafo.add_weighted_edges_from(
        [(0, 1, 1000), (1, 0, 4000), (1, 2, 1000), (2, 1, 5000),
         (2, 0, 1000), (0, 2, 7000)], weight="length"
    )
    matriz = modulo.matriz_por_red(grafo, {"BODEGA": 0, "CLI-001": 1, "CLI-002": 2})
    assert matriz["BODEGA"]["CLI-002"] == 2.0
    assert matriz["CLI-002"]["BODEGA"] == 1.0
    assert matriz["CLI-001"]["BODEGA"] == 2.0
    assert set(matriz) == {"BODEGA", "CLI-001", "CLI-002"}
    assert set(modulo.preparar_grafo_para_menu(matriz)) == {"grafoVial"}


def test_ruta_inaccesible_no_produce_grafo_falso():
    grafo = nx.DiGraph()
    grafo.add_edge(0, 1, length=1000)
    with pytest.raises(ValueError, match="Sin camino"):
        modulo.matriz_por_red(grafo, {"BODEGA": 0, "CLI-001": 1})


def test_grafo_incompleto_se_rechaza():
    with pytest.raises(ValueError, match="no está completa"):
        modulo.preparar_grafo_para_menu({"BODEGA": {"CLI-001": 1}, "CLI-001": {}})


def test_caja_demasiado_grande_se_rechaza(puntos):
    points = dict(puntos)
    points["CLI-002"] = (4.88, -74.31)
    with pytest.raises(ValueError, match="supera el límite"):
        modulo.construir_con_osm(points, max_area_km2=20, ox_mod=SimpleNamespace())


def test_integra_osmnx_ficticio_y_exporta_sin_internet(tmp_path, puntos):
    graph = nx.DiGraph()
    graph.add_edge(0, 1, length=1200)
    graph.add_edge(1, 0, length=1500)
    graph.add_edge(1, 2, length=2500)
    graph.add_edge(2, 1, length=2200)
    graph.add_edge(2, 0, length=1300)
    graph.add_edge(0, 2, length=4100)
    data = {"BODEGA": 0, "CLI-001": 1, "CLI-002": 2}
    fake_cache = []

    class FakeOx:
        settings = SimpleNamespace(use_cache=False, cache_folder="")
        def _graph(*_args, **kwargs):
            assert kwargs["network_type"] == "drive"
            return graph
        graph = SimpleNamespace(graph_from_bbox=_graph)
        io = SimpleNamespace(
            save_graphml=lambda grafo, filepath: fake_cache.append(filepath),
            load_graphml=lambda filepath: graph,
        )
        distance = SimpleNamespace(
            nearest_nodes=lambda grafo, X, Y, return_dist: (
                data[next(k for k, (lat, lon) in puntos.items() if lat == Y and lon == X)], 30.0
            )
        )

    matriz, meta = modulo.construir_con_osm(puntos, cache=tmp_path / "red.graphml", ox_mod=FakeOx)
    assert matriz["BODEGA"]["CLI-002"] == 3.7  # 0→1→2
    assert matriz["CLI-002"]["BODEGA"] == 1.3
    assert meta["grafoDirigido"] is True
    assert len(fake_cache) == 1


def test_geocodificacion_solo_sugiere_no_confirma(operacion, tmp_path):
    ubicaciones = modulo.ubicaciones_desde_operacion(operacion)

    class FakeLocation:
        latitude = 4.61
        longitude = -74.07
        address = "Una calle de Bogotá"
        raw = {"addresstype": "road"}

    class FakeGeo:
        def geocode(self, *_args, **kwargs):
            assert kwargs["country_codes"] == "co"
            return FakeLocation()

    updated, count = modulo.geocodificar_candidatos(
        ubicaciones, contacto="estudiante@example.org", cache_path=tmp_path / "cache.json",
        geocoder=FakeGeo(), pausa_segundos=0,
    )
    assert count == 3
    assert all(v["confirmado"] is False for v in updated["ubicaciones"].values())
    with pytest.raises(ValueError, match="sin confirmar"):
        modulo.validar_ubicaciones(updated)

    _, second_count = modulo.geocodificar_candidatos(
        updated, contacto="estudiante@example.org", cache_path=tmp_path / "cache.json",
        geocoder=FakeGeo(), pausa_segundos=0,
    )
    assert second_count == 0


def test_comandos_plantilla_y_error_de_generacion(tmp_path, operacion):
    origen = tmp_path / "operacion.json"
    ubicaciones = tmp_path / "coords.json"
    salida = tmp_path / "grafo.json"
    modulo.guardar_json(origen, operacion)
    assert modulo.main(["plantilla", "--json", str(origen), "--salida", str(ubicaciones)]) == 0
    assert modulo.main(["generar", "--json", str(origen), "--ubicaciones", str(ubicaciones), "--salida", str(salida)]) == 2
    assert not salida.exists()
