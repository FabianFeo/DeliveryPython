"""Generador externo de grafo vial para CityDelivery.

No modifica las 13 clases ni los métodos del UML. Requiere ubicaciones
geográficas confirmadas para BODEGA y todos los clientes del JSON.

Uso:
  python scripts/generar_grafo_bogota.py plantilla --json data/citydelivery_ejemplo.json
  python scripts/generar_grafo_bogota.py geocodificar --ubicaciones data/ubicaciones_bogota.json --contacto EMAIL
  python scripts/generar_grafo_bogota.py generar --ubicaciones data/ubicaciones_bogota.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BOGOTA_BOUNDS = {"lat_min": 4.0, "lat_max": 5.2, "lon_min": -74.6, "lon_max": -73.5}
DEFAULT_JSON = Path("data/citydelivery_ejemplo.json")
DEFAULT_UBICACIONES = Path("data/ubicaciones_bogota.json")
DEFAULT_GRAFO = Path("data/grafo_vial_bogota.json")
DEFAULT_CACHE = Path("data/cache_osm/red_bogota.graphml")
MAX_GEOCODE_CALLS = 10


def leer_json(ruta: str | Path) -> dict[str, Any]:
    ruta = Path(ruta)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"No existe el archivo: {ruta}") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON inválido en {ruta}: {exc}") from exc
    if not isinstance(datos, dict):
        raise ValueError(f"El archivo {ruta} debe contener un objeto JSON.")
    return datos


def guardar_json(ruta: str | Path, datos: dict[str, Any]) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ubicaciones_desde_operacion(datos: dict[str, Any]) -> dict[str, Any]:
    """Plantilla sin coordenadas inventadas: la única Bodega + clientes."""
    configuracion = datos.get("configuracion", {})
    bodega = configuracion.get("bodega", {}) if isinstance(configuracion, dict) else {}
    if not isinstance(bodega, dict) or not isinstance(bodega.get("direccion"), str) or not bodega["direccion"].strip():
        raise ValueError("Falta configuracion.bodega.direccion en el JSON de CityDelivery.")
    clientes = datos.get("clientes", [])
    if not isinstance(clientes, list) or not clientes:
        raise ValueError("El JSON debe contener al menos un cliente.")
    ubicaciones = {
        "BODEGA": {
            "direccion": bodega["direccion"], "lat": None, "lon": None,
            "confirmado": False, "fuente": "Pendiente de localizar y verificar",
        }
    }
    for indice, item in enumerate(clientes, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise ValueError(f"clientes[{indice}]: falta un ID válido.")
        if not isinstance(item.get("direccion"), str) or not item["direccion"].strip():
            raise ValueError(f"clientes[{indice}]: falta dirección válida.")
        clave = item["id"].strip()
        if clave == "BODEGA" or clave in ubicaciones:
            raise ValueError(f"ID de cliente duplicado o reservado: {clave}")
        ubicaciones[clave] = {
            "direccion": f"{item['direccion'].strip()}, Bogotá, Colombia",
            "lat": None, "lon": None, "confirmado": False,
            "fuente": "Pendiente de localizar y verificar",
        }
    return {
        "nota": "Completar coordenadas reales y establecer confirmado=true tras revisarlas. No se inventan ubicaciones.",
        "origen": "CityDelivery: una única Bodega Central",
        "ubicaciones": ubicaciones,
    }


def _coordenada_valida(ubicacion: dict[str, Any], nombre: str) -> tuple[float, float]:
    if not ubicacion.get("confirmado") is True:
        raise ValueError(f"{nombre}: ubicación sin confirmar. Revísala y marca confirmado=true.")
    lat, lon = ubicacion.get("lat"), ubicacion.get("lon")
    for campo, valor in [("lat", lat), ("lon", lon)]:
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            raise ValueError(f"{nombre}: {campo} debe ser un número finito (no null).")
    if not (BOGOTA_BOUNDS["lat_min"] <= lat <= BOGOTA_BOUNDS["lat_max"] and
            BOGOTA_BOUNDS["lon_min"] <= lon <= BOGOTA_BOUNDS["lon_max"]):
        raise ValueError(f"{nombre}: coordenada fuera de la región de Bogotá. Revisar lat/lon.")
    return float(lat), float(lon)


def validar_ubicaciones(datos: dict[str, Any]) -> dict[str, tuple[float, float]]:
    ubicaciones = datos.get("ubicaciones")
    if not isinstance(ubicaciones, dict) or "BODEGA" not in ubicaciones or len(ubicaciones) < 2:
        raise ValueError("Se requiere ubicaciones con BODEGA y al menos un cliente.")
    resultado = {}
    for nombre, ubicacion in ubicaciones.items():
        if not isinstance(nombre, str) or not isinstance(ubicacion, dict):
            raise ValueError(f"Ubicación inválida: {nombre!r}.")
        resultado[nombre] = _coordenada_valida(ubicacion, nombre)
    return resultado


def validar_contra_operacion(ubicaciones: dict[str, Any], operacion: dict[str, Any]) -> None:
    clientes = operacion.get("clientes", [])
    if not isinstance(clientes, list):
        raise ValueError("clientes debe ser una lista.")
    esperados = {"BODEGA"} | {c["id"] for c in clientes if isinstance(c, dict) and "id" in c}
    recibidos = set(ubicaciones.get("ubicaciones", {}))
    if esperados != recibidos:
        raise ValueError(
            f"Las ubicaciones no corresponden al JSON. Faltan: {sorted(esperados-recibidos)}. "
            f"Sobran: {sorted(recibidos-esperados)}."
        )


def caja_geografica(puntos: dict[str, tuple[float, float]], margen_km: float = 1.5) -> tuple[float, float, float, float, float]:
    """BBox (oeste, sur, este, norte, km² aprox) de los puntos más margen."""
    if margen_km < 0 or not math.isfinite(margen_km):
        raise ValueError("El margen debe ser un número finito no negativo.")
    latitudes = [lat for lat, _ in puntos.values()]
    longitudes = [lon for _, lon in puntos.values()]
    lat_centro = sum(latitudes) / len(latitudes)
    km_por_grado_lon = 111.32 * math.cos(math.radians(lat_centro))
    lat_margen = margen_km / 111.32
    lon_margen = margen_km / km_por_grado_lon
    oeste, este = min(longitudes) - lon_margen, max(longitudes) + lon_margen
    sur, norte = min(latitudes) - lat_margen, max(latitudes) + lat_margen
    area = (este - oeste) * km_por_grado_lon * (norte - sur) * 111.32
    return oeste, sur, este, norte, area


def matriz_por_red(grafo_calle, nodos: dict[str, Any], *, nx_mod=None) -> dict[str, dict[str, float]]:
    """Dijkstra sobre grafo dirigido de OSM. Distancias en km."""
    if nx_mod is None:
        import networkx as nx_mod
    resultado: dict[str, dict[str, float]] = {}
    for origen, nodo_inicial in nodos.items():
        caminos = nx_mod.single_source_dijkstra_path_length(grafo_calle, nodo_inicial, weight="length")
        resultado[origen] = {}
        for destino, nodo_final in nodos.items():
            if origen == destino:
                continue
            metros = caminos.get(nodo_final)
            if metros is None or not math.isfinite(metros) or metros < 0:
                raise ValueError(
                    f"Sin camino de circulación {origen} → {destino}. "
                    "Revisa red, sentido de las vías y ubicaciones."
                )
            resultado[origen][destino] = round(float(metros) / 1000, 5)
    return resultado


def construir_con_osm(
    puntos: dict[str, tuple[float, float]],
    *, cache: str | Path = DEFAULT_CACHE,
    margen_km: float = 1.5,
    max_area_km2: float = 850,
    max_ajuste_m: float = 350,
    ox_mod=None,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    """Descarga/reutiliza una sola red dirigida y calcula todas las conexiones."""
    if ox_mod is None:
        try:
            import osmnx as ox_mod
        except ImportError as exc:
            raise RuntimeError("Falta OSMnx: instala requirements_grafo.txt en un entorno compatible.") from exc
    if not (math.isfinite(max_ajuste_m) and max_ajuste_m > 0):
        raise ValueError("La distancia máxima de ajuste a la calle debe ser positiva.")
    bbox = caja_geografica(puntos, margen_km)
    if bbox[-1] > max_area_km2:
        raise ValueError(
            f"El área solicitada ({bbox[-1]:.1f} km²) supera el límite "
            f"({max_area_km2:.0f} km²). Usa una red GraphML descargada/preparada por separado "
            "o aumenta el límite conscientemente."
        )
    cache = Path(cache)
    ox_mod.settings.use_cache = True
    ox_mod.settings.cache_folder = str(cache.parent / "respuestas_osm")
    if cache.is_file():
        grafo = ox_mod.io.load_graphml(filepath=str(cache))
        fuente = f"GraphML reutilizado: {cache}"
    else:
        grafo = ox_mod.graph.graph_from_bbox(bbox[:4], network_type="drive", simplify=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        ox_mod.io.save_graphml(grafo, filepath=str(cache))
        fuente = f"OpenStreetMap (OSMnx drive), guardado en {cache}"
    nodos, separaciones = {}, {}
    for nombre, (lat, lon) in puntos.items():
        cercano, metros = ox_mod.distance.nearest_nodes(
            grafo, X=lon, Y=lat, return_dist=True
        )
        if float(metros) > max_ajuste_m:
            raise ValueError(
                f"{nombre}: la calle más cercana está a {float(metros):.0f} m "
                f"(máximo {max_ajuste_m:.0f} m). Revisa la ubicación o red almacenada."
            )
        nodos[nombre] = cercano
        separaciones[nombre] = round(float(metros), 1)
    matriz = matriz_por_red(grafo, nodos)
    meta = {
        "fuente": fuente,
        "grafoDirigido": bool(grafo.is_directed()),
        "red": "drive",
        "unidad": "km",
        "pesoDijkstra": "length (metros por tramo)",
        "cajaGeografica": {"oeste": bbox[0], "sur": bbox[1], "este": bbox[2], "norte": bbox[3]},
        "areaAproximadaKm2": round(bbox[-1], 2),
        "distanciaHastaCalleMetros": separaciones,
        "numeroIntersecciones": len(grafo.nodes),
        "numeroTramosDirigidos": len(grafo.edges),
        "advertencia": "Las ubicaciones deben validarse. La red no incorpora tráfico en tiempo real ni todas las restricciones de vehículo.",
    }
    return matriz, meta


def preparar_grafo_para_menu(matriz: dict[str, dict[str, float]]) -> dict[str, Any]:
    if "BODEGA" not in matriz:
        raise ValueError("Falta BODEGA.")
    nodos = set(matriz)
    for origen, vecinos in matriz.items():
        if not isinstance(vecinos, dict) or set(vecinos) != nodos - {origen}:
            raise ValueError(f"La matriz no está completa en {origen}.")
        for destino, km in vecinos.items():
            if not isinstance(km, (int, float)) or isinstance(km, bool) or not math.isfinite(km) or km < 0:
                raise ValueError(f"Distancia inválida en {origen} → {destino}.")
    return {"grafoVial": matriz}


def geocodificar_candidatos(
    plantilla: dict[str, Any], *, contacto: str, cache_path: str | Path,
    geocoder=None, pausa_segundos: float = 1.2,
) -> tuple[dict[str, Any], int]:
    """Uso puntual MANUAL: sugiere ubicaciones, NUNCA confirma automáticamente.

    Máximo 10 consultas nuevas por ejecución, sin paralelismo y con caché.
    Se debe revisar cada dirección antes de cambiar confirmado a true.
    """
    if not isinstance(contacto, str) or "@" not in contacto or len(contacto) < 6:
        raise ValueError("Indica un correo de contacto real para identificar la consulta.")
    import time
    cache_path = Path(cache_path)
    cache = leer_json(cache_path) if cache_path.exists() else {}
    if geocoder is None:
        try:
            from geopy.geocoders import Nominatim
        except ImportError as exc:
            raise RuntimeError("Falta geopy. Instala requirements_grafo.txt.") from exc
        geocoder = Nominatim(user_agent=f"CityDeliveryAcademico/1.0 ({contacto})", timeout=20)
    pendientes = [
        (clave, valor) for clave, valor in plantilla.get("ubicaciones", {}).items()
        if isinstance(valor, dict) and valor.get("confirmado") is not True
    ]
    nuevas = [x for x in pendientes if x[1].get("direccion", "") not in cache]
    if len(nuevas) > MAX_GEOCODE_CALLS:
        raise ValueError(
            f"Hay {len(nuevas)} consultas nuevas; máximo {MAX_GEOCODE_CALLS} por ejecución. "
            "Usa coordenadas manuales o un proveedor de geocodificación contratado."
        )
    llamadas = 0
    for nombre, registro in pendientes:
        direccion = registro.get("direccion", "")
        if not isinstance(direccion, str) or not direccion.strip():
            raise ValueError(f"{nombre}: falta la dirección.")
        if direccion not in cache:
            if llamadas:
                time.sleep(pausa_segundos)
            encontrado = geocoder.geocode(direccion, exactly_one=True, country_codes="co", addressdetails=True)
            llamadas += 1
            if encontrado is None:
                cache[direccion] = {"encontrado": False}
            else:
                raw = getattr(encontrado, "raw", {}) or {}
                cache[direccion] = {
                    "encontrado": True,
                    "lat": float(encontrado.latitude),
                    "lon": float(encontrado.longitude),
                    "descripcion": str(getattr(encontrado, "address", "")),
                    "tipo": str(raw.get("addresstype", raw.get("type", "no_identificado"))),
                }
            guardar_json(cache_path, cache)
        sugerencia = cache[direccion]
        if sugerencia.get("encontrado"):
            registro["lat"] = sugerencia["lat"]
            registro["lon"] = sugerencia["lon"]
            registro["confirmado"] = False
            registro["fuente"] = "Sugerencia automática SIN confirmar; verificar manualmente"
            registro["coincidencia"] = sugerencia.get("descripcion", "")
            registro["tipoCoincidencia"] = sugerencia.get("tipo", "")
        else:
            registro["fuente"] = "Dirección no encontrada; requiere coordenadas manuales"
    return plantilla, llamadas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exportar grafo vial dirigido Bogotá → CityDelivery, sin modificar UML.")
    comandos = parser.add_subparsers(dest="accion", required=True)
    plantilla = comandos.add_parser("plantilla", help="Crear plantilla de coordenadas para UNA Bodega Central y clientes.")
    plantilla.add_argument("--json", default=str(DEFAULT_JSON), help="JSON de la operación CityDelivery")
    plantilla.add_argument("--salida", default=str(DEFAULT_UBICACIONES))

    geocodificar = comandos.add_parser("geocodificar", help="Sugerir coordenadas (manual y puntual; requiere confirmar).")
    geocodificar.add_argument("--ubicaciones", default=str(DEFAULT_UBICACIONES))
    geocodificar.add_argument("--contacto", required=True, help="Correo real para User-Agent (no se guarda en salida).")
    geocodificar.add_argument("--cache", default="data/cache_osm/geocodificacion.json")

    generar = comandos.add_parser("generar", help="Crear grafoVial a partir de coordenadas confirmadas.")
    generar.add_argument("--json", default=str(DEFAULT_JSON), help="Verificar que todos los ID coincidan")
    generar.add_argument("--ubicaciones", default=str(DEFAULT_UBICACIONES))
    generar.add_argument("--salida", default=str(DEFAULT_GRAFO))
    generar.add_argument("--cache", default=str(DEFAULT_CACHE), help="Red vial GraphML local (se reutiliza)")
    generar.add_argument("--margen-km", type=float, default=1.5)
    generar.add_argument("--max-area-km2", type=float, default=850)
    generar.add_argument("--max-ajuste-m", type=float, default=350)
    args = parser.parse_args(argv)
    try:
        if args.accion == "plantilla":
            datos = ubicaciones_desde_operacion(leer_json(args.json))
            guardar_json(args.salida, datos)
            print(f"✅ Plantilla de {len(datos['ubicaciones'])} puntos: {args.salida}")
            print("Completa/revisa lat y lon de cada punto y marca confirmado=true SOLO tras verificarlo.")
        elif args.accion == "geocodificar":
            print("AVISO: las direcciones se envían a un servicio de terceros. Uso puntual, manual y con caché.")
            datos = leer_json(args.ubicaciones)
            actualizados, consultas = geocodificar_candidatos(datos, contacto=args.contacto, cache_path=args.cache)
            guardar_json(args.ubicaciones, actualizados)
            print(f"✅ {consultas} consultas nuevas. Revisa cada ubicación, aún SIN confirmar.")
            print(f"Consulta la política: https://operations.osmfoundation.org/policies/nominatim/")
        elif args.accion == "generar":
            datos = leer_json(args.ubicaciones)
            validar_contra_operacion(datos, leer_json(args.json))
            puntos = validar_ubicaciones(datos)
            print(f"Calculando distancias sobre calles para {len(puntos)} nodos...")
            matriz, meta = construir_con_osm(
                puntos, cache=args.cache, margen_km=args.margen_km,
                max_area_km2=args.max_area_km2, max_ajuste_m=args.max_ajuste_m
            )
            salida = preparar_grafo_para_menu(matriz)
            guardar_json(args.salida, salida)
            meta["fechaGeneracionUTC"] = datetime.now(timezone.utc).isoformat()
            meta["origen"] = "OpenStreetMap contributors | ODbL"
            guardar_json(str(Path(args.salida).with_suffix("")) + "_metadatos.json", meta)
            print(f"✅ Grafo vial compatible con opción 15: {args.salida}")
            print(f"✅ {len(matriz)} nodos; {sum(map(len, matriz.values()))} distancias dirigidas.")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
