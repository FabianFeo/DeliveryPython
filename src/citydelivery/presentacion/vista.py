"""Presentación visual en consola usando Rich.

Todas las funciones son externas al UML. No se introducen clases ni métodos
sobre los 13 componentes del modelo de CityDelivery.
"""
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(highlight=False)


def titulo(texto, subtitulo=None):
    contenido = Text(texto, style='bold bright_cyan', justify='center')
    if subtitulo:
        contenido.append('\n' + subtitulo, style='dim white')
    console.print(Panel(contenido, border_style='bright_cyan', box=box.ROUNDED, expand=True))


def aviso(mensaje, tipo='info'):
    estilos = {
        'info': ('cyan', 'INFORMACIÓN'),
        'ok': ('green', 'OPERACIÓN COMPLETADA'),
        'warning': ('yellow', 'ATENCIÓN'),
        'error': ('red', 'ERROR'),
    }
    estilo, encabezado = estilos.get(tipo, estilos['info'])
    console.print(Panel(str(mensaje), title=encabezado, title_align='left',
                        border_style=estilo, box=box.ROUNDED))


def tabla(encabezado, columnas, filas):
    t = Table(title=encabezado, box=box.ROUNDED, header_style='bold cyan',
              show_lines=False, row_styles=['', 'dim'], expand=True)
    for nombre in columnas:
        t.add_column(nombre, overflow='fold')
    filas = list(filas)
    for fila in filas:
        t.add_row(*(str(x) for x in fila))
    if filas:
        console.print(t)
    else:
        aviso('No hay registros para mostrar.', 'warning')


def indice_estado(estado):
    estados = {
        'DISPONIBLE': '[green]DISPONIBLE[/green]',
        'RESERVADO': '[yellow]RESERVADO[/yellow]',
        'EN_RUTA': '[bright_cyan]EN_RUTA[/bright_cyan]',
        'FINALIZADA': '[green]FINALIZADA[/green]',
        'INHABILITADO': '[red]INHABILITADO[/red]',
        'PLANEADA': '[yellow]PLANEADA[/yellow]',
        'ASIGNADO': '[cyan]ASIGNADO[/cyan]',
        'PENDIENTE': '[yellow]PENDIENTE[/yellow]',
        'RECHAZADO': '[red]RECHAZADO[/red]',
        'ENTREGADO': '[green]ENTREGADO[/green]',
    }
    return estados.get(str(estado), str(estado))


def indicadores(etiquetas_valores):
    t = Table.grid(expand=True, padding=(0, 1))
    for _ in etiquetas_valores:
        t.add_column(justify='center', ratio=1)
    labels = [Text(str(n), style='dim', justify='center') for n,_ in etiquetas_valores]
    vals = [Text(str(v), style='bold bright_white', justify='center') for _,v in etiquetas_valores]
    t.add_row(*vals)
    t.add_row(*labels)
    console.print(Panel(t, border_style='grey50', box=box.ROUNDED))


def pantalla_principal(sistema=None, gestor=None):
    titulo('CITYDELIVERY  /  CENTRO DE OPERACIONES',
           'Gestión logística urbana  •  TSP + Dijkstra  •  Python')
    if sistema is None:
        aviso('Operación: SIN CONFIGURAR. Crea la bodega o carga información desde JSON.', 'warning')
    else:
        indicadores([
            ('ZONAS', len(sistema.zonas)),
            ('CLIENTES', len(sistema.clientes)),
            ('VEHÍCULOS', len(sistema.vehiculos)),
            ('PAQUETES', len(gestor.paquetes_entrada)),
        ])
        console.print(f'[dim]Fecha de operación: {gestor.fecha_operacion} '
                      f'| Rutas: {len(sistema.rutas)} '
                      f'| Pendientes: {len(gestor.obtener_paquetes_pendientes())}[/dim]')

    items = [
        ('INICIO', [('01', 'Crear operación y Bodega Central'),
                    ('02', 'Cargar información desde JSON')]),
        ('REGISTROS', [('03', 'Registrar zona'), ('04', 'Registrar cliente'),
                       ('05', 'Registrar vehículo'), ('06', 'Registrar paquete')]),
        ('CONSULTAS', [('07', 'Zonas y clientes'), ('08', 'Inventario y rechazos'),
                       ('09', 'Flota y destinos'), ('10', 'Rutas')]),
        ('OPERACIÓN', [('11', 'PLANIFICAR DESPACHOS'), ('12', 'Iniciar ruta'),
                        ('13', 'Finalizar ruta')]),
        ('RESULTADOS', [('14', 'Métricas y reportes'), ('15', 'Cargar grafo vial'),
                         ('16', 'Alertas'), ('17', 'Exportar reporte JSON')]),
    ]
    t = Table(box=box.SIMPLE_HEAVY, show_header=False, expand=True, padding=(0, 1))
    t.add_column('Opción', style='bold bright_cyan', width=4)
    t.add_column('Acción', ratio=3)
    for grupo, opciones in items:
        t.add_row('', f'[bold blue]{grupo}[/bold blue]')
        for numero, texto in opciones:
            detalle = f'[bold green]{texto}[/bold green]' if numero == '11' else texto
            t.add_row(numero, detalle)
    t.add_row('00', '[bold]Salir[/bold]')
    console.print(t)


