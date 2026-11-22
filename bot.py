import os
import random
import asyncio
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord import app_commands
from google import genai
from google.genai import types
from mem0 import MemoryClient

# ==================== TRUCO PARA RENDER GRATIS (FLASK) ====================
app = Flask('')

@app.route('/')
def home():
    return "Bot Online y Servidor Activo en Python"

def run_web_server():
    puerto = int(os.environ.get("PORT", 3000))
    print(f"[Flask] Puerto detectado con éxito: {puerto}")
    app.run(host='0.0.0.0', port=puerto)

def mantener_vivo():
    t = Thread(target=run_web_server)
    t.start()

mantener_vivo()
# ==========================================================================


# ==================== CONFIGURACIÓN DE IA Y MEMORIA ====================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MEM0_API_KEY = os.environ.get("MEM0_API_KEY")

cliente_gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
cliente_memoria = MemoryClient(api_key=MEM0_API_KEY) if MEM0_API_KEY else None


# ==================== CONFIGURACIÓN DE DISCORD ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

sorteo_activo = None

@bot.event
async def on_ready():
    print(f"🚀 ¡Bot conectado correctamente como {bot.user}!")
    try:
        sincronizados = await bot.tree.sync()
        print(f"✅ [Comandos] ¡Comandos globales ({len(sincronizados)}) cargados exitosamente!")
    except Exception as e:
        print(f"❌ [Comandos] Error al registrar los comandos: {e}")


# ==================== IA CON MENCIONES (@NombaX) Y RESPUESTAS ====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    fue_mencionado = bot.user in message.mentions
    es_respuesta_al_bot = (
        message.reference is not None
        and isinstance(message.reference.resolved, discord.Message)
        and message.reference.resolved.author.id == bot.user.id
    )

    if fue_mencionado or es_respuesta_al_bot:
        texto_limpio = (
            message.content
            .replace(f"<@{bot.user.id}>", "")
            .replace(f"<@!{bot.user.id}>", "")
            .strip()
        )

        if not texto_limpio:
            texto_limpio = "Hola, ¿qué tal?"

        if not cliente_gemini or not cliente_memoria:
            await message.reply("❌ Faltan configurar las claves GEMINI_API_KEY o MEM0_API_KEY en Render.")
            return

        async with message.channel.typing():
            try:
                usuario_id = str(message.author.id)
                nombre_usuario = message.author.display_name

                # 1. Buscamos en Mem0 los recuerdos de este usuario (con límite de 5s)
                try:
                    resultados_memoria = await asyncio.wait_for(
                        asyncio.to_thread(
                            cliente_memoria.search,
                            query=texto_limpio,
                            filters={"user_id": usuario_id}
                        ),
                        timeout=5.0
                    )
                except Exception:
                    resultados_memoria = []

                lista_recuerdos = []
                if isinstance(resultados_memoria, dict) and "results" in resultados_memoria:
                    lista_recuerdos = [r.get("memory", "") for r in resultados_memoria["results"] if r.get("memory")]
                elif isinstance(resultados_memoria, list):
                    lista_recuerdos = [r.get("memory", "") for r in resultados_memoria if isinstance(r, dict) and r.get("memory")]

                contexto_recuerdos = (
                    "\n".join(f"- {recuerdo}" for recuerdo in lista_recuerdos)
                    if lista_recuerdos
                    else "Aún no tienes recuerdos previos con este usuario."
                )

                instrucciones_sistema = (
                    f"Eres NombaX, un bot de Discord cercano, natural y con buen sentido del humor. "
                    f"Estás conversando con {nombre_usuario}. "
                    f"Aprende y adapta tu forma de hablar al estilo de este usuario (jerga, tono, humor) y toma en cuenta lo que sabes de él/ella:\n"
                    f"{contexto_recuerdos}\n\n"
                    f"Reglas importantes:\n"
                    f"- Responde como en una charla real de Discord, directo y sin sonar robótico.\n"
                    f"- Mantén tus respuestas por debajo de los 1900 caracteres."
                )

                                # 2. Generamos la respuesta con Gemini (usando gemini-3.8-flash con 2 intentos rápidos)
                respuesta_gemini = None
                ultimo_error = None

                for intento in range(2):
                    try:
                        respuesta_gemini = await asyncio.wait_for(
                            asyncio.to_thread(
                                cliente_gemini.models.generate_content,
                                model="gemini-3.8-flash",
                                contents=texto_limpio,
                                config=types.GenerateContentConfig(
                                    system_instruction=instrucciones_sistema,
                                    temperature=0.75
                                )
                            ),
                            timeout=12.0
                        )
                        break
                    except Exception as err_modelo:
                        ultimo_error = err_modelo
                        await asyncio.sleep(1.5)


                if not respuesta_gemini:
                    raise ultimo_error if ultimo_error else Exception("Servidores de IA ocupados, intenta en unos segundos.")

                # 3. Sacamos el texto de la respuesta (esta es la línea que faltaba)
                texto_respuesta = respuesta_gemini.text or "Me quedé en blanco un segundo, dime otra vez."

                if len(texto_respuesta) > 1950:
                    texto_respuesta = texto_respuesta[:1950] + "..."

                # 4. Respondemos en texto normal directo en el chat
                await message.reply(texto_respuesta, mention_author=False)

                # 5. Guardamos la conversación en Mem0 en segundo plano
                conversacion = [
                    {"role": "user", "content": texto_limpio},
                    {"role": "assistant", "content": texto_respuesta}
                ]
                asyncio.create_task(
                    asyncio.to_thread(
                        cliente_memoria.add,
                        messages=conversacion,
                        user_id=usuario_id
                    )
                )

            except Exception as e:
                print(f"Error en IA por mención: {e}", flush=True)
                await message.reply(f"❌ Fallo técnico: `{str(e)[:200]}`")

    await bot.process_commands(message)


