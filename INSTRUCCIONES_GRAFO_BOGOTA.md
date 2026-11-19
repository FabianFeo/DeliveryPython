# CityDelivery · Generador de grafo vial de Bogotá

Este módulo **no cambia las 13 clases ni los métodos del UML**. Es una herramienta externa de preparación: convierte una red vial real en el JSON `grafoVial` que ya lee `CityDelivery` desde la opción **15. Cargar grafo vial**.

## Qué produce

- **UNA sola BODEGA Central**, con el identificador fijo `BODEGA`.
- Un nodo por cada `clientes[].id` del archivo de operación, por ejemplo `CLI-001`, `CLI-002`.
- Distancias **dirigidas** (pueden diferir según el sentido de las calles) en **kilómetros**.
- Caminos mínimos calculados con Dijkstra sobre OpenStreetMap, usando la longitud de cada tramo (`length`) en metros.
- Un JSON compatible con el menú: `data/grafo_vial_bogota.json`.
- Un archivo de metadatos con la procedencia de los datos y las distancias hasta los nodos viales.

El `GestorDespachos` utiliza ese JSON para ejecutar su propio Dijkstra + TSP. **No se modifica `gestor_despachos.py`.**

## Instalación en Windows / VS Code

Descomprime el ZIP sobre la **carpeta raíz** de tu repositorio `D:\programacion\DeliveryPython`, combinando carpetas, sin reemplazar clases existentes.

