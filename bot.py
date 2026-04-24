import discord
from discord.ext import commands
from discord import app_commands
import re
import json
import os
import asyncio
from datetime import datetime, timezone
 
# ─── CONFIG ───────────────────────────────────────────────────────────────────
CART_CHANNEL_NAME    = "cartbot"
CLAIM_CHANNEL_NAME   = "🎟️-wts-carts"
TICKET_CATEGORY_NAME = "Tickets"
ADMIN_ROLE_NAME      = "Admin"
CONFIG_FILE          = "config.json"
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
    return {
        "custom_message": "⚡ Premier arrivé, premier servi ! Clique vite.",
        "pas": "10"
    }
 
def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
 
config = load_config()
 
# ─── PARSER EMBED ─────────────────────────────────────────────────────────────
def parse_expires(value: str) -> int | None:
    """
    Convertit 'dans X minutes', 'il y a X minutes', 'in X minutes' etc.
    en timestamp Unix futur (pour Discord <t:...>).
    Retourne None si non parsable.
    """
    now = int(datetime.now(timezone.utc).timestamp())
    value = value.lower().strip()
 
    # "dans X minutes / heures"
    m = re.search(r"dans\s+(\d+)\s+(minute|heure|seconde)", value)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if "seconde" in unit: return now + n
        if "minute"  in unit: return now + n * 60
        if "heure"   in unit: return now + n * 3600
 
    # "in X minutes / hours"
    m = re.search(r"in\s+(\d+)\s+(minute|hour|second)", value)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if "second" in unit: return now + n
        if "minute" in unit: return now + n * 60
        if "hour"   in unit: return now + n * 3600
 
    # "il y a X minutes" → déjà expiré, on met -1
    if "il y a" in value or "ago" in value:
        return -1
 
    return None
 
def parse_any_embed(embed: discord.Embed) -> dict | None:
    data = {
        "site": None, "event": None, "section": None,
        "seats": None, "row": None, "access": None,
        "price": None, "event_date": None,
        "expires_ts": None, "image_url": None,
    }
 
    # Image depuis thumbnail ou image de l'embed source
    if embed.thumbnail and embed.thumbnail.url:
        data["image_url"] = embed.thumbnail.url
    elif embed.image and embed.image.url:
        data["image_url"] = embed.image.url
 
    for field in embed.fields:
        name  = field.name.strip().lower()
        value = field.value.strip()
        if "site" in name:                               data["site"]       = value
        elif "event" in name and "date" not in name:    data["event"]      = value
        elif "section" in name or "categ" in name:      data["section"]    = value
        elif "seat" in name or "place" in name:         data["seats"]      = value
        elif "row" in name or "rang" in name:           data["row"]        = value
        elif "access" in name:                          data["access"]     = value
        elif "price" in name or "prix" in name:        data["price"]      = value
        elif "date" in name and "event" in name:        data["event_date"] = value
        elif "expire" in name:
            data["expires_ts"] = parse_expires(value)
 
    if not data["event"] and embed.description:
        m = re.search(r"Event[:\s]+(.+)", embed.description, re.IGNORECASE)
        if m:
            data["event"] = m.group(1).strip()
 
    if not any(v for k, v in data.items() if k not in ("expires_ts", "image_url")):
        return None
 
    return data
 
