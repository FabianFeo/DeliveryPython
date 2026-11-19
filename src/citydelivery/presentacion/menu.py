import json
import sys
from datetime import date
from math import isfinite
from pathlib import Path

from ..logistica import gestor_despachos as modulo_despachos
from ..logistica.citydelivery import CityDelivery
from ..logistica.gestor_despachos import GestorDespachos
from ..modelos.bodega import Bodega
from ..modelos.cliente import ClientePremium, ClienteStandard
from ..modelos.paquete import Paquete
from ..modelos.vehiculo import CamionPesado, Motocicleta, VanReparto
from ..modelos.zona import Zona
from ..servicios.lector_json import cargar_sistema_desde_json
from .vista import (
    aviso,
    console,
    indicadores,
    indice_estado,
    metricas_visual,
    mostrar_resumen_importacion,
    pantalla_principal,
    resumen_despachos,
    rutas_visuales,
    tabla,
    titulo,
)


def iniciar_menu_interactivo(estado=None):
    """Interactúa con el sistema y devuelve su estado al salir.

    Es una función externa a las 13 clases: el código del UML no se modifica.
    Las entradas se reciben por consola y son independientes de Colab.
    """

    if estado is not None and not isinstance(estado, dict):
        raise TypeError("estado debe ser el diccionario devuelto por el menú.")
    sistema: CityDelivery | None = estado.get("sistema") if estado else None
    gestor: GestorDespachos | None = estado.get("gestor") if estado else None
    grafo_vial = estado.get("grafo_vial", {}) if estado else {}

    # Ayudas LOCALMENTE dentro del menú, nunca métodos de las clases UML.
    def pedir_texto(mensaje):
        valor = input(mensaje).strip()
        if not valor:
            raise ValueError("El dato no puede estar vacío.")
        return valor

    def pedir_numero(mensaje, minimo=0, estricto=False):
        texto = pedir_texto(mensaje).replace(",", ".")
        try:
            valor = float(texto)
        except ValueError as error:
            raise ValueError("Escribe un número válido.") from error
        if not isfinite(valor) or (valor <= minimo if estricto else valor < minimo):
            comparacion = "mayor que" if estricto else "mayor o igual que"
            raise ValueError(f"El número debe ser {comparacion} {minimo}.")
        return valor

    def pedir_entero(mensaje, minimo=1):
        valor = pedir_texto(mensaje)
        try:
            numero = int(valor)
        except ValueError as error:
            raise ValueError("Escribe un número entero.") from error
        if numero < minimo:
            raise ValueError(f"El entero debe ser >= {minimo}.")
        return numero

    def pedir_si_no(mensaje):
        valor = pedir_texto(mensaje + " (s/n): ").lower()
        if valor not in ("s", "n", "si", "sí", "no"):
            raise ValueError("Responde s o n.")
        return valor in ("s", "si", "sí")

    def pedir_fecha(mensaje):
        try:
            return date.fromisoformat(pedir_texto(mensaje + " (AAAA-MM-DD): "))
        except ValueError as error:
            raise ValueError("Fecha inválida: usa AAAA-MM-DD.") from error

    def buscar_zona(identificador):
        actual = sistema
        if actual is None:
            return None
        return next((z for z in actual.zonas if z.id == identificador), None)

    def buscar_cliente(identificador):
        actual = sistema
        if actual is None:
            return None
        return next((c for c in actual.clientes if c.id == identificador), None)

    def buscar_ruta(identificador):
        actual = sistema
        if actual is None:
            return None
        return next((r for r in actual.rutas if r.id == identificador), None)

    def exigir_operacion() -> tuple[CityDelivery, GestorDespachos]:
        """Devuelve referencias válidas para trabajar con la operación actual.

        Además de ayudar a Pylance, evita acceder a None si se invoca
        una acción sin haber creado o importado previamente información.
        """
        sistema_actual = sistema
        gestor_actual = gestor
        if sistema_actual is None or gestor_actual is None:
            raise ValueError(
                "Primero crea una operación (opción 1) o carga información JSON (opción 2)."
            )
        return sistema_actual, gestor_actual

    def definir_grafo(red):
        nonlocal grafo_vial
        grafo_vial = red or {}
        # GestorDespachos.generar_rutas consulta globals() de SU módulo.
        # Evita perder el grafo si este menú se importa de un archivo .py.
        modulo_despachos.GRAFO_VIAL = grafo_vial

    def leer_json_usuario(encabezado):
        titulo(encabezado, "Indica la ubicación del archivo de información")
        ruta = Path(
            pedir_texto("Archivo JSON (ej. data\\citydelivery_ejemplo.json): ").strip(
                '"'
            )
        ).expanduser()
        if not ruta.is_file():
            raise ValueError(f"No existe el archivo: {ruta}")
        return ruta.read_bytes()

    def nueva_empresa():
        nonlocal sistema, gestor
        titulo("CREAR NUEVA OPERACIÓN", "Configuración de Bodega Central")
        direccion = pedir_texto("Dirección de la Bodega Central: ")
        max_peso = pedir_numero("Capacidad máxima de peso (kg): ", estricto=True)
        max_volumen = pedir_numero("Capacidad máxima de volumen (m3): ", estricto=True)
        fecha_operacion = pedir_fecha("Fecha de operación")
        bodega = Bodega(direccion, max_peso, max_volumen)
        nuevo_sistema = CityDelivery(bodega)
        nuevo_gestor = GestorDespachos(nuevo_sistema, fecha_operacion)
        if sistema is not None and not pedir_si_no("¿Reemplazar la operación actual?"):
            print("Operación anterior conservada.")
            return
        sistema, gestor = nuevo_sistema, nuevo_gestor
        definir_grafo({})
        print(
            "✅ Operación creada. Ahora registra zonas, clientes, vehículos y paquetes."
        )

    def agregar_informacion_desde_json(resultado):
        """Fusiona datos sin añadir clases ni métodos al modelo UML.

        Se conserva la Bodega Central y la fecha actual. Los IDs repetidos
        se omiten para no sobrescribir rutas y registros existentes.
        """
        sistema_actual, gestor_actual = exigir_operacion()
        origen = resultado["sistema"]
        gestor_origen = resultado["gestor"]
        conteos = {
            "zonas": 0,
            "clientes": 0,
            "vehiculos": 0,
            "paquetes": 0,
            "omitidos": 0,
            "rechazados": 0,
        }

        for z in origen.zonas:
            if sistema_actual.registrar_zona(z):
                conteos["zonas"] += 1
            else:
                conteos["omitidos"] += 1

        for c in origen.clientes:
            z = buscar_zona(c.zona.id)
            if z is None or buscar_cliente(c.id) is not None:
                conteos["omitidos"] += 1
                continue
            if isinstance(c, ClientePremium):
                nuevo = ClientePremium(
                    c.id,
                    c.nombre,
                    c.direccion,
                    z,
                    fecha_compra_suscripcion=c.fecha_compra_suscripcion,
                    duracion_suscripcion_dias=c.duracion_suscripcion_dias,
                    suscripcion_activa_declarada=c.suscripcion_activa_declarada,
                )
            else:
                nuevo = ClienteStandard(c.id, c.nombre, c.direccion, z)
            if sistema_actual.registrar_cliente(nuevo):
                conteos["clientes"] += 1
            else:
                conteos["omitidos"] += 1

        for v in origen.vehiculos:
            if sistema_actual.registrar_vehiculo(v):
                conteos["vehiculos"] += 1
            else:
                conteos["omitidos"] += 1

        conocidos = {p.codigo for p in gestor_actual.paquetes_entrada}
        for p in gestor_origen.paquetes_entrada:
            if p.codigo in conocidos:
                conteos["omitidos"] += 1
                continue
            destinatario = buscar_cliente(p.cliente_destino.id)
            if destinatario is None:
                conteos["omitidos"] += 1
                gestor_actual.alertas.append(
                    f"JSON: paquete {p.codigo} sin destinatario registrado"
                )
                continue
            nuevo = Paquete(p.codigo, p.peso, p.volumen, destinatario)
            conocidos.add(nuevo.codigo)
            gestor_actual.paquetes_entrada.append(nuevo)
            if p.estado == "RECHAZADO":
                nuevo.registrar_incidencia(
                    "RECHAZADO", p.motivo_incidencia or "Rechazado en origen"
                )
                conteos["rechazados"] += 1
            elif not sistema_actual.bodega.agregar_paquete(nuevo):
                gestor_actual.alertas.append(
                    f"JSON: {nuevo.codigo}: {nuevo.motivo_incidencia}"
                )
                conteos["rechazados"] += 1
            conteos["paquetes"] += 1

        gestor_actual.alertas.extend(f"Importación: {a}" for a in gestor_origen.alertas)
        if gestor_actual.fecha_operacion != gestor_origen.fecha_operacion:
            gestor_actual.alertas.append(
                "La fecha del JSON no coincide con la operación actual; "
                "se mantuvo la fecha de la operación existente."
            )
        if resultado["grafo_vial"]:
            definir_grafo(resultado["grafo_vial"])
        return conteos

    def cargar_json_empresa():
        nonlocal sistema, gestor
        contenido = leer_json_usuario("CARGAR JSON DE INFORMACIÓN")
        grafo_anterior = modulo_despachos.GRAFO_VIAL
        try:
            resultado = cargar_sistema_desde_json(contenido)
        except Exception:
            modulo_despachos.GRAFO_VIAL = grafo_anterior
            raise

        if sistema is not None:
            titulo(
                "IMPORTACIÓN DE INFORMACIÓN",
                "Ya existe una operación. Elige cómo incorporar el archivo.",
            )
            console.print(
                "  [green]A[/green]  Agregar registros nuevos (conservar bodega, fecha y rutas)"
            )
            console.print(
                "  [yellow]R[/yellow]  Reemplazar información actual por los datos del JSON"
            )
            console.print("  [red]C[/red]  Cancelar sin cambios")
            modo = pedir_texto("Elige [A/R/C]: ").upper()
            if modo in ("C", "N", "NO"):
                modulo_despachos.GRAFO_VIAL = grafo_anterior
                aviso(
                    "Importación cancelada. Se conservaron todos los datos actuales.",
                    "info",
                )
                return
            if modo in ("A", "AGREGAR"):
                modulo_despachos.GRAFO_VIAL = grafo_anterior
                conteos = agregar_informacion_desde_json(resultado)
                aviso(
                    "Archivo cargado: información agregada sin borrar registros existentes.",
                    "ok",
                )
                sistema_actual, gestor_actual = exigir_operacion()
                mostrar_resumen_importacion(conteos, sistema_actual, gestor_actual)
                if conteos["omitidos"] or conteos["rechazados"]:
                    aviso(
                        "Se omitieron IDs repetidos y/o se rechazaron paquetes. "
                        "Revisa las alertas y el inventario.",
                        "warning",
                    )
                return
            if modo not in ("R", "REEMPLAZAR"):
                modulo_despachos.GRAFO_VIAL = grafo_anterior
                raise ValueError("Selecciona A, R o C para cargar el archivo.")

        sistema, gestor = resultado["sistema"], resultado["gestor"]
        definir_grafo(resultado["grafo_vial"])
        aviso("Archivo cargado: información disponible para planificar entregas.", "ok")
        sistema_actual, gestor_actual = exigir_operacion()
        mostrar_resumen_importacion(resultado["resumen"], sistema_actual, gestor_actual)
        if gestor_actual.alertas:
            aviso(
                f"{len(gestor_actual.alertas)} alerta(s). Consulta la opción 16.",
                "warning",
            )

    def registrar_zona():
        sistema_actual, gestor_actual = exigir_operacion()
        print("\n--- REGISTRAR ZONA ---")
        zona = Zona(
            pedir_texto("ID de zona: "),
            pedir_texto("Nombre: "),
            pedir_numero("Distancia desde la bodega (km): "),
            pedir_si_no("¿Permite camiones pesados?"),
        )
        if sistema_actual.registrar_zona(zona):
            print(f"✅ Zona {zona.id} registrada.")
        else:
            print("❌ Zona duplicada o inválida.")

    def registrar_cliente():
        sistema_actual, gestor_actual = exigir_operacion()
        if not sistema_actual.zonas:
            print("⚠️ Debes registrar primero una zona.")
            return
        print("\n--- REGISTRAR CLIENTE ---")
        print("Zonas:", ", ".join(f"{z.id}: {z.nombre}" for z in sistema_actual.zonas))
        identificador = pedir_texto("ID de cliente: ")
        nombre = pedir_texto("Nombre: ")
        direccion = pedir_texto("Dirección: ")
        zona = buscar_zona(pedir_texto("ID de zona: "))
        if zona is None:
            print("❌ La zona no existe.")
            return
        categoria = pedir_texto("Categoría (P=Premium, E=Estándar): ").upper()
        if categoria in ("E", "ESTANDAR", "ESTÁNDAR"):
            cliente = ClienteStandard(identificador, nombre, direccion, zona)
        elif categoria in ("P", "PREMIUM"):
            if pedir_si_no("¿Conoces la fecha de compra de la suscripción?"):
                compra = pedir_fecha("Fecha de compra")
                duracion = pedir_entero("Duración de suscripción (días): ")
                cliente = ClientePremium(
                    identificador,
                    nombre,
                    direccion,
                    zona,
                    fecha_compra_suscripcion=compra,
                    duracion_suscripcion_dias=duracion,
                )
            else:
                print(
                    "Sin fechas: se registra estado declarado, como en el JSON de ejemplo."
                )
                declarada = pedir_si_no("¿La suscripción se declara activa?")
                cliente = ClientePremium(
                    identificador,
                    nombre,
                    direccion,
                    zona,
                    suscripcion_activa_declarada=declarada,
                )
        else:
            print("❌ Categoría no reconocida.")
            return
        if sistema_actual.registrar_cliente(cliente):
            print(f"✅ Cliente {cliente.id} registrado.")
        else:
            print(
                "❌ No fue posible registrar al cliente (ID repetido o zona no registrada)."
            )

    def registrar_vehiculo():
        sistema_actual, gestor_actual = exigir_operacion()
        print("\n--- REGISTRAR VEHÍCULO ---")
        print("1. Motocicleta | 2. Van | 3. Camión pesado")
        tipo = pedir_texto("Tipo: ")
        identificador = pedir_texto("Identificador único: ")
        peso = pedir_numero("Capacidad máxima de peso (kg): ", estricto=True)
        volumen = pedir_numero("Capacidad máxima de volumen (m3): ", estricto=True)
        habilitado = pedir_si_no("¿Habilitado para despachos?")
        if tipo == "1":
            tarifa = pedir_numero("Tarifa por kilómetro (COP): ")
            limite = pedir_numero(
                "Peso individual máximo de paquete (kg, menor a 5): ", estricto=True
            )
            if limite >= 5:
                raise ValueError(
                    "El límite individual de motocicleta debe ser menor de 5 kg."
                )
            vehiculo = Motocicleta(
                identificador,
                peso,
                volumen,
                tarifa,
                peso_maximo_por_paquete_kg=limite,
                habilitado=habilitado,
            )
        elif tipo == "2":
            tarifa = pedir_numero("Tarifa por kg-km (COP): ")
            vehiculo = VanReparto(
                identificador, peso, volumen, tarifa, habilitado=habilitado
            )
        elif tipo == "3":
            tarifa = pedir_numero("Tarifa base por viaje (COP): ")
            impuesto = pedir_numero("Impuesto ambiental por viaje (COP): ")
            vehiculo = CamionPesado(
                identificador, peso, volumen, tarifa, impuesto, habilitado=habilitado
            )
        else:
            print("❌ Tipo de vehículo inválido.")
            return
        if sistema_actual.registrar_vehiculo(vehiculo):
            print(f"✅ Vehículo {vehiculo.identificador} registrado.")
        else:
            print("❌ Vehículo inválido, duplicado o con carga previa.")

    def registrar_paquete():
        sistema_actual, gestor_actual = exigir_operacion()
        if not sistema_actual.clientes:
            print("⚠️ Debes registrar primero un cliente.")
            return
        print("\n--- REGISTRAR PAQUETE ---")
        print(
            "Clientes:",
            ", ".join(f"{c.id}: {c.nombre}" for c in sistema_actual.clientes),
        )
        codigo = pedir_texto("Código único del paquete: ")
        if any(p.codigo == codigo for p in gestor_actual.paquetes_entrada):
            print(
                "❌ Ese código ya fue recibido anteriormente, incluso si fue rechazado."
            )
            return
        peso = pedir_numero("Peso (kg): ", estricto=True)
        volumen = pedir_numero("Volumen (m3): ", estricto=True)
        cliente = buscar_cliente(pedir_texto("ID del cliente destinatario: "))
        if cliente is None:
            print("❌ El cliente no existe.")
            return
        paquete = Paquete(codigo, peso, volumen, cliente)
        # El gestor incluye tanto los aceptados como los rechazados.
        gestor_actual.paquetes_entrada.append(paquete)
        if sistema_actual.bodega.agregar_paquete(paquete):
            print(f"✅ Paquete {codigo} recibido en Bodega Central.")
        else:
            gestor_actual.alertas.append(
                f"Paquete {codigo}: {paquete.motivo_incidencia}"
            )
            print(f"❌ Paquete rechazado: {paquete.motivo_incidencia}")

    def mostrar_zonas_clientes():
        sistema_actual, gestor_actual = exigir_operacion()
        titulo("ZONAS Y CLIENTES", "Catálogo de destinos y destinatarios")
        tabla(
            "ZONAS REGISTRADAS",
            ["ID", "Nombre", "Distancia ida", "Camión pesado"],
            [
                (
                    z.id,
                    z.nombre,
                    f"{z.distancia_desde_bodega_km:g} km",
                    "PERMITIDO" if z.acceso_camiones_pesados else "RESTRINGIDO",
                )
                for z in sistema_actual.zonas
            ],
        )
        tabla(
            "CLIENTES REGISTRADOS",
            ["ID", "Nombre", "Categoría", "Zona", "Suscripción", "Dirección"],
            [
                (
                    c.id,
                    c.nombre,
                    "PREMIUM" if isinstance(c, ClientePremium) else "ESTÁNDAR",
                    c.zona.nombre,
                    "Activa"
                    if isinstance(c, ClientePremium)
                    and c.tiene_suscripcion_activa(gestor_actual.fecha_operacion)
                    else "Inactiva"
                    if isinstance(c, ClientePremium)
                    else "No aplica",
                    c.direccion,
                )
                for c in sistema_actual.clientes
            ],
        )

    def mostrar_inventario():
        sistema_actual, gestor_actual = exigir_operacion()
        titulo("INVENTARIO Y CAPACIDAD", "Bodega Central")
        b = sistema_actual.bodega
        indicadores(
            [
                ("PAQUETES EN BODEGA", len(b.consultar_inventario())),
                (
                    "PESO",
                    f"{b.calcular_peso_ocupado():,.1f} / {b.capacidad_max_peso:,.1f} kg",
                ),
                (
                    "VOLUMEN",
                    f"{b.calcular_volumen_ocupado():,.3f} / {b.capacidad_max_volumen:,.3f} m³",
                ),
            ]
        )
        console.print(f"[dim]Dirección de bodega: {b.direccion}[/dim]")
        tabla(
            "PAQUETES ALMACENADOS",
            ["Código", "Peso kg", "Volumen m³", "Estado", "Cliente", "Incidencia"],
            [
                (
                    p.codigo,
                    f"{p.peso:g}",
                    f"{p.volumen:g}",
                    indice_estado(p.estado),
                    p.cliente_destino.id,
                    p.motivo_incidencia or "-",
                )
                for p in b.consultar_inventario()
            ],
        )
        rechazados = gestor_actual.obtener_paquetes_rechazados()
        if rechazados:
            tabla(
                "PAQUETES RECHAZADOS",
                ["Código", "Motivo"],
                [(p.codigo, p.motivo_incidencia) for p in rechazados],
            )

    def mostrar_flota():
        sistema_actual, gestor_actual = exigir_operacion()
        titulo("FLOTA Y DESTINOS", "Estado en la simulación")
        filas = []
        for v in sistema_actual.vehiculos:
            estado_v = sistema_actual.obtener_estado_vehiculo(v.identificador)
            ruta = sistema_actual.consultar_ruta_vehiculo(v.identificador)
            destino = ruta.zona.nombre if ruta else "Sin ruta"
            filas.append(
                (
                    v.identificador,
                    type(v).__name__,
                    indice_estado(estado_v),
                    f"{v.calcular_peso_actual():g}/{v.capacidad_max_peso:g}",
                    destino,
                )
            )
        tabla(
            "VEHÍCULOS REGISTRADOS",
            ["ID", "Tipo", "Estado", "Peso kg", "Destino"],
            filas,
        )

    def mostrar_rutas():
        sistema_actual, gestor_actual = exigir_operacion()
        titulo("RUTAS DE LA OPERACIÓN", "Planeadas, en curso y finalizadas")
        rutas_visuales(sistema_actual.rutas, "ESTADO DE RUTAS")
        if sistema_actual.rutas:
            tabla(
                "ENTREGAS POR RUTA",
                ["Ruta", "Paquete", "Cliente", "Dirección"],
                [
                    (
                        r.id,
                        p.codigo,
                        p.cliente_destino.nombre,
                        p.cliente_destino.direccion,
                    )
                    for r in sistema_actual.rutas
                    for p in r.obtener_entregas()
                ],
            )

    def planificar():
        sistema_actual, gestor_actual = exigir_operacion()
        titulo("PLANIFICAR DESPACHOS", "Opción 11  •  Asignación automática")
        if (
            not sistema_actual.vehiculos
            or not sistema_actual.clientes
            or not sistema_actual.zonas
        ):
            faltantes = [
                nombre
                for nombre, registros in (
                    ("zonas", sistema_actual.zonas),
                    ("clientes", sistema_actual.clientes),
                    ("vehículos", sistema_actual.vehiculos),
                )
                if not registros
            ]
            aviso(
                "No se puede planificar todavía. Faltan: "
                + ", ".join(faltantes)
                + ". Regístralos desde las opciones 3 a 5 o carga un JSON de información.",
                "warning",
            )
            return
        total_pendientes = len(gestor_actual.obtener_paquetes_pendientes())
        if total_pendientes == 0:
            if sistema_actual.rutas:
                aviso(
                    "No hay paquetes pendientes para asignar. "
                    "Estas son las rutas existentes:",
                    "info",
                )
                rutas_visuales(sistema_actual.rutas)
            else:
                aviso(
                    "No hay paquetes pendientes. Registra paquetes en la opción 6 "
                    "o carga información desde JSON con la opción 2.",
                    "warning",
                )
            return
        try:
            nuevas = gestor_actual.generar_rutas()
        except (ValueError, TypeError, KeyError, OSError) as error:
            aviso(f"No se pudo planificar la operación: {error}", "error")
            return
        resumen_despachos(
            sistema_actual, gestor_actual, nuevas, total_pendientes, grafo_vial
        )
        pendientes = gestor_actual.obtener_paquetes_no_asignados()
        if pendientes:
            tabla(
                "PAQUETES POR ASIGNAR",
                ["Código", "Cliente", "Motivo"],
                [
                    (
                        p.codigo,
                        p.cliente_destino.nombre,
                        p.motivo_incidencia or "En espera de vehículo compatible",
                    )
                    for p in pendientes
                ],
            )

    def iniciar_ruta():
        sistema_actual, gestor_actual = exigir_operacion()
        opciones = [r for r in sistema_actual.rutas if r.estado == "PLANEADA"]
        if not opciones:
            print("No hay rutas PLANEADAS para iniciar.")
            return
        print("Rutas planeadas:", ", ".join(r.id for r in opciones))
        ruta = buscar_ruta(pedir_texto("ID de la ruta que inicia: "))
        if ruta is None or ruta.estado != "PLANEADA":
            print("❌ No existe una ruta planeada con ese ID.")
            return
        if not ruta.validar_ruta(gestor_actual.fecha_operacion):
            print("❌ Ruta inválida para esta fecha. No se inició.")
            return
        if not ruta.iniciar_ruta():
            print("❌ No se pudo iniciar la ruta.")
            return
        # La Bodega conserva el registro de la mercancía hasta FINALIZADA.
        # CityDelivery.finalizar_ruta() retira esos paquetes de inventario.
        print(
            f"✅ Ruta {ruta.id} EN_RUTA. Vehículo {ruta.vehiculo.identificador} ocupado."
        )

    def finalizar_ruta():
        sistema_actual, gestor_actual = exigir_operacion()
        opciones = [r for r in sistema_actual.rutas if r.estado == "EN_RUTA"]
        if not opciones:
            print("No hay rutas EN_RUTA para finalizar.")
            return
        print("Rutas en viaje:", ", ".join(r.id for r in opciones))
        ruta = buscar_ruta(pedir_texto("ID de la ruta que finaliza: "))
        if ruta is None:
            print("❌ Ruta desconocida.")
            return
        if sistema_actual.finalizar_ruta(ruta.id):
            print(
                f"✅ Ruta {ruta.id} FINALIZADA. Vehículo disponible para otra asignación."
            )
        else:
            print("❌ No se pudo finalizar. La ruta debe estar EN_RUTA.")

    def mostrar_reporte():
        sistema_actual, gestor_actual = exigir_operacion()
        metricas_visual(gestor_actual.generar_reporte())

    def configurar_grafo():
        contenido = leer_json_usuario("CARGAR GRAFO VIAL")
        try:
            datos = json.loads(contenido.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"JSON inválido: {error}") from error
        if not isinstance(datos, dict):
            raise TypeError("El grafo debe ser un objeto JSON.")
        red = datos.get("grafoVial", datos.get("redVial", datos))
        if not isinstance(red, dict):
            raise TypeError("El grafo vial debe ser un objeto JSON de conexiones.")
        if "BODEGA" not in red:
            raise ValueError("El grafo debe contener un nodo BODEGA.")
        for origen, vecinos in red.items():
            if not isinstance(origen, str) or not isinstance(vecinos, dict):
                raise TypeError("Cada nodo debe tener un diccionario de conexiones.")
            for destino, km in vecinos.items():
                if (
                    not isinstance(destino, str)
                    or isinstance(km, bool)
                    or not isinstance(km, (int, float))
                    or not isfinite(km)
                    or km < 0
                ):
                    raise ValueError(
                        "Las distancias deben ser numéricas, finitas y no negativas."
                    )
        sistema_actual = sistema
        if sistema_actual is not None and sistema_actual.rutas:
            if not pedir_si_no(
                "¿Cambiar el grafo? Se recalcularán rutas PLANEADAS al volver a planificar."
            ):
                return
        definir_grafo(red)
        print(
            f"✅ Grafo cargado ({len(red)} nodos). Se usará para futuras planificaciones."
        )

    def exportar_reporte():
        sistema_actual, gestor_actual = exigir_operacion()
        ruta = Path(
            pedir_texto(
                "Nombre de archivo de salida (por ej. reporte_citydelivery.json): "
            )
        )
        if ruta.suffix.lower() != ".json":
            raise ValueError("El archivo de salida debe terminar en .json")
        reporte = gestor_actual.generar_reporte()
        ruta.write_text(
            json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print("✅ Reporte exportado:", ruta.resolve())

    def mostrar_alertas():
        titulo("ALERTAS DE OPERACIÓN", "Validaciones y eventos")
        gestor_actual = gestor
        if gestor_actual is not None and gestor_actual.alertas:
            tabla(
                "ALERTAS",
                ["N.º", "Mensaje"],
                [
                    (str(i), alerta)
                    for i, alerta in enumerate(gestor_actual.alertas, start=1)
                ],
            )
        else:
            aviso("Sin alertas.", "ok")

    def pausar_entre_pantallas():
        # En pytest o con entradas redirigidas no hacemos preguntas adicionales.
        if sys.stdin.isatty():
            try:
                input("\nPresiona ENTER para regresar al menú... ")
            except (EOFError, KeyboardInterrupt):
                pass

    # Si se reanuda una sesión anterior, recuperar su grafo.
    if sistema is not None:
        definir_grafo(grafo_vial)

    while True:
        # Limpiar solo en una consola real: los resultados nunca se pierden
        # mientras se esté esperando ENTER tras una operación.
        if sys.stdout.isatty():
            console.clear()
        pantalla_principal(sistema, gestor)

        try:
            opcion = input("Selecciona una opción [0-17]: ").strip()
            if opcion in ("0", "00"):
                print("Sesión terminada. ¡Hasta luego!")
                return {"sistema": sistema, "gestor": gestor, "grafo_vial": grafo_vial}
            if opcion == "1":
                nueva_empresa()
                pausar_entre_pantallas()
                continue
            if opcion == "2":
                cargar_json_empresa()
                pausar_entre_pantallas()
                continue
            if sistema is None:
                aviso(
                    "Primero crea la operación (1) o carga información desde JSON (2).",
                    "warning",
                )
                pausar_entre_pantallas()
                continue
            acciones = {
                "3": registrar_zona,
                "4": registrar_cliente,
                "5": registrar_vehiculo,
                "6": registrar_paquete,
                "7": mostrar_zonas_clientes,
                "8": mostrar_inventario,
                "9": mostrar_flota,
                "10": mostrar_rutas,
                "11": planificar,
                "12": iniciar_ruta,
                "13": finalizar_ruta,
                "14": mostrar_reporte,
                "15": configurar_grafo,
                "16": mostrar_alertas,
                "17": exportar_reporte,
            }
            if opcion in acciones:
                acciones[opcion]()
            else:
                aviso("Opción no reconocida.", "warning")
            pausar_entre_pantallas()
        except (ValueError, TypeError, OSError, KeyError) as error:
            aviso("No se completó la operación: " + str(error), "error")
            pausar_entre_pantallas()
        except (EOFError, KeyboardInterrupt, StopIteration):
            print("\nEntrada finalizada. Saliendo del menú.")
            return {"sistema": sistema, "gestor": gestor, "grafo_vial": grafo_vial}
