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

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLO = RAIZ / "data" / "citydelivery_ejemplo.json"


@pytest.fixture(autouse=True)
def limpiar_grafo_global():
    modulo_gestor.GRAFO_VIAL = None
    yield
    modulo_gestor.GRAFO_VIAL = None


def ejecutar(monkeypatch, entradas, estado=None):
    secuencia = iter(entradas)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(secuencia))
    return iniciar_menu_interactivo(estado)


def operacion_prueba(con_paquete=False):
    bodega = Bodega("Bodega Centro", 1000, 30)
    sistema = CityDelivery(bodega)
    zona = Zona("Z-01", "Centro", 11, True)
    cliente = ClienteStandard("CLI-01", "Ana", "Calle 1", zona)
    van = VanReparto("VAN-01", 500, 4, 120)
    assert sistema.registrar_zona(zona)
    assert sistema.registrar_cliente(cliente)
    assert sistema.registrar_vehiculo(van)
    gestor = GestorDespachos(sistema, date(2026, 11, 10))
    if con_paquete:
        paquete = Paquete("PK-01", 10, 0.2, cliente)
        assert bodega.agregar_paquete(paquete)
        gestor.paquetes_entrada.append(paquete)
    return {"sistema": sistema, "gestor": gestor, "grafo_vial": {}}


def test_salir_sin_operacion(monkeypatch, capsys):
    estado = ejecutar(monkeypatch, ["0"])
    assert estado["sistema"] is None
    assert "Sesión terminada" in capsys.readouterr().out


def test_sin_operacion_exige_crear_o_importar(monkeypatch, capsys):
    estado = ejecutar(monkeypatch, ["3", "11", "0"])
    assert estado["gestor"] is None
    assert "Primero crea la operación" in capsys.readouterr().out


def test_crear_operacion_desde_cero(monkeypatch):
    estado = ejecutar(
        monkeypatch, ["1", "Bodega central", "900", "12,5", "2026-11-10", "0"]
    )
    assert estado["sistema"].bodega.capacidad_max_peso == 900
    assert estado["sistema"].bodega.capacidad_max_volumen == 12.5
    assert estado["gestor"].fecha_operacion.isoformat() == "2026-11-10"


def test_error_numero_y_fecha_sin_romper_menu(monkeypatch, capsys):
    estado = ejecutar(
        monkeypatch, ["1", "Bodega", "-1", "1", "Bodega", "100", "3", "2026-99-99", "0"]
    )
    assert estado["sistema"] is None
    assert capsys.readouterr().out.count("No se completó") == 2


def test_registrar_zonas_y_bloquear_duplicados(monkeypatch, capsys):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch,
        ["3", "Z-02", "Norte", "13", "n", "3", "Z-02", "Duplicada", "1", "s", "7", "0"],
        estado,
    )
    assert len(final["sistema"].zonas) == 2
    assert "Zona duplicada" in capsys.readouterr().out


def test_registrar_cliente_estandar(monkeypatch):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch, ["4", "CLI-02", "Luis", "Carrera 7", "Z-01", "E", "0"], estado
    )
    assert len(final["sistema"].clientes) == 2
    assert final["sistema"].clientes[-1].nombre == "Luis"


def test_registrar_cliente_premium_con_fechas(monkeypatch):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch,
        ["4", "CLI-02", "Sofia", "Calle 7", "Z-01", "P", "s", "2026-11-01", "30", "0"],
        estado,
    )
    assert final["sistema"].clientes[-1].tiene_suscripcion_activa(date(2026, 11, 10))


def test_registrar_cliente_premium_sin_fechas(monkeypatch):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch,
        ["4", "CLI-02", "Sofia", "Calle 7", "Z-01", "P", "n", "s", "0"],
        estado,
    )
    assert final["sistema"].clientes[-1].tiene_suscripcion_activa(date(2026, 11, 10))


def test_rechazar_cliente_de_zona_inexistente(monkeypatch, capsys):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch, ["4", "CLI-02", "Ana", "Calle 7", "Z-XXX", "0"], estado
    )
    assert len(final["sistema"].clientes) == 1
    assert "La zona no existe" in capsys.readouterr().out