# ─── CONSTRUCTION EMBED CLAIM ─────────────────────────────────────────────────
def build_claim_embed(cart: dict, custom_msg: str, pas: str) -> discord.Embed:
    embed = discord.Embed(
        title="🎟️  Cart disponible",
        description=f"*{custom_msg}*",
        color=0xE8B84B,
    )
 
    if cart.get("event"):
        embed.add_field(
            name="🎤  Événement",
            value=f"### {cart['event']}",
            inline=False
        )
 
    # Ligne 1 : Site + Date concert
    if cart.get("site") or cart.get("event_date"):
        if cart.get("site"):
            embed.add_field(name="🌐  Site",        value=cart["site"],       inline=True)
        if cart.get("event_date"):
            embed.add_field(name="📅  Date concert", value=cart["event_date"], inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
 
    # Catégorie pleine largeur
    if cart.get("section"):
        embed.add_field(name="🏟️  Catégorie", value=f"```{cart['section']}```", inline=False)
 
    # Ligne 2 : Places + Rangée + Prix
    if cart.get("seats"):
        embed.add_field(name="💺  Places",     value=f"`{cart['seats']}`", inline=True)
    if cart.get("row"):
        embed.add_field(name="📍  Rangée",     value=f"`{cart['row']}`",   inline=True)
    if cart.get("price"):
        embed.add_field(name="💶  Prix total", value=f"`{cart['price']}`", inline=True)
 
    # Accès
    if cart.get("access"):
        embed.add_field(name="🚪  Accès", value=cart["access"], inline=False)
 
    # Expiration
    ts = cart.get("expires_ts")
    if ts == -1:
        embed.add_field(name="⏱️  Expiration", value="⚠️ **Cart déjà expiré**", inline=False)
    elif ts:
        embed.add_field(
            name="⏱️  Expiration",
            value=f"<t:{ts}:R>  *(le <t:{ts}:T>)*",
            inline=False
        )
 
    # Séparateur + PAS
    embed.add_field(name="\u200b", value="──────────────────────────", inline=False)
    embed.add_field(
        name="💳  Pay After Success",
        value=f"```{pas} € / ticket```",
        inline=False
    )
 
    # Image du concert
    if cart.get("image_url"):
        embed.set_thumbnail(url=cart["image_url"])
 
    embed.set_footer(text="ShopTesPlaces  •  Clique sur Claim Cart pour ouvrir un ticket")
    embed.timestamp = datetime.now(timezone.utc)
 
    return embed
 
# ─── STOCKAGE DES MESSAGES POUR UPDATE PAS ────────────────────────────────────
# { message_id: cart_dict }
active_carts: dict[int, dict] = {}
 
# ─── VUE BOUTON CLAIM ─────────────────────────────────────────────────────────
class ClaimView(discord.ui.View):
    def __init__(self, cart: dict, msg_id: int = 0):
        super().__init__(timeout=None)
        self.cart   = cart
        self.msg_id = msg_id
 
    @discord.ui.button(label="🎫  Claim Cart", style=discord.ButtonStyle.success, custom_id="claim_cart")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user  = interaction.user
 
        existing = discord.utils.get(
            guild.text_channels,
            name=f"ticket-{user.name.lower().replace(' ', '-')}"
        )
        if existing:
            await interaction.response.send_message(
                f"❌ Tu as déjà un ticket ouvert : {existing.mention}", ephemeral=True
            )
            return
 
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY_NAME)
 
        admin_role = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)
 
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )
 
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name.lower().replace(' ', '-')}",
            category=category,
            overwrites=overwrites,
            topic=f"🎟️ Ticket cart — {user.display_name}"
        )
 
        # PAS courant depuis config
        pas = config.get("pas", "?")
        cart = self.cart
 
        ticket_embed = discord.Embed(
            title=f"🎫  Ticket — {user.display_name}",
            description=(
                f"Bienvenue {user.mention} !\n"
                f"Un admin va te contacter rapidement.\n\n"
                f"Voici le récapitulatif du cart :"
            ),
            color=0x57F287,
        )
        if cart.get("event"):
            ticket_embed.add_field(name="🎤  Événement", value=f"### {cart['event']}", inline=False)
 
        row = []
        if cart.get("event_date"): row.append(f"📅  **Date**\n{cart['event_date']}")
        if cart.get("seats"):      row.append(f"💺  **Places**\n`{cart['seats']}`")
        if cart.get("price"):      row.append(f"💶  **Prix**\n`{cart['price']}`")
        for r in row:
            ticket_embed.add_field(name="\u200b", value=r, inline=True)
 
        if cart.get("section"):
            ticket_embed.add_field(
                name="🏟️  Catégorie", value=f"```{cart['section']}```", inline=False
            )
 
        ticket_embed.add_field(name="\u200b", value="──────────────────────────", inline=False)
        ticket_embed.add_field(
            name="💳  Pay After Success",
            value=f"```{pas} € / ticket```",
            inline=False
        )
 
        if cart.get("image_url"):
            ticket_embed.set_thumbnail(url=cart["image_url"])
 
        ticket_embed.set_footer(text="Ferme le ticket une fois la transaction terminée.")
        ticket_embed.timestamp = datetime.now(timezone.utc)
 
        close_view = CloseView()
        await ticket_channel.send(
            content=f"{user.mention} {admin_role.mention if admin_role else ''}",
            embed=ticket_embed,
            view=close_view
        )
 
        await interaction.response.send_message(
            f"✅ Ton ticket a été créé : {ticket_channel.mention}", ephemeral=True
        )
 
        # Désactive le bouton
        button.disabled = True
        button.label    = f"✅  Claimé par {user.display_name}"
        button.style    = discord.ButtonStyle.secondary
        await interaction.message.edit(view=self)
 
        # Retire du registre actif
        active_carts.pop(interaction.message.id, None)
 
 
