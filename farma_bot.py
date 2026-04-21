import logging
import os
import psycopg2
from psycopg2 import extras
from dotenv import load_dotenv
from thefuzz import process, fuzz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CallbackQueryHandler, filters

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados PostgreSQL."""
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    """Cria a tabela e popula com a Super Lista caso o banco esteja vazio (PostgreSQL)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # DDL no padrão Postgres
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS remedio (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255),
            principio_ativo VARCHAR(255),
            tipo VARCHAR(50),
            apresentacao VARCHAR(255),
            preco DECIMAL(10,2)
        )
    ''')
    conn.commit()

    # Verifica se já existem dados
    cursor.execute("SELECT COUNT(*) FROM remedio")
    if cursor.fetchone()[0] == 0:
        logging.info("Populando banco de dados com a Super Lista estratégica...")
        
        # Super Lista Estratégica Completa
        dados = [
            # ADIÇÃO ESPECIAL PARA SUA AMIGA
            ('Rocaltrol', 'Calcitriol', 'REFERENCIA', '0.25mcg capsula', 115.00),
            ('Calcitriol Sigman Pharma', 'Calcitriol', 'GENERICO', '0.25mcg capsula', 58.00),
            ('Calcitriol Eurofarma', 'Calcitriol', 'GENERICO', '0.25mcg capsula', 54.50),

            # ANALGÉSICOS E ANTI-INFLAMATÓRIOS
            ('Buscofem', 'Ibuprofeno', 'REFERENCIA', '400mg capsula', 25.50),
            ('Ibuprofeno Medley', 'Ibuprofeno', 'GENERICO', '400mg capsula', 12.90),
            ('Ibuprofeno EMS', 'Ibuprofeno', 'GENERICO', '400mg capsula', 10.50),
            ('Advil', 'Ibuprofeno', 'REFERENCIA', '400mg capsula', 28.00),
            ('Tylenol', 'Paracetamol', 'REFERENCIA', '500mg comprimido', 18.00),
            ('Paracetamol Neo Química', 'Paracetamol', 'GENERICO', '500mg comprimido', 8.50),
            ('Novalgina', 'Dipirona', 'REFERENCIA', '500mg comprimido', 22.00),
            ('Dipirona Eurofarma', 'Dipirona', 'GENERICO', '500mg comprimido', 7.90),
            ('Dorflex', 'Dipirona', 'SIMILAR', '500mg comprimido', 15.00),
            ('Cataflam', 'Diclofenaco Potassico', 'REFERENCIA', '50mg comprimido', 35.00),
            ('Diclofenaco Potassico EMS', 'Diclofenaco Potassico', 'GENERICO', '50mg comprimido', 14.00),
            ('Voltaren', 'Diclofenaco Sodico', 'REFERENCIA', '50mg comprimido', 32.00),
            ('Diclofenaco Sodico Medley', 'Diclofenaco Sodico', 'GENERICO', '50mg comprimido', 12.50),

            # ALERGIA E GRIPE
            ('Allegra', 'Fexofenadina', 'REFERENCIA', '120mg comprimido', 55.00),
            ('Fexofenadina EMS', 'Fexofenadina', 'GENERICO', '120mg comprimido', 28.00),
            ('Claritin', 'Loratadina', 'REFERENCIA', '10mg comprimido', 42.00),
            ('Loratadina Medley', 'Loratadina', 'GENERICO', '10mg comprimido', 15.50),
            ('Zyrtec', 'Cetirizina', 'REFERENCIA', '10mg comprimido', 50.00),
            ('Cetirizina Medley', 'Cetirizina', 'GENERICO', '10mg comprimido', 22.00),

            # ESTÔMAGO E DIGESTÃO
            ('Buscopan Composto', 'Escopolamina', 'REFERENCIA', 'comprimido', 24.00),
            ('Escopolamina Neo Quimica', 'Escopolamina', 'GENERICO', 'comprimido', 11.00),
            ('Nexium', 'Esomeprazol', 'REFERENCIA', '40mg comprimido', 95.00),
            ('Esomeprazol Medley', 'Esomeprazol', 'GENERICO', '40mg comprimido', 45.00),
            ('PantoCalm', 'Pantoprazol', 'REFERENCIA', '40mg comprimido', 60.00),
            ('Pantoprazol Eurofarma', 'Pantoprazol', 'GENERICO', '40mg comprimido', 22.00),
            ('Luftal', 'Simeticona', 'REFERENCIA', '75mg gotas', 26.00),
            ('Simeticona Medley', 'Simeticona', 'GENERICO', '75mg gotas', 12.00),

            # PRESSÃO E CORAÇÃO (Uso Contínuo)
            ('Aradois', 'Losartana Potassica', 'REFERENCIA', '50mg comprimido', 45.00),
            ('Losartana Potassica Medley', 'Losartana Potassica', 'GENERICO', '50mg comprimido', 15.00),
            ('Selozok', 'Metoprolol', 'REFERENCIA', '50mg comprimido', 65.00),
            ('Metoprolol EMS', 'Metoprolol', 'GENERICO', '50mg comprimido', 32.00),
            ('Diovan', 'Valsartana', 'REFERENCIA', '160mg comprimido', 110.00),
            ('Valsartana Medley', 'Valsartana', 'GENERICO', '160mg comprimido', 48.00),

            # COLESTEROL E DIABETES
            ('Lipitor', 'Atorvastatina', 'REFERENCIA', '20mg comprimido', 140.00),
            ('Atorvastatina Medley', 'Atorvastatina', 'GENERICO', '20mg comprimido', 45.00),
            ('Crestor', 'Rosuvastatina', 'REFERENCIA', '10mg comprimido', 115.00),
            ('Rosuvastatina Medley', 'Rosuvastatina', 'GENERICO', '10mg comprimido', 38.00),
            ('Glifage XR', 'Metformina', 'REFERENCIA', '500mg comprimido', 20.00),
            ('Metformina Germed', 'Metformina', 'GENERICO', '500mg comprimido', 8.00),

            # ANTIBIÓTICOS E OUTROS
            ('Amoxil', 'Amoxicilina', 'REFERENCIA', '500mg capsula', 48.00),
            ('Amoxicilina EMS', 'Amoxicilina', 'GENERICO', '500mg capsula', 19.90),
            ('Astro', 'Azitromicina', 'REFERENCIA', '500mg comprimido', 35.00),
            ('Azitromicina Medley', 'Azitromicina', 'GENERICO', '500mg comprimido', 16.00),
            ('Puran T4', 'Levotiroxina', 'REFERENCIA', '50mcg comprimido', 22.00),
            ('Levotiroxina Generica', 'Levotiroxina', 'GENERICO', '50mcg comprimido', 14.00)
        ]

        # Inserção em massa no Postgres
        cursor.executemany(
            'INSERT INTO remedio (nome, principio_ativo, tipo, apresentacao, preco) VALUES (%s, %s, %s, %s, %s)',
            dados
        )
        conn.commit()
    
    cursor.close()
    conn.close()

def buscar_remedio_inteligente(termo_usuario):
    """Busca aproximada considerando Nome Comercial e Princípio Ativo (Postgres)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT DISTINCT nome FROM remedio WHERE tipo = 'REFERENCIA'")
        nomes = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT principio_ativo FROM remedio")
        principios = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        opcoes = list(set(nomes + principios))
        if not opcoes:
            return None, False
            
        melhor_match, score = process.extractOne(termo_usuario, opcoes, scorer=fuzz.token_sort_ratio)
        
        if score >= 85:
            return melhor_match, True
        elif score >= 60:
            return melhor_match, False
        else:
            return None, False
    except Exception as e:
        logging.error(f"Erro na busca inteligente: {e}")
        return None, False

async def realizar_comparacao_e_enviar(update_or_query, termo_correto):
    """Busca o medicamento de referência e o genérico mais barato (Postgres)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.DictCursor)
        
        # 1. Tenta buscar como Nome Comercial de Referência
        cursor.execute("SELECT nome, principio_ativo, tipo, apresentacao, preco FROM remedio WHERE nome = %s AND tipo = 'REFERENCIA'", (termo_correto,))
        res = cursor.fetchone()
        
        # 2. Se não achou, tenta buscar como Princípio Ativo (pegando a primeira referência correspondente)
        if not res:
            cursor.execute("SELECT nome, principio_ativo, tipo, apresentacao, preco FROM remedio WHERE principio_ativo = %s AND tipo = 'REFERENCIA' LIMIT 1", (termo_correto,))
            res = cursor.fetchone()

        if not res:
            msg = f"Encontrei '{termo_correto}', mas não temos um medicamento de referência correspondente na base para comparar."
            cursor.close()
            conn.close()
            if isinstance(update_or_query, Update):
                await update_or_query.message.reply_text(msg)
            else:
                await update_or_query.edit_message_text(msg)
            return

        nome_ref, principio, tipo, apresentacao, preco_ref = res['nome'], res['principio_ativo'], res['tipo'], res['apresentacao'], res['preco']

        # Busca genérico mais barato para esse princípio e apresentação
        cursor.execute("""
            SELECT nome, preco FROM remedio 
            WHERE principio_ativo = %s AND apresentacao = %s AND tipo = 'GENERICO'
            ORDER BY preco ASC LIMIT 1
        """, (principio, apresentacao))
        
        generico = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not generico:
            msg = f"🔍 Resultado para {nome_ref} (R$ {float(preco_ref):.2f}):\n\nInfelizmente não temos genéricos cadastrados para {principio} ({apresentacao}) no momento."
            if isinstance(update_or_query, Update):
                await update_or_query.message.reply_text(msg)
            else:
                await update_or_query.edit_message_text(msg)
            return

        nome_gen, preco_gen = generico['nome'], generico['preco']
        economia_reais = float(preco_ref) - float(preco_gen)
        economia_percent = (economia_reais / float(preco_ref)) * 100

        resposta = (
            f"🔍 Resultado para {nome_ref} (R$ {float(preco_ref):.2f}):\n\n"
            f"✅ Encontrei uma opção mais barata!\n"
            f"💊 {nome_gen} (Genérico)\n"
            f"💰 Preço: R$ {float(preco_gen):.2f}\n"
            f"📉 Economia de: R$ {economia_reais:.2f} ({economia_percent:.1f}%)"
        )
        
        if isinstance(update_or_query, Update):
            await update_or_query.message.reply_text(resposta, reply_markup=ReplyKeyboardRemove())
        else:
            await update_or_query.edit_message_text(resposta)
            
    except Exception as e:
        logging.error(f"Erro na comparação de preços: {e}")
        msg = "Ocorreu um erro técnico ao processar sua solicitação. Tente novamente mais tarde."
        if isinstance(update_or_query, Update):
            await update_or_query.message.reply_text(msg)
        else:
            await update_or_query.edit_message_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    
    # Busca inteligente
    nome_correto, exato = buscar_remedio_inteligente(user_text)
    
    if not nome_correto:
        await update.message.reply_text(f"Poxa, ainda não temos o medicamento ou princípio '{user_text}' em nossa base. 😕")
        return

    if exato:
        await realizar_comparacao_e_enviar(update, nome_correto)
    else:
        # Sugestão com botões Inline
        keyboard = [
            [
                InlineKeyboardButton("✅ Sim", callback_data=f"sim_{nome_correto}"),
                InlineKeyboardButton("❌ Não", callback_data="nao")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Você quis dizer '{nome_correto}'?",
            reply_markup=reply_markup
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("sim_"):
        termo_sugerido = query.data.split("sim_")[1]
        await realizar_comparacao_e_enviar(query, termo_sugerido)
    else:
        await query.edit_message_text("Tudo bem! Tente digitar o nome comercial ou o princípio ativo novamente. 💊")

if __name__ == '__main__':
    # Inicialização do Banco de Dados no Postgres
    try:
        init_db()
        print("Banco de Dados PostgreSQL inicializado e Super Lista verificada!")
    except Exception as e:
        print(f"CRITICAL: Erro ao inicializar o banco Postgres: {e}")

    application = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    print("FarmaBot rodando no modo de produção (PostgreSQL)...")
    application.run_polling()
