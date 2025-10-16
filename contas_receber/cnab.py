import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

ALLOWED_ALFA_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 /-.")


@dataclass
class Titulo:
    nosso_numero: str
    valor: float
    numero_documento: str = ''
    data_vencimento: Optional[date] = None
    data_emissao: Optional[date] = None
    juros_mora: float = 0.0
    multa: float = 0.0
    tipo_inscricao_pagador: str = '1'
    documento_pagador: str = ''
    nome_pagador: str = ''
    endereco_pagador: str = ''
    bairro_pagador: str = ''
    cep_pagador: str = ''
    cidade_pagador: str = ''
    uf_pagador: str = ''
    uso_empresa: str = ''


class CNAB240Writer:
    def __init__(self, empresa, conta):
        self.empresa = empresa
        self.conta = conta

    def gerar(self, titulos: List[Titulo]) -> str:
        if not titulos:
            raise ValueError('Nenhum titulo informado para gerar a remessa')

        timestamp = datetime.now()
        linhas = [
            self._header_arquivo(timestamp),
            self._header_lote(timestamp),
        ]

        sequencial = 1
        total_valor = Decimal('0.00')
        for titulo in titulos:
            valor = Decimal(str(titulo.valor or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            total_valor += valor
            linhas.append(self._segmento_p(sequencial, titulo, valor, timestamp))
            sequencial += 1
            linhas.append(self._segmento_q(sequencial, titulo))
            sequencial += 1
            linhas.append(self._segmento_r(sequencial, titulo, valor, timestamp))
            sequencial += 1

        registros_lote = len(titulos) * 3 + 2
        linhas.append(self._trailer_lote(registros_lote, total_valor))
        total_registros = len(titulos) * 3 + 4
        linhas.append(self._trailer_arquivo(total_registros))
        return '\r\n'.join(linhas) + '\r\n'

    def _header_arquivo(self, timestamp: datetime) -> str:
        banco = self._num(self._digits(getattr(self.conta, 'banco', '')), 3)
        lote = '0000'
        registro = '0'
        cnab = ' ' * 9
        tipo_inscricao = self._tipo_inscricao(getattr(self.empresa, 'documento', ''))
        inscricao = self._num(self._digits(getattr(self.empresa, 'documento', '')), 14)
        convenio = self._convenio()
        agencia_num, agencia_dv = self._split_num_dv(getattr(self.conta, 'agencia', ''))
        conta_num, conta_dv = self._split_num_dv(getattr(self.conta, 'conta', ''))
        nome_empresa = self._alfa(getattr(self.empresa, 'razao_social_nome', ''), 30)
        nome_banco = self._alfa(getattr(self.conta, 'nome_banco', '') or 'BANCO DO BRASIL S.A.', 30)
        codigo_remessa = '1'
        data_geracao = timestamp.strftime('%d%m%Y')
        hora_geracao = timestamp.strftime('%H%M%S')
        numero_sequencial = timestamp.strftime('%H%M%S')
        layout_version = '083'
        densidade = '01600'
        reservado_banco = ' ' * 20
        reservado_empresa = ' ' * 20
        cnab_final = ' ' * 29
        return (
            banco
            + lote
            + registro
            + cnab
            + tipo_inscricao
            + inscricao
            + convenio
            + self._num(agencia_num, 5)
            + self._alfa(agencia_dv or ' ', 1)
            + self._num(conta_num, 12)
            + self._alfa(conta_dv or ' ', 1)
            + ' '
            + nome_empresa
            + nome_banco
            + ' ' * 10
            + codigo_remessa
            + data_geracao
            + hora_geracao
            + numero_sequencial
            + layout_version
            + densidade
            + reservado_banco
            + reservado_empresa
            + cnab_final
        )

    def _header_lote(self, timestamp: datetime) -> str:
        banco = self._num(self._digits(getattr(self.conta, 'banco', '')), 3)
        lote = '0001'
        registro = '1'
        tipo_operacao = 'R'
        tipo_servico = '01'
        uso_exclusivo = ' ' * 2
        layout_lote = '042'
        cnab = ' '
        tipo_inscricao = self._tipo_inscricao(getattr(self.empresa, 'documento', ''))
        inscricao = self._num(self._digits(getattr(self.empresa, 'documento', '')), 15)
        convenio = self._convenio()
        agencia_num, agencia_dv = self._split_num_dv(getattr(self.conta, 'agencia', ''))
        conta_num, conta_dv = self._split_num_dv(getattr(self.conta, 'conta', ''))
        nome_empresa = self._alfa(getattr(self.empresa, 'razao_social_nome', ''), 30)
        mensagem1 = ' ' * 40
        mensagem2 = ' ' * 40
        numero_remessa = '00000001'
        data_gravacao = timestamp.strftime('%d%m%Y')
        data_credito = '00000000'
        uso_final = ' ' * 33
        return (
            banco
            + lote
            + registro
            + tipo_operacao
            + tipo_servico
            + uso_exclusivo
            + layout_lote
            + cnab
            + tipo_inscricao
            + inscricao
            + convenio
            + self._num(agencia_num, 5)
            + self._alfa(agencia_dv or ' ', 1)
            + self._num(conta_num, 12)
            + self._alfa(conta_dv or ' ', 1)
            + ' '
            + nome_empresa
            + mensagem1
            + mensagem2
            + numero_remessa
            + data_gravacao
            + data_credito
            + uso_final
        )

    def _segmento_p(self, sequencial: int, titulo: Titulo, valor: Decimal, timestamp: datetime) -> str:
        banco = self._num(self._digits(getattr(self.conta, 'banco', '')), 3)
        lote = '0001'
        registro = '3'
        seq = self._num(sequencial, 5)
        segmento = 'P'
        cnab = ' '
        movimento = '01'
        agencia_num, agencia_dv = self._split_num_dv(getattr(self.conta, 'agencia', ''))
        conta_num, conta_dv = self._split_num_dv(getattr(self.conta, 'conta', ''))
        nosso_numero = self._nosso_numero(titulo)
        carteira = self._carteira_codigo()
        forma_cadastramento = '1'
        tipo_documento = '1'
        emissao_boleto = '2'
        distribuicao = '2'
        numero_documento = self._alfa(titulo.numero_documento or titulo.nosso_numero, 15)
        data_vencimento = self._date(titulo.data_vencimento or timestamp.date())
        valor_titulo = self._decimal(valor, 15, 2)
        agencia_cobradora = '00000'
        dv_cobradora = ' '
        especie = self._num(self._digits(getattr(self.conta, 'especie_documento', '')) or '02', 2)
        aceite = 'N'
        data_emissao = self._date(titulo.data_emissao or timestamp.date())
        codigo_juros, data_juros, valor_juros = self._juros_fields(titulo, valor, timestamp)
        codigo_desconto = '0'
        data_desconto = '00000000'
        valor_desconto = '0' * 15
        valor_iof = '0' * 15
        valor_abatimento = '0' * 15
        uso_empresa = self._alfa(titulo.uso_empresa or numero_documento.strip(), 25)
        codigo_protesto, prazo_protesto = self._protesto_fields()
        codigo_baixa = '0'
        prazo_baixa = '000'
        codigo_moeda = '09'
        numero_contrato = self._num(self._digits(getattr(self.conta, 'contrato', '')), 10)
        uso_livre = ' '
        return (
            banco
            + lote
            + registro
            + seq
            + segmento
            + cnab
            + movimento
            + self._num(agencia_num, 5)
            + self._alfa(agencia_dv or ' ', 1)
            + self._num(conta_num, 12)
            + self._alfa(conta_dv or ' ', 1)
            + ' '
            + nosso_numero
            + carteira
            + forma_cadastramento
            + tipo_documento
            + emissao_boleto
            + distribuicao
            + numero_documento
            + data_vencimento
            + valor_titulo
            + agencia_cobradora
            + dv_cobradora
            + especie
            + aceite
            + data_emissao
            + codigo_juros
            + data_juros
            + valor_juros
            + codigo_desconto
            + data_desconto
            + valor_desconto
            + valor_iof
            + valor_abatimento
            + uso_empresa
            + codigo_protesto
            + prazo_protesto
            + codigo_baixa
            + prazo_baixa
            + codigo_moeda
            + numero_contrato
            + uso_livre
        )

    def _segmento_q(self, sequencial: int, titulo: Titulo) -> str:
        banco = self._num(self._digits(getattr(self.conta, 'banco', '')), 3)
        lote = '0001'
        registro = '3'
        seq = self._num(sequencial, 5)
        segmento = 'Q'
        cnab = ' '
        movimento = '01'
        tipo_inscricao = titulo.tipo_inscricao_pagador if titulo.tipo_inscricao_pagador in {'1', '2'} else self._tipo_inscricao(titulo.documento_pagador)
        inscricao = self._num(self._digits(titulo.documento_pagador), 15)
        nome = self._alfa(titulo.nome_pagador, 40)
        endereco = self._alfa(titulo.endereco_pagador, 40)
        bairro = self._alfa(titulo.bairro_pagador, 15)
        cep = self._digits(titulo.cep_pagador)[:8]
        cep_base = self._num(cep[:5], 5)
        cep_sufixo = self._num(cep[5:], 3)
        cidade = self._alfa(titulo.cidade_pagador, 15)
        uf = self._alfa(titulo.uf_pagador, 2)
        sacador_tipo = '0'
        sacador_numero = '0' * 15
        sacador_nome = ' ' * 40
        banco_corresp = '000'
        nosso_numero_corresp = ' ' * 20
        cnab_final = ' ' * 8
        return (
            banco
            + lote
            + registro
            + seq
            + segmento
            + cnab
            + movimento
            + tipo_inscricao
            + inscricao
            + nome
            + endereco
            + bairro
            + cep_base
            + cep_sufixo
            + cidade
            + uf
            + sacador_tipo
            + sacador_numero
            + sacador_nome
            + banco_corresp
            + nosso_numero_corresp
            + cnab_final
        )

    def _segmento_r(self, sequencial: int, titulo: Titulo, valor: Decimal, timestamp: datetime) -> str:
        banco = self._num(self._digits(getattr(self.conta, 'banco', '')), 3)
        lote = '0001'
        registro = '3'
        seq = self._num(sequencial, 5)
        segmento = 'R'
        cnab = ' '
        movimento = '01'
        zeros_15 = '0' * 15
        codigo_multa = '0'
        data_multa = '00000000'
        valor_multa = zeros_15
        multa = Decimal(str(titulo.multa or 0))
        if multa > 0:
            codigo_multa = '2'
            base_data = titulo.data_vencimento or timestamp.date()
            data_multa = self._date(base_data + timedelta(days=1))
            valor_multa = self._decimal(multa, 15, 2)
        info_pagador = ' ' * 10
        mensagem3 = ' ' * 40
        mensagem4 = ' ' * 40
        cnab_bloco = ' ' * 20
        ocorrencias = '0' * 8
        banco_debito = '000'
        agencia_debito = '00000'
        dv_agencia = ' '
        conta_debito = '000000000000'
        dv_conta = '0'
        dv_ag_conta = ' '
        aviso = '0'
        cnab_final = ' ' * 9
        return (
            banco
            + lote
            + registro
            + seq
            + segmento
            + cnab
            + movimento
            + '0'
            + '00000000'
            + zeros_15
            + '0'
            + '00000000'
            + zeros_15
            + codigo_multa
            + data_multa
            + valor_multa
            + info_pagador
            + mensagem3
            + mensagem4
            + cnab_bloco
            + ocorrencias
            + banco_debito
            + agencia_debito
            + dv_agencia
            + conta_debito
            + dv_conta
            + dv_ag_conta
            + aviso
            + cnab_final
        )

    def _trailer_lote(self, registros_lote: int, total_valor: Decimal) -> str:
        banco = self._num(self._digits(getattr(self.conta, 'banco', '')), 3)
        lote = '0001'
        registro = '5'
        cnab = ' ' * 9
        quantidade = self._num(registros_lote, 6)
        soma_valor = self._decimal(total_valor, 18, 2)
        quantidade_moeda = '0' * 18
        aviso = self._num('', 6)
        cnab_bloco = ' ' * 165
        ocorrencias = ' ' * 10
        return banco + lote + registro + cnab + quantidade + soma_valor + quantidade_moeda + aviso + cnab_bloco + ocorrencias

    def _trailer_arquivo(self, total_registros: int) -> str:
        banco = self._num(self._digits(getattr(self.conta, 'banco', '')), 3)
        lote = '9999'
        registro = '9'
        cnab = ' ' * 9
        total_lotes = self._num(1, 6)
        quantidade_registros = self._num(total_registros, 6)
        quantidade_contas = self._num('', 6)
        cnab_final = ' ' * 205
        return banco + lote + registro + cnab + total_lotes + quantidade_registros + quantidade_contas + cnab_final

    def _convenio(self) -> str:
        numero = self._digits(getattr(self.conta, 'convenio', ''))
        carteira = self._digits(getattr(self.conta, 'carteira', '17'))
        variacao = self._digits(getattr(self.conta, 'variacao', ''))
        if not numero:
            return ' ' * 20
        return (
            numero[-9:].rjust(9, '0')
            + '0014'
            + carteira[-2:].rjust(2, '0')
            + variacao[-3:].rjust(3, '0')
            + '  '
        )

    def _juros_fields(self, titulo: Titulo, valor: Decimal, timestamp: datetime) -> tuple[str, str, str]:
        juros = Decimal(str(titulo.juros_mora or 0))
        if juros <= 0:
            return '3', '00000000', '0' * 15
        base_date = titulo.data_vencimento or timestamp.date()
        data = self._date(base_date + timedelta(days=1))
        valor_dia = (valor * juros / Decimal('100')) / Decimal('30')
        return '1', data, self._decimal(valor_dia, 15, 2)

    def _protesto_fields(self) -> tuple[str, str]:
        dias = int(getattr(self.conta, 'dias_protesto', 0) or 0)
        if dias > 0:
            return '1', self._num(dias, 2)
        return '3', '00'

    def _carteira_codigo(self) -> str:
        carteira = self._digits(getattr(self.conta, 'carteira', ''))
        if carteira == '31':
            return '2'
        if carteira == '51' or carteira == '11':
            return '4'
        if carteira == '17':
            return '7'
        return (carteira[-1:] or '7')

    def _nosso_numero(self, titulo: Titulo) -> str:
        convenio = self._digits(getattr(self.conta, 'convenio', ''))
        sequencial = self._digits(titulo.nosso_numero)

        if len(convenio) == 7:
            numero = convenio[-7:] + sequencial.zfill(10)
        else:
            numero = sequencial.zfill(17)

        return numero[:17].ljust(20)

    def _tipo_inscricao(self, documento: str) -> str:
        digits = self._digits(documento)
        if len(digits) == 14:
            return '2'
        return '1'

    def _digits(self, value: Optional[str]) -> str:
        return re.sub(r'\D', '', value or '')

    def _alfa(self, value: Optional[str], length: int) -> str:
        if not value:
            return ' ' * length
        normalized = unicodedata.normalize('NFKD', str(value))
        chars = []
        for ch in normalized.upper():
            if unicodedata.combining(ch):
                continue
            if ch in ALLOWED_ALFA_CHARS:
                chars.append(ch)
            elif ch == ',':
                chars.append(' ')
        texto = ''.join(chars).strip()
        return texto[:length].ljust(length)

    def _num(self, value, length: int) -> str:
        digits = re.sub(r'\D', '', str(value)) if value not in (None, '') else ''
        if not digits:
            digits = '0'
        return digits[-length:].rjust(length, '0')

    def _decimal(self, value: Decimal, length: int, decimals: int) -> str:
        quant = Decimal('1').scaleb(-decimals)
        valor = Decimal(value or 0).quantize(quant, rounding=ROUND_HALF_UP)
        sem_ponto = f"{valor:.{decimals}f}".replace('.', '')
        return sem_ponto[-length:].rjust(length, '0')

    def _date(self, value: Optional[date]) -> str:
        if not value:
            return '00000000'
        return value.strftime('%d%m%Y')

    def _split_num_dv(self, value: Optional[str]) -> tuple[str, str]:
        if not value:
            return '', ''
        value = value.strip()
        match = re.match(r'^(\d+)[-\/]?([0-9Xx]?)$', value)
        if match:
            numero, dv = match.groups()
            return numero, dv.upper()
        digits = self._digits(value)
        return digits, ''


class CNAB240Reader:
    def __init__(self, conteudo: str):
        self.conteudo = [linha.rstrip('\r\n') for linha in conteudo.splitlines() if linha.strip()]

    def titulos_pagados(self):
        for linha in self.conteudo:
            if len(linha) < 240:
                continue
            if linha[7] != '3':
                continue
            segmento = linha[13]
            if segmento == 'P':
                nosso_numero = linha[37:57].strip()
                if not nosso_numero:
                    continue
                valor_str = re.sub(r'\D', '', linha[85:100])
                if not valor_str:
                    continue
                valor = Decimal(valor_str) / Decimal('100')
                yield nosso_numero, float(valor)
            elif segmento == 'T':
                nosso_numero = linha[4:24].strip()
                if not nosso_numero:
                    continue
                valor_str = re.sub(r'\D', '', linha[24:37])
                if not valor_str:
                    continue
                valor = Decimal(valor_str) / Decimal('100')
                yield nosso_numero, float(valor)
