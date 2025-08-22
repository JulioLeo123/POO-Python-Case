"""
Repositórios: interfaces e implementações em memória.
"""
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
from ecommerce_refatorado.entidades import Cliente, Produto, Pedido, TipoClienteEnum

class RepositorioClientes(ABC):
    @abstractmethod
    def buscar_por_id(self, id: int) -> Optional[Cliente]:
        pass
    @abstractmethod
    def salvar(self, cliente: Cliente) -> None:
        pass
    @abstractmethod
    def listar_todos(self) -> List[Cliente]:
        pass

class RepositorioProdutos(ABC):
    @abstractmethod
    def buscar_por_id(self, id: int) -> Optional[Produto]:
        pass
    @abstractmethod
    def atualizar(self, produto: Produto) -> None:
        pass
    @abstractmethod
    def listar_por_categoria(self, categoria: str) -> List[Produto]:
        pass

class RepositorioPedidos(ABC):
    @abstractmethod
    def salvar(self, pedido: Pedido) -> None:
        pass
    @abstractmethod
    def proximo_id(self) -> int:
        pass
    @abstractmethod
    def buscar_por_cliente(self, cliente_id: int) -> List[Pedido]:
        pass

class RepositorioClientesMemoria(RepositorioClientes):
    def __init__(self):
        self._clientes: Dict[int, Cliente] = {}
        self._proximo_id = 1
    def buscar_por_id(self, id: int) -> Optional[Cliente]:
        return self._clientes.get(id)
    def salvar(self, cliente: Cliente) -> None:
        if cliente.id == 0:
            cliente_com_id = Cliente(
                id=self._proximo_id,
                nome=cliente.nome,
                email=cliente.email,
                tipo=cliente.tipo,
                limite_credito=cliente.limite_credito,
                ativo=cliente.ativo,
                bloqueado=cliente.bloqueado,
                saldo_conta=cliente.saldo_conta,
                pre_aprovado=cliente.pre_aprovado
            )
            self._clientes[self._proximo_id] = cliente_com_id
            self._proximo_id += 1
        else:
            self._clientes[cliente.id] = cliente
    def listar_todos(self) -> List[Cliente]:
        return list(self._clientes.values())

class RepositorioProdutosMemoria(RepositorioProdutos):
    def __init__(self):
        self._produtos: Dict[int, Produto] = {}
        self._proximo_id = 1
    def buscar_por_id(self, id: int) -> Optional[Produto]:
        return self._produtos.get(id)
    def atualizar(self, produto: Produto) -> None:
        self._produtos[produto.id] = produto
    def salvar(self, produto: Produto) -> Produto:
        if produto.id == 0:
            produto_com_id = Produto(
                id=self._proximo_id,
                nome=produto.nome,
                preco=produto.preco,
                estoque=produto.estoque,
                categoria=produto.categoria,
                ativo=produto.ativo
            )
            self._produtos[self._proximo_id] = produto_com_id
            self._proximo_id += 1
            return produto_com_id
        else:
            self._produtos[produto.id] = produto
            return produto
    def listar_por_categoria(self, categoria: str) -> List[Produto]:
        return [p for p in self._produtos.values() if p.categoria == categoria]

class RepositorioPedidosMemoria(RepositorioPedidos):
    def __init__(self):
        self._pedidos: Dict[int, Pedido] = {}
        self._proximo_id = 1
    def salvar(self, pedido: Pedido) -> None:
        self._pedidos[pedido.id] = pedido
    def proximo_id(self) -> int:
        id_atual = self._proximo_id
        self._proximo_id += 1
        return id_atual
    def buscar_por_cliente(self, cliente_id: int) -> List[Pedido]:
        return [p for p in self._pedidos.values() if p.cliente.id == cliente_id]
