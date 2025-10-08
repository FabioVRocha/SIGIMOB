"""Geração de boletos em PDF reaproveitando o template HTML."""

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

    contexto = dict(
        titulo=titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        linha_digitavel=linha,
        barcode=codigo_barras_html(barcode_num),
    )
    return contexto, barcode_num


def render_boleto_html(
    titulo,
    *,
    empresa=None,
    conta=None,
    cliente=None,
    is_pdf=False,
):
    """Renderiza o boleto em HTML reutilizando o mesmo template da visualização."""

    empresa, conta, cliente = _resolver_entidades(
        titulo, empresa=empresa, conta=conta, cliente=cliente
    )
    contexto, _ = _montar_contexto_boleto(titulo, empresa, conta, cliente)
    contexto["is_pdf"] = is_pdf
    return render_template("financeiro/contas_a_receber/boleto.html", **contexto)


def _inject_pdf_styles(html: str) -> str:
    """Garante que o HTML possua regras de impressão adequadas."""

    if "@page" in html:
        return html

    styles = (
        "<style>@page { size: A4; margin: 0; } "
        "html, body { margin: 0; padding: 0; }" "</style>"
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
    contexto, barcode_num = _montar_contexto_boleto(titulo, empresa, conta, cliente)

    html = render_boleto_html(
        titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        is_pdf=False,
    )
    html = _inject_pdf_styles(html)
    
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

    if _render_with_pyppeteer(html, filepath):
        return

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
            linha_digitavel_texto=contexto["linha_digitavel"],
            barcode_numero=barcode_num,
            valor_formatado=f"{float(titulo.valor_previsto):.2f}",
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
        linha_digitavel_texto=contexto["linha_digitavel"],
        barcode_numero=barcode_num,
        valor_formatado=f"{float(titulo.valor_previsto):.2f}",
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
        browser = await launch(
            args=["--no-sandbox", "--disable-gpu"],
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
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            try:
                new_loop.run_until_complete(_gerar_pdf())
            finally:
                new_loop.close()
        else:
            loop.run_until_complete(_gerar_pdf())
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


"""Geração de boletos em PDF reaproveitando o template HTML."""

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

    contexto = dict(
        titulo=titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        linha_digitavel=linha,
        barcode=codigo_barras_html(barcode_num),
    )
    return contexto, barcode_num


def render_boleto_html(
    titulo,
    *,
    empresa=None,
    conta=None,
    cliente=None,
    is_pdf=False,
):
    """Renderiza o boleto em HTML reutilizando o mesmo template da visualização."""

    empresa, conta, cliente = _resolver_entidades(
        titulo, empresa=empresa, conta=conta, cliente=cliente
    )
    contexto, _ = _montar_contexto_boleto(titulo, empresa, conta, cliente)
    contexto["is_pdf"] = is_pdf
    return render_template("financeiro/contas_a_receber/boleto.html", **contexto)


def _inject_pdf_styles(html: str) -> str:
    """Garante que o HTML possua regras de impressão adequadas."""

    if "@page" in html:
        return html

    styles = (
        "<style>@page { size: A4; margin: 0; } "
        "html, body { margin: 0; padding: 0; }" "</style>"
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
    contexto, barcode_num = _montar_contexto_boleto(titulo, empresa, conta, cliente)

    html = render_boleto_html(
        titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        is_pdf=False,
    )
    html = _inject_pdf_styles(html)
    
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

    if _render_with_pyppeteer(html, filepath):
        return

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
            linha_digitavel_texto=contexto["linha_digitavel"],
            barcode_numero=barcode_num,
            valor_formatado=f"{float(titulo.valor_previsto):.2f}",
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
        linha_digitavel_texto=contexto["linha_digitavel"],
        barcode_numero=barcode_num,
        valor_formatado=f"{float(titulo.valor_previsto):.2f}",
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
        browser = await launch(
            args=["--no-sandbox", "--disable-gpu"],
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
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            try:
                new_loop.run_until_complete(_gerar_pdf())
            finally:
                new_loop.close()
        else:
            loop.run_until_complete(_gerar_pdf())
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
    """Gera o boleto com FPDF replicando o layout do Boleto Correto.pdf."""
    boleto_pdf = BoletoPDF(
        titulo=titulo,
        empresa=empresa,
        conta=conta,
        cliente=cliente,
        linha_digitavel_texto=linha_digitavel_texto,
        barcode_numero=barcode_numero,
        valor_formatado=valor_formatado,
    )
    boleto_pdf.gerar(filepath)


class BoletoPDF(FPDF):
    def __init__(self, *, titulo, empresa, conta, cliente, linha_digitavel_texto, barcode_numero, valor_formatado):
        super().__init__("P", "mm", "A4")
        self.titulo = titulo
        self.empresa = empresa
        self.conta = conta
        self.cliente = cliente
        self.linha_digitavel_texto = linha_digitavel_texto
        self.barcode_numero = barcode_numero
        self.valor_formatado = valor_formatado
        
        self.set_auto_page_break(False)
        self.add_page()
        self.set_margins(10, 10, 10)
        self.set_text_color(0, 0, 0)
        self.w_total = 190

    def gerar(self, filepath: str):
        self.draw_recibo_sacado(20)
        self.line(10, 100, 200, 100)
        self.draw_ficha_compensacao(105)
        
        directory = os.path.dirname(filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.output(filepath)

    def _header(self, y_pos: float):
        self.set_font("Helvetica", "B", 13)
        logo_path = _bank_logo_path()
        if logo_path:
            self.image(logo_path, 15, y_pos, 40)

        banco_codigo = (digits(self.conta.banco) or "000")[:3]
        self.set_xy(60, y_pos)
        self.cell(20, 10, f"{banco_codigo}", border=0, align="C")
        self.line(58, y_pos, 58, y_pos + 10)
        self.line(80, y_pos, 80, y_pos + 10)

        self.set_font("Helvetica", "B", 12)
        self.set_xy(82, y_pos)
        self.cell(0, 10, self.linha_digitavel_texto, border=0, align="R")
        self.line(10, y_pos + 12, 200, y_pos + 12)
        return y_pos + 12

    def _campo(self, x, y, w, h, label, value, label_size=7, value_size=9, align='L', border='T'):
        self.set_font("Helvetica", "", label_size)
        self.set_xy(x, y + 0.5)
        self.cell(w, 3, label, border=0, align="L")
        
        self.set_font("Helvetica", "B", value_size)
        self.set_xy(x, y + 4)
        self.cell(w, 5, value, border=0, align=align)
        
        self.rect(x, y, w, h)

    def draw_recibo_sacado(self, y_start):
        y = self._header(y_start)
        h = 12

        self._campo(10, y, 80, h, "Cedente", self.empresa.razao_social_nome)
        self._campo(90, y, 45, h, "Agência/Código Cedente", f"{self.conta.agencia} / {self.conta.conta}")
        self._campo(135, y, 45, h, "CPF/CNPJ Cedente", self.empresa.documento)
        self._campo(180, y, 20, h, "Vencimento", self.titulo.data_vencimento.strftime("%d/%m/%Y"))
        y += h

        self._campo(10, y, 80, h, "Sacado", self.cliente.razao_social_nome)
        self._campo(90, y, 45, h, "Nosso Número", self.titulo.nosso_numero)
        self._campo(135, y, 45, h, "N. do documento", str(self.titulo.id))
        self._campo(180, y, 20, h, "Data Documento", self.titulo.data_vencimento.strftime("%d/%m/%Y"))
        y += h

        self._campo(10, y, 170, h, "Endereço Cedente", self.empresa.endereco)
        self._campo(180, y, 20, h, "Valor Documento", self.valor_formatado, align='R')
        y += h

        self._campo(10, y, 170, 20, "Demonstrativo", "")
        self._campo(180, y, 20, 20, "", "")
        y += 20

        self.set_font("Helvetica", "", 8)
        self.set_xy(10, y)
        self.cell(0, 5, "Autenticação Mecânica", align="R")

    def draw_ficha_compensacao(self, y_start):
        y = self._header(y_start)
        h = 12

        self._campo(10, y, 150, h, "Local de pagamento", "Pagável em qualquer banco até o vencimento.")
        self._campo(160, y, 40, h, "Vencimento", self.titulo.data_vencimento.strftime("%d/%m/%Y"), align='R')
        y += h

        self._campo(10, y, 150, h, "Cedente", self.empresa.razao_social_nome)
        self._campo(160, y, 40, h, "Agência/Código cedente", f"{self.conta.agencia} / {self.conta.conta}", align='R')
        y += h

        self._campo(10, y, 30, h, "Data do documento", self.titulo.data_vencimento.strftime("%d/%m/%Y"))
        self._campo(40, y, 30, h, "N. do documento", str(self.titulo.id))
        self._campo(70, y, 25, h, "Espécie doc", getattr(self.conta, "especie_documento", "") or "DM")
        self._campo(95, y, 20, h, "Aceite", "N")
        self._campo(115, y, 35, h, "Data processamento", datetime.now().strftime("%d/%m/%Y"))
        self._campo(150, y, 50, h, "Nosso número", self.titulo.nosso_numero, align='R')
        y += h

        self._campo(10, y, 30, h, "Uso do banco", "")
        self._campo(40, y, 30, h, "Carteira", getattr(self.conta, "carteira", "") or "")
        self._campo(70, y, 25, h, "Espécie", "R$")
        self._campo(95, y, 20, h, "Quantidade", "")
        self._campo(115, y, 35, h, "Valor", "")
        self._campo(150, y, 50, h, "(=) Valor documento", self.valor_formatado, align='R')
        y += h

        self.set_font("Helvetica", "", 7)
        self.set_xy(10, y + 0.5)
        self.cell(140, 3, "Instruções (Todas as informações deste bloqueto são de exclusiva responsabilidade do cedente)")
        self.rect(10, y, 140, 36)

        y_inst = y
        h_inst = 7.2
        self._campo(150, y_inst, 50, h_inst, "(-) Descontos/Abatimentos", "", align='R')
        y_inst += h_inst
        self._campo(150, y_inst, 50, h_inst, "(-) Outras deduções", "", align='R')
        y_inst += h_inst
        self._campo(150, y_inst, 50, h_inst, "(+) Mora/Multa", "", align='R')
        y_inst += h_inst
        self._campo(150, y_inst, 50, h_inst, "(+) Outros acréscimos", "", align='R')
        y_inst += h_inst
        self._campo(150, y_inst, 50, h_inst, "(=) Valor cobrado", "", align='R')
        y += 36

        pagador_info = [
            f"Sacado: {self.cliente.razao_social_nome} - CPF/CNPJ: {self.cliente.documento}",
            self.cliente.endereco,
            f"{self.cliente.bairro} - {self.cliente.cidade} - {self.cliente.estado} - {self.cliente.cep}"
        ]
        self.set_font("Helvetica", "", 9)
        self.set_xy(10, y + 1)
        self.multi_cell(190, 4, "\n".join(filter(None, pagador_info)))
        y += 15

        self.set_font("Helvetica", "", 7)
        self.set_xy(10, y)
        self.cell(100, 4, "Sacador / Avalista:")
        self.set_xy(150, y)
        self.cell(50, 4, "Código de baixa", align="R")
        y += 8

        self.set_font("Helvetica", "", 9)
        self.set_xy(150, y)
        self.cell(50, 4, "Autenticação Mecânica / Ficha de Compensação", align="C")
        
        _draw_barcode(self, self.barcode_numero, 10, y, 120, 20)


def _draw_barcode(pdf: FPDF, numero: str, x: float, y: float, width: float, height: float) -> None:
    sequencia = _codigo_barras_itf_sequence(numero)
    total_unidades = sum(unidades for _, unidades in sequencia)
    if not total_unidades:
        return
    modulo = width / total_unidades

    pdf.set_fill_color(0, 0, 0)
    pos = x
    for is_bar, unidades in sequencia:
        largura = unidades * modulo
        if is_bar:
            pdf.rect(pos, y, largura, height, style="F")
        pos += largura


def _codigo_barras_itf_sequence(numero: str) -> list[tuple[bool, int]]:
    padroes = {
        "0": "nnwwn", "1": "wnnnw", "2": "nwnnw", "3": "wwnnn", "4": "nnwnw",
        "5": "wnwnn", "6": "nwwnn", "7": "nnnww", "8": "wnnwn", "9": "nwnwn",
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
