import os
import random
import asyncio
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord import app_commands

# ==================== TRUCO PARA RENDER GRATIS (FLASK) ====================
# Creamos un servidor web idéntico a Express para engañar a Render y abrir el puerto 10000
app = Flask('')

@app.route('/')
def home():
    return "Bot Online y Servidor Activo en Python"

def run_web_server():
    # Render asigna automáticamente un puerto en la variable PORT, si no usa el 3000
    puerto = int(os.environ.get("PORT", 3000))
    print(f"[Flask] Puerto detectado con éxito: {puerto}")
    app.run(host='0.0.0.0', port=puerto)

# Iniciamos el servidor web en un hilo secundario para que no congele al bot de Discord
def mantener_vivo():
    t = Thread(target=run_web_server)
    t.start()

mantener_vivo()
# ==========================================================================


# ==================== CONFIGURACIÓN DE DISCORD ====================
# Activamos los Intents Privilegiados obligatorios para leer miembros y reacciones
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

# Inicializamos el cliente del Bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Variable global en memoria para almacenar el sorteo activo
sorteo_activo = None

@bot.event
async def on_ready():
    print(f"🚀 ¡Bot conectado correctamente como {bot.user}!")
    try:
        # Sincroniza los comandos de barra (/) con la API de Discord al encender
        sincronizados = await bot.tree.sync()
        print(f"✅ [Comandos] ¡Comandos globales ({len(sincronizados)}) cargados exitosamente!")
    except Exception as e:
        print(f"❌ [Comandos] Error al registrar los comandos: {e}")


# ==================== MANEJADOR DE COMANDOS DE BARRA (/) ====================

# --- COMANDO: DECIR ---
@bot.tree.command(name="decir", description="Hace que el bot diga un mensaje")
@app_commands.describe(mensaje="Mensaje que enviará el bot")
async def decir(interaction: discord.Interaction, mensaje: str):
    # Respondemos de forma oculta (ephemeral) para que Discord no dé error de interacción
    await interaction.response.send_message("✅ Mensaje enviado con éxito.", ephemeral=True)
    # Enviamos el mensaje real al canal de texto
    await interaction.channel.send(mensaje)


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

    # Verificamos si el usuario es administrador
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
        return

    # Creamos el diseño del cuadro (Embed) azul
    embed = discord.Embed(
        title="🎁 ¡NUEVO SORTEO ACTIVO! 🎁",
        description=f"{mensaje}\n\nPara entrar, simplemente presiona el botón de **🎉** aquí abajo.",
        color=discord.Color.from_rgb(30, 144, 255) # Azul Dodger
    )
    embed.add_field(name="🏆 Premio", value=f"**{objeto}**", inline=True)
    embed.add_field(name="👥 Ganadores", value=f"**{ganadores}**", inline=True)
    embed.set_footer(text="NombaX Sorteos • ¡Buena suerte a todos!")

    if imagen:
        embed.set_image(url=imagen.url)

    await interaction.response.send_message("📦 Generando sorteo...", ephemeral=True)
    
    # Enviamos el embed al canal y le añadimos la reacción 🎉
    mensaje_sorteo = await interaction.channel.send(embed=embed)
    await mensaje_sorteo.add_reaction("🎉")

    # Guardamos los datos del sorteo en la memoria global
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

    # Deferimos la respuesta para indicarle a Discord que procesaremos datos pesados
    await interaction.response.defer()

    try:
        # Buscamos el canal y el mensaje original del sorteo
        canal = bot.get_channel(sorteo_activo["canal_id"])
        mensaje_original = await canal.fetch_message(sorteo_activo["mensaje_id"])
        
        # Obtenemos los usuarios que reaccionaron con 🎉
        reaccion = discord.utils.get(mensaje_original.reactions, emoji="🎉")
        participantes = []
        
        if reaccion:
            async for usuario in reaccion.users():
                if not usuario.bot: # Filtramos para que no entren bots al sorteo
                    participantes.append(usuario)

        if not participantes:
            await interaction.followup.send("❌ El sorteo no puede realizarse porque nadie ha reaccionado con 🎉 todavía.")
            return

        await interaction.followup.send("📦 **|** _Barajando la lista de participantes y seleccionando boletos de forma segura..._")
        
        # Esperamos 2.5 segundos para simular suspenso
        await asyncio.sleep(2.5)

        num_ganadores = sorteo_activo["ganadores_requeridos"]
        # Evitamos que pida más ganadores de la cantidad total de participantes reales
        total_ganadores_reales = min(num_ganadores, len(participantes))

        # Seleccionamos ganadores al azar sin repetir
        ganadores_elegidos = random.sample(participantes, total_ganadores_reales)

        # Construimos el texto de mención en lista
        texto_menciones = "\n".join([f"{i+1}. {g.mention} (**{g.name}**)" for i, g in enumerate(ganadores_elegidos)])
        menciones_simples = " ".join([g.mention for g in ganadores_elegidos])

        # Diseñamos el embed de resultados (Verde)
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

        # Enviamos los resultados al canal del sorteo
        await interaction.channel.send(content=f"¡Sorteo finalizado! 🏆 {menciones_simples}", embed=embed_ganador)

        # Anuncio automático en el canal 〔👑〕news
        canal_news = discord.utils.get(interaction.guild.text_channels, name="〔👑〕news")
        if canal_news:
            await canal_news.send(
                content=f"📢 **¡Atención Comunidad!** Felicidades a {menciones_simples} por haber ganado el sorteo de **{sorteo_activo['premio']}** 👑🎉"
            )

        # Reseteamos la variable del sorteo para permitir uno nuevo
        sorteo_activo = None

    except Exception as e:
        print(f"Error procesando sorteo: {e}")
        await interaction.followup.send("❌ Hubo un problema técnico al intentar procesar el sorteo.")


# ==================== EVENTO DE BIENVENIDA AUTOMÁTICO ====================
@bot.event
async def on_member_join(member):
    try:
        # Buscamos el canal de bienvenidas directamente por su nombre exacto
        canal_bienvenida = discord.utils.get(member.guild.text_channels, name="〔💬〕general")
        if not canal_bienvenida:
            print("❌ [Bienvenida] No se encontró ningún canal llamado 〔💬〕general")
            return

        # Buscamos los canales de roles y reglas por sus nombres para mencionarlos dinámicamente
        canal_roles = discord.utils.get(member.guild.text_channels, name="roles")
        canal_reglas = discord.utils.get(member.guild.text_channels, name="reglas")

        # Si el canal existe sacamos su etiqueta interactiva <#ID>, si no, dejamos el texto plano #nombre
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


