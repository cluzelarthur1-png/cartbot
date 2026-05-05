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
ADMIN_ROLE_NAMES     = ["Admin", "owner", "runner"]
CONFIG_FILE          = "config.json"
INVITES_FILE         = "invites.json"
# ──────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
intents.invites         = True

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

# ─── INVITES PERSISTANTES ─────────────────────────────────────────────────────
def load_invites_data():
    if os.path.exists(INVITES_FILE):
        with open(INVITES_FILE, "r") as f:
            return json.load(f)
    # Structure :
    # {
    #   "members": {
    #     "user_id": {
    #       "inviter_id": "...",   # qui l'a invité
    #       "invite_code": "...",
    #       "joined_at": timestamp,
    #       "left": bool,
    #       "fake": bool
    #     }
    #   },
    #   "bonus": {
    #     "user_id": int   # bonus ajoutés manuellement
    #   }
    # }
    return {"members": {}, "bonus": {}}

def save_invites_data():
    with open(INVITES_FILE, "w") as f:
        json.dump(invites_data, f, indent=2)

invites_data = load_invites_data()

# Cache des invitations Discord en mémoire { code: uses }
invite_cache: dict[str, int] = {}

# ─── HELPERS INVITATIONS ──────────────────────────────────────────────────────
def is_fake_account(member: discord.Member) -> bool:
    """Détecte les comptes suspects : bots, comptes très récents, sans avatar."""
    if member.bot:
        return True
    account_age = (datetime.now(timezone.utc) - member.created_at).days
    if account_age < 7:
        return True
    if member.default_avatar and not member.avatar:
        if account_age < 30:
            return True
    return False

def get_invite_stats(user_id: str) -> dict:
    """Calcule les stats d'un inviteur."""
    normal   = 0
    left     = 0
    fake     = 0
    bonus    = invites_data["bonus"].get(user_id, 0)

    for mid, mdata in invites_data["members"].items():
        if str(mdata.get("inviter_id")) != str(user_id):
            continue
        if mdata.get("fake"):
            fake += 1
        elif mdata.get("left"):
            left += 1
        else:
            normal += 1

    total = normal + bonus
    return {"normal": normal, "left": left, "fake": fake, "bonus": bonus, "total": total}

# ─── CHECK RÔLE ADMIN ────────────────────────────────────────────────────────
def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        user_roles = [r.name.lower() for r in interaction.user.roles]
        if any(r.lower() in user_roles for r in ADMIN_ROLE_NAMES):
            return True
        raise app_commands.MissingRole(ADMIN_ROLE_NAMES[0])
    return app_commands.check(predicate)

# ─── PARSER EXPIRATION ────────────────────────────────────────────────────────
def parse_expires(value: str) -> int | None:
    now = int(datetime.now(timezone.utc).timestamp())
    v   = value.strip()
    m = re.search(r"<t:(\d+)(?::[RrtTdDf])?>", v)
    if m:
        ts = int(m.group(1))
        return ts if ts > now else -1
    v = v.lower()
    m = re.search(r"dans\s+(\d+)\s+(minute|heure|seconde)", v)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if "seconde" in unit: return now + n
        if "minute"  in unit: return now + n * 60
        if "heure"   in unit: return now + n * 3600
    m = re.search(r"in\s+(\d+)\s+(minute|hour|second)", v)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if "second" in unit: return now + n
        if "minute" in unit: return now + n * 60
        if "hour"   in unit: return now + n * 3600
    if "il y a" in v or "ago" in v:
        return -1
    return None

