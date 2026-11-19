import copy
import io
import json
from datetime import date
from pathlib import Path

import pytest

from citydelivery.logistica import gestor_despachos as modulo_gestor
from citydelivery.logistica.citydelivery import CityDelivery
from citydelivery.logistica.gestor_despachos import GestorDespachos
from citydelivery.modelos.cliente import ClientePremium, ClienteStandard
from citydelivery.modelos.vehiculo import CamionPesado, Motocicleta, VanReparto
from citydelivery.servicios.lector_json import cargar_sistema_desde_json

RUTA_EJEMPLO = (
    Path(__file__).resolve().parents[1] / "data" / "citydelivery_ejemplo.json"
)


@pytest.fixture(autouse=True)
def reiniciar_grafo():
    modulo_gestor.GRAFO_VIAL = None
    yield
    modulo_gestor.GRAFO_VIAL = None


@pytest.fixture
def datos():
    return json.loads(RUTA_EJEMPLO.read_text(encoding="utf-8"))


def test_archivo_profesor_carga_cinco_zonas_seis_clientes_y_quince_paquetes():
    resultado = cargar_sistema_desde_json(RUTA_EJEMPLO)
    assert isinstance(resultado["sistema"], CityDelivery)
    assert isinstance(resultado["gestor"], GestorDespachos)
    assert resultado["resumen"]["zonas"] == 5
    assert resultado["resumen"]["clientes"] == 6
    assert resultado["resumen"]["vehiculos"] == 5
    assert resultado["resumen"]["paquetesRecibidos"] == 15
    assert resultado["resumen"]["paquetesAlmacenados"] == 15
    assert resultado["resumen"]["paquetesRechazados"] == 0
    assert resultado["resumen"]["fechaOperacion"] == "2026-11-10"
    assert resultado["resumen"]["tieneGrafoVial"] is False


def test_referencias_entre_clientes_paquetes_y_zonas(datos):
    r = cargar_sistema_desde_json(datos)
    s = r["sistema"]
    assert s.bodega.direccion == datos["configuracion"]["bodega"]["direccion"]
    assert len({id(p.cliente_destino) for p in s.bodega.paquetes}) == 6
    assert all(
        any(p.cliente_destino is c for c in s.clientes) for p in s.bodega.paquetes
    )
    assert all(any(c.zona is z for z in s.zonas) for c in s.clientes)
    assert sum(isinstance(c, ClientePremium) for c in s.clientes) == 3
    assert sum(isinstance(c, ClienteStandard) for c in s.clientes) == 3


def test_tipos_de_vehiculos_y_tarifas_coinciden_con_json(datos):
    s = cargar_sistema_desde_json(datos)["sistema"]
    assert sum(isinstance(v, Motocicleta) for v in s.vehiculos) == 2
    assert sum(isinstance(v, VanReparto) for v in s.vehiculos) == 2
    assert sum(isinstance(v, CamionPesado) for v in s.vehiculos) == 1
    van = next(v for v in s.vehiculos if isinstance(v, VanReparto))
    assert van.costo_por_kg_km == 120.0
    camion = next(v for v in s.vehiculos if isinstance(v, CamionPesado))
    assert camion.calcular_costo(17.5) == 215000


def test_primera_planificacion_profesor_y_metricas_sin_grafo(datos):
    r = cargar_sistema_desde_json(datos)
    r["gestor"].asignar_paquetes()
    reporte = r["gestor"].generar_reporte()
    assert reporte["totalPaquetes"] == 15
    assert reporte["asignados"] == 11
    assert len(reporte["pendientes"]) == 4
    assert len(reporte["rutas"]) == 5
    assert reporte["costoTotalCOP"] == 841220.0
    assert reporte["distanciaTotalKm"] == 63.5
    assert reporte["eficienciaTSPvsOrdenCodigoPct"] is None
    assert "Estimación" in reporte["metodoRutas"]
    assert any("No se aplicaron TSP ni Dijkstra" in a for a in reporte["alertas"])


@pytest.mark.parametrize(
    "tipo", ["dict", "bytes", "texto", "archivo_texto", "archivo_bytes"]
)
def test_acepta_multiples_formatos_de_entrada(datos, tipo):
    serializado = json.dumps(datos, ensure_ascii=False)
    origen = {
        "dict": datos,
        "bytes": serializado.encode("utf-8"),
        "texto": serializado,
        "archivo_texto": io.StringIO(serializado),
        "archivo_bytes": io.BytesIO(serializado.encode("utf-8")),
    }[tipo]
    assert cargar_sistema_desde_json(origen)["resumen"]["paquetesAlmacenados"] == 15


def test_fecha_de_operacion_opcional_sobrescribe_metadata(datos):
    resultado = cargar_sistema_desde_json(datos, fecha_operacion=date(2026, 11, 16))
    assert resultado["gestor"].fecha_operacion == date(2026, 11, 16)
    assert resultado["resumen"]["fechaOperacion"] == "2026-11-16"


