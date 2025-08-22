"""
Testes de caracterização e unitários para o sistema refatorado.
"""
import pytest
from ecommerce_refatorado.sistema_ecommerce_refatorado import SistemaEcommerceRefatorado

@pytest.fixture
def sistema_configurado():
    sistema = SistemaEcommerceRefatorado()
    sistema.adicionar_produto("Notebook Dell", 2500.00, 10, "Eletrônicos")
    sistema.adicionar_produto("Mouse Logitech", 50.00, 100, "Periféricos")
    sistema.adicionar_produto("Teclado Mecânico", 200.00, 50, "Periféricos")
    sistema.adicionar_cliente("João Silva", "joao@email.com", "premium")
    sistema.adicionar_cliente("Maria Santos", "maria@email.com", "vip")
    sistema.adicionar_cliente("Empresa XYZ", "contato@xyz.com", "corporativo", 100000)
    return sistema

def test_pedido_cliente_premium_com_desconto(sistema_configurado):
    dados_pedido = {
        "cliente_id": 1,
        "produtos": [{"produto_id": 1, "quantidade": 1}],
        "forma_pagamento": "cartao_credito",
        "endereco_entrega": {"rua": "Rua A", "cidade": "SP", "estado": "SP", "cep": "01234-000"}
    }
    resultado = sistema_configurado.processar_pedido_completo(dados_pedido)
    assert resultado["sucesso"] is True
    assert resultado["total_final"] == 2125.0

def test_pedido_frete_gratuito_sp_acima_200(sistema_configurado):
    dados_pedido = {
        "cliente_id": 1,
        "produtos": [{"produto_id": 2, "quantidade": 5}],
        "forma_pagamento": "pix",
        "endereco_entrega": {"rua": "Rua B", "cidade": "SP", "estado": "SP", "cep": "01234-000"}
    }
    resultado = sistema_configurado.processar_pedido_completo(dados_pedido)
    assert resultado["total_final"] == 225.0

def test_erro_cliente_inexistente(sistema_configurado):
    dados_pedido = {
        "cliente_id": 999,
        "produtos": [{"produto_id": 1, "quantidade": 1}],
        "forma_pagamento": "pix",
        "endereco_entrega": {"rua": "Rua C", "cidade": "SP", "estado": "SP", "cep": "01234-000"}
    }
    resultado = sistema_configurado.processar_pedido_completo(dados_pedido)
    assert "erro" in resultado
    assert "Cliente não encontrado" in resultado["erro"]

def test_erro_estoque_insuficiente(sistema_configurado):
    dados_pedido = {
        "cliente_id": 1,
        "produtos": [{"produto_id": 1, "quantidade": 20}],
        "forma_pagamento": "pix",
        "endereco_entrega": {"rua": "Rua D", "cidade": "SP", "estado": "SP", "cep": "01234-000"}
    }
    resultado = sistema_configurado.processar_pedido_completo(dados_pedido)
    assert "erro" in resultado
    assert "Estoque insuficiente" in resultado["erro"]

def test_cliente_bloqueado_nao_pode_comprar(sistema_configurado):
    # Bloqueia cliente 1
    cliente = sistema_configurado.repositorio_clientes.buscar_por_id(1)
    from ecommerce_refatorado.entidades import Cliente
    cliente_bloqueado = Cliente(
        id=cliente.id,
        nome=cliente.nome,
        email=cliente.email,
        tipo=cliente.tipo,
        limite_credito=cliente.limite_credito,
        ativo=cliente.ativo,
        bloqueado=True
    )
    sistema_configurado.repositorio_clientes._clientes[1] = cliente_bloqueado
    dados_pedido = {
        "cliente_id": 1,
        "produtos": [{"produto_id": 1, "quantidade": 1}],
        "forma_pagamento": "pix",
        "endereco_entrega": {"rua": "Rua E", "cidade": "SP", "estado": "SP", "cep": "01234-000"}
    }
    resultado = sistema_configurado.processar_pedido_completo(dados_pedido)
    assert "erro" in resultado
    assert "Cliente bloqueado" in resultado["erro"]
