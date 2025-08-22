"""
Sistema principal refatorado: Facade para uso externo.
"""
from typing import Dict, Any
from ecommerce_refatorado.entidades import Produto, Cliente, TipoClienteEnum
from ecommerce_refatorado.repositorios import (
    RepositorioClientesMemoria, RepositorioProdutosMemoria, RepositorioPedidosMemoria
)
from ecommerce_refatorado.processador_pedido import ProcessadorPedido
from ecommerce_refatorado.servicos import ServicoEmailConsole

class SistemaEcommerceRefatorado:
    def __init__(self):
        self.repositorio_clientes = RepositorioClientesMemoria()
        self.repositorio_produtos = RepositorioProdutosMemoria()
        self.repositorio_pedidos = RepositorioPedidosMemoria()
        self.servico_email = ServicoEmailConsole()
        self.processador_pedido = ProcessadorPedido(
            repositorio_clientes=self.repositorio_clientes,
            repositorio_produtos=self.repositorio_produtos,
            repositorio_pedidos=self.repositorio_pedidos,
            servico_email=self.servico_email
        )
    def processar_pedido_completo(self, dados_pedido: Dict[str, Any]) -> Dict[str, Any]:
        resultado = self.processador_pedido.processar(dados_pedido)
        if resultado.sucesso:
            return {
                "sucesso": True,
                "pedido_id": resultado.pedido_id,
                "total_final": resultado.total_final,
                "prazo_entrega": resultado.prazo_entrega
            }
        else:
            return {"erro": resultado.erro}
    def adicionar_produto(self, nome: str, preco: float, estoque: int, categoria: str) -> int:
        produto = Produto(
            id=0,
            nome=nome,
            preco=preco,
            estoque=estoque,
            categoria=categoria
        )
        produto_salvo = self.repositorio_produtos.salvar(produto)
        return produto_salvo.id
    def adicionar_cliente(self, nome: str, email: str, tipo: str, limite_credito: float = 0) -> int:
        tipo_enum = TipoClienteEnum(tipo)
        limites_padrao = {
            TipoClienteEnum.REGULAR: 1000,
            TipoClienteEnum.PREMIUM: 5000,
            TipoClienteEnum.VIP: 15000,
            TipoClienteEnum.CORPORATIVO: 50000
        }
        cliente = Cliente(
            id=0,
            nome=nome,
            email=email,
            tipo=tipo_enum,
            limite_credito=limite_credito or limites_padrao[tipo_enum]
        )
        self.repositorio_clientes.salvar(cliente)
        return cliente.id

if __name__ == "__main__":
    import json
    print("=== SISTEMA REFATORADO ===")
    sistema = SistemaEcommerceRefatorado()
    sistema.adicionar_produto("Notebook Dell", 2500.00, 10, "Eletrônicos")
    sistema.adicionar_produto("Mouse Logitech", 50.00, 100, "Periféricos")
    sistema.adicionar_cliente("João Silva", "joao@email.com", "premium")
    dados_pedido = {
        "cliente_id": 1,
        "produtos": [
            {"produto_id": 1, "quantidade": 1},
            {"produto_id": 2, "quantidade": 2}
        ],
        "forma_pagamento": "cartao_credito",
        "endereco_entrega": {
            "rua": "Rua das Flores, 123",
            "cidade": "São Paulo",
            "estado": "SP",
            "cep": "01234-567"
        }
    }
    resultado = sistema.processar_pedido_completo(dados_pedido)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