def test_fecha_de_suscripcion_prevalece_sobre_flag(datos):
    premium = next(c for c in datos["clientes"] if c["id"] == "CLI-001")
    premium.update(
        {
            "fechaCompraSuscripcion": "2026-01-01",
            "duracionSuscripcionDias": 5,
            "suscripcionActiva": True,
        }
    )
    cliente = cargar_sistema_desde_json(datos)["sistema"].clientes[0]
    assert isinstance(cliente, ClientePremium)
    assert not cliente.tiene_suscripcion_activa(date(2026, 11, 10))


def test_suscripcion_sin_fechas_usa_booleano_declarado(datos):
    premium = next(c for c in datos["clientes"] if c["id"] == "CLI-001")
    premium["suscripcionActiva"] = True
    cliente = cargar_sistema_desde_json(datos)["sistema"].clientes[0]
    assert cliente.tiene_suscripcion_activa(date(2026, 11, 10))
    assert not cliente.zona.permite_camion_pesado(cliente, date(2026, 11, 10))


def test_flota_generada_si_no_hay_lista_explicita(datos):
    del datos["vehiculos"]
    r = cargar_sistema_desde_json(datos)
    assert len(r["sistema"].vehiculos) == 5
    assert {v.identificador for v in r["sistema"].vehiculos} == {
        "MOTO-01",
        "MOTO-02",
        "VAN-01",
        "VAN-02",
        "CAM-01",
    }
    assert any("cantidadDisponible" in a for a in r["gestor"].alertas)


def test_lista_explicita_de_vehiculos_prevalece_sobre_cantidad_disponible(datos):
    datos["vehiculos"] = [
        {"id": "UNICA-VAN", "tipo": "VAN", "disponible": True},
    ]
    r = cargar_sistema_desde_json(datos)
    assert [v.identificador for v in r["sistema"].vehiculos] == ["UNICA-VAN"]


def test_vehiculo_inhabilitado_no_es_disponible(datos):
    datos["vehiculos"][0]["disponible"] = False
    sistema = cargar_sistema_desde_json(datos)["sistema"]
    assert sistema.obtener_estado_vehiculo("MOTO-01") == "INHABILITADO"
    assert "MOTO-01" not in [
        v.identificador for v in sistema.obtener_vehiculos_disponibles()
    ]


def test_duplicado_de_vehiculo_genera_alerta(datos):
    datos["vehiculos"].append(copy.deepcopy(datos["vehiculos"][0]))
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["vehiculos"] == 5
    assert r["resumen"]["registrosOmitidos"]["vehiculos"] == 1
    assert any(
        "duplic" in a.lower() or "repetid" in a.lower() for a in r["gestor"].alertas
    )


def test_zona_invalida_impide_cliente_que_la_referencia(datos):
    datos["zonas"][0]["distanciaDesdeBodegaKm"] = -5
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["zonas"] == 4
    assert r["resumen"]["registrosOmitidos"]["zonas"] == 1
    assert r["resumen"]["registrosOmitidos"]["clientes"] == 1
    assert r["resumen"]["registrosOmitidos"]["paquetes"] >= 1


def test_capacidad_bodega_rechaza_paquete_sin_omitirlo(datos):
    datos["configuracion"]["bodega"]["capacidadMaximaKg"] = 1
    datos["configuracion"]["bodega"]["capacidadMaximaM3"] = 1
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["paquetesRecibidos"] == 15
    assert r["resumen"]["paquetesAlmacenados"] == 0
    assert r["resumen"]["paquetesRechazados"] == 15
    assert r["resumen"]["paquetesOmitidosPorDatosInvalidos"] == 0


def test_codigo_paquete_duplicado_se_registra_como_rechazado(datos):
    datos["paquetes"].append(copy.deepcopy(datos["paquetes"][0]))
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["paquetesRecibidos"] == 16
    assert r["resumen"]["paquetesAlmacenados"] == 15
    assert r["resumen"]["paquetesRechazados"] == 1
    assert any(
        p.codigo == "PK-001" and p.estado == "RECHAZADO"
        for p in r["gestor"].paquetes_entrada
    )


def test_paquete_rechazado_en_json_conserva_motivo(datos):
    datos["paquetes"][0].update(
        {"estado": "RECHAZADO", "motivoIncidencia": "Empaque no conforme"}
    )
    r = cargar_sistema_desde_json(datos)
    rechazado = next(p for p in r["gestor"].paquetes_entrada if p.codigo == "PK-001")
    assert rechazado.estado == "RECHAZADO"
    assert rechazado.motivo_incidencia == "Empaque no conforme"
    assert r["resumen"]["paquetesAlmacenados"] == 14


def test_paquete_cliente_desconocido_se_omite_con_alerta(datos):
    datos["paquetes"][0]["clienteId"] = "NO-EXISTE"
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["registrosOmitidos"]["paquetes"] == 1
    assert r["resumen"]["paquetesAlmacenados"] == 14
    assert any("clienteId desconocido" in a for a in r["gestor"].alertas)


def test_paquete_con_estado_entregado_sin_ruta_se_omite(datos):
    datos["paquetes"][0]["estado"] = "ENTREGADO"
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["registrosOmitidos"]["paquetes"] == 1
    assert any("no reconstruible sin historial" in a for a in r["gestor"].alertas)


