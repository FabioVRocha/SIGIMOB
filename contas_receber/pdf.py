"""Geração de boletos em PDF reaproveitando o template HTML."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from flask import current_app, render_template

from .boleto_utils import (
    codigo_barras_html,
    codigo_barras_numero,
    linha_digitavel,
    digits,
)

from fpdf import FPDF

PT_TO_MM = 0.352777778

try:  # WeasyPrint usa dependências nativas; pode estar ausente.
    from weasyprint import HTML  # type: ignore
except Exception as exc:  # pragma: no cover - depende do SO
    HTML = None  # type: ignore
    _WEASYPRINT_ERROR = exc
else:
    _WEASYPRINT_ERROR = None

try:
    from xhtml2pdf import pisa  # type: ignore
except Exception:  # pragma: no cover - mantemos fallback manual
    pisa = None  # type: ignore


def gerar_pdf_boleto(titulo, empresa, conta, cliente, filepath: str) -> None:
    """Gera o PDF do boleto.

    Tenta primeiro renderizar o HTML existente com o WeasyPrint. Caso a
    biblioteca não esteja instalada (ou falhe), cai automaticamente para o
    gerador manual que já era utilizado anteriormente.
    """

    nosso_numero = titulo.nosso_numero or ""
    valor_float = float(titulo.valor_previsto)
    documento = str(titulo.id)

    linha = linha_digitavel(conta, nosso_numero, titulo.data_vencimento, valor_float)
    barcode_num = codigo_barras_numero(conta, nosso_numero, documento, valor_float)

    contexto = dict(
        titulo=titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        linha_digitavel=linha,
        barcode=codigo_barras_html(barcode_num),
        is_pdf=True,
    )

    html = render_template("financeiro/contas_a_receber/boleto.html", **contexto)

    if HTML is not None:
        try:
            HTML(string=html, base_url=current_app.root_path).write_pdf(target=filepath)
            return
        except Exception as exc:  # pragma: no cover
            current_app.logger.warning(
                "WeasyPrint falhou (%s). Tentando Chromium headless.",
                exc,
            )
    else:
        current_app.logger.info(
            "WeasyPrint indisponível (%s). Tentando Chromium headless.",
            _WEASYPRINT_ERROR,
        )

    if _render_with_chromium(html, filepath):
        return

    if _render_with_wkhtmltopdf(html, filepath):
        return

    if pisa is None:
        current_app.logger.warning(
            "xhtml2pdf indisponível. Voltando ao gerador PDF manual.",
        )
        _gerar_pdf_manual(
            titulo=titulo,
            empresa=empresa,
            conta=conta,
            cliente=cliente,
            filepath=filepath,
            linha_digitavel_texto=linha,
            barcode_numero=barcode_num,
            valor_formatado=f"{valor_float:.2f}",
        )
        return

    try:
        _render_with_pisa(html, filepath)
        return
    except Exception as exc:  # pragma: no cover
        current_app.logger.warning(
            "xhtml2pdf falhou (%s). Voltando ao gerador PDF manual.",
            exc,
        )

    _gerar_pdf_manual(
        titulo=titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        filepath=filepath,
        linha_digitavel_texto=linha,
        barcode_numero=barcode_num,
        valor_formatado=f"{valor_float:.2f}",
    )


def _link_callback(uri: str, rel: str) -> str:
    """Permite que o xhtml2pdf resolva caminhos estáticos."""

    if uri.startswith("data:"):
        return uri
    root = Path(current_app.root_path)
    static = root / "static"
    target = Path(uri)
    if target.is_file():
        return str(target)
    candidate = (root / uri.lstrip("/\\")).resolve()
    if candidate.is_file():
        return str(candidate)
    static_candidate = (static / uri.lstrip("/\\")).resolve()
    if static_candidate.is_file():
        return str(static_candidate)
    return uri


def _render_with_pisa(html: str, filepath: str) -> None:
    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(filepath, "wb") as arquivo:
        resultado = pisa.CreatePDF(
            html,
            dest=arquivo,
            link_callback=_link_callback,
            encoding="utf-8",
        )
    if getattr(resultado, "err", 0):
        raise RuntimeError("Falha ao gerar boleto com xhtml2pdf.")


def _render_with_chromium(html: str, filepath: str) -> bool:
    comando = _chromium_executable()
    if not comando:
        return False
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "boleto.html"
            html_path.write_text(html, encoding="utf-8")
            cmd = comando + [
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                f"--print-to-pdf={Path(filepath).resolve()}",
                html_path.as_uri(),
            ]
            resultado = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            if resultado.returncode == 0 and Path(filepath).exists():
                return True
            current_app.logger.warning(
                "Chromium headless falhou (ret=%s, stderr=%s)",
                resultado.returncode,
                resultado.stderr.decode("utf-8", errors="ignore"),
            )
    except Exception as exc:  # pragma: no cover
        current_app.logger.warning("Chromium headless não pôde gerar PDF: %s", exc)
    return False


def _render_with_wkhtmltopdf(html: str, filepath: str) -> bool:
    comando = shutil.which("wkhtmltopdf")
    if not comando:
        return False
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html", encoding="utf-8") as tmp:
            tmp.write(html)
            tmp_path = tmp.name
        cmd = [
            comando,
            "--encoding",
            "utf-8",
            "--quiet",
            tmp_path,
            filepath,
        ]
        resultado = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
        if resultado.returncode == 0 and Path(filepath).exists():
            return True
        current_app.logger.warning(
            "wkhtmltopdf falhou (ret=%s, stderr=%s)",
            resultado.returncode,
            resultado.stderr.decode("utf-8", errors="ignore"),
        )
    except Exception as exc:  # pragma: no cover
        current_app.logger.warning("wkhtmltopdf não pôde gerar PDF: %s", exc)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return False


def _chromium_executable() -> list[str] | None:
    candidatos = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "BraveSoftware/Brave-Browser/Application/brave.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "BraveSoftware/Brave-Browser/Application/brave.exe",
    ]
    for caminho in candidatos:
        if caminho and caminho.exists():
            return [str(caminho)]
    for nome in ("msedge", "chrome", "chromium", "brave"):
        executavel = shutil.which(nome)
        if executavel:
            return [executavel]
    return None


def _gerar_pdf_manual(
    *,
    titulo,
    empresa,
    conta,
    cliente,
    filepath: str,
    linha_digitavel_texto: str,
    barcode_numero: str,
    valor_formatado: str,
) -> None:
    """Gera o boleto com FPDF replicando o layout HTML."""

    due_date = titulo.data_vencimento.strftime("%d/%m/%Y")
    doc_num = str(titulo.id)
    beneficiario = empresa.razao_social_nome or ""
    agencia_conta = f"{conta.agencia} / {conta.conta}".strip()
    banco_nome = conta.nome_banco or conta.banco or ""
    cnpj = empresa.documento or ""

    pagador_nome = cliente.razao_social_nome or ""
    pagador_doc = cliente.documento or ""

    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_margins(0, 0, 0)
    pdf.set_text_color(0, 0, 0)

    content_width = 190.0
    margin_left = (pdf.w - content_width) / 2
    scale = content_width / 750.0

    def px(value: float) -> float:
        return value * scale

    y = 12.0

    banco_codigo = (digits(conta.banco) or "000")[:3]

    header_height = _draw_header(
        pdf,
        margin_left,
        y,
        content_width,
        px,
        banco_codigo,
        banco_nome,
        linha_digitavel_texto,
    )
    y += header_height + px(8)

    endereco_cedente = _format_endereco(empresa)
    sacado_ident = _compose_identificacao(pagador_nome, pagador_doc)
    sacado_endereco = _format_endereco(cliente)

    col_widths_recibo = [px(390), px(130), px(130), px(100)]
    rows_recibo = [
        [
            {"label": "Cedente", "value": beneficiario},
            {"label": "Agência/Código Cedente", "value": agencia_conta},
            {"label": "CPF/CNPJ Cedente", "value": cnpj},
            {"label": "Vencimento", "value": due_date},
        ],
        [
            {"label": "Sacado", "value": sacado_ident},
            {"label": "Nosso Número", "value": titulo.nosso_numero or ""},
            {"label": "N. do documento", "value": doc_num},
            {"label": "Data Documento", "value": due_date},
        ],
        [
            {"label": "Endereço Cedente", "value": endereco_cedente, "span": 3},
            {"label": "Valor Documento", "value": valor_formatado},
        ],
    ]

    y += _draw_table(pdf, margin_left, y, col_widths_recibo, rows_recibo, px) + px(8)

    y += _draw_box(pdf, margin_left, y, content_width, px(190), "Demonstrativo") + px(6)
    y += _draw_box(pdf, margin_left, y, content_width, px(80), "Autenticação Mecânica") + px(10)

    y += _draw_hr(pdf, margin_left, y, content_width) + px(6)

    header_height = _draw_header(
        pdf,
        margin_left,
        y,
        content_width,
        px,
        banco_codigo,
        banco_nome,
        linha_digitavel_texto,
    )
    y += header_height + px(8)

    col_widths_baixa = [px(180), px(120), px(120), px(70), px(70), px(90), px(100)]
    rows_baixa = [
        [
            {
                "label": "Local de pagamento",
                "value": "Pagável em qualquer banco até o vencimento. Após, atualize o boleto no site bb.com.br",
                "span": 6,
            },
            {"label": "Vencimento", "value": due_date},
        ],
        [
            {"label": "Cedente", "value": beneficiario, "span": 6},
            {"label": "Agência/Código cedente", "value": agencia_conta},
        ],
        [
            {"label": "Data do documento", "value": due_date},
            {"label": "N. do documento", "value": doc_num, "span": 2},
            {"label": "Espécie doc", "value": getattr(conta, "especie_documento", "") or ""},
            {"label": "Aceite", "value": "N"},
            {"label": "Data processamento", "value": due_date},
            {"label": "Nosso número", "value": titulo.nosso_numero or ""},
        ],
        [
            {"label": "Uso do banco", "value": ""},
            {"label": "Carteira", "value": getattr(conta, "carteira", "") or ""},
            {"label": "Espécie", "value": "R$"},
            {"label": "Quantidade", "value": "", "span": 2},
            {"label": "Valor", "value": ""},
            {"label": "(=) Valor documento", "value": valor_formatado},
        ],
    ]

    y += _draw_table(pdf, margin_left, y, col_widths_baixa, rows_baixa, px)
    y += _draw_instrucoes(pdf, margin_left, y, col_widths_baixa, px)
    y += _draw_rodape(pdf, margin_left, y, col_widths_baixa, px, cliente, barcode_numero)

    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)
    pdf.output(filepath)


def _draw_header(pdf: FPDF, x: float, y: float, width: float, px, banco_codigo: str, banco_nome: str, linha_digitavel: str) -> float:
    header_height = px(60)
    logo_width = px(170)
    codigo_width = px(70)
    linha_width = width - logo_width - codigo_width

    pdf.set_line_width(0.8)
    pdf.line(x, y + header_height, x + width, y + header_height)
    pdf.set_line_width(0.2)

    logo_path = _bank_logo_path()
    if logo_path:
        pdf.image(logo_path, x + px(10), y + px(6), w=logo_width - px(20))

    pdf.set_font("Helvetica", "B", 22)
    pdf.set_xy(x + logo_width, y + header_height / 2 - 7)
    pdf.cell(codigo_width, 10, banco_codigo, align="C")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(x + logo_width, y + header_height - px(18))
    pdf.cell(codigo_width, 6, banco_nome, align="C")

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(x + logo_width + codigo_width, y + header_height / 2 - 5)
    pdf.cell(linha_width, 8, linha_digitavel, align="R")

    return header_height


def _draw_box(pdf: FPDF, x: float, y: float, width: float, height: float, title: str) -> float:
    pdf.rect(x, y, width, height)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(x + 1.5, y + 4)
    pdf.cell(width - 3, 4, title)
    return height


def _draw_hr(pdf: FPDF, x: float, y: float, width: float) -> float:
    dash = 3.0
    gap = 1.5
    current = x
    while current < x + width:
        end = min(current + dash, x + width)
        pdf.line(current, y, end, y)
        current = end + gap
    return 0.2


def _draw_table(pdf: FPDF, x: float, y: float, col_widths: list[float], rows: list[list[dict]], px) -> float:
    label_font = 7
    value_font = 10
    current_y = y
    for row in rows:
        col_index = 0
        heights: list[float] = []
        for cell in row:
            span = cell.get("span", 1)
            width = sum(col_widths[col_index:col_index + span])
            label = cell.get("label", "")
            value = cell.get("value", "")
            label_size = cell.get("label_font_size", label_font)
            value_size = cell.get("value_font_size", value_font)
            min_height = cell.get("min_height", px(27))
            heights.append(
                _cell_height(pdf, width, label, value, label_size, value_size, min_height)
            )
            col_index += span
        row_height = max(heights) if heights else px(27)

        col_index = 0
        current_x = x
        for cell in row:
            span = cell.get("span", 1)
            width = sum(col_widths[col_index:col_index + span])
            pdf.rect(current_x, current_y, width, row_height)
            draw_callback = cell.get("draw")
            if draw_callback:
                draw_callback(pdf, current_x, current_y, width, row_height)
            else:
                label = cell.get("label", "")
                value = cell.get("value", "")
                label_size = cell.get("label_font_size", label_font)
                value_size = cell.get("value_font_size", value_font)
                _render_cell_content(pdf, current_x, current_y, width, row_height, label, value, label_size, value_size)
            current_x += width
            col_index += span
        current_y += row_height
    return current_y - y


def _cell_height(pdf: FPDF, width: float, label: str, value: str, label_size: int, value_size: int, min_height: float) -> float:
    height = 2.4  # paddings
    if label:
        height += label_size * PT_TO_MM * 1.1
    if value:
        pdf.set_font("Helvetica", "", value_size)
        lines = _wrap_text(pdf, value, width - 2.4)
        line_height = value_size * PT_TO_MM * 1.2
        if not lines:
            height += line_height
        else:
            height += line_height * len(lines)
    return max(height, min_height)


def _render_cell_content(
    pdf: FPDF,
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    value: str,
    label_size: int,
    value_size: int,
) -> None:
    padding = 1.2
    cursor_y = y + padding
    if label:
        pdf.set_font("Helvetica", "B", label_size)
        pdf.set_xy(x + padding, cursor_y)
        line_height = label_size * PT_TO_MM * 1.2
        pdf.cell(width - padding * 2, line_height, label)
        cursor_y += line_height
    if value:
        pdf.set_font("Helvetica", "", value_size)
        lines = _wrap_text(pdf, value, width - padding * 2)
        line_height = value_size * PT_TO_MM * 1.2
        if not lines:
            lines = [""]
        for line in lines:
            pdf.set_xy(x + padding, cursor_y)
            pdf.cell(width - padding * 2, line_height, line)
            cursor_y += line_height


def _draw_instrucoes(pdf: FPDF, x: float, y: float, col_widths: list[float], px) -> float:
    left_width = sum(col_widths[:-1])
    right_width = col_widths[-1]
    instruction_height = px(27) * 5

    pdf.rect(x, y, left_width, instruction_height)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(x + 1.5, y + 4)
    pdf.multi_cell(
        left_width - 3,
        4,
        "Instruções\n(Todas as informações deste bloqueto são de exclusiva responsabilidade do cedente)",
    )

    etiquetas = [
        "(-) Descontos/Abatimentos",
        "(-) Outras deduções",
        "(+) Mora/Multa",
        "(+) Outros acréscimos",
        "(=) Valor cobrado",
    ]
    item_height = instruction_height / len(etiquetas)
    for idx, etiqueta in enumerate(etiquetas):
        top = y + idx * item_height
        pdf.rect(x + left_width, top, right_width, item_height)
        pdf.set_font("Helvetica", "B" if idx == len(etiquetas) - 1 else "", 8)
        pdf.set_xy(x + left_width + 1.5, top + 3)
        pdf.multi_cell(right_width - 3, 4, etiqueta)
    return instruction_height


def _draw_rodape(
    pdf: FPDF,
    x: float,
    y: float,
    col_widths: list[float],
    px,
    cliente,
    barcode_numero: str,
) -> float:
    w_label = px(40)
    w_code = col_widths[-1]
    left_total = sum(col_widths[:-1])
    w_middle = left_total - w_label
    rodape_cols = [w_label, w_middle, w_code]

    sacado_linhas = [
        _compose_identificacao(cliente.razao_social_nome or "", cliente.documento or ""),
        cliente.endereco or "",
        _join_nonempty([cliente.bairro, cliente.cidade, cliente.estado, cliente.cep]),
    ]
    sacado_texto = "\n".join([linha for linha in sacado_linhas if linha])

    rows = [
        [
            {"label": "Sacado", "value": "", "min_height": px(27)},
            {"label": "", "value": sacado_texto, "span": 2, "value_font_size": 9, "min_height": px(27)},
        ],
        [
            {"label": "Sacador / Avalista", "value": "", "span": 2},
            {"label": "Código de baixa", "value": ""},
        ],
    ]

    consumed = _draw_table(pdf, x, y, rodape_cols, rows, px)
    y += consumed

    barcode_height = px(70)
    left_width = rodape_cols[0] + rodape_cols[1]
    pdf.rect(x, y, left_width, barcode_height)
    _draw_barcode(
        pdf,
        barcode_numero,
        x + px(12),
        y + px(10),
        left_width - px(24),
        barcode_height - px(20),
    )

    pdf.rect(x + left_width, y, rodape_cols[2], barcode_height)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(x + left_width + 1.5, y + 4)
    pdf.multi_cell(rodape_cols[2] - 3, 4, "Autenticação Mecânica / Ficha de Compensação")

    return consumed + barcode_height


def _wrap_text(pdf: FPDF, text: str, width: float) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if pdf.get_string_width(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                if pdf.get_string_width(word) <= width:
                    current = word
                else:
                    buffer = ""
                    for ch in word:
                        candidate = buffer + ch
                        if pdf.get_string_width(candidate) <= width:
                            buffer = candidate
                        else:
                            if buffer:
                                lines.append(buffer)
                            buffer = ch
                    current = buffer
        lines.append(current)
    return lines


def _compose_identificacao(nome: str, documento: str) -> str:
    if nome and documento:
        return f"{nome} - CPF/CNPJ: {documento}"
    if nome:
        return nome
    if documento:
        return f"CPF/CNPJ: {documento}"
    return ""


def _format_endereco(entidade) -> str:
    if entidade is None:
        return ""
    partes = [
        getattr(entidade, "endereco", ""),
        _join_nonempty(
            [getattr(entidade, "bairro", ""), getattr(entidade, "cidade", ""), getattr(entidade, "estado", "")]
        ),
        getattr(entidade, "cep", ""),
    ]
    return _join_nonempty(partes)


def _join_nonempty(items: Iterable[str], sep: str = " - ") -> str:
    return sep.join([item for item in items if item])


def _draw_barcode(pdf: FPDF, numero: str, x: float, y: float, width: float, height: float) -> None:
    sequencia = _codigo_barras_itf_sequence(numero)
    total_unidades = sum(unidades for _, unidades in sequencia)
    if not total_unidades:
        return
    modulo = width / total_unidades

    pdf.set_fill_color(255, 255, 255)
    pdf.rect(x, y, width, height, style="F")
    pdf.set_fill_color(0, 0, 0)
    pos = x
    for is_bar, unidades in sequencia:
        largura = unidades * modulo
        if is_bar:
            pdf.rect(pos, y, largura, height, style="F")
        pos += largura


def _codigo_barras_itf_sequence(numero: str) -> list[tuple[bool, int]]:
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

    sequencia: list[tuple[bool, int]] = []

    def adicionar(barras: str, espacos: str) -> None:
        for b, e in zip(barras, espacos):
            sequencia.append((True, 3 if b == "w" else 1))
            sequencia.append((False, 3 if e == "w" else 1))

    adicionar("nn", "nn")
    for i in range(0, len(numero), 2):
        barras = padroes[numero[i]]
        espacos = padroes[numero[i + 1]]
        adicionar(barras, espacos)
    sequencia.extend([(True, 3), (False, 1), (True, 1)])
    return sequencia


_BANK_LOGO_BYTES: bytes | None = None
_BANK_LOGO_FILE: Path | None = None


def _bank_logo_path() -> str | None:
    global _BANK_LOGO_BYTES, _BANK_LOGO_FILE
    if _BANK_LOGO_FILE and _BANK_LOGO_FILE.exists():
        return str(_BANK_LOGO_FILE)
    if _BANK_LOGO_BYTES is None:
        _BANK_LOGO_BYTES = _extract_logo_bytes()
    if not _BANK_LOGO_BYTES:
        return None
    fd, caminho = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    Path(caminho).write_bytes(_BANK_LOGO_BYTES)
    _BANK_LOGO_FILE = Path(caminho)
    return caminho


def _extract_logo_bytes() -> bytes:
    template_rel = Path("templates") / "financeiro" / "contas_a_receber" / "boleto.html"
    template_path = Path(current_app.root_path) / template_rel
    try:
        conteudo = template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return b""
    marcador = "data:image/jpeg;base64,"
    inicio = conteudo.find(marcador)
    if inicio == -1:
        return b""
    inicio += len(marcador)
    fim = conteudo.find('"', inicio)
    if fim == -1:
        return b""
    encoded = conteudo[inicio:fim]
    try:
        return base64.b64decode(encoded)
    except Exception:
        return b""