# ─── VUE FERMETURE TICKET ─────────────────────────────────────────────────────
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
 
    @discord.ui.button(
        label="🔒  Fermer le ticket",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket"
    )
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Fermeture dans 5 secondes...")
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
    if message.author == bot.user:
        return
 
    if message.channel.name != CART_CHANNEL_NAME:
        await bot.process_commands(message)
        return
 
    for embed in message.embeds:
        cart = parse_any_embed(embed)
        if cart:
            # Recherche du salon claims (supporte les emojis dans le nom)
            claim_channel = None
            for ch in message.guild.text_channels:
                if CLAIM_CHANNEL_NAME.lower() in ch.name.lower():
                    claim_channel = ch
                    break
 
            if not claim_channel:
                print(f"⚠️ Salon '{CLAIM_CHANNEL_NAME}' introuvable !")
                return
 
            claim_embed = build_claim_embed(cart, config["custom_message"], config.get("pas", "?"))
            view        = ClaimView(cart)
            sent        = await claim_channel.send(embed=claim_embed, view=view)
 
            # Enregistre pour update PAS ultérieur
            active_carts[sent.id] = {"cart": cart, "message": sent, "channel_id": claim_channel.id}
            view.msg_id = sent.id
 
            print(f"✅ Cart relayé : {cart.get('event', 'inconnu')}")
            break
 
    await bot.process_commands(message)
 
 
# ─── COMMANDES SLASH ──────────────────────────────────────────────────────────
 
@bot.tree.command(name="setmessage", description="Change le message affiché sur les carts")
@app_commands.describe(message="Le nouveau message")
@app_commands.checks.has_role(ADMIN_ROLE_NAME)
async def setmessage(interaction: discord.Interaction, message: str):
    config["custom_message"] = message
    save_config(config)
    await interaction.response.send_message(
        f"✅ Message mis à jour :\n> *{message}*", ephemeral=True
    )
 
@setmessage.error
async def setmessage_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
 
# ──────────────────────────────────────────────────────────────────────────────
 
@bot.tree.command(
    name="setpas",
    description="Définit le PAS et met à jour TOUS les embeds actifs dans #claims"
)
@app_commands.describe(montant="Montant en € par ticket (ex: 15)")
@app_commands.checks.has_role(ADMIN_ROLE_NAME)
async def setpas(interaction: discord.Interaction, montant: str):
    config["pas"] = montant
    save_config(config)
 
    updated = 0
    for msg_id, data in list(active_carts.items()):
        try:
            channel = interaction.guild.get_channel(data["channel_id"])
            if not channel:
                continue
            msg = await channel.fetch_message(msg_id)
            # Reconstruit l'embed avec le nouveau PAS
            new_embed = build_claim_embed(
                data["cart"], config["custom_message"], montant
            )
            await msg.edit(embed=new_embed)
            updated += 1
        except Exception as e:
            print(f"⚠️ Impossible de mettre à jour le message {msg_id} : {e}")
            active_carts.pop(msg_id, None)
 
    await interaction.response.send_message(
        f"✅ PAS mis à jour : **{montant} € / ticket**\n"
        f"🔄 {updated} embed(s) mis à jour en temps réel.",
        ephemeral=True
    )
 
@setpas.error
async def setpas_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
 
# ──────────────────────────────────────────────────────────────────────────────
 
@bot.tree.command(name="config", description="Affiche la configuration actuelle du bot")
async def view_config(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚙️  Configuration — ShopTesPlaces Bot",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="💬  Message custom",
        value=f"*{config['custom_message']}*",
        inline=False
    )
    embed.add_field(
        name="💳  PAS actuel",
        value=f"```{config.get('pas', '?')} € / ticket```",
        inline=False
    )
    embed.add_field(
        name="🛒  Carts actifs",
        value=f"`{len(active_carts)}` cart(s) en attente de claim",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
 
# ─── LANCEMENT ────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("❌ Variable d'environnement DISCORD_TOKEN manquante !")
 
bot.run(TOKEN)
