import json
import os
import logging
import re
import io
from contextlib import asynccontextmanager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler
from openai import OpenAI
import edge_tts
from pydub import AudioSegment

# --- CONFIGURAÇÃO (USE VARIÁVEIS DE AMBIENTE) ---
# O Render vai ler essas variáveis que você vai configurar no painel dele.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
# O Render vai fornecer a URL do seu app automaticamente
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

VOZ_FLUA = "pt-BR-FranciscaNeural"

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

SYSTEM_PROMPT = """Você é Flua, uma IA amiga... (mesmo prompt de antes) ..."""

MEM_FILE = "memorias_flua.json"

# --- FUNÇÕES (carregar_memorias, salvar_memorias, limpar_texto_para_audio, gerar_audio) ---
# (Mantenha as mesmas funções que você já tem no seu código local)

# --- LÓGICA CENTRAL DA FLUA ---
async def processar_mensagem(update: Update, user_id: str, user_message: str):
    # (Mesma lógica de antes)
    ...

# --- FUNÇÕES DO BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Eu sou a Flua. Manda um texto ou um áudio!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(action="typing")
    await processar_mensagem(update, str(update.effective_user.id), update.message.text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (Mesma lógica de antes)
    ...

# --- CONFIGURAÇÃO DO WEBHOOK (A MÁGICA ACONTECE AQUI) ---
# Cria a aplicação do Telegram
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler('start', start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))

# Cria o app web (Starlette) que vai receber as atualizações do Telegram
async def telegram_webhook(request: Request):
    req_json = await request.json()
    update = Update.de_json(req_json, application.bot)
    await application.process_update(update)
    return Response("ok")

# Define a rota do webhook
routes = [Route(f"/{TELEGRAM_TOKEN}", telegram_webhook, methods=["POST"])]

# Cria o app
app = Starlette(routes=routes)

# Evento que roda quando o app inicia no Render
@app.on_event("startup")
async def on_startup():
    # Define o webhook no Telegram para apontar para a URL do Render
    await application.bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}")
    print(f"Webhook definido para {RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}")

# Evento que roda quando o app para
@app.on_event("shutdown")
async def on_shutdown():
    await application.bot.delete_webhook()
    await application.shutdown()

if __name__ == '__main__':
    # Modo local (polling) - apenas para testes no seu PC
    print("Rodando em modo local (polling)...")
    application.run_polling()