@pytest.mark.parametrize(
    "tipo,extras",
    [
        ("1", ["900", "4.99"]),
        ("2", ["120"]),
        ("3", ["180000", "35000"]),
    ],
)
def test_registrar_tres_tipos_vehiculos(monkeypatch, tipo, extras):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch, ["5", tipo, "NUEVO-01", "500", "4", "s", *extras, "0"], estado
    )
    assert len(final["sistema"].vehiculos) == 2
    assert final["sistema"].vehiculos[-1].identificador == "NUEVO-01"


def test_rechazar_limite_motocicleta_de_cinco_kg(monkeypatch, capsys):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch, ["5", "1", "MOTO-10", "25", ".12", "s", "900", "5", "0"], estado
    )
    assert len(final["sistema"].vehiculos) == 1
    assert "menor de 5 kg" in capsys.readouterr().out


def test_no_registrar_vehiculo_duplicado(monkeypatch, capsys):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch, ["5", "2", "VAN-01", "500", "4", "s", "120", "0"], estado
    )
    assert len(final["sistema"].vehiculos) == 1
    assert "duplicado" in capsys.readouterr().out


def test_registrar_paquete_y_consultar_inventario(monkeypatch, capsys):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch, ["6", "PK-NEW", "5", ".03", "CLI-01", "8", "0"], estado
    )
    assert len(final["sistema"].bodega.paquetes) == 1
    assert final["gestor"].paquetes_entrada[-1].codigo == "PK-NEW"
    assert "PK-NEW" in capsys.readouterr().out


def test_rechazo_por_capacidad_y_codigo_duplicado(monkeypatch, capsys):
    estado = operacion_prueba()
    final = ejecutar(
        monkeypatch,
        ["6", "PK-RECH", "3000", ".2", "CLI-01", "6", "PK-RECH", "0"],
        estado,
    )
    assert len(final["gestor"].paquetes_entrada) == 1
    assert final["gestor"].paquetes_entrada[0].estado == "RECHAZADO"
    assert "ya fue recibido" in capsys.readouterr().out


def test_planificar_automaticamente_y_ver_rutas(monkeypatch, capsys):
    estado = operacion_prueba(con_paquete=True)
    final = ejecutar(monkeypatch, ["11", "10", "9", "0"], estado)
    assert len(final["sistema"].rutas) == 1
    assert final["sistema"].rutas[0].estado == "PLANEADA"
    assert final["sistema"].obtener_estado_vehiculo("VAN-01") == "RESERVADO"
    assert "Sin grafo" in capsys.readouterr().out


def test_inicio_fin_y_replanificar(monkeypatch, capsys):
    estado = operacion_prueba(con_paquete=True)
    final = ejecutar(
        monkeypatch, ["11", "12", "R-001", "9", "13", "R-001", "9", "0"], estado
    )
    assert final["sistema"].rutas[0].estado == "FINALIZADA"
    assert final["sistema"].obtener_estado_vehiculo("VAN-01") == "DISPONIBLE"
    assert final["sistema"].bodega.consultar_inventario() == []
    assert final["gestor"].generar_reporte()["asignados"] == 1
    assert "FINALIZADA" in capsys.readouterr().out


def test_ruta_invalida_no_cambia_estado(monkeypatch, capsys):
    estado = operacion_prueba(con_paquete=True)
    final = ejecutar(monkeypatch, ["11", "12", "R-NO", "0"], estado)
    assert final["sistema"].rutas[0].estado == "PLANEADA"
    assert "No existe una ruta planeada" in capsys.readouterr().out


def test_exportar_reporte(monkeypatch, tmp_path):
    estado = operacion_prueba(con_paquete=True)
    salida = tmp_path / "reporte.json"
    final = ejecutar(monkeypatch, ["11", "17", str(salida), "0"], estado)
    reporte = json.loads(salida.read_text(encoding="utf-8"))
    assert reporte["asignados"] == 1
    assert reporte["fechaOperacion"] == "2026-11-10"
    assert len(reporte["rutas"]) == 1
    assert final["sistema"] is estado["sistema"]


def test_carga_json_del_profesor(monkeypatch, capsys):
    final = ejecutar(monkeypatch, ["2", str(EJEMPLO), "0"])
    assert len(final["sistema"].zonas) == 5
    assert len(final["sistema"].clientes) == 6
    assert len(final["sistema"].vehiculos) == 5
    assert len(final["gestor"].paquetes_entrada) == 15
    assert "Archivo cargado" in capsys.readouterr().out