# ─── PARSER EMBED ─────────────────────────────────────────────────────────────
def parse_any_embed(embed: discord.Embed) -> dict | None:
    data = {
        "site": None, "event": None, "section": None,
        "seats": None, "row": None, "access": None,
        "price": None, "event_date": None,
        "expires_ts": None, "image_url": None,
    }
    if embed.thumbnail and embed.thumbnail.url:
        data["image_url"] = embed.thumbnail.url
    elif embed.image and embed.image.url:
        data["image_url"] = embed.image.url

    for field in embed.fields:
        name  = field.name.strip().lower()
        value = field.value.strip()
        if "expire" in name:
            data["expires_ts"] = parse_expires(value)
        elif "site" in name:
            data["site"] = value
        elif "event" in name and "date" not in name:
            data["event"] = value
        elif "event date" in name or name == "event date":
            data["event_date"] = value
        elif "section" in name or "categ" in name:
            data["section"] = value
        elif "seat" in name or "place" in name:
            data["seats"] = value
        elif "row" in name or "rang" in name:
            data["row"] = value
        elif "access" in name:
            data["access"] = value
        elif "price" in name or "prix" in name:
            data["price"] = value
        elif "date" in name and not data["event_date"]:
            data["event_date"] = value

    if not data["event"] and embed.description:
        m = re.search(r"Event[:\s]+(.+)", embed.description, re.IGNORECASE)
        if m:
            data["event"] = m.group(1).strip()

    useful_keys = ("site", "event", "section", "seats", "price")
    if not any(data[k] for k in useful_keys):
        return None
    return data

# ─── CONSTRUCTION EMBED CLAIM ─────────────────────────────────────────────────
def build_claim_embed(cart: dict, custom_msg: str, pas: str) -> discord.Embed:
    event_name = cart.get("event", "")
    embed = discord.Embed(
        title="🎟️  Cart disponible",
        description=f"*{custom_msg}*",
        color=0x2B2D31,
    )
    if event_name:
        embed.add_field(name="🎤  Événement", value=f"**{event_name}**", inline=False)
    if cart.get("site"):
        embed.add_field(name="🌐  Site", value=cart["site"], inline=True)
    if cart.get("event_date"):
        embed.add_field(name="📅  Date", value=cart["event_date"], inline=True)
    if cart.get("site") and cart.get("event_date"):
        embed.add_field(name="\u200b", value="\u200b", inline=True)
    if cart.get("section"):
        embed.add_field(name="🏟️  Catégorie", value=f"`{cart['section']}`", inline=False)
    if cart.get("seats"):
        embed.add_field(name="💺  Places", value=cart["seats"], inline=True)
    if cart.get("row"):
        embed.add_field(name="📍  Rangée", value=cart["row"], inline=True)
    if cart.get("price"):
        embed.add_field(name="💶  Prix", value=cart["price"], inline=True)
    if cart.get("access"):
        embed.add_field(name="🚪  Accès", value=cart["access"], inline=True)
    ts = cart.get("expires_ts")
    if ts == -1:
        embed.add_field(name="⏳  Expire", value="~~expiré~~", inline=True)
    elif ts:
        embed.add_field(name="⏳  Expire", value=f"<t:{ts}:R>", inline=True)
    embed.add_field(name="💳  Pay After Success", value=f"`{pas} € / ticket`", inline=False)
    embed.add_field(
        name="\u200b",
        value="-# ⚠️ En cliquant sur Claim Cart, vous certifiez disposer des extensions requises et vous engagez à honorer le PAS.",
        inline=False
    )
    if cart.get("image_url"):
        embed.set_thumbnail(url=cart["image_url"])
    embed.set_footer(text="ShopTesPlaces")
    embed.timestamp = datetime.now(timezone.utc)
    return embed

