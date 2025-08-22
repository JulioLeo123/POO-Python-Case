"""
Processamento de pedidos: validação, cálculo de frete, orquestração.
"""
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from ecommerce_refatorado.entidades import (
    Cliente, Produto, Pedido, ItemPedido, Endereco, 
    FormaPagamentoEnum, TipoClienteEnum
)
from ecommerce_refatorado.repositorios import RepositorioClientes, RepositorioProdutos, RepositorioPedidos
from ecommerce_refatorado.servicos import ServicoEmail

@dataclass
class ResultadoPedido:
    sucesso: bool
    pedido_id: Optional[int] = None
    total_final: Optional[float] = None
    erro: Optional[str] = None
    prazo_entrega: str = "3-5 dias úteis"

class CalculadoraFrete:
    def calcular(self, total_pedido: float, estado: str) -> float:
        if estado == "SP":
            return 0.0 if total_pedido > 200 else 15.0
        elif estado in ["RJ", "MG", "ES"]:
            return 0.0 if total_pedido > 300 else 25.0
        else:
            return 0.0 if total_pedido > 500 else 35.0

class ValidadorPedido:
    def validar_dados_basicos(self, dados_pedido: Dict[str, Any]) -> Optional[str]:
        if not dados_pedido:
            return "Dados do pedido não fornecidos"
        campos_obrigatorios = ["cliente_id", "produtos", "forma_pagamento", "endereco_entrega"]
        for campo in campos_obrigatorios:
            if campo not in dados_pedido:
                return f"Campo obrigatório ausente: {campo}"
        if not dados_pedido["produtos"] or len(dados_pedido["produtos"]) == 0:
            return "Nenhum produto no pedido"
        return None
    def validar_cliente(self, cliente: Cliente, total: float, forma_pagamento: str) -> Optional[str]:
        pode_comprar, motivo = cliente.pode_comprar(total, forma_pagamento)
        return None if pode_comprar else motivo
    def validar_produto(self, produto: Produto, quantidade: int) -> Optional[str]:
        if not produto.ativo:
            return f"Produto {produto.nome} não está ativo"
        if not produto.tem_estoque_disponivel(quantidade):
            return f"Estoque insuficiente para {produto.nome}"
        return None

class ProcessadorItens:
    def processar_itens(
        self, 
        produtos_dados: List[Dict[str, Any]], 
        cliente: Cliente,
        repositorio_produtos: RepositorioProdutos
    ) -> Tuple[List[ItemPedido], Optional[str]]:
        itens_processados = []
        for item_dados in produtos_dados:
            produto_id = item_dados.get("produto_id")
            quantidade = item_dados.get("quantidade", 1)
            produto = repositorio_produtos.buscar_por_id(produto_id)
            if not produto:
                return [], f"Produto {produto_id} não encontrado"
            validador = ValidadorPedido()
            erro_validacao = validador.validar_produto(produto, quantidade)
            if erro_validacao:
                return [], erro_validacao
            subtotal = produto.preco * quantidade
            desconto = cliente.calcular_desconto(subtotal, quantidade)
            item = ItemPedido(
                produto=produto,
                quantidade=quantidade,
                preco_unitario=produto.preco,
                desconto=desconto
            )
            itens_processados.append(item)
        return itens_processados, None

class ProcessadorPedido:
    def __init__(
        self,
        repositorio_clientes: RepositorioClientes,
        repositorio_produtos: RepositorioProdutos,
        repositorio_pedidos: RepositorioPedidos,
        servico_email: ServicoEmail
    ):
        self.repositorio_clientes = repositorio_clientes
        self.repositorio_produtos = repositorio_produtos
        self.repositorio_pedidos = repositorio_pedidos
        self.servico_email = servico_email
        self.calculadora_frete = CalculadoraFrete()
        self.processador_itens = ProcessadorItens()
        self.validador = ValidadorPedido()
    def processar(self, dados_pedido: Dict[str, Any]) -> ResultadoPedido:
        erro_basico = self.validador.validar_dados_basicos(dados_pedido)
        if erro_basico:
            return ResultadoPedido(sucesso=False, erro=erro_basico)
        cliente = self.repositorio_clientes.buscar_por_id(dados_pedido["cliente_id"])
        if not cliente:
            return ResultadoPedido(sucesso=False, erro="Cliente não encontrado")
        itens, erro_itens = self.processador_itens.processar_itens(
            dados_pedido["produtos"], 
            cliente, 
            self.repositorio_produtos
        )
        if erro_itens:
            return ResultadoPedido(sucesso=False, erro=erro_itens)
        total_produtos = sum(item.total for item in itens)
        endereco = Endereco(**dados_pedido["endereco_entrega"])
        frete = self.calculadora_frete.calcular(total_produtos, endereco.estado)
        total_final = total_produtos + frete
        forma_pagamento = dados_pedido["forma_pagamento"]
        erro_pagamento = self.validador.validar_cliente(cliente, total_final, forma_pagamento)
        if erro_pagamento:
            return ResultadoPedido(sucesso=False, erro=erro_pagamento)
        pedido = Pedido(
            id=self.repositorio_pedidos.proximo_id(),
            cliente=cliente,
            itens=itens,
            endereco_entrega=endereco,
            forma_pagamento=FormaPagamentoEnum(forma_pagamento),
            frete=frete,
            status="confirmado"
        )
        self.repositorio_pedidos.salvar(pedido)
        self._atualizar_estoque(itens)
        self.servico_email.enviar_confirmacao_pedido(cliente.email, pedido)
        return ResultadoPedido(
            sucesso=True,
            pedido_id=pedido.id,
            total_final=total_final
        )
    def _atualizar_estoque(self, itens: List[ItemPedido]) -> None:
        for item in itens:
            produto_atualizado = item.produto.reduzir_estoque(item.quantidade)
            self.repositorio_produtos.atualizar(produto_atualizado)