# ==================== MANEJADOR DE COMANDOS DE BARRA (/) ====================

# --- COMANDO: DECIR (AHORA CON SOPORTE PARA IMÁGENES Y VIDEOS) ---
@bot.tree.command(name="decir", description="Envía un mensaje, imagen o video al instante")
@app_commands.describe(
    mensaje="Escribe aquí el texto (opcional)",
    archivo="Sube aquí una imagen o video (opcional)"
)
async def decir(
    interaction: discord.Interaction, 
    mensaje: str = None, 
    archivo: discord.Attachment = None
):
    if not mensaje and not archivo:
        await interaction.response.send_message("❌ Debes escribir un mensaje o subir una imagen/video.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    try:
        archivo_enviar = await archivo.to_file() if archivo else None
        await interaction.channel.send(content=mensaje, file=archivo_enviar)
        await interaction.followup.send("✅ Contenido enviado con éxito.", ephemeral=True)
    except Exception as e:
        print(f"Error en comando decir: {e}")
        await interaction.followup.send("❌ Hubo un error al enviar el mensaje o el archivo (revisa que el video no sea muy pesado).", ephemeral=True)


# --- COMANDO: 8BALL (BOLA 8 MÁGICA) ---
@bot.tree.command(name="8ball", description="Hazle una pregunta a la bola 8 mágica")
@app_commands.describe(
    pregunta="Escribe la pregunta que quieres hacerle a la bola mágica"
)
async def eight_ball(interaction: discord.Interaction, pregunta: str):
    respuestas = [
        "Sí, definitivamente. 🟢",
        "Es totalmente seguro. 🟢",
        "Sin ninguna duda. 🟢",
        "Todo apunta a que sí. 🟢",
        "Puedes contar con ello. 🟢",
        "Claro que sí. 🟢",
        "Por supuesto. 🟢",
        "Respuesta confusa, vuelve a intentarlo. 🟡",
        "Pregunta de nuevo más tarde. 🟡",
        "Mejor no te lo digo ahora. 🟡",
        "No puedo predecirlo en este momento. 🟡",
        "Concéntrate y pregunta otra vez. 🟡",
        "No cuentes con ello. 🔴",
        "Mi respuesta es no. 🔴",
        "Mis fuentes dicen que no. 🔴",
        "Las perspectivas no son muy buenas. 🔴",
        "Muy dudoso. 🔴",
        "Definitivamente no. 🔴"
    ]

    respuesta_elegida = random.choice(respuestas)

    embed = discord.Embed(
        title="🎱 La Bola 8 Mágica dice...",
        color=discord.Color.purple()
    )
    embed.add_field(name="❓ Pregunta", value=pregunta, inline=False)
    embed.add_field(name="🔮 Respuesta", value=f"**{respuesta_elegida}**", inline=False)
    embed.set_footer(text=f"Preguntado por {interaction.user.name}")

    await interaction.response.send_message(embed=embed)


# --- COMANDO: CREAR SORTEO ---
@bot.tree.command(name="crear-sorteo", description="Inicia un sorteo")
@app_commands.describe(
    objeto="Premio del sorteo", 
    ganadores="Cantidad de ganadores (por defecto 1)", 
    mensaje="Mensaje extra o descripción", 
    imagen="Imagen del premio"
)
async def crear_sorteo(
    interaction: discord.Interaction, 
    objeto: str, 
    ganadores: int = 1, 
    mensaje: str = "¡Reacciona con 🎉 para participar en este sorteo!", 
    imagen: discord.Attachment = None
):
    global sorteo_activo

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎁 ¡NUEVO SORTEO ACTIVO! 🎁",
        description=f"{mensaje}\n\nPara entrar, simplemente presiona el botón de **🎉** aquí abajo.",
        color=discord.Color.from_rgb(30, 144, 255)
    )
    embed.add_field(name="🏆 Premio", value=f"**{objeto}**", inline=True)
    embed.add_field(name="👥 Ganadores", value=f"**{ganadores}**", inline=True)
    embed.set_footer(text="NombaX Sorteos • ¡Buena suerte a todos!")

    if imagen:
        embed.set_image(url=imagen.url)

    await interaction.response.send_message("📦 Generando sorteo...", ephemeral=True)
    
    mensaje_sorteo = await interaction.channel.send(embed=embed)
    await mensaje_sorteo.add_reaction("🎉")

    sorteo_activo = {
        "premio": objeto,
        "ganadores_requeridos": ganadores,
        "imagen_url": imagen.url if imagen else None,
        "mensaje_id": mensaje_sorteo.id,
        "canal_id": interaction.channel.id
    }