# ─── STOCKAGE CARTS ACTIFS ────────────────────────────────────────────────────
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
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for rname in ADMIN_ROLE_NAMES:
            role = discord.utils.get(guild.roles, name=rname)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name.lower().replace(' ', '-')}",
            category=category,
            overwrites=overwrites,
            topic=f"🎟️ Ticket cart — {user.display_name}"
        )
        pas  = config.get("pas", "?")
        cart = self.cart
        ticket_embed = discord.Embed(
            title=f"🎫  Ticket — {user.display_name}",
            description=f"Bienvenue {user.mention} !\nUn admin va te contacter rapidement.\n\nVoici le récapitulatif du cart :",
            color=0x57F287,
        )
        if cart.get("event"):
            ticket_embed.add_field(name="🎤  Événement", value=f"**{cart['event']}**", inline=False)
        row = []
        if cart.get("event_date"): row.append(("📅  Date",   cart["event_date"]))
        if cart.get("seats"):      row.append(("💺  Places", f"`{cart['seats']}`"))
        if cart.get("price"):      row.append(("💶  Prix",   f"`{cart['price']}`"))
        for n, v in row:
            ticket_embed.add_field(name=n, value=v, inline=True)
        if cart.get("section"):
            ticket_embed.add_field(name="🏟️  Catégorie", value=f"```{cart['section']}```", inline=False)
        ticket_embed.add_field(name="\u200b", value="──────────────────────────", inline=False)
        ticket_embed.add_field(name="💳  Pay After Success", value=f"```{pas} € / ticket```", inline=False)
        if cart.get("image_url"):
            ticket_embed.set_thumbnail(url=cart["image_url"])
        ticket_embed.set_footer(text="Ferme le ticket une fois la transaction terminée.")
        ticket_embed.timestamp = datetime.now(timezone.utc)
        mentions = " ".join(
            role.mention
            for rname in ADMIN_ROLE_NAMES
            if (role := discord.utils.get(guild.roles, name=rname))
        )
        close_view = CloseView()
        await ticket_channel.send(content=f"{user.mention} {mentions}", embed=ticket_embed, view=close_view)
        await interaction.response.send_message(f"✅ Ton ticket a été créé : {ticket_channel.mention}", ephemeral=True)
        button.disabled = True
        button.label    = f"✅  Claimed by {user.display_name}"
        button.style    = discord.ButtonStyle.secondary
        await interaction.message.edit(view=self)
        active_carts.pop(interaction.message.id, None)

# ─── VUE FERMETURE TICKET ─────────────────────────────────────────────────────
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒  Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Fermeture dans 5 secondes...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

# ─── EVENTS CART ──────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    # Cache les invitations de tous les serveurs
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            for inv in invites:
                invite_cache[inv.code] = inv.uses
        except Exception as e:
            print(f"⚠️ Impossible de charger les invites de {guild.name} : {e}")
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
            claim_channel = None
            for ch in message.guild.text_channels:
                if "wts carts" in ch.name.lower() or CLAIM_CHANNEL_NAME.lower() in ch.name.lower():
                    claim_channel = ch
                    break
            if not claim_channel:
                print(f"⚠️ Salon '{CLAIM_CHANNEL_NAME}' introuvable !")
                return
            claim_embed = build_claim_embed(cart, config["custom_message"], config.get("pas", "?"))
            view        = ClaimView(cart)
            sent        = await claim_channel.send(embed=claim_embed, view=view)
            active_carts[sent.id] = {"cart": cart, "channel_id": claim_channel.id}
            view.msg_id = sent.id
            print(f"✅ Cart relayé : {cart.get('event', 'inconnu')} | expires_ts={cart.get('expires_ts')}")
            break
    await bot.process_commands(message)

# ─── EVENTS INVITATIONS ───────────────────────────────────────────────────────
@bot.event
async def on_invite_create(invite: discord.Invite):
    invite_cache[invite.code] = invite.uses or 0

@bot.event
async def on_invite_delete(invite: discord.Invite):
    invite_cache.pop(invite.code, None)

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    try:
        new_invites = await guild.invites()
    except:
        return

    used_code    = None
    inviter      = None

    for inv in new_invites:
        cached_uses = invite_cache.get(inv.code, 0)
        if inv.uses > cached_uses:
            used_code = inv.code
            inviter   = inv.inviter
            break

    # Met à jour le cache
    for inv in new_invites:
        invite_cache[inv.code] = inv.uses

    fake = is_fake_account(member)

    invites_data["members"][str(member.id)] = {
        "inviter_id":   str(inviter.id) if inviter else None,
        "invite_code":  used_code,
        "joined_at":    int(datetime.now(timezone.utc).timestamp()),
        "left":         False,
        "fake":         fake,
        "username":     str(member),
    }
    save_invites_data()
    print(f"➕ {member} rejoint | invité par {inviter} | fake={fake} | code={used_code}")

