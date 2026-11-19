# Corrección para los 7 fallos de mejora local en CityDelivery

Los 7 fallos (`test_mejora_local_despachos.py`) se reproducen exactamente cuando
`gestor_despachos.py` conserva la versión antigua de la Migración 06.
La versión corregida importa `rescatar_pendientes` y la ejecuta dentro de
`GestorDespachos.generar_rutas`, inmediatamente después de la asignación inicial.

## Instalar desde VS Code (PowerShell)

1. Abre `D:\programacion\DeliveryPython`.
2. Guarda copia de seguridad del archivo anterior:

   Copy-Item .\src\citydelivery\logistica\gestor_despachos.py .\src\citydelivery\logistica\gestor_despachos_backup.py.txt

3. Descomprime ESTE ZIP en `D:\programacion\DeliveryPython` y reemplaza
   exclusivamente los dos archivos contenidos en la carpeta `src\citydelivery\logistica`.
   No reemplaces otras clases ni las pruebas existentes.
4. Comprueba el enlace al optimizador:

   Select-String -Path .\src\citydelivery\logistica\gestor_despachos.py -Pattern 'rescatar_pendientes'

   Deben aparecer la importación y la llamada al auxiliar.
5. Ejecuta primero las pruebas de mejora local:

   .\.venv\Scripts\python.exe -m pytest tests\test_mejora_local_despachos.py -v

   Esperado: 14 passed.
6. Ejecuta todas las pruebas:

   .\.venv\Scripts\python.exe -m pytest -q

   Esperado: 202 passed, si tu repositorio conserva las 202 pruebas del registro compartido.

## Ejecutar el programa

   .\.venv\Scripts\python.exe main.py

Si faltase la dependencia de la interfaz Rich:

   .\.venv\Scripts\python.exe -m pip install -r requirements_ui.txt

## Alcance y precauciones

Se mantienen las 13 clases del UML y todas sus firmas públicas.
El optimizador `rescatar_pendientes` es una función externa, no un método nuevo.
No es necesario modificar el lector JSON, el menú o los otros módulos.
No requiere coordenadas ni OpenStreetMap: el JSON de zonas ya permite estimar distancias.

Validación realizada: con el gestor antiguo, 7 failed y 7 passed en las 14
pruebas de mejora local, con los mismos nombres de las 7 pruebas fallidas
aportadas por el usuario. Con el gestor corregido, 202 passed en el conjunto
completo de pruebas reconstruido de las 8 migraciones y el generador de grafos.