# --- COMANDO: SORTEAR ---
@bot.tree.command(name="sortear", description="Saca los ganadores al azar")
async def sortear(interaction: discord.Interaction):
    global sorteo_activo

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
        return
    if not sorteo_activo:
        await interaction.response.send_message("❌ No hay ningún sorteo activo en este momento.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        canal = bot.get_channel(sorteo_activo["canal_id"])
        mensaje_original = await canal.fetch_message(sorteo_activo["mensaje_id"])
        
        reaccion = discord.utils.get(mensaje_original.reactions, emoji="🎉")
        participantes = []
        
        if reaccion:
            async for usuario in reaccion.users():
                if not usuario.bot:
                    participantes.append(usuario)

        if not participantes:
            await interaction.followup.send("❌ El sorteo no puede realizarse porque nadie ha reaccionado con 🎉 todavía.")
            return

        await interaction.followup.send("📦 **|** _Barajando la lista de participantes y seleccionando boletos de forma segura..._")
        
        await asyncio.sleep(2.5)

        num_ganadores = sorteo_activo["ganadores_requeridos"]
        total_ganadores_reales = min(num_ganadores, len(participantes))

        ganadores_elegidos = random.sample(participantes, total_ganadores_reales)

        texto_menciones = "\n".join([f"{i+1}. {g.mention} (**{g.name}**)" for i, g in enumerate(ganadores_elegidos)])
        menciones_simples = " ".join([g.mention for g in ganadores_elegidos])

        embed_ganador = discord.Embed(
            title="🎉 ¡RESULTADOS DEL SORTEO! 🎉" if total_ganadores_reales > 1 else "🎉 ¡TENEMOS UN GANADOR! 🎉",
            description=f"El sorteo ha concluido exitosamente entre los **{len(participantes)}** participantes del servidor.",
            color=discord.Color.green()
        )
        embed_ganador.add_field(name="🏆 Objeto Sorteado", value=f"**{sorteo_activo['premio']}**", inline=False)
        embed_ganador.add_field(
            name="👑 Lista de Ganadores" if total_ganadores_reales > 1 else "👑 Ganador(a)", 
            value=texto_menciones, 
            inline=False
        )
        embed_ganador.set_footer(text="NombaX Sorteos • ¡Felicidades a los afortunados!")

        if sorteo_activo["imagen_url"]:
            embed_ganador.set_thumbnail(url=sorteo_activo["imagen_url"])

        await interaction.channel.send(content=f"¡Sorteo finalizado! 🏆 {menciones_simples}", embed=embed_ganador)

        canal_news = discord.utils.get(interaction.guild.text_channels, name="〔👑〕news")
        if canal_news:
            await canal_news.send(
                content=f"📢 **¡Atención Comunidad!** Felicidades a {menciones_simples} por haber ganado el sorteo de **{sorteo_activo['premio']}** 👑🎉"
            )

        sorteo_activo = None

    except Exception as e:
        print(f"Error procesando sorteo: {e}")
        await interaction.followup.send("❌ Hubo un problema técnico al intentar procesar el sorteo.")


# ==================== EVENTO DE BIENVENIDA AUTOMÁTICO ====================
@bot.event
async def on_member_join(member):
    try:
        canal_bienvenida = discord.utils.get(member.guild.text_channels, name="〔💬〕general")
        if not canal_bienvenida:
            print("❌ [Bienvenida] No se encontró ningún canal llamado 〔💬〕general")
            return

        canal_roles = discord.utils.get(member.guild.text_channels, name="roles")
        canal_reglas = discord.utils.get(member.guild.text_channels, name="reglas")

        mencion_roles = canal_roles.mention if canal_roles else "#roles"
        mencion_reglas = canal_reglas.mention if canal_reglas else "#reglas"

        mensaje_bienvenida = (
            f"_Hola {member.mention} bienvenido al sunshine ☀️_\n\n"
            f"_• 🎭 Puedes elegir tus roles en el canal {mencion_roles} para personalizar tu perfil._\n"
            f"_• 📜 Lee detenidamente las {mencion_reglas} del servidor para conocer las normas de convivencia y evitar sanciones por parte de la administración._\n\n"
            f"_Una vez hecho esto, eres libre de integrarte a los canales de texto y voz. ¡Diviértete!_"
        )

        await canal_bienvenida.send(mensaje_bienvenida)
        print(f"✅ [Bienvenida] Mensaje enviado correctamente para: {member.name}")

    except Exception as e:
        print(f"❌ [Bienvenida] Error crítico en bienvenida: {e}")


# ==================== ENCENDER EL BOT ====================
TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)
