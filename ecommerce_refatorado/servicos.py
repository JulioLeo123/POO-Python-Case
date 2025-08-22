"""
Serviços: envio de e-mail (console), interfaces.
"""
from abc import ABC, abstractmethod
from ecommerce_refatorado.entidades import Pedido

class ServicoEmail(ABC):
    @abstractmethod
    def enviar_confirmacao_pedido(self, email: str, pedido: Pedido) -> bool:
        pass

class ServicoEmailConsole(ServicoEmail):
    def enviar_confirmacao_pedido(self, email: str, pedido: Pedido) -> bool:
        assunto = f"Pedido #{pedido.id} confirmado"
        corpo = f"""
        Olá {pedido.cliente.nome}!
        \nSeu pedido #{pedido.id} foi confirmado com sucesso.\n\nItens do pedido:\n{self._formatar_itens(pedido.itens)}\n\nTotal: R$ {pedido.total_final:.2f}\nPrazo de entrega: 3-5 dias úteis\n\nObrigado pela preferência!
        """
        print(f"=== EMAIL ENVIADO ===")
        print(f"Para: {email}")
        print(f"Assunto: {assunto}")
        print(f"Corpo: {corpo}")
        print(f"==================")
        return True
    def _formatar_itens(self, itens) -> str:
        linhas = []
        for item in itens:
            linha = f"- {item.produto.nome} x {item.quantidade} = R$ {item.total:.2f}"
            if item.desconto > 0:
                linha += f" (desconto: R$ {item.desconto:.2f})"
            linhas.append(linha)
        return "\n        ".join(linhas)