OSMnx y sus dependencias geoespaciales pueden requerir una versión de Python para la que existan ruedas (`wheels`) disponibles. Como tu proyecto principal usa Python 3.15, para el generador **recomiendo otro entorno virtual con Python 3.13**. Puedes instalarlo desde [python.org](https://www.python.org/downloads/) si todavía no lo tienes.

En PowerShell, desde la raíz del repositorio:

```powershell
py -3.13 --version
py -3.13 -m venv .venv-grafos
.\.venv-grafos\Scripts\python.exe -m pip install --upgrade pip
.\.venv-grafos\Scripts\python.exe -m pip install -r requirements_grafo.txt
```

Si ya tienes una versión de Python compatible con OSMnx, puedes usarla en lugar de 3.13. **No cambies el entorno `.venv` actual de CityDelivery.**

Añade al `.gitignore` principal estas líneas (la caché y las coordenadas pueden contener información de direcciones):

```gitignore
.venv-grafos/
data/cache_osm/
data/ubicaciones_bogota.json
```

## Paso 1. Generar una plantilla con las direcciones del profesor

```powershell
.\.venv-grafos\Scripts\python.exe scripts\generar_grafo_bogota.py plantilla --json data\citydelivery_ejemplo.json
```

Esto crea `data/ubicaciones_bogota.json`, con **7 puntos** del ejemplo: BODEGA + 6 clientes. Todas las coordenadas empiezan en `null`, y `confirmado` en `false` para **no inventar posiciones**.

**No vuelvas a ejecutar `plantilla` después de completar ese archivo**, porque sobrescribiría las coordenadas verificadas.

## Paso 2. Localizar y confirmar cada ubicación

Abre `data/ubicaciones_bogota.json` en VS Code y completa para cada nodo:

```json
"CLI-001": {
  "direccion": "Calle 92 # 14-20, Bogotá, Colombia",
  "lat": 4.0,
  "lon": -74.0,
  "confirmado": true,
  "fuente": "Coordenadas verificadas por el grupo"
}
```

**Los números del ejemplo anterior son SOLO para explicar el formato, no corresponden a esa dirección. No los copies como coordenadas reales.** Usa coordenadas que hayas revisado en un mapa y marca `confirmado=true` únicamente entonces.

### Búsqueda opcional de sugerencias (solo para el ejercicio académico)

Si las direcciones son ficticias o no tienes coordenadas, puedes probar sugerencias de un geocodificador. **No las toma como ciertas**: se guardan con `confirmado=false` y deben verificarse manualmente.

```powershell
.\.venv-grafos\Scripts\python.exe scripts\generar_grafo_bogota.py geocodificar --ubicaciones data\ubicaciones_bogota.json --contacto TU_CORREO_REAL
```

**Antes de utilizarlo:** lee la [política oficial de Nominatim](https://operations.osmfoundation.org/policies/nominatim/). Esta opción es únicamente para un uso académico puntual, bajo la responsabilidad de quien ejecuta el script. Envía las direcciones a un servicio externo: **no uses direcciones privadas o información personal sensible**. Usa un correo real como identificación de la aplicación, evita repetir consultas, no uses esta función en procesos automáticos recurrentes. El script utiliza una sola conexión por vez, con caché, un máximo de 10 consultas nuevas por ejecución y una pausa mínima de 1,2 segundos entre peticiones. Para un uso frecuente o a escala, utiliza un geocodificador contratado o propio.

Los datos de Bogotá del JSON del profesor pueden ser ficticios; un geocodificador puede devolver una calle parecida y no la dirección exacta. **Siempre confirma manualmente la posición.**

## Paso 3. Generar el grafo real de conducción

Cuando todos los puntos estén confirmados:

```powershell
.\.venv-grafos\Scripts\python.exe scripts\generar_grafo_bogota.py generar --json data\citydelivery_ejemplo.json --ubicaciones data\ubicaciones_bogota.json --salida data\grafo_vial_bogota.json
```

La primera ejecución puede descargar una red vial extensa mediante **OSMnx / OpenStreetMap**. No se descarga nada cuando se ejecutan las pruebas. La red se almacena en `data/cache_osm/red_bogota.graphml` para reutilizarla.

El script limita por defecto el área aproximada a 850 km², por precaución. Si los clientes están muy dispersos, dará un error explicativo antes de descargar. También fallará si alguna ubicación queda demasiado lejos de una calle de conducción o si la red no permite el recorrido dirigido entre alguno de los nodos. **No rellena distancias faltantes con valores ficticios.**

Si los puntos se cambian significativamente después de descargar la red, elimina `data/cache_osm/red_bogota.graphml` para reconstruirla con la nueva área. Conserva el resto de la caché para minimizar consultas duplicadas.

## Paso 4. Cargar el grafo en el menú

```powershell
python main.py
```

1. En la **opción 2**, carga la información del archivo `data\citydelivery_ejemplo.json`.
2. En la **opción 15**, carga el archivo `data\grafo_vial_bogota.json`.
3. En la **opción 11**, planifica los despachos.
4. En la **opción 14**, revisa distancias, costos y métricas.

**Importante:** carga el grafo **antes de planificar**. Si ya tienes rutas `PLANEADA`, consulta primero el estado de la operación; el menú puede permitir recalcular algunas rutas al planificar otra vez.

### JSON de salida compatible

```json
{
  "grafoVial": {
    "BODEGA": {"CLI-001": 2.6, "CLI-002": 4.1},
    "CLI-001": {"BODEGA": 3.1, "CLI-002": 1.8},
    "CLI-002": {"BODEGA": 4.5, "CLI-001": 1.7}
  }
}
```

**Estos valores son ilustrativos, no distancias verificadas de Bogotá.** El script real incluye todos los clientes y sus distancias según la red descargada.

## Pruebas locales, sin internet

Desde el repositorio:

```powershell
python -m pytest tests\test_generador_grafo_bogota.py -v
python -m pytest -v
```

La primera instrucción comprueba el generador con un grafo sintético en memoria. Las pruebas existentes de CityDelivery permanecen intactas.

## Limitaciones que explicaremos al profesor

- La geocodificación **no garantiza direcciones exactas**, por eso requiere verificación humana.
- Los caminos se calculan por distancia vial, **no** por tiempo en tráfico real ni restricciones de circulación por tipo de vehículo. Las restricciones de zonas y camiones las aplica el modelo existente.
- **Dijkstra** obtiene los caminos mínimos entre destinos; **TSP** determina el orden de visita para los paquetes asignados a cada ruta.
- El diseño UML actual usa **una `Zona` por `Ruta`** y el algoritmo organiza primero paquetes por zona; esto **no es** una optimización conjunta de todas las zonas y todos los vehículos (VRP global).
- Es posible que el área vial extraída tenga vías unidireccionales que impidan llegar a algunos destinos desde ciertos puntos. El generador falla con un mensaje explicativo, no inventa las conexiones.
- Atribución: **© OpenStreetMap contributors**, datos disponibles bajo licencia **ODbL**. Más información: https://www.openstreetmap.org/copyright

## Documentación

- OSMnx: https://osmnx.readthedocs.io/en/stable/user-reference.html
- Política de Nominatim: https://operations.osmfoundation.org/policies/nominatim/
