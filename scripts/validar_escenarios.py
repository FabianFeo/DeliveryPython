"""Validador de archivos JSON sorpresa para CityDelivery.

Uso desde la raiz del repositorio:
    .\\.venv\\Scripts\\python.exe scripts\\validar_escenarios.py

No altera las clases del UML, no requiere internet y no modifica datos.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from citydelivery.servicios.lector_json import cargar_sistema_desde_json

CASOS = [
    ('sorpresa_sin_vehiculos.json', 'Sin vehiculos'),
    ('sorpresa_solo_motocicletas.json', 'Solo motos'),
    ('sorpresa_bodega_llena.json', 'Bodega sin capacidad'),
    ('sorpresa_camion_restringido.json', 'Camion y zona restringida'),
    ('sorpresa_75_paquetes.json', '75 paquetes'),
    ('sorpresa_datos_invalidos.json', 'Datos invalidos'),
    ('sorpresa_grafo_sintetico.json', 'Grafo sintetico'),
]


def comprobar(sistema, gestor, resumen, nombre):
    rutas = sistema.rutas
    codigos = [p.codigo for ruta in rutas for p in ruta.paquetes]
    assert len(codigos) == len(set(codigos)), 'Paquetes duplicados entre rutas'
    for ruta in rutas:
        assert ruta.paquetes, 'Ruta sin paquetes'
        assert all(p.cliente_destino.zona is ruta.zona for p in ruta.paquetes)
        assert sum(p.peso for p in ruta.paquetes) <= ruta.vehiculo.capacidad_max_peso + 1e-9
        assert sum(p.volumen for p in ruta.paquetes) <= ruta.vehiculo.capacidad_max_volumen + 1e-9
        assert all(ruta.vehiculo.puede_entregar(p.cliente_destino, gestor.fecha_operacion) for p in ruta.paquetes)
    for vehiculo in sistema.vehiculos:
        assert sum(r.vehiculo is vehiculo and r.ocupa_vehiculo() for r in rutas) <= 1
    assert resumen['costoTotalCOP'] >= 0
    assert resumen['asignados'] == len(codigos)
    if nombre == 'sorpresa_sin_vehiculos.json':
        assert not rutas and resumen['asignados'] == 0
    elif nombre == 'sorpresa_solo_motocicletas.json':
        assert all(p.peso < 5 for r in rutas for p in r.paquetes)
    elif nombre == 'sorpresa_bodega_llena.json':
        assert not rutas and len(resumen['rechazados']) == 15
    elif nombre == 'sorpresa_camion_restringido.json':
        assert [p.codigo for r in rutas for p in r.paquetes] == ['PK-STD']
        assert {p['codigo'] for p in resumen['pendientes']} == {'PK-VIP'}
    elif nombre == 'sorpresa_75_paquetes.json':
        assert resumen['totalPaquetes'] == 75
    elif nombre == 'sorpresa_datos_invalidos.json':
        assert gestor.alertas, 'Debio producir alertas de validacion'
    elif nombre == 'sorpresa_grafo_sintetico.json':
        assert any(r.distancia_km > 0 for r in rutas)
        assert not any('no aplicable' in a for a in gestor.alertas)


def main():
    errores = []
    path = ROOT / 'data' / 'casos_sorpresa'
    print('\nCITYDELIVERY | VALIDACION DE JSON SORPRESA (sin internet)')
    print('-' * 98)
    print(f"{'Escenario':29} {'Zonas':>5} {'Clie.':>5} {'Veh.':>5} {'Asig.':>6} {'Pend.':>6} {'Rech.':>6} {'Costo COP':>12}  Resultado")
    print('-' * 98)
    for nombre, etiqueta in CASOS:
        try:
            resultado = cargar_sistema_desde_json(path / nombre)
            sistema = resultado['sistema']
            gestor = resultado['gestor']
            gestor.asignar_paquetes()
            reporte = gestor.generar_reporte()
            comprobar(sistema, gestor, reporte, nombre)
            print(f"{etiqueta:29} {len(sistema.zonas):>5} {len(sistema.clientes):>5} {len(sistema.vehiculos):>5} "
                  f"{reporte['asignados']:>6} {len(reporte['pendientes']):>6} {len(reporte['rechazados']):>6} "
                  f"{reporte['costoTotalCOP']:>12,.0f}  OK")
        except Exception as exc:
            print(f'{etiqueta:29} ERROR: {exc}')
            errores.append((nombre, str(exc)))
    print('-' * 98)
    print(f'Escenarios: {len(CASOS)} | Correctos: {len(CASOS) - len(errores)} | Fallidos: {len(errores)}')
    if errores:
        print('Revise las diferencias antes de la sustentacion.')
        return 1
    print('Validacion de los siete archivos JSON completada correctamente.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
