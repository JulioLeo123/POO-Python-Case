"""
Módulo de entidades e value objects do sistema de e-commerce refatorado.
"""
from dataclasses import dataclass
from typing import List, Optional
from abc import ABC, abstractmethod
from enum import Enum

@dataclass(frozen=True)
class Endereco:
    rua: str
    cidade: str
    estado: str
    cep: str
    def __post_init__(self):
        if not self.estado or len(self.estado) != 2:
            raise ValueError("Estado deve ter 2 caracteres")
        if not self.cep or len(self.cep) < 8:
            raise ValueError("CEP inválido")

@dataclass(frozen=True)
class Produto:
    id: int
    nome: str
    preco: float
    estoque: int
    categoria: str
    ativo: bool = True
    def __post_init__(self):
        if self.preco <= 0:
            raise ValueError("Preço deve ser positivo")
        if self.estoque < 0:
            raise ValueError("Estoque não pode ser negativo")
        if not self.nome.strip():
            raise ValueError("Nome é obrigatório")
    def tem_estoque_disponivel(self, quantidade: int) -> bool:
        return self.ativo and self.estoque >= quantidade
    def reduzir_estoque(self, quantidade: int) -> 'Produto':
        if not self.tem_estoque_disponivel(quantidade):
            raise ValueError(f"Estoque insuficiente para {self.nome}")
        return Produto(
            id=self.id,
            nome=self.nome,
            preco=self.preco,
            estoque=self.estoque - quantidade,
            categoria=self.categoria,
            ativo=self.ativo
        )

class TipoClienteEnum(Enum):
    REGULAR = "regular"
    PREMIUM = "premium"
    VIP = "vip"
    CORPORATIVO = "corporativo"

class CalculadoraDesconto(ABC):
    @abstractmethod
    def calcular_desconto(self, subtotal: float, quantidade: int = 1) -> float:
        pass
class DescontoRegular(CalculadoraDesconto):
    def calcular_desconto(self, subtotal: float, quantidade: int = 1) -> float:
        return 0.0
class DescontoPremium(CalculadoraDesconto):
    def calcular_desconto(self, subtotal: float, quantidade: int = 1) -> float:
        if subtotal > 1000:
            return subtotal * 0.15
        return subtotal * 0.10
class DescontoVIP(CalculadoraDesconto):
    def calcular_desconto(self, subtotal: float, quantidade: int = 1) -> float:
        if subtotal > 2000:
            return subtotal * 0.25
        elif subtotal > 1000:
            return subtotal * 0.20
        return subtotal * 0.15
class DescontoCorporativo(CalculadoraDesconto):
    def calcular_desconto(self, subtotal: float, quantidade: int = 1) -> float:
        if quantidade > 100:
            return subtotal * 0.30
        elif quantidade > 50:
            return subtotal * 0.25
        return subtotal * 0.20

@dataclass(frozen=True)
class Cliente:
    id: int
    nome: str
    email: str
    tipo: TipoClienteEnum
    limite_credito: float
    ativo: bool = True
    bloqueado: bool = False
    saldo_conta: float = 0.0
    pre_aprovado: bool = False
    def __post_init__(self):
        if self.limite_credito < 0:
            raise ValueError("Limite de crédito não pode ser negativo")
        if "@" not in self.email:
            raise ValueError("Email inválido")
        calculadoras = {
            TipoClienteEnum.REGULAR: DescontoRegular(),
            TipoClienteEnum.PREMIUM: DescontoPremium(),
            TipoClienteEnum.VIP: DescontoVIP(),
            TipoClienteEnum.CORPORATIVO: DescontoCorporativo()
        }
        object.__setattr__(self, '_calculadora_desconto', calculadoras[self.tipo])
    def calcular_desconto(self, subtotal: float, quantidade: int = 1) -> float:
        return self._calculadora_desconto.calcular_desconto(subtotal, quantidade)
    def pode_comprar(self, total: float, forma_pagamento: str) -> tuple[bool, str]:
        if not self.ativo:
            return False, "Cliente inativo"
        if self.bloqueado:
            return False, "Cliente bloqueado"
        if forma_pagamento == "cartao_credito":
            if self.limite_credito < total:
                return False, "Limite de crédito insuficiente"
            if total > 5000 and not self.pre_aprovado:
                return False, "Transação requer pré-aprovação"
        elif forma_pagamento == "cartao_debito":
            if self.saldo_conta < total:
                return False, "Saldo insuficiente"
        return True, ""

class FormaPagamentoEnum(Enum):
    CARTAO_CREDITO = "cartao_credito"
    CARTAO_DEBITO = "cartao_debito"
    PIX = "pix"
    BOLETO = "boleto"

@dataclass(frozen=True)
class ItemPedido:
    produto: Produto
    quantidade: int
    preco_unitario: float
    desconto: float
    @property
    def subtotal(self) -> float:
        return self.preco_unitario * self.quantidade
    @property
    def total(self) -> float:
        return self.subtotal - self.desconto

@dataclass
class Pedido:
    id: int
    cliente: Cliente
    itens: List[ItemPedido]
    endereco_entrega: Endereco
    forma_pagamento: FormaPagamentoEnum
    frete: float = 0.0
    data_criacao: Optional[str] = None
    status: str = "pendente"
    @property
    def total_produtos(self) -> float:
        return sum(item.total for item in self.itens)
    @property
    def total_final(self) -> float:
        return self.total_produtos + self.frete
