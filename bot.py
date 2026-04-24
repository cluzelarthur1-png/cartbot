import discord
from discord.ext import commands
from discord import app_commands
import re
import json
import os

# ─── CONFIG ───────────────────────────────────────────────────────────────────
CART_CHANNEL_NAME   = "carts"          # salon où KalysBot poste
CLAIM_CHANNEL_NAME  = "claims"         # salon où ton bot reposte
TICKET_CATEGORY_NAME = "tickets"       # catégorie pour les tickets
KALYSBOT_NAME       = "KalysBot"       # nom exact du bot à écouter
ADMIN_ROLE_NAME     = "Admin"          # nom du rôle admin sur ton serveur
CONFIG_FILE         = "config.json"    # fichier de config persistant
# ──────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ─── CONFIG PERSISTANTE ───────────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"custom_message": "⚡ Premier arrivé, premier servi ! Clique vite."}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

config = load_config()

# ─── PARSER EMBED KALYSBOT ────────────────────────────────────────────────────
def parse_kalysbot_embed(embed: discord.Embed) -> dict | None:
    """Extrait les infos d'un embed KalysBot Cart Ready."""
    if not embed.title or "Cart Ready" not in embed.title:
        return None

    data = {
        "site": None,
        "event": None,
        "section": None,
        "seats": None,
        "row": None,
        "access": None,
        "price": None,
        "event_date": None,
    }

    for field in embed.fields:
        name  = field.name.strip().lower()
        value = field.value.strip()

        if name == "site":
            data["site"] = value
        elif name == "event":
            data["event"] = value
        elif name == "section":
            data["section"] = value
        elif name == "seats":
            data["seats"] = value
        elif name == "row":
            data["row"] = value
        elif name == "access":
            data["access"] = value
        elif name == "price":
            data["price"] = value
        elif name == "event date":
            data["event_date"] = value

    # Fallback : parse depuis la description si fields vides
    if not data["event"] and embed.description:
        match = re.search(r"Event[:\s]+(.+)", embed.description, re.IGNORECASE)
        if match:
            data["event"] = match.group(1).strip()

    return data

# ─── EMBED CLAIM ──────────────────────────────────────────────────────────────
def build_claim_embed(cart: dict, custom_msg: str) -> discord.Embed:
    embed = discord.Embed(
        title="🛒 Cart disponible !",
        color=0x5865F2,
    )
    if cart.get("site"):
        embed.add_field(name="🌐 Site",        value=cart["site"],       inline=True)
    if cart.get("event"):
        embed.add_field(name="🎤 Événement",   value=cart["event"],      inline=True)
    if cart.get("event_date"):
        embed.add_field(name="📅 Date",         value=cart["event_date"], inline=True)
    if cart.get("section"):
        embed.add_field(name="🏟️ Catégorie",   value=cart["section"],    inline=False)
    if cart.get("seats"):
        embed.add_field(name="💺 Places",       value=cart["seats"],      inline=True)
    if cart.get("row"):
        embed.add_field(name="📍 Rangée",       value=cart["row"],        inline=True)
    if cart.get("price"):
        embed.add_field(name="💶 Prix",         value=cart["price"],      inline=True)
    if cart.get("access"):
        embed.add_field(name="🚪 Accès",        value=cart["access"],     inline=True)

    embed.add_field(name="\u200b", value=f"_{custom_msg}_", inline=False)
    embed.set_footer(text="Clique sur le bouton pour ouvrir un ticket")
    return embed

