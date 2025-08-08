from dataclasses import dataclass
from typing import List


@dataclass
class Titulo:
    nosso_numero: str
    valor: float


class CNAB240Writer:
    def __init__(self, empresa, conta):
        self.empresa = empresa
        self.conta = conta

    def gerar(self, titulos: List[Titulo]) -> str:
        linhas = []
        header = f"{self.conta.banco:0>3}0000HEADER".ljust(240)
        linhas.append(header)
        seq = 1
        for t in titulos:
            detalhe = f"{self.conta.banco:0>3}T{t.nosso_numero:>20}{int(t.valor*100):0>13}{seq:0>6}".ljust(240)
            linhas.append(detalhe)
            seq += 1
        trailer = f"{self.conta.banco:0>3}9999TRAILER{seq:0>6}".ljust(240)
        linhas.append(trailer)
        return "\n".join(linhas) + "\n"


class CNAB240Reader:
    def __init__(self, conteudo: str):
        self.conteudo = conteudo.splitlines()

    def titulos_pagados(self):
        for linha in self.conteudo[1:-1]:
            banco = linha[:3]
            if linha[3] != 'T':
                continue
            nosso_numero = linha[4:24].strip()
            valor = int(linha[24:37]) / 100.0
            yield nosso_numero, valor