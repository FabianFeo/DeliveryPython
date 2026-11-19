import json
from datetime import date
from math import isfinite
from pathlib import Path

from ..logistica.citydelivery import CityDelivery
from ..logistica.gestor_despachos import GestorDespachos
from ..modelos.bodega import Bodega
from ..modelos.cliente import ClientePremium, ClienteStandard
from ..modelos.paquete import Paquete
from ..modelos.vehiculo import CamionPesado, Motocicleta, VanReparto
from ..modelos.zona import Zona


def cargar_sistema_desde_json(origen, fecha_operacion=None):
    """Construye CityDelivery + GestorDespachos a partir del JSON del proyecto.

    'origen' puede ser una ruta a archivo, bytes de files.upload(), un objeto
    tipo archivo, un diccionario Python o texto JSON. No fija cantidades.

    Devuelve un diccionario con claves: sistema, gestor, grafo_vial, resumen.
    El grafo vial opcional se configura automáticamente en el módulo del
    gestor; no se agrega ningún atributo al UML. La aplicación admite una
    operación activa a la vez (GRAFO_VIAL es configuración global del módulo).

    Una configuración principal inválida produce ValueError. Los registros
    individuales inválidos se omiten con una alerta para seguir procesando.
    """

    # 1. Interpretar la fuente sin instalar bibliotecas externas.
    if isinstance(origen, dict):
        datos = origen
    elif isinstance(origen, (bytes, bytearray)):
        try:
            datos = json.loads(origen.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Archivo JSON ilegible: {error}") from error
    elif hasattr(origen, "read"):
        try:
            datos = json.load(origen)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Archivo JSON ilegible: {error}") from error
    elif isinstance(origen, (str, Path)):
        texto = str(origen)
        if texto.lstrip().startswith("{"):
            try:
                datos = json.loads(texto)
            except json.JSONDecodeError as error:
                raise ValueError(f"Texto JSON inválido: {error}") from error
        else:
            ruta = Path(origen)
            if not ruta.is_file():
                raise FileNotFoundError(f"No se encontró el JSON: {ruta}")
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"Archivo JSON ilegible: {error}") from error
    else:
        raise TypeError("Origen inválido: use archivo, bytes, texto JSON o dict.")

    if not isinstance(datos, dict):
        raise ValueError("La raíz del archivo JSON debe ser un objeto.")

    def seccion_lista(nombre):
        valor = datos.get(nombre, [])
        if not isinstance(valor, list):
            raise ValueError(f"La sección {nombre} debe ser una lista JSON.")
        return valor

    def fecha_iso(valor, etiqueta):
        if isinstance(valor, date):
            return valor
        if not isinstance(valor, str):
            raise ValueError(f"{etiqueta}: fecha obligatoria con formato AAAA-MM-DD.")
        try:
            return date.fromisoformat(valor)
        except ValueError as error:
            raise ValueError(f"{etiqueta}: use AAAA-MM-DD ({valor}).") from error

    # 2. Fecha y configuración general.
    metadata = datos.get("metadata", {})
    configuracion = datos.get("configuracion", {})
    if not isinstance(metadata, dict) or not isinstance(configuracion, dict):
        raise ValueError("metadata y configuracion deben ser objetos JSON.")
    if metadata.get("sistema", "CityDelivery") != "CityDelivery":
        raise ValueError("El archivo no declara el sistema CityDelivery.")

    fecha = fecha_iso(
        fecha_operacion
        if fecha_operacion is not None
        else metadata.get("fechaOperacion"),
        "fechaOperacion",
    )
    for clave, valor_esperado in [
        ("moneda", "COP"),
        ("unidadPeso", "kg"),
        ("unidadVolumen", "m3"),
    ]:
        valor = configuracion.get(clave, valor_esperado)
        if valor != valor_esperado:
            raise ValueError(
                f"Configuración {clave}={valor!r} no soportada; se espera {valor_esperado}."
            )

    bodega_data = configuracion.get("bodega")
    if not isinstance(bodega_data, dict):
        raise ValueError("Falta configuracion.bodega con capacidades.")
    try:
        bodega = Bodega(
            bodega_data["direccion"],
            bodega_data["capacidadMaximaKg"],
            bodega_data["capacidadMaximaM3"],
        )
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError(f"Configuración de Bodega inválida: {error}") from error

    sistema = CityDelivery(bodega)
    alertas_carga = []
    omitidos = {"zonas": 0, "clientes": 0, "vehiculos": 0, "paquetes": 0}

    # 3. Zonas: IDs del JSON y distancias, sin crear zonas de ejemplo fijas.
    zonas = {}
    for indice, item in enumerate(seccion_lista("zonas"), start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("no es un objeto JSON")
            zona = Zona(
                item["id"],
                item["nombre"],
                item["distanciaDesdeBodegaKm"],
                item["accesoCamionesPesados"],
            )
            if not sistema.registrar_zona(zona):
                raise ValueError(f"ID duplicado: {zona.id}")
            zonas[zona.id] = zona
        except (KeyError, TypeError, ValueError) as error:
            omitidos["zonas"] += 1
            alertas_carga.append(f"zonas[{indice}]: {error}")

    # 4. Clientes Estándar/Premium y vigencia por fecha cuando se informa.
    clientes = {}
    for indice, item in enumerate(seccion_lista("clientes"), start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("no es un objeto JSON")
            zona_id = item["zonaId"]
            if zona_id not in zonas:
                raise ValueError(f"zonaId desconocido: {zona_id}")
            categoria = str(item["categoria"]).strip().upper()
            if categoria == "PREMIUM":
                fecha_compra = item.get("fechaCompraSuscripcion")
                if fecha_compra is not None:
                    fecha_compra = fecha_iso(fecha_compra, "fechaCompraSuscripcion")
                cliente = ClientePremium(
                    item["id"],
                    item["nombre"],
                    item["direccion"],
                    zonas[zona_id],
                    fecha_compra_suscripcion=fecha_compra,
                    duracion_suscripcion_dias=item.get("duracionSuscripcionDias"),
                    suscripcion_activa_declarada=item.get("suscripcionActiva"),
                )
            elif categoria in ("ESTANDAR", "STANDARD"):
                cliente = ClienteStandard(
                    item["id"], item["nombre"], item["direccion"], zonas[zona_id]
                )
            else:
                raise ValueError(f"categoría de cliente desconocida: {categoria}")
            if not sistema.registrar_cliente(cliente):
                raise ValueError(f"ID duplicado o zona no registrada: {cliente.id}")
            clientes[cliente.id] = cliente
        except (KeyError, TypeError, ValueError) as error:
            omitidos["clientes"] += 1
            alertas_carga.append(f"clientes[{indice}]: {error}")

    # 5. Configuración de tipos de vehículo (tarifas y capacidades).
    def normalizar_tipo(valor):
        tipo = str(valor).strip().upper().replace("-", "_").replace(" ", "_")
        alias = {"MOTO": "MOTOCICLETA", "VAN_REPARTO": "VAN", "CAMION": "CAMION_PESADO"}
        return alias.get(tipo, tipo)

    tipos = {}
    for indice, item in enumerate(seccion_lista("tiposVehiculo"), start=1):
        if not isinstance(item, dict) or "tipo" not in item:
            alertas_carga.append(f"tiposVehiculo[{indice}]: definición inválida")
            continue
        tipo = normalizar_tipo(item["tipo"])
        if tipo not in ("MOTOCICLETA", "VAN", "CAMION_PESADO"):
            alertas_carga.append(f"tiposVehiculo[{indice}]: tipo desconocido {tipo}")
            continue
        if tipo in tipos:
            alertas_carga.append(f"tiposVehiculo[{indice}]: tipo repetido {tipo}")
            continue
        tipos[tipo] = item

    # Usar la lista vehiculos como autoridad. Si no existe esa sección,
    # crear cantidades variables según cantidadDisponible en tiposVehiculo.
    if "vehiculos" in datos:
        vehiculos_entrada = seccion_lista("vehiculos")
    else:
        vehiculos_entrada = []
        prefijos = {"MOTOCICLETA": "MOTO", "VAN": "VAN", "CAMION_PESADO": "CAM"}
        for tipo, conf in tipos.items():
            cantidad = conf.get("cantidadDisponible", 0)
            if type(cantidad) is not int or cantidad < 0:
                raise ValueError(f"cantidadDisponible inválida para {tipo}.")
            for consecutivo in range(1, cantidad + 1):
                vehiculos_entrada.append(
                    {
                        "id": f"{prefijos[tipo]}-{consecutivo:02d}",
                        "tipo": tipo,
                        "disponible": True,
                    }
                )
        if vehiculos_entrada:
            alertas_carga.append(
                "No había lista vehiculos: se generaron IDs usando cantidadDisponible."
            )

    for indice, item in enumerate(vehiculos_entrada, start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("no es un objeto JSON")
            tipo = normalizar_tipo(item["tipo"])
            # Un JSON también puede llevar capacidades/tarifas por vehículo.
            conf = {**tipos.get(tipo, {}), **item}
            identificador = conf["id"]
            peso = conf["capacidadMaximaKg"]
            volumen = conf["capacidadMaximaM3"]
            habilitado = conf.get("disponible", True)
            if tipo == "MOTOCICLETA":
                vehiculo = Motocicleta(
                    identificador,
                    peso,
                    volumen,
                    conf["costoFijoPorKmCOP"],
                    conf.get("pesoMaximoPorPaqueteKg", 4.99),
                    habilitado=habilitado,
                )
            elif tipo == "VAN":
                vehiculo = VanReparto(
                    identificador,
                    peso,
                    volumen,
                    conf["costoPorKgKmCOP"],
                    habilitado=habilitado,
                )
            elif tipo == "CAMION_PESADO":
                vehiculo = CamionPesado(
                    identificador,
                    peso,
                    volumen,
                    conf["tarifaBasePorViajeCOP"],
                    conf["impuestoAmbientalFijoCOP"],
                    habilitado=habilitado,
                )
            else:
                raise ValueError(f"tipo de vehículo desconocido: {tipo}")
            if not sistema.registrar_vehiculo(vehiculo):
                raise ValueError(f"ID repetido o vehículo inválido: {identificador}")
        except (KeyError, TypeError, ValueError) as error:
            omitidos["vehiculos"] += 1
            alertas_carga.append(f"vehiculos[{indice}]: {error}")

    # 6. Inventario. La Bodega valida peso y volumen y rechaza excesos.
    # La lista de entrada conserva incluso los paquetes RECHAZADOS.
    paquetes_entrada = []
    codigos_recibidos = set()
    for indice, item in enumerate(seccion_lista("paquetes"), start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("no es un objeto JSON")
            cliente_id = item["clienteId"]
            if cliente_id not in clientes:
                raise ValueError(f"clienteId desconocido: {cliente_id}")
            paquete = Paquete(
                item["codigo"], item["pesoKg"], item["volumenM3"], clientes[cliente_id]
            )
            estado = str(item.get("estado", "PENDIENTE")).upper()
            if paquete.codigo in codigos_recibidos:
                paquete.registrar_incidencia(
                    "RECHAZADO", "Código de paquete repetido en JSON"
                )
                paquetes_entrada.append(paquete)
                alertas_carga.append(f"Paquete {paquete.codigo}: código duplicado")
                continue
            if estado not in ("PENDIENTE", "RECHAZADO"):
                raise ValueError(
                    f"estado {estado} no reconstruible sin historial de rutas"
                )
            codigos_recibidos.add(paquete.codigo)

            if estado == "RECHAZADO":
                paquete.registrar_incidencia(
                    "RECHAZADO",
                    item.get("motivoIncidencia") or "Rechazado en origen JSON",
                )
            elif estado == "PENDIENTE":
                if not bodega.agregar_paquete(paquete):
                    alertas_carga.append(
                        f"Paquete {paquete.codigo}: {paquete.motivo_incidencia}"
                    )
            paquetes_entrada.append(paquete)
        except (KeyError, TypeError, ValueError) as error:
            omitidos["paquetes"] += 1
            alertas_carga.append(f"paquetes[{indice}]: {error}")

    # 7. Gestor, fechas y configuración de la jornada.
    despacho_data = configuracion.get("despacho", {})
    if not isinstance(despacho_data, dict):
        raise ValueError("configuracion.despacho debe ser un objeto JSON.")
    try:
        gestor = GestorDespachos(
            sistema,
            fecha,
            hora_inicio_matutino=despacho_data.get("horaInicioMatutino", "06:00"),
            hora_fin_matutino=despacho_data.get("horaFinMatutino", "12:00"),
            criterio_prioridad=despacho_data.get(
                "criterioPrioridad", ["PREMIUM", "ESTANDAR"]
            ),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Configuración de despacho inválida: {error}") from error

    gestor.paquetes_entrada = paquetes_entrada
    gestor.alertas.extend(alertas_carga)

    # 8. Grafo vial opcional. No se inventan distancias entre destinatarios.
    grafo = datos.get("grafoVial", datos.get("redVial", configuracion.get("grafoVial")))
    if grafo is not None:
        valido = isinstance(grafo, dict) and "BODEGA" in grafo
        if valido:
            for origen_nodo, vecinos in grafo.items():
                if not isinstance(origen_nodo, str) or not isinstance(vecinos, dict):
                    valido = False
                    break
                for destino_nodo, distancia in vecinos.items():
                    if (
                        not isinstance(destino_nodo, str)
                        or isinstance(distancia, bool)
                        or not isinstance(distancia, (int, float))
                        or not isfinite(distancia)
                        or distancia < 0
                    ):
                        valido = False
                        break
                if not valido:
                    break
        if not valido:
            grafo = None
            gestor.alertas.append(
                "grafoVial inválido: se utilizará estimación por zona."
            )

    # La configuración del grafo corresponde a la operación recién importada.
    # Restablecer a None evita usar por error una red de un JSON anterior.
    from ..logistica import gestor_despachos as modulo_despachos

    modulo_despachos.GRAFO_VIAL = grafo or None

    resumen = {
        "fechaOperacion": fecha.isoformat(),
        "zonas": len(sistema.zonas),
        "clientes": len(sistema.clientes),
        "vehiculos": len(sistema.vehiculos),
        "paquetesRecibidos": len(seccion_lista("paquetes")),
        "paquetesAlmacenados": len(bodega.consultar_inventario()),
        "paquetesRechazados": len(
            [p for p in paquetes_entrada if p.estado == "RECHAZADO"]
        ),
        "paquetesOmitidosPorDatosInvalidos": omitidos["paquetes"],
        "registrosOmitidos": dict(omitidos),
        "tieneGrafoVial": bool(grafo),
        "alertas": len(gestor.alertas),
    }
    return {
        "sistema": sistema,
        "gestor": gestor,
        "grafo_vial": grafo,
        "resumen": resumen,
    }
