# SIGIMOB

Sistema de Gestão de Imóveis e Aluguéis.

## Requisitos

- Python 3.8 ou superior
- PostgreSQL 9.3 ou superior

## Passo a passo de instalação

1. **Clone ou copie este repositório** para sua máquina.

2. **Crie o ambiente virtual** e ative-o:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate    # Windows
   ```

3. **Instale as dependências** presentes em `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```
   Se houver erro ao instalar `psycopg2-binary`, tente:
   ```bash
   pip install psycopg2-binary==2.9.9 --only-binary=:all:
   ```

4. **Configure o banco de dados PostgreSQL**:
   - Crie um banco (por exemplo `sigimob_db`).
   - Altere a variável `DATABASE_URL` em `config.py` ou defina-a como variável
     de ambiente no formato:
     `postgresql://usuario:senha@localhost:5432/sigimob_db`
   - Rode o script `SQL Criação Banco de Dados.txt` no banco criado para
     gerar as tabelas iniciais.
     - Se estiver atualizando uma instalação antiga, execute também:
     ```sql
     ALTER TABLE imoveis ADD COLUMN IF NOT EXISTS max_contratos INTEGER DEFAULT 1;
     ```

5. **Defina a chave secreta** em `config.py` (ou via variável de ambiente
   `SECRET_KEY`) para proteger as sessões do Flask.

6. **Execute a aplicação**:
   ```bash
   python app.py
   ```
   O servidor iniciará na porta padrão do Flask (5000). Acesse
   `http://localhost:5000` pelo navegador.

A aplicação é executada ouvindo em todas as interfaces de rede
   (`0.0.0.0`), permitindo o acesso a partir de outros computadores da
   mesma rede. Se o IP do servidor for `192.168.0.254`, por exemplo,
   utilize `http://192.168.0.254:5000/` no navegador para acessar o
   sistema.

   Caso o endereço ainda não seja acessível, verifique se a porta 5000
   está liberada no firewall do servidor.

As pastas de upload serão criadas automaticamente no primeiro uso.