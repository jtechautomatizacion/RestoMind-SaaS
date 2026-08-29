from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(String, primary_key=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    telefono = Column(String, nullable=True)
    pais = Column(String, default="Perú")
    moneda = Column(String, default="PEN")
    estado = Column(String, default="activo")
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Relationships
    usuarios = relationship("Usuario", back_populates="cliente", cascade="all, delete-orphan")
    platos = relationship("Plato", back_populates="cliente", cascade="all, delete-orphan")
    mesas = relationship("Mesa", back_populates="cliente", cascade="all, delete-orphan")
    comandas = relationship("Comanda", back_populates="cliente", cascade="all, delete-orphan")
    compras = relationship("Compra", back_populates="cliente", cascade="all, delete-orphan")


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(String, primary_key=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="mozo")  # admin, jefe_cocina, mozo
    estado = Column(String, default="activo")
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Relationships
    cliente = relationship("Cliente", back_populates="usuarios")


class Plato(Base):
    __tablename__ = "platos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)
    categoria = Column(String, nullable=False)
    precio_venta = Column(Float, nullable=False)
    descripcion = Column(Text, nullable=True)
    imagen_url = Column(String, nullable=True)
    estado = Column(String, default="activo")  # activo, inactivo
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cliente = relationship("Cliente", back_populates="platos")
    comanda_platos = relationship("ComandaPlato", back_populates="plato", cascade="all, delete-orphan")


class Mesa(Base):
    __tablename__ = "mesas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    numero = Column(Integer, nullable=False)
    capacidad = Column(Integer, default=4)
    ubicacion = Column(String, nullable=True)
    estado = Column(String, default="disponible")  # disponible, ocupada
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Unique constraint: un número de mesa por cliente
    __table_args__ = (UniqueConstraint("cliente_id", "numero", name="uq_cliente_mesa_numero"),)

    # Relationships
    cliente = relationship("Cliente", back_populates="mesas")


class Comanda(Base):
    __tablename__ = "comandas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    numero_mesa = Column(Integer, nullable=False)
    total_cuenta = Column(Float, nullable=False)
    estado = Column(String, default="cocina")  # cocina, entregado, cobrado, cancelado
    creado_por = Column(String, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cliente = relationship("Cliente", back_populates="comandas")
    comanda_platos = relationship("ComandaPlato", back_populates="comanda", cascade="all, delete-orphan")


class ComandaPlato(Base):
    __tablename__ = "comanda_platos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comanda_id = Column(Integer, ForeignKey("comandas.id"), nullable=False)
    plato_id = Column(Integer, ForeignKey("platos.id"), nullable=False)
    cantidad = Column(Integer, default=1)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    # Relationships
    comanda = relationship("Comanda", back_populates="comanda_platos")
    plato = relationship("Plato", back_populates="comanda_platos")


class Compra(Base):
    __tablename__ = "compras"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    descripcion = Column(String, nullable=False)
    categoria = Column(String, nullable=True)
    monto = Column(Float, nullable=False)
    fecha = Column(String, nullable=False)  # YYYY-MM-DD
    estado = Column(String, default="registrado")  # registrado, cancelado
    creado_por = Column(String, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Relationships
    cliente = relationship("Cliente", back_populates="compras")
