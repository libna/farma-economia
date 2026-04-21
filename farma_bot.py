import logging
import os
import psycopg2
import pandas as pd
from psycopg2 import extras
from datetime import datetime
from dotenv import load_dotenv
from thefuzz import process, fuzz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters

# Carrega variáveis de ambiente
load_dotenv()

# Configuração de Logs de Sistema
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# DEBUG: Verificação de Ambiente
db_url_debug = os.getenv("DATABASE_URL")
if db_url_debug:
    print(f"DEBUG: DATABASE_URL detectada: {db_url_debug[:10]}...")
else:
    print("DEBUG: DATABASE_URL NÃO detectada!")

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

def get_db_connection():
    """Conexão resiliente com suporte ao Railway/Postgres."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL não configurada!")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, sslmode='require')

def init_db():
    """Cria o Schema Profissional e popula a lista inicial."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Tabela de Medicamentos (Schema ANVISA-Ready com limites expandidos)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS remedio (
                ean VARCHAR(13) PRIMARY KEY,
                nome_comercial VARCHAR(500),
                principio_ativo VARCHAR(500),
                laboratorio VARCHAR(500),
                dosagem VARCHAR(255),
                forma_farmaceutica VARCHAR(500),
                preco DECIMAL(10,2),
                tipo VARCHAR(100)
            )
        ''')

        # Migração Automática para bases existentes
        colunas_para_expandir = ['nome_comercial', 'principio_ativo', 'laboratorio', 'forma_farmaceutica']
        for col in colunas_para_expandir:
            cursor.execute(f"ALTER TABLE remedio ALTER COLUMN {col} TYPE VARCHAR(500);")

        # Tabela de Logs (Business Intelligence)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs_busca (
                id SERIAL PRIMARY KEY,
                termo_usuario TEXT,
                resultado_encontrado TEXT,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        # Carga Inicial Estratégica
        cursor.execute("SELECT COUNT(*) FROM remedio")
        if cursor.fetchone()[0] == 0:
            logging.info("Iniciando Carga Inicial Profissional...")
            dados = [
                # EAN | Nome | Principio | Lab | Dosagem | Forma | Preco | Tipo
                ('7891058021301', 'Rocaltrol', 'Calcitriol', 'Roche', '0.25mcg', 'Capsula Mole', 115.00, 'REFERENCIA'),
                ('7896004719222', 'Calcitriol Sigman', 'Calcitriol', 'Sigman Pharma', '0.25mcg', 'Capsula Mole', 58.00, 'GENERICO'),
                ('7891317449212', 'Buscofem', 'Ibuprofeno', 'Boehringer', '400mg', 'Capsula Mole', 25.50, 'REFERENCIA'),
                ('7896004724110', 'Ibuprofeno EMS', 'Ibuprofeno', 'EMS', '400mg', 'Capsula Mole', 10.50, 'GENERICO'),
                ('7891058001105', 'Tylenol', 'Paracetamol', 'Janssen', '500mg', 'Comprimido', 18.00, 'REFERENCIA'),
                ('7896714214224', 'Paracetamol Neo', 'Paracetamol', 'Neo Química', '500mg', 'Comprimido', 8.50, 'GENERICO'),
                ('7896004702118', 'Novalgina', 'Dipirona', 'Sanofi', '500mg', 'Comprimido', 22.00, 'REFERENCIA'),
                ('7896714201118', 'Dipirona Euro', 'Dipirona', 'Eurofarma', '500mg', 'Comprimido', 7.90, 'GENERICO')
            ]
            cursor.executemany(
                'INSERT INTO remedio (ean, nome_comercial, principio_ativo, laboratorio, dosagem, forma_farmaceutica, preco, tipo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                dados
            )
            conn.commit()
        
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"Erro no init_db: {e}")

def registrar_log(termo, resultado):
    """Registra a busca para análise de mercado futura."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO logs_busca (termo_usuario, resultado_encontrado) VALUES (%s, %s)", (termo, resultado))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"Erro ao registrar log: {e}")

def buscar_remedio_inteligente(termo_usuario):
    """Busca aproximada em nomes e princípios ativos."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT nome_comercial FROM remedio WHERE tipo = 'REFERENCIA'")
        nomes = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT principio_ativo FROM remedio")
        principios = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        opcoes = list(set(nomes + principios))
        if not opcoes: return None, False
            
        melhor_match, score = process.extractOne(termo_usuario, opcoes, scorer=fuzz.token_sort_ratio)
        return (melhor_match, True) if score >= 85 else (melhor_match, False) if score >= 60 else (None, False)
    except Exception as e:
        logging.error(f"Erro na busca: {e}")
        return None, False

async def realizar_comparacao_e_enviar(update_or_query, termo_correto):
    """Busca por Nome ou Princípio, garantindo comparação de mesma dosagem e forma."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.DictCursor)
        
        # 1. Busca Referência (por Nome Comercial ou Princípio Ativo)
        cursor.execute("""
            SELECT * FROM remedio 
            WHERE (nome_comercial = %s OR principio_ativo = %s) AND tipo = 'REFERENCIA' 
            LIMIT 1
        """, (termo_correto, termo_correto))
        ref = cursor.fetchone()
        
        if not ref:
            msg = f"Encontrei '{termo_correto}', mas não temos um medicamento de referência correspondente."
            registrar_log(termo_correto, "NÃO ENCONTRADO")
            if isinstance(update_or_query, Update): await update_or_query.message.reply_text(msg)
            else: await update_or_query.edit_message_text(msg)
            return

        # 2. Busca o Genérico mais barato com MESMA DOSAGEM E FORMA
        cursor.execute("""
            SELECT nome_comercial, preco, laboratorio FROM remedio 
            WHERE principio_ativo = %s AND dosagem = %s AND forma_farmaceutica = %s AND tipo = 'GENERICO'
            ORDER BY preco ASC LIMIT 1
        """, (ref['principio_ativo'], ref['dosagem'], ref['forma_farmaceutica']))
        gen = cursor.fetchone()
        
        cursor.close()
        conn.close()

        res_log = f"{ref['nome_comercial']} -> {gen['nome_comercial'] if gen else 'SEM GENERICO'}"
        registrar_log(termo_correto, res_log)

        header = f"🔍 {ref['nome_comercial']} ({ref['laboratorio']})\n💊 {ref['dosagem']} | {ref['forma_farmaceutica']}\n💰 R$ {float(ref['preco']):.2f}"

        if not gen:
            resposta = f"{header}\n\n⚠️ Não encontramos genéricos para esta apresentação no momento."
        else:
            economia_r = float(ref['preco']) - float(gen['preco'])
            economia_p = (economia_r / float(ref['preco'])) * 100
            resposta = (
                f"{header}\n\n"
                f"✅ Opção mais barata encontrada:\n"
                f"💊 {gen['nome_comercial']} ({gen['laboratorio']})\n"
                f"💰 Preço: R$ {float(gen['preco']):.2f}\n"
                f"📉 Economia de: R$ {economia_r:.2f} ({economia_p:.1f}%)"
            )
        
        if isinstance(update_or_query, Update): await update_or_query.message.reply_text(resposta, reply_markup=ReplyKeyboardRemove())
        else: await update_or_query.edit_message_text(resposta)
            
    except Exception as e:
        logging.error(f"Erro na comparação: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    nome_correto, exato = buscar_remedio_inteligente(user_text)
    
    if not nome_correto:
        await update.message.reply_text(f"Poxa, ainda não temos '{user_text}' em nossa base. 😕")
        registrar_log(user_text, "DESCONHECIDO")
        return

    if exato:
        await realizar_comparacao_e_enviar(update, nome_correto)
    else:
        keyboard = [[InlineKeyboardButton("✅ Sim", callback_data=f"sim_{nome_correto}"), InlineKeyboardButton("❌ Não", callback_data="nao")]]
        await update.message.reply_text(f"Você quis dizer '{nome_correto}'?", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("sim_"):
        await realizar_comparacao_e_enviar(query, query.data.split("sim_")[1])
    else:
        await query.edit_message_text("Tudo bem! Tente pesquisar novamente. 💊")

async def comando_carga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando administrativo para carga em lote via EAN."""
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ Acesso negado. Apenas o administrador pode realizar cargas.")
        return

    linhas = update.message.text.split('\n')[1:] # Ignora a primeira linha (/carga)
    if not linhas:
        await update.message.reply_text("Formato: /carga\nEAN | Nome | Principio | Lab | Dosagem | Forma | Preco | Tipo")
        return

    sucesso, erro = 0, 0
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for linha in linhas:
        try:
            parts = [p.strip() for p in linha.split('|')]
            if len(parts) < 8: continue
            
            # UPSERT: Insere ou atualiza caso o EAN já exista
            cursor.execute("""
                INSERT INTO remedio (ean, nome_comercial, principio_ativo, laboratorio, dosagem, forma_farmaceutica, preco, tipo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ean) DO UPDATE SET 
                nome_comercial=EXCLUDED.nome_comercial, preco=EXCLUDED.preco;
            """, parts)
            sucesso += 1
        except Exception: erro += 1

    conn.commit()
    cursor.close()
    conn.close()
    await update.message.reply_text(f"✅ Carga finalizada!\nSucesso: {sucesso}\nErros: {erro}")

def normalize_text(text):
    if pd.isna(text): return ""
    return str(text).title().strip()

def normalize_type(text):
    if pd.isna(text): return ""
    text = str(text).upper()
    if "GENÉRICO" in text or "GENERICO" in text: return "GENERICO"
    if "REFERÊNCIA" in text or "REFERENCIA" in text: return "REFERENCIA"
    if "SIMILAR" in text: return "SIMILAR"
    return text

async def update_message_progress(update, processados, total):
    """Atualiza o progresso no Telegram a cada 5000 registros para evitar bloqueio."""
    if processados % 5000 == 0 or processados == total:
        await update.message.reply_text(f"⏳ Processando: {processados}/{total}...")

async def comando_carga_completa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lê o Excel da ANVISA localmente e processa em lotes."""
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ Acesso negado.")
        return

    arquivo_default = "data/lista_anvisa.xlsx"
    caminho_arquivo = arquivo_default if os.path.exists(arquivo_default) else "data/xls_conformidade_site_20260416_151911506.xlsx"

    if not os.path.exists(caminho_arquivo):
        await update.message.reply_text(f"❌ Erro: Arquivo {caminho_arquivo} não encontrado.")
        return

    await update.message.reply_text(f"🚀 Iniciando processamento de {os.path.basename(caminho_arquivo)}...")

    try:
        # 1. Leitura e Limpeza de Cabeçalho (skiprows=41 e normalização)
        df = pd.read_excel(caminho_arquivo, skiprows=41)
        df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True).str.upper()
        logging.info(f"Colunas após limpeza: {df.columns.tolist()}")
        
        # 2. Mapeamento Atualizado (Normalizado)
        mapeamento = {
            'EAN 1': 'ean',
            'SUBSTÂNCIA': 'principio_ativo',
            'PRODUTO': 'nome_comercial',
            'LABORATÓRIO': 'laboratorio',
            'APRESENTAÇÃO': 'apresentacao',
            'PMC 20 %': 'preco',
            'TIPO DE PRODUTO (STATUS DO PRODUTO)': 'tipo'
        }

        # Verifica colunas
        colunas_faltando = [col for col in mapeamento.keys() if col not in df.columns]
        if colunas_faltando:
            lista_cols = ", ".join(df.columns.tolist())
            await update.message.reply_text(f"❌ Erro: Colunas não encontradas: {colunas_faltando}\n\nColunas detectadas: [{lista_cols}]")
            return

        # Filtra e renomeia
        df = df[list(mapeamento.keys())].copy()
        df.rename(columns=mapeamento, inplace=True)

        # 3. Limpeza: Remover EAN nulo
        df.dropna(subset=['ean'], inplace=True)
        
        # 4. Conversão de Preço (Tratamento de vírgula para ponto)
        # Garante string, remove possíveis R$ ou espaços, remove separador de milhar (ponto) e troca vírgula por ponto
        df['preco'] = df['preco'].astype(str).str.replace('R$', '', regex=False).str.strip()
        df['preco'] = df['preco'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df['preco'] = pd.to_numeric(df['preco'], errors='coerce').fillna(0.0)

        # 5. Normalização de Dados (com Slicing de segurança)
        df['ean'] = df['ean'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.slice(0, 13)
        df['principio_ativo'] = df['principio_ativo'].apply(normalize_text).str.slice(0, 490)
        df['nome_comercial'] = df['nome_comercial'].apply(normalize_text).str.slice(0, 490)
        df['laboratorio'] = df['laboratorio'].apply(normalize_text).str.slice(0, 490)
        df['apresentacao'] = df['apresentacao'].apply(normalize_text).str.slice(0, 490)
        df['tipo'] = df['tipo'].apply(normalize_type).str.slice(0, 90)

        total_registros = len(df)
        batch_size = 1000
        processados = 0
        
        await update.message.reply_text(f"📊 {total_registros} registros válidos encontrados. Iniciando carga...")

        conn = get_db_connection()
        cursor = conn.cursor()

        for i in range(0, total_registros, batch_size):
            try:
                batch = df.iloc[i : i + batch_size]
                dados_batch = [
                    (
                        row['ean'], row['nome_comercial'], row['principio_ativo'], row['laboratorio'], 
                        "", row['apresentacao'], float(row['preco']), row['tipo']
                    )
                    for _, row in batch.iterrows()
                ]

                cursor.executemany("""
                    INSERT INTO remedio (ean, nome_comercial, principio_ativo, laboratorio, dosagem, forma_farmaceutica, preco, tipo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ean) DO UPDATE SET 
                    preco=EXCLUDED.preco, 
                    nome_comercial=EXCLUDED.nome_comercial,
                    principio_ativo=EXCLUDED.principio_ativo,
                    laboratorio=EXCLUDED.laboratorio,
                    forma_farmaceutica=EXCLUDED.forma_farmaceutica,
                    tipo=EXCLUDED.tipo;
                """, dados_batch)
                
                conn.commit()
                processados += len(batch)
                await update_message_progress(update, processados, total_registros)
            except Exception as batch_e:
                conn.rollback()
                logging.error(f"Erro no lote {i//batch_size}: {batch_e}")
                await update.message.reply_text(f"⚠️ Erro no lote {i//batch_size + 1}: {str(batch_e)[:200]}")

        cursor.close()
        conn.close()
        await update.message.reply_text(f"✅ Carga finalizada com sucesso! {processados} medicamentos processados.")

    except Exception as e:
        logging.error(f"Erro na carga completa: {e}")
        await update.message.reply_text(f"❌ Erro crítico: {str(e)}")

if __name__ == '__main__':
    init_db()
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("carga", comando_carga))
    application.add_handler(CommandHandler("carga_completa", comando_carga_completa))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    print("FarmaBot PRO iniciado...")
    application.run_polling()
