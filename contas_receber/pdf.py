# -*- coding: utf-8 -*-
"""Funções utilitárias para geração de boletos em PDF.

O arquivo original possuía apenas uma frase solta em português, o que causava
um ``SyntaxError`` ao importar o módulo. O texto agora fica registrado neste
docstring, preservando a descrição e garantindo que o interpretador consiga
executar o restante do módulo normalmente.
"""

from __future__ import annotations

import asyncio
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
from caixa_banco.models import ContaBanco
from .models import EmpresaLicenciada, Pessoa

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

try:
    from pyppeteer import launch  # type: ignore
except Exception:  # pragma: no cover - execução sem pyppeteer continua válida
    launch = None  # type: ignore


def _resolver_entidades(titulo, empresa=None, conta=None, cliente=None):
    """Garante que todas as entidades necessárias estejam disponíveis."""

    empresa_resolvida = empresa or EmpresaLicenciada.query.first()
    conta_resolvida = conta or ContaBanco.query.first()
    cliente_resolvido = cliente or Pessoa.query.get(titulo.cliente_id)

    if not all([empresa_resolvida, conta_resolvida, cliente_resolvido]):
        raise ValueError("Dados incompletos para gerar o boleto")

    return empresa_resolvida, conta_resolvida, cliente_resolvido


def _montar_contexto_boleto(titulo, empresa, conta, cliente):
    documento = str(titulo.id)
    valor_float = float(titulo.valor_previsto)
    nosso_numero = titulo.nosso_numero or ""

    linha = linha_digitavel(
        conta, nosso_numero, titulo.data_vencimento, valor_float, documento
    )
    barcode_num = codigo_barras_numero(
        conta, nosso_numero, documento, valor_float, titulo.data_vencimento
    )

    banco_bruto = getattr(conta, "banco", "") or ""
    banco_digitos = digits(banco_bruto)
    codigo_banco = (banco_digitos[:3] or "000").zfill(3)
    dv_banco = banco_digitos[3:4]
    if dv_banco:
        codigo_banco = f"{codigo_banco}-{dv_banco}"

    contexto = dict(
        titulo=titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        linha_digitavel=linha,
        barcode=codigo_barras_html(barcode_num),
        codigo_banco=codigo_banco,
    )
    return contexto, barcode_num


def render_boleto_html(
    titulo,
    *,
    empresa=None,
    conta=None,
    cliente=None,
    is_pdf=False,
    template_name="financeiro/contas_a_receber/boleto.html",
):
    """Renderiza o boleto em HTML reutilizando o mesmo template da visualização."""

    empresa, conta, cliente = _resolver_entidades(
        titulo, empresa=empresa, conta=conta, cliente=cliente
    )
    contexto, _ = _montar_contexto_boleto(titulo, empresa, conta, cliente)
    contexto["is_pdf"] = is_pdf
    logo_bytes = _extract_logo_bytes()
    contexto["logo_banco_b64"] = base64.b64encode(logo_bytes).decode("utf-8") if logo_bytes else ""
    contexto["now"] = datetime.now
    return render_template(template_name, **contexto)


def _inject_pdf_styles(html: str) -> str:
    """Garante que o HTML possua regras de impressão adequadas."""

    if "@page" in html:
        return html

    styles = (
        "<style>@page { size: A4; margin: 0; } "
        "html, body { margin: 0; padding: 0; }""</style>"
    )
    closing_head = "</head>"
    if closing_head in html:
        return html.replace(closing_head, styles + closing_head, 1)
    return styles + html


def gerar_pdf_boleto(titulo, empresa, conta, cliente, filepath: str) -> None:
    """Gera o PDF do boleto reutilizando o HTML exibido na aplicação."""

    empresa, conta, cliente = _resolver_entidades(
        titulo, empresa=empresa, conta=conta, cliente=cliente
    )

    html = render_boleto_html(
        titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        is_pdf=True,
    )
    html = _inject_pdf_styles(html)
    
    if HTML is not None:
        try:
            HTML(string=html, base_url=current_app.root_path).write_pdf(target=filepath)
            return
        except Exception as exc:
            current_app.logger.warning(
                "WeasyPrint falhou (%s). Tentando outras opções.",
                exc,
            )
    else:
        current_app.logger.info(
            "WeasyPrint indisponível (%s). Tentando outras opções.",
            _WEASYPRINT_ERROR,
        )

    if _render_with_pyppeteer(html, filepath):
        return

    if _render_with_chromium(html, filepath):
        return

    if _render_with_wkhtmltopdf(html, filepath):
        return

    if pisa is not None:
        try:
            _render_with_pisa(html, filepath)
            return
        except Exception as exc:
            current_app.logger.warning(
                "xhtml2pdf falhou (%s).",
                exc,
            )

    raise RuntimeError("Não foi possível gerar o PDF do boleto. Verifique as dependências (WeasyPrint, pyppeteer, etc.)")


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
            user_data_dir = Path(tmpdir) / "user-data"
            user_data_dir.mkdir()
            html_path = Path(tmpdir) / "boleto.html"
            html_path.write_text(html, encoding="utf-8")
            cmd = comando + [
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                f'--user-data-dir={user_data_dir}',
                "--print-to-pdf-no-header",
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


def _render_with_pyppeteer(html: str, filepath: str) -> bool:
    """Renderiza o boleto em PDF utilizando o Chromium embarcado do pyppeteer."""

    if launch is None:
        return False

    async def _gerar_pdf() -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            user_data_dir = Path(tmpdir) / "user-data"
            user_data_dir.mkdir()
            browser = await launch(
                args=["--no-sandbox", "--disable-gpu", f"--user-data-dir={user_data_dir}"],
                handleSIGINT=False,
                handleSIGTERM=False,
                handleSIGHUP=False,
            )
            try:
                page = await browser.newPage()
                await page.setViewport({"width": 800, "height": 1200})
                await page.setContent(html, waitUntil="networkidle0")
                await page.emulateMediaType("screen")
                await page.pdf(
                    path=str(Path(filepath).resolve()),
                    format="A4",
                    printBackground=True,
                    preferCSSPageSize=True,
                    margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
                )
            finally:
                await browser.close()

    try:
        # Garante que um loop de eventos esteja disponível e o utiliza para rodar a função assíncrona.
        # A criação de um novo loop ou a obtenção do existente é gerenciada pelo asyncio.
        asyncio.run(_gerar_pdf())
    except Exception as exc:  # pragma: no cover - depende do ambiente
        current_app.logger.warning("pyppeteer não pôde gerar PDF: %s", exc)
        return False

    return Path(filepath).exists()

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