@bot.event
async def on_member_remove(member: discord.Member):
    uid = str(member.id)
    if uid in invites_data["members"]:
        invites_data["members"][uid]["left"] = True
        save_invites_data()
    print(f"➖ {member} a quitté le serveur")

# ─── COMMANDES CART ───────────────────────────────────────────────────────────
@bot.tree.command(name="setmessage", description="Change le message affiché sur les carts")
@app_commands.describe(message="Le nouveau message")
@is_admin()
async def setmessage(interaction: discord.Interaction, message: str):
    config["custom_message"] = message
    save_config(config)
    await interaction.response.send_message(f"✅ Message mis à jour :\n> *{message}*", ephemeral=True)

@setmessage.error
async def setmessage_error(interaction: discord.Interaction, error):
    await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)

@bot.tree.command(name="setpas", description="Définit le PAS et met à jour tous les embeds actifs")
@app_commands.describe(montant="Montant en € par ticket (ex: 15)")
@is_admin()
async def setpas(interaction: discord.Interaction, montant: str):
    config["pas"] = montant
    save_config(config)
    updated = 0
    for msg_id, data in list(active_carts.items()):
        try:
            channel = interaction.guild.get_channel(data["channel_id"])
            if not channel: continue
            msg = await channel.fetch_message(msg_id)
            new_embed = build_claim_embed(data["cart"], config["custom_message"], montant)
            await msg.edit(embed=new_embed)
            updated += 1
        except Exception as e:
            print(f"⚠️ Impossible de MAJ le message {msg_id} : {e}")
            active_carts.pop(msg_id, None)
    await interaction.response.send_message(
        f"✅ PAS mis à jour : **{montant} € / ticket**\n🔄 {updated} embed(s) mis à jour en temps réel.",
        ephemeral=True
    )

@setpas.error
async def setpas_error(interaction: discord.Interaction, error):
    await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)

