import re
from datetime import date, datetime
from itertools import cycle
from typing import Union


DateLike = Union[date, datetime]


def digits(value: str) -> str:
    """Return only numeric characters from value."""
    return re.sub(r"\D", "", value or "")


def _fator_vencimento(vencimento: DateLike | None) -> str:
    if not vencimento:
        return "0000"

    if isinstance(vencimento, datetime):
        vencimento = vencimento.date()

    base = date(1997, 10, 7)
    dias = (vencimento - base).days
    return f"{max(dias, 0):04d}"[:4]


def _valor_formatado(valor: float | None) -> str:
    centavos = int(round(float(valor or 0) * 100))
    return f"{centavos:010d}"[:10]


def _montar_campo_livre(conta, nosso_numero: str, documento: str) -> str:
    agencia = digits(getattr(conta, "agencia", ""))[:4].zfill(4)
    conta_num = digits(getattr(conta, "conta", ""))[:8].zfill(8)
    carteira = digits(getattr(conta, "carteira", "17") or "17")[:2].zfill(2)
    nosso = digits(nosso_numero) or digits(documento)
    nosso = nosso[:11].zfill(11)
    return (carteira + agencia + nosso + conta_num)[:25].ljust(25, "0")


def _dv_mod11(numero: str) -> str:
    pesos = cycle(range(2, 10))
    soma = 0
    for digito, peso in zip(reversed(numero), pesos):
        soma += int(digito) * peso
    resto = soma % 11
    dv = 11 - resto
    if dv in (0, 10, 11):
        return "1"
    return str(dv)


def _dv_mod10(numero: str) -> str:
    soma = 0
    peso = 2
    for digito in reversed(numero):
        parcial = int(digito) * peso
        soma += parcial // 10 + parcial % 10
        peso = 1 if peso == 2 else 2
    return str((10 - (soma % 10)) % 10)


def _codigo_barras_base(conta, nosso_numero: str, documento: str, vencimento: DateLike, valor: float) -> str:
    banco = (digits(getattr(conta, "banco", "")) or "000")[:3].zfill(3)
    moeda = "9"
    fator = _fator_vencimento(vencimento)
    valor_str = _valor_formatado(valor)
    campo_livre = _montar_campo_livre(conta, nosso_numero, documento)

    parcial = banco + moeda + fator + valor_str + campo_livre
    dv = _dv_mod11(parcial)
    return banco + moeda + dv + fator + valor_str + campo_livre


def linha_digitavel(conta, nosso_numero: str, vencimento: DateLike, valor: float, documento: str = "") -> str:
    """Generate the "linha digitável" string for the boleto."""

    codigo = _codigo_barras_base(conta, nosso_numero, documento, vencimento, valor)
    banco_moeda = codigo[:4]
    fator = codigo[5:9]
    valor_str = codigo[9:19]
    campo_livre = codigo[19:]

    campo1 = banco_moeda + campo_livre[:5]
    campo2 = campo_livre[5:15]
    campo3 = campo_livre[15:25]

    dv1 = _dv_mod10(campo1)
    dv2 = _dv_mod10(campo2)
    dv3 = _dv_mod10(campo3)

    campo1_fmt = f"{campo1[:5]}.{campo1[5:]}{dv1}"
    campo2_fmt = f"{campo2[:5]}.{campo2[5:]}{dv2}"
    campo3_fmt = f"{campo3[:5]}.{campo3[5:]}{dv3}"

    return f"{campo1_fmt} {campo2_fmt} {campo3_fmt} {codigo[4]} {fator}{valor_str}"


def codigo_barras_numero(conta, nosso_numero: str, documento: str, valor: float, vencimento: DateLike | None = None) -> str:
    """Return the 44-digit numeric string encoded in the boleto barcode."""

    return _codigo_barras_base(conta, nosso_numero, documento, vencimento or date.today(), valor)


def codigo_barras_html(numero: str) -> str:
    """Generate the ITF barcode spans used by the boleto template."""
    padroes = {
        "0": "nnwwn",
        "1": "wnnnw",
        "2": "nwnnw",
        "3": "wwnnn",
        "4": "nnwnw",
        "5": "wnwnn",
        "6": "nwwnn",
        "7": "nnnww",
        "8": "wnnwn",
        "9": "nwnwn",
    }

    numero = digits(numero)
    if len(numero) % 2:
        numero = "0" + numero

    def span_bar(largura: str, espaco: bool = False) -> str:
        classe = largura
        if espaco:
            classe += " s"
        return f"<span class='{classe}'></span>"

    partes = []
    for idx, ch in enumerate("nnnn"):
        partes.append(span_bar(ch, espaco=bool(idx % 2)))

    for i in range(0, len(numero), 2):
        barras = padroes[numero[i]]
        espacos = padroes[numero[i + 1]]
        for b, e in zip(barras, espacos):
            partes.append(span_bar(b))
            partes.append(span_bar(e, espaco=True))

    for idx, ch in enumerate("wnn"):
        partes.append(span_bar(ch, espaco=bool(idx % 2)))

    return "".join(partes)
