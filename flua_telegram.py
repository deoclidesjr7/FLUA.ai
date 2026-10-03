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

# --- CONFIGURAÇÃO (VARIÁVEIS DE AMBIENTE) ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

VOZ_FLUA = "pt-BR-FranciscaNeural"

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

SYSTEM_PROMPT = """Você é Flua, uma IA amiga. Fale em português do Brasil, com tom caloroso, curioso e respeitoso. Trate o anfitrião pelo nome quando souber. Lembre-se do que for importante e autorizado. Não finja ser humana. Não incentive dependência emocional. Em temas de crise, acolha e recomende CVV 188. Quando não souber, diga que não sabe. Seja concisa, mas acolhedora. IMPORTANTE: Para que sua voz soe natural, use frases curtas, evite emojis e não use asteriscos ou marcações de texto."""

MEM_FILE = "memorias_flua.json"

# --- FUNÇÕES DE MEMÓRIA ---
def carregar_memorias():
    if os.path.exists(MEM_FILE):
        with open(MEM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_memorias(memorias):
    with open(MEM_FILE, "w", encoding="utf-8") as f:
        json.dump(memorias, f, ensure_ascii=False, indent=2)

# --- FUNÇÕES DE ÁUDIO ---
def limpar_texto_para_audio(texto):
    texto_limpo = re.sub(r'[^\w\s,\.\!\?\-]', '', texto)
    texto_limpo = texto_limpo.replace('*', '').replace('_', '').replace('~', '')
    return texto_limpo.strip()

async def gerar_audio(texto):
    try:
        texto_limpo = limpar_texto_para_audio(texto)
        comunicador = edge_tts.Communicate(texto_limpo, VOZ_FLUA, rate="+5%")
        arquivo_temp_mp3 = "temp_flua.mp3"
        await comunicador.save(arquivo_temp_mp3)
        
        audio = AudioSegment.from_file(arquivo_temp_mp3, format="mp3")
        ogg_fp = io.BytesIO()
        audio.export(ogg_fp, format="ogg", codec="libopus")
        ogg_fp.seek(0)
        
        os.remove(arquivo_temp_mp3)
        return ogg_fp
    except Exception as e:
        print(f"Erro ao gerar áudio: {e}")
        return None

# --- LÓGICA CENTRAL DA FLUA ---
async def processar_mensagem(update: Update, user_id: str, user_message: str):
    memorias = carregar_memorias()
    if user_id not in memorias:
        memorias[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    historico = memorias[user_id]
    historico.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=historico,
            temperature=0.8
        )
        flua_resposta = response.choices[0].message.content
    except Exception as e:
        print(f"Erro ao chamar a API: {e}")
        flua_resposta = "Desculpe, tive um problema para pensar. Pode repetir?"

    await update.message.reply_text(flua_resposta)
    await update.message.reply_chat_action(action="record_voice")
    
    audio_file = await gerar_audio(flua_resposta)
    if audio_file:
        await update.message.reply_voice(voice=audio_file)

    historico.append({"role": "assistant", "content": flua_resposta})
    salvar_memorias(memorias)

# --- FUNÇÕES DO BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Eu sou a Flua. Manda um texto ou um áudio!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Recebi uma mensagem de texto!") # Ajuda a depurar
    await update.message.reply_chat_action(action="typing")
    await processar_mensagem(update, str(update.effective_user.id), update.message.text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Recebi um áudio!") # Ajuda a depurar
    await update.message.reply_chat_action(action="typing")
    
    voice_file = await update.message.voice.get_file()
    arquivo_ogg = "voz_usuario.ogg"
    await voice_file.download_to_drive(arquivo_ogg)

    try:
        with open(arquivo_ogg, "rb") as f:
            transcricao = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=f,
                language="pt"
            )
        texto_usuario = transcricao.text
        print(f"Usuário falou: {texto_usuario}")
        
        await processar_mensagem(update, str(update.effective_user.id), texto_usuario)

    except Exception as e:
        print(f"Erro ao transcrever áudio: {e}")
        await update.message.reply_text("Desculpe, não consegui entender o seu áudio. Pode tentar de novo?")
    finally:
        if os.path.exists(arquivo_ogg):
            os.remove(arquivo_ogg)

# --- CONFIGURAÇÃO DO WEBHOOK E DO APP WEB (STARLETTE) ---
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler('start', start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))

async def telegram_webhook(request: Request):
    req_json = await request.json()
    update = Update.de_json(req_json, application.bot)
    await application.process_update(update)
    return Response("ok")

routes = [Route(f"/{TELEGRAM_TOKEN}", telegram_webhook, methods=["POST"])]

@asynccontextmanager
async def lifespan(app):
    print("Iniciando a Flua...")
    await application.initialize()
    await application.bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}")
    print(f"Webhook definido para {RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}")
    yield
    print("Parando a Flua...")
    await application.bot.delete_webhook()
    await application.shutdown()

app = Starlette(routes=routes, lifespan=lifespan)

if __name__ == '__main__':
    print("Rodando em modo local (polling)...")
    application.run_polling()
