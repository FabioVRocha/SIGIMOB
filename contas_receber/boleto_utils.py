import re
from datetime import date, datetime
from typing import Union


DateLike = Union[date, datetime]


def digits(value: str) -> str:
    """Return only numeric characters from value."""
    return re.sub(r"\D", "", value or "")


def linha_digitavel(conta, nosso_numero: str, vencimento: DateLike, valor: float) -> str:
    """Generate a 47-digit placeholder line formatted as a boleto "linha digitável"."""
    banco = (digits(getattr(conta, "banco", "")) or "000").rjust(3, "0")[:3]
    moeda = "9"

    vencimento_data = vencimento.date() if isinstance(vencimento, datetime) else vencimento
    fator = (vencimento_data - date(1997, 10, 7)).days
    fator_str = str(max(fator, 0)).rjust(4, "0")[:4]

    valor_centavos = int(round(float(valor) * 100))
    valor_str = f"{valor_centavos:010d}"[:10]

    agencia = digits(getattr(conta, "agencia", ""))[:4].ljust(4, "0")
    conta_num = digits(getattr(conta, "conta", "")).replace("-", "")[:8].ljust(8, "0")
    nn = digits(nosso_numero)[:11].rjust(11, "0")
    carteira = digits(getattr(conta, "carteira", "17") or "17")[:2].rjust(2, "0")

    base = banco + moeda + carteira + agencia + nn + conta_num + fator_str + valor_str
    base = (base + ("0" * 47))[:47]

    c1 = f"{base[0:5]}.{base[5:10]}"
    c2 = f"{base[10:15]}.{base[15:21]}"
    c3 = f"{base[21:26]}.{base[26:32]}"
    dv = base[32]
    c5 = base[33:47]
    return f"{c1} {c2} {c3} {dv} {c5}"


def codigo_barras_numero(conta, nosso_numero: str, documento: str, valor: float) -> str:
    """Return the numeric string used to build the barcode placeholder."""
    numero = digits(getattr(conta, "banco", ""))
    numero += digits(nosso_numero or documento)
    numero += digits(f"{float(valor):.2f}")
    return numero[:44].ljust(44, "0")


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
