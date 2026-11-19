from ..modelos.bodega import Bodega
from ..modelos.cliente import Cliente
from ..modelos.vehiculo import Vehiculo
from ..modelos.zona import Zona
from .ruta import Ruta


class CityDelivery:
    def __init__(self, bodega: Bodega):
        if not isinstance(bodega, Bodega):
            raise TypeError("Se necesita una Bodega Central válida.")
        self.bodega = bodega
        self.clientes: list[Cliente] = []
        self.vehiculos: list[Vehiculo] = []
        self.zonas: list[Zona] = []
        self.rutas: list[Ruta] = []

    def registrar_zona(self, zona: Zona) -> bool:
        if not isinstance(zona, Zona):
            return False
        if any(guardada.id == zona.id for guardada in self.zonas):
            return False
        self.zonas.append(zona)
        return True

    def registrar_cliente(self, cliente: Cliente) -> bool:
        if not isinstance(cliente, Cliente):
            return False
        # La referencia del cliente debe ser una zona YA registrada.
        if not any(zona is cliente.zona for zona in self.zonas):
            return False
        if any(guardado.id == cliente.id for guardado in self.clientes):
            return False
        self.clientes.append(cliente)
        return True

    def registrar_vehiculo(self, vehiculo: Vehiculo) -> bool:
        if not isinstance(vehiculo, Vehiculo):
            return False
        if any(v.identificador == vehiculo.identificador for v in self.vehiculos):
            return False
        # Un vehículo nuevo se da de alta sin mercancía preasignada.
        if vehiculo.carga_actual:
            return False
        self.vehiculos.append(vehiculo)
        return True

    def registrar_ruta(self, ruta: Ruta) -> bool:
        """Registra una ruta planeada y reserva su vehículo.

        El GestorDespachos validará la ruta según la fecha de operación
        antes de registrarla; aquí se comprueba la coherencia del sistema.
        """
        if not isinstance(ruta, Ruta) or ruta.estado != "PLANEADA":
            return False
        if not ruta.paquetes:
            return False
        if len({paquete.codigo for paquete in ruta.paquetes}) != len(ruta.paquetes):
            return False
        if not any(vehiculo is ruta.vehiculo for vehiculo in self.vehiculos):
            return False
        if not any(zona is ruta.zona for zona in self.zonas):
            return False
        if any(guardada.id == ruta.id for guardada in self.rutas):
            return False
        if not ruta.vehiculo.esta_disponible(self.rutas):
            return False

        for paquete in ruta.paquetes:
            if (
                paquete.estado != "ASIGNADO"
                or paquete not in ruta.vehiculo.carga_actual
                or paquete not in self.bodega.paquetes
                or paquete.cliente_destino.zona is not ruta.zona
                or not any(
                    cliente is paquete.cliente_destino for cliente in self.clientes
                )
            ):
                return False
            # Un paquete no puede pertenecer a más de una ruta registrada.
            if any(
                paquete is guardado or paquete.codigo == guardado.codigo
                for existente in self.rutas
                for guardado in existente.paquetes
            ):
                return False

        self.rutas.append(ruta)
        return True

    def obtener_vehiculos_disponibles(self) -> list[Vehiculo]:
        return [
            vehiculo
            for vehiculo in self.vehiculos
            if vehiculo.esta_disponible(self.rutas)
        ]

    def obtener_vehiculos_en_ruta(self) -> list[Vehiculo]:
        return [
            vehiculo
            for vehiculo in self.vehiculos
            if any(
                ruta.vehiculo is vehiculo and ruta.estado == "EN_RUTA"
                for ruta in self.rutas
            )
        ]

    def obtener_estado_vehiculo(self, id_vehiculo: str) -> str:
        vehiculo = next(
            (v for v in self.vehiculos if v.identificador == id_vehiculo), None
        )
        if vehiculo is None:
            raise ValueError(f"Vehículo no registrado: {id_vehiculo}")
        if not vehiculo.habilitado:
            return "INHABILITADO"
        ruta = self.consultar_ruta_vehiculo(id_vehiculo)
        if ruta is None:
            return "DISPONIBLE"
        return "EN_RUTA" if ruta.estado == "EN_RUTA" else "RESERVADO"

    def consultar_ruta_vehiculo(self, id_vehiculo: str) -> Ruta | None:
        if not any(v.identificador == id_vehiculo for v in self.vehiculos):
            return None
        return next(
            (
                ruta
                for ruta in self.rutas
                if ruta.vehiculo.identificador == id_vehiculo and ruta.ocupa_vehiculo()
            ),
            None,
        )

    def finalizar_ruta(self, id_ruta: str) -> bool:
        ruta = next((r for r in self.rutas if r.id == id_ruta), None)
        if ruta is None or ruta.estado != "EN_RUTA":
            return False
        if not ruta.finalizar_ruta():
            return False
        # Los paquetes salen del inventario cuando el viaje se completa.
        for paquete in ruta.paquetes:
            if paquete in self.bodega.paquetes:
                self.bodega.retirar_paquete(paquete)
        return True
