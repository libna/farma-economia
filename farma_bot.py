import logging
import sqlite3
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_TOKEN")

def init_db():
    """Inicializa o banco de dados SQLite com os dados do projeto original."""
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE remedio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            principio_ativo TEXT,
            tipo TEXT,
            apresentacao TEXT,
            preco REAL
        )
    ''')
    
    # Dados vindos do data.sql original
    dados = [
        ('Buscofem', 'Ibuprofeno', 'REFERENCIA', '400mg capsula', 25.50),
        ('Ibuprofeno Medley', 'Ibuprofeno', 'GENERICO', '400mg capsula', 12.90),
        ('Ibuprofeno EMS', 'Ibuprofeno', 'GENERICO', '400mg capsula', 10.50),
        ('Tylenol', 'Paracetamol', 'REFERENCIA', '500mg comprimido', 18.00),
        ('Paracetamol Neo Química', 'Paracetamol', 'GENERICO', '500mg comprimido', 8.50),
        ('Novalgina', 'Dipirona', 'REFERENCIA', '500mg comprimido', 22.00),
        ('Dipirona Eurofarma', 'Dipirona', 'GENERICO', '500mg comprimido', 7.90),
        ('Advil', 'Ibuprofeno', 'REFERENCIA', '400mg capsula', 28.00),
        ('Dorflex', 'Dipirona', 'SIMILAR', '500mg comprimido', 15.00),
        ('Ibuprofeno Teuto', 'Ibuprofeno', 'GENERICO', '400mg capsula', 11.20),
    ]
    
    cursor.executemany(
        'INSERT INTO remedio (nome, principio_ativo, tipo, apresentacao, preco) VALUES (?, ?, ?, ?, ?)', 
        dados
    )
    conn.commit()
    return conn

# Inicializa banco global
db_conn = init_db()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    cursor = db_conn.cursor()
    
    # 1. Busca o remédio digitado
    cursor.execute("SELECT nome, principio_ativo, tipo, apresentacao, preco FROM remedio WHERE nome = ? COLLATE NOCASE", (user_text,))
    ref = cursor.fetchone()
    
    if not ref:
        await update.message.reply_text(f"Poxa, ainda não temos o medicamento '{user_text}' em nossa base. 😕")
        return

    nome_ref, principio, tipo, apresentacao, preco_ref = ref
    
    if tipo != 'REFERENCIA':
        await update.message.reply_text(
            f"Encontrei o {nome_ref} ({tipo}), que custa R$ {preco_ref:.2f}. "
            "Para comparar preços, tente digitar o nome de um medicamento de referência (ex: Buscofem)."
        )
        return

    # 2. Busca genéricos equivalentes
    cursor.execute("""
        SELECT nome, preco FROM remedio 
        WHERE principio_ativo = ? AND apresentacao = ? AND tipo = 'GENERICO'
        ORDER BY preco ASC LIMIT 1
    """, (principio, apresentacao))
    
    generico = cursor.fetchone()
    
    if not generico:
        await update.message.reply_text(
            f"Encontrei o {nome_ref} (R$ {preco_ref:.2f}), mas não temos genéricos para "
            f"{principio} ({apresentacao}) no momento."
        )
        return

    nome_gen, preco_gen = generico
    economia_reais = preco_ref - preco_gen
    economia_percent = (economia_reais / preco_ref) * 100

    resposta = (
        f"🔍 Resultado para {nome_ref} (R$ {preco_ref:.2f}):\n\n"
        f"✅ Encontrei uma opção mais barata!\n"
        f"💊 {nome_gen} (Genérico)\n"
        f"💰 Preço: R$ {preco_gen:.2f}\n"
        f"📉 Economia de: R$ {economia_reais:.2f} ({economia_percent:.1f}%)"
    )
    
    await update.message.reply_text(resposta)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    application.add_handler(message_handler)
    
    print("FarmaBot Python iniciado... Pressione Ctrl+C para parar.")
    application.run_polling()