def mostrar_resumen_importacion(resumen, sistema, gestor):
    titulo('CARGAR JSON DE INFORMACIÓN', 'Resultado de la importación')
    indicadores([
        ('ZONAS', len(sistema.zonas)), ('CLIENTES', len(sistema.clientes)),
        ('VEHÍCULOS', len(sistema.vehiculos)),
        ('PAQUETES RECIBIDOS', len(gestor.paquetes_entrada)),
    ])
    console.print(f'[dim]Fecha: {gestor.fecha_operacion} | '
                  f'Bodega: {sistema.bodega.direccion}[/dim]')
    if resumen:
        console.print('[dim]Detalles de carga:[/dim] ' + str(resumen))


def rutas_visuales(rutas, encabezado='RUTAS PLANIFICADAS'):
    filas = [
        (r.id, r.vehiculo.identificador, r.zona.nombre, indice_estado(r.estado),
         str(len(r.paquetes)), f'{r.distancia_km:,.2f}',
         f'$ {r.calcular_costo():,.0f}')
        for r in rutas
    ]
    tabla(encabezado,
          ['Ruta', 'Vehículo', 'Zona', 'Estado', 'Paq.', 'Km', 'Costo COP'], filas)


def resumen_despachos(sistema, gestor, nuevas, pendientes_iniciales, grafo_vial):
    reporte = gestor.generar_reporte()
    titulo('RESULTADO DE PLANIFICACIÓN', 'Opción 11  •  Resumen de la operación')
    indicadores([
        ('RUTAS NUEVAS', len(nuevas)),
        ('RUTAS TOTALES', len(sistema.rutas)),
        ('ASIGNADOS', reporte['asignados']),
        ('PENDIENTES', len(reporte['pendientes'])),
    ])
    indicadores([
        ('DISTANCIA ACUMULADA', f"{reporte['distanciaTotalKm']:,.2f} km"),
        ('COSTO TOTAL', f"$ {reporte['costoTotalCOP']:,.0f} COP"),
        ('PORCENTAJE ASIGNADO', f"{reporte['porcentajeAsignado']:,.1f}%"),
    ])
    rutas_visuales(sistema.rutas, 'RUTAS DE LA OPERACIÓN')
    if nuevas:
        aviso(f'{len(nuevas)} ruta(s) nueva(s) registrada(s). '
              f'Paquetes pendientes antes: {pendientes_iniciales}; '
              f'ahora: {len(reporte["pendientes"])}.', 'ok')
    elif sistema.rutas:
        aviso('No se crearon rutas adicionales. Puedes tener vehículos reservados '
              'o paquetes incompatibles. Consulta las rutas y las alertas.', 'warning')
    else:
        aviso('No se generaron rutas. Comprueba los vehículos disponibles, '
              'la capacidad y las restricciones de las zonas.', 'warning')
    if not grafo_vial:
        aviso('Sin grafo: solo distancia estimada de ida por zona. '
              'Para aplicar Dijkstra + TSP carga una red vial en la opción 15.', 'info')
    else:
        aviso('Dijkstra + TSP se aplica cuando el grafo conecta todos los destinos. '
              'Si faltan conexiones, consulta las alertas de rutas.', 'info')


def metricas_visual(reporte):
    titulo('MÉTRICAS DE OPERACIÓN', f"Fecha {reporte['fechaOperacion']}")
    console.print(f"Paquetes recibidos: {reporte['totalPaquetes']}")
    indicadores([
        ('ASIGNADOS', reporte['asignados']),
        ('PENDIENTES', len(reporte['pendientes'])),
        ('RECHAZADOS', len(reporte['rechazados'])),
        ('RUTAS', len(reporte['rutas'])),
    ])
    indicadores([
        ('DISTANCIA', f"{reporte['distanciaTotalKm']:,.2f} km"),
        ('COSTO', f"$ {reporte['costoTotalCOP']:,.0f} COP"),
        ('ASIGNADO', f"{reporte['porcentajeAsignado']:,.1f}%"),
    ])
    fila = []
    for r in reporte['rutas']:
        fila.append((r['id'], r['vehiculo'], indice_estado(r['estado']),
                     f"{r['ocupacionPesoPct']:.1f}%",
                     f"{r['ocupacionVolumenPct']:.1f}%"))
    tabla('UTILIZACIÓN DE LA FLOTA',
          ['Ruta','Vehículo','Estado','Peso','Volumen'],fila)
    met = Table(title='OPTIMIZACIÓN', box=box.MINIMAL_DOUBLE_HEAD, expand=True)
    met.add_column('Indicador', style='cyan')
    met.add_column('Valor', ratio=2)
    met.add_row('Método de rutas', reporte['metodoRutas'])
    met.add_row('Eficiencia consolidación (ida)',
                'No comparable' if reporte['eficienciaConsolidacionIdaPct'] is None
                else f"{reporte['eficienciaConsolidacionIdaPct']}%")
    met.add_row('Eficiencia TSP vs orden por código',
                'No disponible' if reporte['eficienciaTSPvsOrdenCodigoPct'] is None
                else f"{reporte['eficienciaTSPvsOrdenCodigoPct']}%")
    console.print(met)
