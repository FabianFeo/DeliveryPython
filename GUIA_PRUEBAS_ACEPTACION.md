# CityDelivery | Pruebas de aceptación y sustentación

Este paquete **solo añade** un archivo de pruebas, siete JSON sorpresa, un validador y esta guía. **No sobrescribe `src/citydelivery` ni altera las 13 clases o métodos del UML.**

## 1. Instalar la batería

Desde la raíz del repositorio `D:\programacion\DeliveryPython`, extrae el ZIP conservando las carpetas `tests`, `data/casos_sorpresa` y `scripts`.

Utiliza siempre **el intérprete del entorno virtual**:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

**Referencia observada en la versión validada:** 218 pruebas correctas (202 originales + 16 de aceptación). Si tienes cambios propios o pruebas nuevas, el total puede ser distinto. Si hay fallos, conserva su salida: no cambies clases a ciegas.

Para ejecutar solo las nuevas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_aceptacion_sorpresa.py -v
```

## 2. Probar siete JSON sorpresa de forma automática

```powershell
.\.venv\Scripts\python.exe scripts\validar_escenarios.py
```

No requiere internet, OSMnx, coordenadas reales ni grafo vial de Bogotá. Imprime una tabla por escenario y termina con `7 correctos, 0 fallidos` en la versión validada. **Las distancias por zona son estimaciones de ida, no rutas viales reales**. El grafo incluido es **sintético**, solo para probar Dijkstra + TSP.

| Archivo | Qué comprueba |
|---|---|
| `sorpresa_sin_vehiculos.json` | Sin flota, cero asignaciones, 15 pendientes |
| `sorpresa_solo_motocicletas.json` | Ninguna moto carga paquetes de 5 kg o más |
| `sorpresa_bodega_llena.json` | Bodega pequeña, 15 rechazados, 0 entregas planeadas |
| `sorpresa_camion_restringido.json` | Camión no entrega a Premium activo en zona restringida, sí a Estándar |
| `sorpresa_75_paquetes.json` | Escala a una cantidad variable y controla duplicados y capacidad |
| `sorpresa_datos_invalidos.json` | Detecta duplicado y cliente desconocido, conserva alertas |
| `sorpresa_grafo_sintetico.json` | Activa Dijkstra + TSP sin usar coordenadas ni datos viales reales |

## 3. Prueba manual de extremo a extremo (menú)

Inicia CityDelivery:

```powershell
.\.venv\Scripts\python.exe main.py
```

Prueba en este orden:

1. **Opción 2**, "Cargar información desde JSON": abre `data\citydelivery_ejemplo.json`. Si existe una operación previa, **elige reemplazar**; no agregar.
2. Comprueba que se cargaron **5 zonas, 6 clientes, 5 vehículos y 15 paquetes**.
3. **Opción 8**, inventario: observa los 15 paquetes iniciales.
4. **Opción 11**, planificar: primera ronda esperada **11 asignados, 4 pendientes, 5 rutas planeadas, 63,5 km estimados de ida y $841.220 COP** en la versión validada sin grafo.
5. **Opción 9**, flota: verifica los vehículos reservados, no libres.
6. **Opción 10**, rutas: verifica códigos, zonas, cliente destinatario y estado `PLANEADA`.
7. **Opción 14**, métricas: comprueba 11 asignados, 4 pendientes y costos consistentes. Debe indicar estimación por zona, **no** una optimización TSP real.
8. **Opción 12**, iniciar cada ruta planeada; **opción 13**, finalizar cada una. Vuelve a **opción 9** y verifica vehículos liberados.
9. **Opción 11**, planifica los cuatro pendientes restantes, inicia y finaliza las nuevas rutas. Deben quedar **15 paquetes entregados y 0 pendientes**.
10. **Opción 17**, exporta un reporte JSON y comprueba su contenido (no supone guardar/restaurar la operación completa).
11. **Opción 0**, salir.

Si alguna pantalla difiere, guarda el texto exacto, la opción pulsada y el JSON cargado para revisarlo.

### Pruebas manuales adicionales

- Reinicia el programa, carga `data\casos_sorpresa\sorpresa_sin_vehiculos.json` y prueba opción 11: debe avisar que **no hay vehículos**, sin cerrarse ni crear rutas.
- Reinicia, carga `data\casos_sorpresa\sorpresa_camion_restringido.json`: el paquete Premium `PK-VIP` debe permanecer **pendiente**; `PK-STD` puede asignarse al camión.
- Reinicia, carga `data\casos_sorpresa\sorpresa_grafo_sintetico.json`: las distancias serán calculadas con grafo ficticio, **no** distancias de Bogotá.
- Prueba registrar manualmente (opciones 3, 4, 5 y 6), duplicar un código, revisar las alertas (opción 16), cargar un grafo (15) y cancelar una importación (2).

## 4. Criterios de aprobación

- Ningún paquete aparece en dos rutas.
- Un vehículo nunca tiene dos rutas simultáneas activas.
- Ningún vehículo supera límites de peso y volumen.
- Los Premium vigentes se priorizan sin vulnerar restricciones.
- Una motocicleta nunca transporta un paquete de **5 kg o más**.
- Regla confirmada por el profesor: un camión tiene prohibido entrar **solo si** la zona restringe camiones **y** el destinatario tiene Premium vigente.
- Las rutas `EN_RUTA` no se reasignan para rescatar pendientes.
- Costos históricos no cambian al finalizar una ruta.
- Carga JSON desconocido no hereda el grafo de la operación anterior.
- Una estimación por zona no se presenta como distancia vial exacta.

## 5. Importante sobre esta validación

Las pruebas de aceptación se ejecutaron con una **copia reconstruida de los paquetes de código entregados en este chat**, no con una lectura directa de `D:\programacion\DeliveryPython` en tu equipo. Las pruebas **no garantizan** la ausencia de todos los errores de producción. Se recomienda repetirlas en tu entorno y realizar la prueba manual del menú.