def test_json_invalido_no_se_carga():
    with pytest.raises(ValueError, match="JSON"):
        cargar_sistema_desde_json(b"{no-es-json")
    with pytest.raises(ValueError, match="raíz"):
        cargar_sistema_desde_json(b"[1, 2]")


def test_ruta_inexistente_da_error_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="No se encontró"):
        cargar_sistema_desde_json(tmp_path / "no_existe.json")


def test_metadata_fecha_invalida_genera_error(datos):
    datos["metadata"]["fechaOperacion"] = "2026-99-99"
    with pytest.raises(ValueError, match="fechaOperacion"):
        cargar_sistema_desde_json(datos)


@pytest.mark.parametrize(
    "clave,valor",
    [("moneda", "USD"), ("unidadPeso", "lb"), ("unidadVolumen", "litros")],
)
def test_unidades_no_soportadas_generan_error(datos, clave, valor):
    datos["configuracion"][clave] = valor
    with pytest.raises(ValueError, match=clave):
        cargar_sistema_desde_json(datos)


def test_sin_bodega_rechaza_configuracion(datos):
    del datos["configuracion"]["bodega"]
    with pytest.raises(ValueError, match="bodega"):
        cargar_sistema_desde_json(datos)


def test_seccion_con_tipo_incorrecto_genera_error(datos):
    datos["clientes"] = {"CLI-1": "dato incorrecto"}
    with pytest.raises(ValueError, match="clientes"):
        cargar_sistema_desde_json(datos)


def test_cantidad_variable_de_paquetes_y_clientes(datos):
    datos["paquetes"] = []
    for i in range(40):
        datos["paquetes"].append(
            {
                "codigo": f"PK-VARIABLE-{i:03d}",
                "pesoKg": 1,
                "volumenM3": 0.001,
                "clienteId": datos["clientes"][i % len(datos["clientes"])]["id"],
            }
        )
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["paquetesRecibidos"] == 40
    assert r["resumen"]["paquetesAlmacenados"] == 40
    assert r["resumen"]["paquetesRechazados"] == 0


def test_tsp_y_dijkstra_se_habilitan_solo_si_hay_grafo_completo(datos):
    datos["zonas"] = [datos["zonas"][0]]
    datos["clientes"] = [
        {
            "id": "C-A",
            "nombre": "Cliente A",
            "direccion": "Calle A",
            "categoria": "ESTANDAR",
            "zonaId": "Z-01",
        },
        {
            "id": "C-B",
            "nombre": "Cliente B",
            "direccion": "Calle B",
            "categoria": "ESTANDAR",
            "zonaId": "Z-01",
        },
    ]
    datos["vehiculos"] = [{"id": "VAN-01", "tipo": "VAN", "disponible": True}]
    datos["paquetes"] = [
        {"codigo": "PA", "pesoKg": 8, "volumenM3": 0.04, "clienteId": "C-A"},
        {"codigo": "PB", "pesoKg": 6, "volumenM3": 0.04, "clienteId": "C-B"},
    ]
    datos["grafoVial"] = {
        "BODEGA": {"C-A": 6, "C-B": 8},
        "C-A": {"BODEGA": 6, "C-B": 3},
        "C-B": {"BODEGA": 8, "C-A": 3},
    }
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["tieneGrafoVial"]
    assert modulo_gestor.GRAFO_VIAL == datos["grafoVial"]
    r["gestor"].asignar_paquetes()
    assert len(r["sistema"].rutas) == 1
    assert r["sistema"].rutas[0].distancia_km == 17.0
    assert r["gestor"].calcular_costo_total() == 28560.0


def test_grafo_invalido_hace_fallback_y_limpia_configuracion(datos):
    modulo_gestor.GRAFO_VIAL = {"BODEGA": {"C1": 1}}
    datos["grafoVial"] = {"BODEGA": {"CLI-01": -3}}
    r = cargar_sistema_desde_json(datos)
    assert r["grafo_vial"] is None
    assert modulo_gestor.GRAFO_VIAL is None
    assert any("grafoVial inválido" in a for a in r["gestor"].alertas)


def test_segunda_operacion_sin_grafo_no_reutiliza_grafo_anterior(datos):
    con_grafo = copy.deepcopy(datos)
    con_grafo["grafoVial"] = {"BODEGA": {"CLI-001": 7}, "CLI-001": {"BODEGA": 7}}
    cargar_sistema_desde_json(con_grafo)
    assert modulo_gestor.GRAFO_VIAL is not None
    cargar_sistema_desde_json(datos)
    assert modulo_gestor.GRAFO_VIAL is None


def test_grafo_sin_conexion_completa_fallback_por_ruta(datos):
    datos["grafoVial"] = {"BODEGA": {"CLI-001": 5}, "CLI-001": {}}
    r = cargar_sistema_desde_json(datos)
    assert r["resumen"]["tieneGrafoVial"]
    r["gestor"].asignar_paquetes()
    assert any("Dijkstra/TSP no aplicable" in a for a in r["gestor"].alertas)
    assert all(
        ruta.distancia_km == ruta.zona.distancia_desde_bodega_km
        for ruta in r["sistema"].rutas
    )