# ─── VUE BOUTON CLAIM ─────────────────────────────────────────────────────────
class ClaimView(discord.ui.View):
    def __init__(self, cart: dict):
        super().__init__(timeout=None)  # persistent
        self.cart = cart

    @discord.ui.button(label="🎫 Claim Cart", style=discord.ButtonStyle.success, custom_id="claim_cart")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user  = interaction.user

        # Vérifie si un ticket existe déjà pour cet user
        existing = discord.utils.get(
            guild.text_channels,
            name=f"ticket-{user.name.lower().replace(' ', '-')}"
        )
        if existing:
            await interaction.response.send_message(
                f"❌ Tu as déjà un ticket ouvert : {existing.mention}", ephemeral=True
            )
            return

        # Catégorie tickets
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        # Rôle admin
        admin_role = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)

        # Permissions du salon ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name.lower().replace(' ', '-')}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket cart pour {user.display_name}"
        )

        # Message dans le ticket
        ticket_embed = discord.Embed(
            title=f"🎫 Ticket de {user.display_name}",
            description=f"Bonjour {user.mention} ! Voici les détails du cart que tu as claim.",
            color=0x57F287,
        )
        cart = self.cart
        if cart.get("event"):
            ticket_embed.add_field(name="🎤 Événement",  value=cart["event"],      inline=True)
        if cart.get("event_date"):
            ticket_embed.add_field(name="📅 Date",        value=cart["event_date"], inline=True)
        if cart.get("section"):
            ticket_embed.add_field(name="🏟️ Catégorie",  value=cart["section"],    inline=False)
        if cart.get("seats"):
            ticket_embed.add_field(name="💺 Places",      value=cart["seats"],      inline=True)
        if cart.get("price"):
            ticket_embed.add_field(name="💶 Prix",        value=cart["price"],      inline=True)
        if cart.get("site"):
            ticket_embed.add_field(name="🌐 Site",        value=cart["site"],       inline=True)
        ticket_embed.set_footer(text="Un admin va te contacter rapidement.")

        close_view = CloseView()
        await ticket_channel.send(
            content=f"{user.mention} {admin_role.mention if admin_role else ''}",
            embed=ticket_embed,
            view=close_view
        )

        await interaction.response.send_message(
            f"✅ Ton ticket a été créé : {ticket_channel.mention}", ephemeral=True
        )

        # Désactive le bouton après claim
        button.disabled = True
        button.label = f"✅ Claimé par {user.display_name}"
        button.style = discord.ButtonStyle.secondary
        await interaction.message.edit(view=self)


# ─── VUE FERMETURE TICKET ─────────────────────────────────────────────────────
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()


# ─── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commande(s) slash synchronisée(s)")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")

@bot.event
async def on_message(message: discord.Message):
    # Ignore ses propres messages
    if message.author == bot.user:
        return

    # Écoute seulement dans #carts
    if message.channel.name != CART_CHANNEL_NAME:
        await bot.process_commands(message)
        return

    # Écoute seulement KalysBot
    if message.author.name != KALYSBOT_NAME:
        await bot.process_commands(message)
        return

    # Parse les embeds
    for embed in message.embeds:
        cart = parse_kalysbot_embed(embed)
        if cart:
            claim_channel = discord.utils.get(message.guild.text_channels, name=CLAIM_CHANNEL_NAME)
            if not claim_channel:
                print(f"⚠️ Salon #{CLAIM_CHANNEL_NAME} introuvable !")
                return

            claim_embed = build_claim_embed(cart, config["custom_message"])
            view = ClaimView(cart)
            await claim_channel.send(embed=claim_embed, view=view)
            print(f"✅ Cart relayé pour {cart.get('event', 'inconnu')}")
            break

    await bot.process_commands(message)

# ─── COMMANDE /setmessage ─────────────────────────────────────────────────────
@bot.tree.command(name="setmessage", description="Change le message personnalisé affiché sur les carts")
@app_commands.describe(message="Le nouveau message à afficher sous les carts")
@app_commands.checks.has_role(ADMIN_ROLE_NAME)
async def setmessage(interaction: discord.Interaction, message: str):
    config["custom_message"] = message
    save_config(config)
    await interaction.response.send_message(
        f"✅ Message mis à jour :\n> _{message}_", ephemeral=True
    )

@setmessage.error
async def setmessage_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("❌ Tu n'as pas la permission.", ephemeral=True)

# ─── COMMANDE /viewmessage ────────────────────────────────────────────────────
@bot.tree.command(name="viewmessage", description="Affiche le message personnalisé actuel")
async def viewmessage(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"💬 Message actuel :\n> _{config['custom_message']}_", ephemeral=True
    )

# ─── LANCEMENT ────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("❌ Variable d'environnement DISCORD_TOKEN manquante !")

bot.run(TOKEN)