@bot.tree.command(name="config", description="Affiche la configuration actuelle du bot")
async def view_config(interaction: discord.Interaction):
    embed = discord.Embed(title="⚙️  Configuration — ShopTesPlaces Bot", color=0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="💬  Message custom", value=f"*{config['custom_message']}*",               inline=False)
    embed.add_field(name="💳  PAS actuel",      value=f"```{config.get('pas', '?')} € / ticket```", inline=False)
    embed.add_field(name="🛒  Carts actifs",    value=f"`{len(active_carts)}` cart(s) en attente",  inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─── COMMANDES INVITATIONS ────────────────────────────────────────────────────

@bot.tree.command(name="invites", description="Voir les invitations d'un membre")
@app_commands.describe(membre="Le membre à inspecter (laisse vide pour toi-même)")
async def invites_cmd(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre or interaction.user
    uid    = str(target.id)
    stats  = get_invite_stats(uid)

    embed = discord.Embed(
        title=f"📨  Invitations — {target.display_name}",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="✅  Valides",   value=f"`{stats['normal']}`", inline=True)
    embed.add_field(name="🚪  Partis",    value=f"`{stats['left']}`",   inline=True)
    embed.add_field(name="🤖  Fakes",     value=f"`{stats['fake']}`",   inline=True)
    embed.add_field(name="🎁  Bonus",     value=f"`{stats['bonus']}`",  inline=True)
    embed.add_field(
        name="🏆  Total",
        value=f"**`{stats['total']}`**  *(valides + bonus)*",
        inline=True
    )

    # Qui a invité ce membre ?
    mdata = invites_data["members"].get(uid)
    if mdata and mdata.get("inviter_id"):
        inviter = interaction.guild.get_member(int(mdata["inviter_id"]))
        inviter_str = inviter.mention if inviter else f"ID {mdata['inviter_id']}"
        embed.add_field(name="👤  Invité par", value=inviter_str, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ──────────────────────────────────────────────────────────────────────────────

@bot.tree.command(name="leaderboard", description="Classement des invitations du serveur")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)

    scores: dict[str, int] = {}
    for uid in set(
        d["inviter_id"]
        for d in invites_data["members"].values()
        if d.get("inviter_id")
    ):
        scores[uid] = get_invite_stats(uid)["total"]

    # Ajoute les gens qui ont seulement des bonus
    for uid in invites_data.get("bonus", {}):
        if uid not in scores:
            scores[uid] = get_invite_stats(uid)["total"]

    # Trie par total décroissant
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="🏆  Leaderboard des invitations",
        description="*Seules les invitations valides + bonus sont comptées*",
        color=0xE8B84B,
        timestamp=datetime.now(timezone.utc)
    )

    medals = ["🥇", "🥈", "🥉"]
    lines  = []

    for i, (uid, total) in enumerate(sorted_scores[:15]):
        member = interaction.guild.get_member(int(uid))
        name   = member.display_name if member else f"Inconnu ({uid})"
        stats  = get_invite_stats(uid)
        medal  = medals[i] if i < 3 else f"`#{i+1}`"
        lines.append(
            f"{medal}  **{name}** — "
            f"**{total}** total  "
            f"*(✅ {stats['normal']} · 🚪 {stats['left']} · 🤖 {stats['fake']} · 🎁 {stats['bonus']})*"
        )

    embed.description = "\n".join(lines) if lines else "*Aucune invitation enregistrée.*"
    embed.set_footer(text=f"{len(sorted_scores)} membre(s) avec des invitations")
    await interaction.followup.send(embed=embed)

# ──────────────────────────────────────────────────────────────────────────────

@bot.tree.command(name="addbonus", description="Ajouter des invitations bonus à un membre")
@app_commands.describe(membre="Le membre", nombre="Nombre d'invitations bonus à ajouter")
@is_admin()
async def addbonus(interaction: discord.Interaction, membre: discord.Member, nombre: int):
    uid = str(membre.id)
    invites_data["bonus"][uid] = invites_data["bonus"].get(uid, 0) + nombre
    save_invites_data()
    total = invites_data["bonus"][uid]
    await interaction.response.send_message(
        f"🎁 **+{nombre}** bonus ajouté à {membre.mention}\n"
        f"Total bonus : **{total}**",
        ephemeral=True
    )

@addbonus.error
async def addbonus_error(interaction: discord.Interaction, error):
    await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)

# ──────────────────────────────────────────────────────────────────────────────

@bot.tree.command(name="setbonus", description="Définir le nombre exact d'invitations bonus d'un membre")
@app_commands.describe(membre="Le membre", nombre="Nombre total de bonus")
@is_admin()
async def setbonus(interaction: discord.Interaction, membre: discord.Member, nombre: int):
    uid = str(membre.id)
    invites_data["bonus"][uid] = nombre
    save_invites_data()
    await interaction.response.send_message(
        f"🎁 Bonus de {membre.mention} défini à **{nombre}**",
        ephemeral=True
    )

@setbonus.error
async def setbonus_error(interaction: discord.Interaction, error):
    await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)

# ──────────────────────────────────────────────────────────────────────────────

@bot.tree.command(name="resetinvites", description="Remettre à zéro les invitations d'un membre")
@app_commands.describe(membre="Le membre à réinitialiser")
@is_admin()
async def resetinvites(interaction: discord.Interaction, membre: discord.Member):
    uid = str(membre.id)
    # Supprime toutes ses invitations enregistrées
    to_delete = [mid for mid, d in invites_data["members"].items() if d.get("inviter_id") == uid]
    for mid in to_delete:
        del invites_data["members"][mid]
    invites_data["bonus"].pop(uid, None)
    save_invites_data()
    await interaction.response.send_message(
        f"🔄 Invitations de {membre.mention} remises à zéro.", ephemeral=True
    )

@resetinvites.error
async def resetinvites_error(interaction: discord.Interaction, error):
    await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)

# ─── LANCEMENT ────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("❌ Variable d'environnement DISCORD_TOKEN manquante !")

bot.run(TOKEN)