def test_json_planificacion_y_metricas(monkeypatch, capsys):
    final = ejecutar(monkeypatch, ["2", str(EJEMPLO), "11", "14", "16", "0"])
    reporte = final["gestor"].generar_reporte()
    assert reporte["asignados"] == 11
    assert len(reporte["pendientes"]) == 4
    assert len(reporte["rutas"]) == 5
    assert reporte["costoTotalCOP"] == 841220.0
    assert "métricas" in capsys.readouterr().out.lower()


def test_json_no_encontrado_se_recupera(monkeypatch, capsys):
    final = ejecutar(monkeypatch, ["2", "__no_existe__.json", "0"])
    assert final["sistema"] is None
    assert "No existe el archivo" in capsys.readouterr().out


def test_rechazar_reemplazo_conserva_grafo_previo(monkeypatch, tmp_path):
    estado = operacion_prueba()
    grafo = {"BODEGA": {"CLI-01": 2}, "CLI-01": {"BODEGA": 2}}
    estado["grafo_vial"] = grafo
    nuevo_json = tmp_path / "otro.json"
    datos = json.loads(EJEMPLO.read_text(encoding="utf-8"))
    datos["grafoVial"] = {"BODEGA": {"CLI-001": 2}, "CLI-001": {"BODEGA": 2}}
    nuevo_json.write_text(json.dumps(datos), encoding="utf-8")
    final = ejecutar(monkeypatch, ["2", str(nuevo_json), "n", "0"], estado)
    assert final["sistema"] is estado["sistema"]
    assert modulo_gestor.GRAFO_VIAL == grafo


def test_cargar_grafo_vial_y_tsp_dijkstra(monkeypatch, tmp_path, capsys):
    estado = operacion_prueba(con_paquete=True)
    grafo = {"BODEGA": {"CLI-01": 3}, "CLI-01": {"BODEGA": 3}}
    archivo = tmp_path / "grafo.json"
    archivo.write_text(json.dumps({"grafoVial": grafo}), encoding="utf-8")
    final = ejecutar(monkeypatch, ["15", str(archivo), "11", "14", "0"], estado)
    assert final["sistema"].rutas[0].distancia_km == 6
    assert final["gestor"].generar_reporte()["eficienciaTSPvsOrdenCodigoPct"] == 0
    assert final["grafo_vial"] == grafo
    assert "Dijkstra + TSP" in capsys.readouterr().out


def test_grafo_invalido_sigue_en_menu(monkeypatch, tmp_path, capsys):
    estado = operacion_prueba()
    archivo = tmp_path / "grafo_malo.json"
    archivo.write_text(
        json.dumps({"grafoVial": {"BODEGA": {"CLI-01": -1}}}), encoding="utf-8"
    )
    final = ejecutar(monkeypatch, ["15", str(archivo), "0"], estado)
    assert final["grafo_vial"] == {}
    assert "No se completó" in capsys.readouterr().out


def test_reporte_sin_paquetes(monkeypatch, capsys):
    estado = operacion_prueba()
    ejecutar(monkeypatch, ["14", "0"], estado)
    assert "Paquetes recibidos: 0" in capsys.readouterr().out


def test_interrupcion_eof_sale_sin_perder_estado(monkeypatch, capsys):
    estado = operacion_prueba()
    monkeypatch.setattr(
        "builtins.input", lambda _prompt="": (_ for _ in ()).throw(EOFError)
    )
    final = iniciar_menu_interactivo(estado)
    assert final["sistema"] is estado["sistema"]
    assert "Entrada finalizada" in capsys.readouterr().out


def test_main_lanzador_desde_raiz_del_repo():
    resultado = subprocess.run(
        [sys.executable, "main.py"],
        input="0\n",
        text=True,
        cwd=RAIZ,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "CITYDELIVERY" in resultado.stdout
    assert "Sesión terminada" in resultado.stdout


def test_grafo_demo_completo_con_profesor_y_algoritmos(monkeypatch, capsys):
    demo = RAIZ / "data" / "grafo_ejemplo_demo.json"
    final = ejecutar(monkeypatch, ["2", str(EJEMPLO), "15", str(demo), "11", "14", "0"])
    assert final["grafo_vial"]
    assert len(final["sistema"].rutas) == 5
    assert len(final["gestor"].obtener_paquetes_no_asignados()) == 4
    assert not any(
        "no aplicable" in alerta.lower() for alerta in final["gestor"].alertas
    )
    assert "Dijkstra + TSP" in capsys.readouterr().out
