import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
import logging
import random
import string
import pytz
from werkzeug.datastructures import auth

# Zeitzone konfigurieren
GERMANY_TZ = pytz.timezone('Europe/Berlin')

def get_now():
    """Gibt die aktuelle Zeit in der deutschen Zeitzone zurück"""
    return datetime.now(GERMANY_TZ)

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('insurance_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('InsuranceBot')

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Datenspeicherung
DATA_FILE = "insurance_data.json"
CONFIG_FILE = "bot_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "log_channel_id": None,
        "kundenkontakt_category_id": None,
        "schadensmeldung_category_id": None,
        "auszahlung_channel_id": None
    }

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

config = load_config()

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            logger.info("Daten erfolgreich geladen")
            return json.load(f)
    logger.warning("Keine Datendatei gefunden, erstelle neue Datenstruktur")
    return {"customers": {}, "invoices": {}, "logs": [], "schadensmeldungen": {}}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    global _last_data_hash
    _last_data_hash = _get_data_hash()
    logger.info("Daten erfolgreich gespeichert")

def _get_data_hash() -> str:
    """Gibt einen Hash des aktuellen Dateiinhalts zurück"""
    import hashlib
    if not os.path.exists(DATA_FILE):
        return ""
    with open(DATA_FILE, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

_last_data_hash: str = ""

def generate_customer_id():
    prefix = "VN"
    year = get_now().strftime("%y")
    random_part = ''.join(random.choices(string.digits, k=6))
    return f"{prefix}-{year}{random_part}"

def generate_invoice_id():
    prefix = "RE"
    year = get_now().strftime("%y")
    month = get_now().strftime("%m")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{year}{month}-{random_part}"

def generate_schaden_id():
    prefix = "SM"
    year = get_now().strftime("%y")
    month = get_now().strftime("%m")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{year}{month}-{random_part}"

def generate_auszahlung_id():
    prefix = "AZ"
    year = get_now().strftime("%y")
    month = get_now().strftime("%m")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{year}{month}-{random_part}"

async def send_to_log_channel(guild, embed):
    """Sendet eine Nachricht in den Log-Channel"""
    if config["log_channel_id"]:
        try:
            log_channel = guild.get_channel(config["log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)
                logger.info(f"Log an Channel {config['log_channel_id']} gesendet")
        except Exception as e:
            logger.error(f"Fehler beim Senden an Log-Channel: {e}")

def create_backup():
    """Erstellt ein Backup der aktuellen Datendatei"""
    try:
        if not os.path.exists("backups"):
            os.makedirs("backups")
        timestamp = get_now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"backups/backup_{timestamp}.json"
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data_to_backup = json.load(f)
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_backup, f, indent=4, ensure_ascii=False)
        return backup_path
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des Backups: {e}")
        return None

def add_log_entry(action, user_id, details):
    log_entry = {
        "timestamp": get_now().isoformat(),
        "action": action,
        "user_id": user_id,
        "details": details
    }
    data['logs'].append(log_entry)
    save_data(data)
    logger.info(f"Log erstellt: {action} von User {user_id}")

data = load_data()

# Versicherungstypen
INSURANCE_TYPES = {
    "Krankenversicherung (Privat)": {
        "price": 10000.00,
        "role": "Krankenversicherung (Privat)",
        "auszahlung_limit": 30000.00
    },
    "Haftpflichtversicherung": {
        "price": 10000.00,
        "role": "Haftpflichtversicherung",
        "auszahlung_limit": 30000.00
    },
    "Hausratversicherung": {
        "price": 10000.00,
        "role": "Hausratversicherung",
        "auszahlung_limit": 30000.00
    },
    "Kfz-Versicherung": {
        "price": 7500.00,
        "role": "Kfz-Versicherung",
        "auszahlung_limit": 20000.00
    },
    "Rechtsschutzversicherung": {
        "price": 5000.00,
        "role": "Rechtsschutzversicherung",
        "auszahlung_limit": 15000.00
    },
    "Berufsunfähigkeitsversicherung": {
        "price": 10000.00,
        "role": "Berufsunfähigkeitsversicherung",
        "auszahlung_limit": 30000.00
    },
    "Bußgeldversicherung": {
        "price": 10000.00,
        "role": "Bußgeldversicherung",
        "auszahlung_limit": 30000.00
    }
}

# Farbschema
COLOR_PRIMARY = 0x2C3E50
COLOR_SUCCESS = 0x27AE60
COLOR_WARNING = 0xE67E22
COLOR_ERROR = 0xC0392B
COLOR_INFO = 0x3498DB
COLOR_DAMAGE = 0xE74C3C

# Rollen-IDs
MITARBEITER_ROLE_ID = 1408800823571513537
LEITUNGSEBENE_ROLE_ID = 1408797319134187601
FIRMENKONTOROLLE_ROLE_ID = 1474047313025433684

def is_mitarbeiter(interaction: discord.Interaction) -> bool:
    mitarbeiter_role = interaction.guild.get_role(MITARBEITER_ROLE_ID)
    leitungsebene_role = interaction.guild.get_role(LEITUNGSEBENE_ROLE_ID)
    return (mitarbeiter_role and mitarbeiter_role in interaction.user.roles) or \
    (leitungsebene_role and leitungsebene_role in interaction.user.roles)

def is_leitungsebene(interaction: discord.Interaction) -> bool:
    leitungsebene_role = interaction.guild.get_role(LEITUNGSEBENE_ROLE_ID)
    return leitungsebene_role and leitungsebene_role in interaction.user.roles

def is_firmenkontorolle(interaction: discord.Interaction) -> bool:
    firmenkontorolle_role = interaction.guild.get_role(FIRMENKONTOROLLE_ROLE_ID)
    return firmenkontorolle_role and firmenkontorolle_role in interaction.user.roles

def get_verfuegbares_guthaben(customer_id: str, versicherung: str) -> float:
    limit = INSURANCE_TYPES.get(versicherung, {}).get("auszahlung_limit", 0.0)
    customer = data['customers'].get(customer_id, {})
    auszahlungen = customer.get("auszahlungen", {})
    bereits_ausgezahlt = auszahlungen.get(versicherung, 0.0)
    return max(0.0, limit - bereits_ausgezahlt)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} erfolgreich gestartet')
    global _last_data_hash
    _last_data_hash = _get_data_hash()
    bot.add_view(KundenkontaktView())
    bot.add_view(SchadensmeldungView())
    bot.add_view(TicketCloseView(0, ""))
    bot.add_view(AuszahlungActionView("dummy", "dummy", 0))
    logger.info("Persistente Views registriert - Alle Buttons funktionieren nun")
    try:
        synced = await bot.tree.sync()
        logger.info(f'{len(synced)} Slash Commands synchronisiert')
        check_invoices.start()
        auto_backup.start()
    except Exception as e:
        logger.error(f'Fehler beim Synchronisieren der Commands: {e}')

@bot.tree.command(name="backup", description="Erstellt ein Backup beider Datenbanken und sendet sie als ZIP")
async def backup_download(interaction: discord.Interaction):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann die Backups herunterladen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        import zipfile
        import io
        data_backup = create_backup()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if os.path.exists(DATA_FILE):
                zip_file.write(DATA_FILE, arcname="insurance_data.json")
            if os.path.exists(CONFIG_FILE):
                zip_file.write(CONFIG_FILE, arcname="bot_config.json")
        zip_buffer.seek(0)
        file = discord.File(zip_buffer, filename=f"insurance_full_backup_{get_now().strftime('%Y%m%d_%H%M%S')}.zip")
        await interaction.followup.send("<:2141file:1473009449412071484> Vollständiger Datenbank-Export (Daten & Konfiguration)", file=file, ephemeral=True)
    except Exception as e:
        logger.error(f"Backup-ZIP-Fehler: {e}")
        await interaction.followup.send(f"<:3518crossmark:1473009455473098894> Fehler beim Erstellen des ZIP-Backups: {e}", ephemeral=True)

@bot.tree.command(name="reload", description="Stellt eine Datenbank-Datei (JSON) wieder her")
@app_commands.describe(datei="Die hochzuladende Datei (insurance_data.json oder bot_config.json)")
async def reload_backup(interaction: discord.Interaction, datei: discord.Attachment):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann die Konfiguration wiederherstellen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    if not datei.filename.endswith('.json'):
        error_embed = discord.Embed(
            title="Falscher Dateityp!",
            description="> Die Bot Konfiguration kann nur mit einer `.json` Datei wiederhergestellt werden. Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Dateiprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
        error_embed.add_field(name="Benötigte Dateien", value="> <:2141file:1473009449412071484> - `insurance_data.json`\n> <:2141file:1473009449412071484> - `bot_config.json`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        create_backup()
        content = await datei.read()
        json_data = json.loads(content.decode('utf-8'))
        target_file = None
        if "customers" in json_data and "logs" in json_data:
            target_file = DATA_FILE
            global data
            data = json_data
            save_data(data)
            msg = "<:3518checkmark:1473009454202228959> `insurance_data.json` (Kundendaten) erfolgreich wiederhergestellt."
        elif "log_channel_id" in json_data or "kundenkontakt_category_id" in json_data:
            target_file = CONFIG_FILE
            global config
            config = json_data
            save_config(config)
            msg = "<:3518checkmark:1473009454202228959> `bot_config.json` (Konfiguration) erfolgreich wiederhergestellt."
        else:
            return await interaction.followup.send("<:3518crossmark:1473009455473098894> Fehler: Unbekanntes Dateiformat. Die Datei muss entweder Kundendaten oder Konfigurationsdaten enthalten.", ephemeral=True)
        await interaction.followup.send(msg, ephemeral=True)
        logger.info(f"Datenbank {target_file} reloaded von User {interaction.user.id}")
    except Exception as e:
        logger.error(f"Reload-Fehler: {e}")
        await interaction.followup.send(f"<:3518crossmark:1473009455473098894> Fehler beim Wiederherstellen: {e}", ephemeral=True)

@bot.tree.command(name="log_channel_setzen", description="Setzt den Channel für System-Logs")
@app_commands.describe(channel="Der Channel für Log-Nachrichten")
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann einen Kanal für die Logs festlegen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    config["log_channel_id"] = channel.id
    save_config(config)

    success_embed = discord.Embed(
        title="Log-Channel konfiguriert!",
        description=f"Alle System-Logs werden nun in {channel.mention} gesendet.",
        color=COLOR_SUCCESS
    )
    await interaction.response.send_message(embed=success_embed, ephemeral=True)

    log_embed = discord.Embed(
        title="System-Konfiguration",
        color=COLOR_INFO,
        timestamp=get_now()
    )
    log_embed.add_field(name="<:8586slashcommand:1473009513006366771> Aktion", value="> <:3518checkmark:1473009454202228959> Log-Channel gesetzt!", inline=False)
    log_embed.add_field(name="<:1041searchthreads:1473009441552203889> Kanalinformationen", value=f"> {channel.mention}\n> - `{channel.name}`\n> - `{channel.id}`", inline=False)
    log_embed.add_field(name="<:7549member:1473009494794698794> Userinformationen", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
    log_embed.add_field(name="<:9847public:1473009530962055291> Serverinformationen", value=f"> - `{interaction.guild.name}`\n> - `{interaction.guild.id}`", inline=False)
    log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
    log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await send_to_log_channel(interaction.guild, log_embed)

    add_log_entry("LOG_CHANNEL_GESETZT", interaction.user.id, {
        "channel_id": channel.id, "channel_name": channel.name,
        "guild_id": interaction.guild.id, "guild_name": interaction.guild.name
    })
    logger.info(f"Log-Channel auf `{channel.id}` gesetzt von {interaction.user.mention} (`{interaction.user.id}`)")

@bot.tree.command(name="kundenkontakt_kategorie_setzen", description="Setzt die Kategorie für Kundenkontakt-Tickets")
@app_commands.describe(category="Die Kategorie für Kundenkontakt-Tickets")
async def set_kundenkontakt_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann die Kundenkontakt-Kategorie festlegen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    config["kundenkontakt_category_id"] = category.id
    save_config(config)

    success_embed = discord.Embed(
        title="Kundenkontakt-Kategorie konfiguriert!",
        description=f"Alle Kundenkontakt-Tickets werden nun in der Kategorie `{category.name}` erstellt.",
        color=COLOR_SUCCESS
    )
    success_embed.set_author(name="Automatische Bestätigungsnachricht", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
    success_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await interaction.response.send_message(embed=success_embed, ephemeral=True)

    log_embed = discord.Embed(
        title="System-Konfiguration",
        color=COLOR_INFO,
        timestamp=get_now()
    )
    log_embed.add_field(name="<:8586slashcommand:1473009513006366771> Aktion", value="> <:3518checkmark:1473009454202228959> Kundenkontakt-Kategorie festgelegt!", inline=False)
    log_embed.add_field(name="<:1041searchthreads:1473009441552203889> Kanalinformationen", value=f"> `{category.name}`\n> - `{category.id}`", inline=False)
    log_embed.add_field(name="<:7549member:1473009494794698794> Userinformationen", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
    log_embed.add_field(name="<:9847public:1473009530962055291> Serverinformationen", value=f"> - `{interaction.guild.name}`\n> - `{interaction.guild.id}`", inline=False)
    log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
    log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await send_to_log_channel(interaction.guild, log_embed)

    add_log_entry("KUNDENKONTAKT_KATEGORIE_GESETZT", interaction.user.id, {
        "category_id": category.id, "category_name": category.name,
        "guild_id": interaction.guild.id, "guild_name": interaction.guild.name
    })
    logger.info(f"Kundenkontakt-Kategorie auf {category.id} gesetzt von User {interaction.user.id}")

@bot.tree.command(name="schadensmeldung_kategorie_setzen", description="Setzt die Kategorie für Schadensmeldungs-Tickets")
@app_commands.describe(category="Die Kategorie für Schadensmeldungs-Tickets")
async def set_schadensmeldung_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann die Schadeensmeldung-Kategorie festlegen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    config["schadensmeldung_category_id"] = category.id
    save_config(config)

    success_embed = discord.Embed(
        title="Schadensmeldung-Kategorie konfiguriert!",
        description=f"Alle Schadensmeldungs-Tickets werden nun in der Kategorie **{category.name}** erstellt.",
        color=COLOR_SUCCESS
    )
    success_embed.set_author(name="Automatische Bestätigungsnachricht", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
    success_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await interaction.response.send_message(embed=success_embed, ephemeral=True)

    log_embed = discord.Embed(
        title="System-Konfiguration",
        color=COLOR_INFO,
        timestamp=get_now()
    )
    log_embed.add_field(name="<:8586slashcommand:1473009513006366771> Aktion", value="> <:3518checkmark:1473009454202228959> Schadensmeldung-Kategorie festgelegt!", inline=False)
    log_embed.add_field(name="<:1041searchthreads:1473009441552203889> Kanalinformationen", value=f"> `{category.name}`\n> - `{category.id}`", inline=False)
    log_embed.add_field(name="<:7549member:1473009494794698794> Userinformationen", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
    log_embed.add_field(name="<:9847public:1473009530962055291> Serverinformationen", value=f"> - `{interaction.guild.name}`\n> - `{interaction.guild.id}`", inline=False)
    log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
    log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await send_to_log_channel(interaction.guild, log_embed)

    add_log_entry("SCHADENSMELDUNG_KATEGORIE_GESETZT", interaction.user.id, {
        "category_id": category.id, "category_name": category.name,
        "guild_id": interaction.guild.id, "guild_name": interaction.guild.name
    })
    logger.info(f"Schadensmeldung-Kategorie auf {category.id} gesetzt von User {interaction.user.id}")

@bot.tree.command(name="auszahlung_kanal_setzen", description="Setzt den Kanal für Auszahlungsanträge")
@app_commands.describe(channel="Der Kanal, in dem Auszahlungsanträge erscheinen sollen")
async def set_auszahlung_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann den Auszahlungs-Kanal festlegen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    config["auszahlung_channel_id"] = channel.id
    save_config(config)

    success_embed = discord.Embed(
        title="Auszahlungs-Kanal konfiguriert!",
        description=f"Alle Auszahlungsanträge werden nun in {channel.mention} gesendet.",
        color=COLOR_SUCCESS
    )
    success_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await interaction.response.send_message(embed=success_embed, ephemeral=True)

    log_embed = discord.Embed(
        title="System-Konfiguration",
        color=COLOR_INFO,
        timestamp=get_now()
    )
    log_embed.add_field(name="<:8586slashcommand:1473009513006366771> Aktion", value="> <:3518checkmark:1473009454202228959> Auszahlungs-Kanal gesetzt!", inline=False)
    log_embed.add_field(name="<:1041searchthreads:1473009441552203889> Kanalinformationen", value=f"> {channel.mention}\n> - `{channel.name}`\n> - `{channel.id}`", inline=False)
    log_embed.add_field(name="<:7549member:1473009494794698794> Userinformationen", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
    log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
    log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await send_to_log_channel(interaction.guild, log_embed)

    add_log_entry("AUSZAHLUNG_KANAL_GESETZT", interaction.user.id, {"channel_id": channel.id, "channel_name": channel.name})
    logger.info(f"Auszahlungs-Kanal auf {channel.id} gesetzt von User {interaction.user.id}")


class AuszahlungAntragsModal(discord.ui.Modal, title="Auszahlungsantrag"):
    betrag = discord.ui.TextInput(
        label="Auszahlungsbetrag (ohne €-Zeichen)",
        placeholder="z.B. 5000.00",
        required=True,
        max_length=20
    )
    beschreibung = discord.ui.TextInput(
        label="Beschreibung (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Kurze Beschreibung des Auszahlungsgrunds, damit die Leitung die Auszahlung überprüfen kann.",
        required=False,
        max_length=500
    )

    def __init__(self, customer_id: str, customer: dict, versicherung: str):
        super().__init__()
        self.customer_id = customer_id
        self.customer = customer
        self.versicherung = versicherung

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            try:
                betrag_float = float(self.betrag.value.replace(",", ".").replace("€", "").strip())
            except ValueError:
                await interaction.followup.send("<:3518crossmark:1473009455473098894> Ungültiger Betrag. Bitte eine Zahl eingeben.", ephemeral=True)
                return

            verfuegbar = get_verfuegbares_guthaben(self.customer_id, self.versicherung)
            limit = INSURANCE_TYPES.get(self.versicherung, {}).get("auszahlung_limit", 0.0)

            if betrag_float <= 0:
                await interaction.followup.send("<:3518crossmark:1473009455473098894> Der Betrag muss größer als 0 sein.", ephemeral=True)
                return
            if betrag_float > verfuegbar:
                await interaction.followup.send(
                    f"<:3518crossmark:1473009455473098894> Der Betrag `{betrag_float:,.2f} €` überschreitet das verfügbare Guthaben von `{verfuegbar:,.2f} €`.",
                    ephemeral=True
                )
                return

            auszahlung_channel_id = config.get("auszahlung_channel_id")
            if not auszahlung_channel_id:
                await interaction.followup.send("<:3518crossmark:1473009455473098894> Der Auszahlungs-Kanal wurde noch nicht konfiguriert! Bitte `/auszahlung_kanal_setzen` verwenden.", ephemeral=True)
                return

            auszahlung_channel = interaction.guild.get_channel(auszahlung_channel_id)
            if not auszahlung_channel:
                await interaction.followup.send("<:3518crossmark:1473009455473098894> Auszahlungs-Kanal nicht gefunden.", ephemeral=True)
                return

            auszahlung_id = generate_auszahlung_id()

            embed = discord.Embed(
                title="Auszahlungsantrag",
                color=COLOR_WARNING,
                timestamp=get_now()
            )
            embed.add_field(name="__Antragsinformationen__", value=f"> <:6224mail:1473009484753277130> - `{auszahlung_id}`\n> <:9654dollar:1473009529414357053> - `{betrag_float:,.2f} €`", inline=False)
            embed.add_field(name="__Versicherungsnehmer__", value=f"> <:7549member:1473009494794698794> - {self.customer['rp_name']}\n> <:4189search:1473009466902315048> - `{self.customer_id}`", inline=False)
            embed.add_field(name="__Versicherungsinformationen__", value=f"> <:4748ticket:1473009472422154311> - `{self.versicherung}`\n> Für diese Versicherung sind noch `{verfuegbar:,.2f} €` von `{limit:,.2f} €` verfügbar, welche dem Kunden beim eintreten eines Versicherungsfalles gezahlt werden.", inline=False)
            beschreibung_text = self.beschreibung.value.strip() if self.beschreibung.value else "—"
            embed.add_field(name="__Optionale Beschreibung__", value=f"```{beschreibung_text}```", inline=False)
            embed.add_field(name="Eingereicht von", value=f"{interaction.user.mention}", inline=True)
            embed.add_field(name="Status", value="> <:3684sync:1473009462628323523> - Ausstehend!", inline=True)
            embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")

            firmenkontorolle_role = interaction.guild.get_role(FIRMENKONTOROLLE_ROLE_ID)
            ping_text = firmenkontorolle_role.mention if firmenkontorolle_role else "@Firmenkontorolle"

            action_view = AuszahlungActionView(auszahlung_id, self.customer_id, betrag_float)
            msg = await auszahlung_channel.send(
                content=f"{ping_text} — Neuer Auszahlungsantrag!",
                embed=embed,
                view=action_view
            )

            if "pending_auszahlungen" not in data:
                data["pending_auszahlungen"] = {}
            data["pending_auszahlungen"][auszahlung_id] = {
                "customer_id": self.customer_id,
                "versicherung": self.versicherung,
                "betrag": betrag_float,
                "beschreibung": beschreibung_text,
                "requester_id": interaction.user.id,
                "message_id": msg.id,
                "channel_id": auszahlung_channel_id,
                "status": "ausstehend",
                "created_at": get_now().isoformat()
            }
            save_data(data)

            add_log_entry("AUSZAHLUNG_EINGEREICHT", interaction.user.id, {
                "auszahlung_id": auszahlung_id,
                "customer_id": self.customer_id,
                "customer_name": self.customer['rp_name'],
                "versicherung": self.versicherung,
                "betrag": betrag_float
            })

            # Log-Embed angepasst an deinen Stil
            log_embed = discord.Embed(
                title="Auszahlungsantrag eingereicht!",
                color=COLOR_WARNING,
                timestamp=get_now()
            )
            log_embed.add_field(name="<:6224mail:1473009484753277130> Antrags-ID", value=f"> `{auszahlung_id}`", inline=False)
            log_embed.add_field(name="<:7549member:1473009494794698794> Versicherungsnehmer", value=f"> {self.customer['rp_name']}\n> `{self.customer_id}`", inline=False)
            log_embed.add_field(name="<:9654dollar:1473009529414357053> Betrag", value=f"> `{betrag_float:,.2f} €`", inline=False)
            log_embed.add_field(name="<:4748ticket:1473009472422154311> Versicherung", value=f"> `{self.versicherung}`", inline=False)
            log_embed.add_field(name="<:7549member:1473009494794698794> Eingereicht von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
            log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
            log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await send_to_log_channel(interaction.guild, log_embed)

            success_embed = discord.Embed(
                title="<:3518checkmark:1473009454202228959> Auszahlungsantrag eingereicht!",
                description=f"Der Antrag `{auszahlung_id}` wurde erfolgreich an die Firmenkontorolle weitergeleitet.",
                color=COLOR_SUCCESS
            )
            success_embed.add_field(name="<:9654dollar:1473009529414357053> Betrag", value=f"> `{betrag_float:,.2f} €`", inline=False)
            success_embed.add_field(name="<:4748ticket:1473009472422154311> Versicherung", value=f"> `{self.versicherung}`", inline=False)
            success_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Fehler beim Einreichen der Auszahlung: {e}", exc_info=True)
            await interaction.followup.send(f"<:3518crossmark:1473009455473098894> Fehler: {e}", ephemeral=True)


class AuszahlungSelectView(discord.ui.View):
    def __init__(self, customer_id: str, customer: dict):
        super().__init__(timeout=300)
        self.customer_id = customer_id
        self.customer = customer
        self._selected: str | None = None

        options = []
        for versicherung in customer.get("versicherungen", []):
            verfuegbar = get_verfuegbares_guthaben(customer_id, versicherung)
            limit = INSURANCE_TYPES.get(versicherung, {}).get("auszahlung_limit", 0.0)
            bereits = limit - verfuegbar
            desc = f"Verfügbar: {verfuegbar:,.0f} € | Ausgezahlt: {bereits:,.0f} € / {limit:,.0f} €"
            options.append(discord.SelectOption(
                label=versicherung[:100],
                description=desc[:100],
                value=versicherung,
                emoji="💰" if verfuegbar > 0 else "🚫"
            ))

        self._select = discord.ui.Select(
            placeholder="Versicherung wählen...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="az_versicherung_select"
        )
        self._select.callback = self._on_select
        self.add_item(self._select)

    async def _on_select(self, interaction: discord.Interaction):
        selected = self._select.values[0]
        self._selected = selected
        verfuegbar = get_verfuegbares_guthaben(self.customer_id, selected)

        if verfuegbar <= 0:
            await interaction.response.send_message(
                f"<:3518crossmark:1473009455473098894> Das Limit für `{selected}` ist bereits ausgeschöpft.",
                ephemeral=True
            )
            return

        modal = AuszahlungAntragsModal(self.customer_id, self.customer, selected)
        await interaction.response.send_modal(modal)


class AuszahlungBestaetigenModal(discord.ui.Modal, title="Auszahlung bestätigen – Nachweis"):
    auszahlungs_link = discord.ui.TextInput(
        label="Link der Auszahlungsnachricht",
        placeholder="https://discord.com/channels/...",
        required=True,
        max_length=500
    )

    def __init__(self, auszahlung_id: str, guild: discord.Guild, confirmer: discord.Member):
        super().__init__()
        self.auszahlung_id = auszahlung_id
        self.guild = guild
        self.confirmer = confirmer

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            pending = data.get("pending_auszahlungen", {}).get(self.auszahlung_id)
            if not pending:
                await interaction.followup.send("<:3518crossmark:1473009455473098894> Auszahlungsantrag nicht gefunden.", ephemeral=True)
                return

            if pending.get("status") != "ausstehend":
                await interaction.followup.send("<:3518crossmark:1473009455473098894> Dieser Antrag wurde bereits bearbeitet.", ephemeral=True)
                return

            customer_id = pending["customer_id"]
            versicherung = pending["versicherung"]
            betrag = pending["betrag"]
            customer = data['customers'].get(customer_id)

            if not customer:
                await interaction.followup.send("<:3518crossmark:1473009455473098894> Kunde nicht gefunden.", ephemeral=True)
                return

            verfuegbar = get_verfuegbares_guthaben(customer_id, versicherung)
            if betrag > verfuegbar:
                await interaction.followup.send(
                    f"<:3518crossmark:1473009455473098894> Das verfügbare Guthaben reicht nicht mehr aus (`{verfuegbar:,.2f} €` verfügbar, `{betrag:,.2f} €` beantragt).",
                    ephemeral=True
                )
                return

            if "auszahlungen" not in data['customers'][customer_id]:
                data['customers'][customer_id]["auszahlungen"] = {}
            data['customers'][customer_id]["auszahlungen"][versicherung] = \
                data['customers'][customer_id]["auszahlungen"].get(versicherung, 0.0) + betrag

            data["pending_auszahlungen"][self.auszahlung_id]["status"] = "bestaetigt"
            data["pending_auszahlungen"][self.auszahlung_id]["bestaetigt_von"] = self.confirmer.id
            data["pending_auszahlungen"][self.auszahlung_id]["bestaetigt_am"] = get_now().isoformat()
            data["pending_auszahlungen"][self.auszahlung_id]["auszahlungs_link"] = self.auszahlungs_link.value
            save_data(data)

            thread_id = customer.get("thread_id")
            if thread_id:
                try:
                    thread = self.guild.get_thread(thread_id)
                    if thread:
                        neues_guthaben = get_verfuegbares_guthaben(customer_id, versicherung)
                        limit = INSURANCE_TYPES.get(versicherung, {}).get("auszahlung_limit", 0.0)

                        vermerk_embed = discord.Embed(
                            title="Auszahlungsvermerk",
                            color=COLOR_PRIMARY,
                            timestamp=get_now()
                        )
                        vermerk_embed.add_field(name="__Antragsinformationen__", value=f"> <:6224mail:1473009484753277130> - `{self.auszahlung_id}`\n> <:4748ticket:1473009472422154311> - `{versicherung}`\n> <:1198link:1473009446610272408> - [Zur Auszahlungsnachricht]({self.auszahlungs_link.value})", inline=False)
                        vermerk_embed.add_field(name="__Auszahlungsinformationen__", value=f"> <:9654dollar:1473009529414357053> Verfügbares Guthaben: `{verfuegbar:,.2f} €`\n> `- {betrag:,.2f} €`\n> <:912926arrow:1473009547282092124> Restliches Guthaben: **`{neues_guthaben:,.2f} €`**", inline=False)
                        vermerk_embed.add_field(name="<:1158refresh:1473009444077178993> Datum", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M Uhr')}", inline=False)
                        vermerk_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
                        await thread.send(embed=vermerk_embed)
                        logger.info(f"Auszahlungsvermerk in Akte {customer_id} hinterlegt")
                except Exception as e:
                    logger.error(f"Fehler beim Posten des Vermerks in Akte: {e}")

            try:
                az_channel = self.guild.get_channel(pending["channel_id"])
                if az_channel:
                    orig_msg = await az_channel.fetch_message(pending["message_id"])
                    if orig_msg.embeds:
                        updated_embed = orig_msg.embeds[0]
                        updated_embed.color = COLOR_SUCCESS
                        for i, field in enumerate(updated_embed.fields):
                            if field.name == "Status":
                                updated_embed.set_field_at(i, name="Status", value="✅ Genehmigt", inline=True)
                                break
                        updated_embed.add_field(name="Genehmigt von", value=f"{self.confirmer.mention}", inline=True)
                        updated_embed.add_field(name="Genehmigt am", value=get_now().strftime('%d.%m.%Y • %H:%M'), inline=True)
                        await orig_msg.edit(embed=updated_embed, view=None)
            except Exception as e:
                logger.error(f"Fehler beim Aktualisieren der Antragsnachricht: {e}")

            add_log_entry("AUSZAHLUNG_BESTAETIGT", self.confirmer.id, {
                "auszahlung_id": self.auszahlung_id,
                "customer_id": customer_id,
                "customer_name": customer['rp_name'],
                "versicherung": versicherung,
                "betrag": betrag,
                "auszahlungs_link": self.auszahlungs_link.value
            })

            log_embed = discord.Embed(
                title="Auszahlung bestätigt!",
                color=COLOR_SUCCESS,
                timestamp=get_now()
            )
            log_embed.add_field(name="<:6224mail:1473009484753277130> Antrags-ID", value=f"> `{self.auszahlung_id}`", inline=False)
            log_embed.add_field(name="<:7549member:1473009494794698794> Versicherungsnehmer", value=f"> {customer['rp_name']}\n> `{customer_id}`", inline=False)
            log_embed.add_field(name="<:9654dollar:1473009529414357053> Betrag", value=f"> `{betrag:,.2f} €`", inline=False)
            log_embed.add_field(name="<:4748ticket:1473009472422154311> Versicherung", value=f"> `{versicherung}`", inline=False)
            log_embed.add_field(name="<:3518checkmark:1473009454202228959> Genehmigt von", value=f"> {self.confirmer.mention}\n> - `{self.confirmer.name}`\n> - `{self.confirmer.id}`", inline=False)
            log_embed.add_field(name="<:1198link:1473009446610272408> Nachweis", value=f"> [Zur Auszahlungsnachricht]({self.auszahlungs_link.value})", inline=False)
            log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
            log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await send_to_log_channel(self.guild, log_embed)

            success_embed = discord.Embed(
                title="Auszahlung erfolgreich bestätigt!",
                description=f"Die Auszahlung `{self.auszahlung_id}` wurde genehmigt und in der Kundenakte vermerkt.",
                color=COLOR_SUCCESS
            )
            success_embed.add_field(name="<:9654dollar:1473009529414357053> Ausgezahlter Betrag", value=f"> `{betrag:,.2f} €`", inline=False)
            success_embed.add_field(name="<:4748ticket:1473009472422154311> Versicherung", value=f"> `{versicherung}`", inline=False)
            success_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Fehler beim Bestätigen der Auszahlung: {e}", exc_info=True)
            await interaction.followup.send(f"<:3518crossmark:1473009455473098894> Fehler: {e}", ephemeral=True)


class AuszahlungActionView(discord.ui.View):
    def __init__(self, auszahlung_id: str, customer_id: str, betrag: float):
        super().__init__(timeout=None)
        self.auszahlung_id = auszahlung_id
        self.customer_id = customer_id
        self.betrag = betrag

    @discord.ui.button(label="Bestätigen", style=discord.ButtonStyle.green, custom_id="auszahlung_bestaetigen", emoji="<:3518checkmark:1473009454202228959>")
    async def bestaetigen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_firmenkontorolle(interaction):
            error_embed = discord.Embed(
                title="Zugriff verweigert!",
                description="> Nur das Firmenkonto kann Auszahlungsanträge bearbeiten! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
                color=COLOR_ERROR
            )
            error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
            error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Firmenkonto`", inline=False)
            error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        pending = data.get("pending_auszahlungen", {}).get(self.auszahlung_id)
        if not pending or pending.get("status") != "ausstehend":
            await interaction.response.send_message("<:3518crossmark:1473009455473098894> Dieser Antrag wurde bereits bearbeitet.", ephemeral=True)
            return

        modal = AuszahlungBestaetigenModal(self.auszahlung_id, interaction.guild, interaction.user)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Abbrechen", style=discord.ButtonStyle.danger, custom_id="auszahlung_abbrechen", emoji="<:3518crossmark:1473009455473098894>")
    async def abbrechen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_firmenkontorolle(interaction):
            error_embed = discord.Embed(
                title="Zugriff verweigert!",
                description="> Nur das Firmenkonto kann Auszahlungsanträge bearbeiten! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
                color=COLOR_ERROR
            )
            error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
            error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Firmenkonto`", inline=False)
            error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        pending = data.get("pending_auszahlungen", {}).get(self.auszahlung_id)
        if not pending or pending.get("status") != "ausstehend":
            await interaction.response.send_message("<:3518crossmark:1473009455473098894> Dieser Antrag wurde bereits bearbeitet.", ephemeral=True)
            return

        data["pending_auszahlungen"][self.auszahlung_id]["status"] = "abgelehnt"
        data["pending_auszahlungen"][self.auszahlung_id]["abgelehnt_von"] = interaction.user.id
        data["pending_auszahlungen"][self.auszahlung_id]["abgelehnt_am"] = get_now().isoformat()
        save_data(data)

        try:
            if interaction.message.embeds:
                updated_embed = interaction.message.embeds[0]
                updated_embed.color = COLOR_ERROR
                for i, field in enumerate(updated_embed.fields):
                    if field.name == "Status":
                        updated_embed.set_field_at(i, name="Status", value="❌ Abgelehnt", inline=True)
                        break
                updated_embed.add_field(name="Abgelehnt von", value=f"{interaction.user.mention}", inline=True)
                updated_embed.add_field(name="Abgelehnt am", value=get_now().strftime('%d.%m.%Y • %H:%M'), inline=True)
                await interaction.message.edit(embed=updated_embed, view=None)
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Antragsnachricht: {e}")

        add_log_entry("AUSZAHLUNG_ABGELEHNT", interaction.user.id, {
            "auszahlung_id": self.auszahlung_id,
            "customer_id": self.customer_id,
            "betrag": self.betrag
        })

        log_embed = discord.Embed(
            title="Auszahlungsantrag abgelehnt!",
            color=COLOR_ERROR,
            timestamp=get_now()
        )
        log_embed.add_field(name="<:6224mail:1473009484753277130> Antrags-ID", value=f"> `{self.auszahlung_id}`", inline=False)
        log_embed.add_field(name="<:4189search:1473009466902315048> Kunden-ID", value=f"> `{self.customer_id}`", inline=False)
        log_embed.add_field(name="<:9654dollar:1473009529414357053> Betrag", value=f"> `{self.betrag:,.2f} €`", inline=False)
        log_embed.add_field(name="<:3518crossmark:1473009455473098894> Abgelehnt von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
        log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
        log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await send_to_log_channel(interaction.guild, log_embed)

        await interaction.response.send_message(
            f"<:3518checkmark:1473009454202228959> Auszahlungsantrag `{self.auszahlung_id}` wurde abgelehnt.",
            ephemeral=True
        )


@bot.tree.command(name="auszahlung_einreichen", description="Reicht einen Auszahlungsantrag für einen Kunden ein")
@app_commands.describe(customer_id="Versicherungsnehmer-ID des Kunden")
async def auszahlung_einreichen(interaction: discord.Interaction, customer_id: str):
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur Mitarbeiter oder die Leitungsebene können Auszahlungsanträge einreichen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`\n> `Mitarbeiter`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    if customer_id not in data['customers']:
        error_embed = discord.Embed(
            title="<:3518crossmark:1473009455473098894> Kunde nicht gefunden!",
            description=f"Es existiert keine Akte mit der Versicherungsnehmer-ID `{customer_id}`.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    customer = data['customers'][customer_id]

    if not customer.get("versicherungen"):
        await interaction.response.send_message("<:3518crossmark:1473009455473098894> Dieser Kunde hat keine abgeschlossenen Versicherungen.", ephemeral=True)
        return

    limits_text = ""
    for versicherung in customer.get("versicherungen", []):
        verfuegbar = get_verfuegbares_guthaben(customer_id, versicherung)
        limit = INSURANCE_TYPES.get(versicherung, {}).get("auszahlung_limit", 0.0)
        status = "💰" if verfuegbar > 0 else "🚫"
        limits_text += f"{status} **{versicherung}**\n> Verfügbar: `{verfuegbar:,.2f} €` von `{limit:,.2f} €`\n"

    select_embed = discord.Embed(
        title="💰 Auszahlungsantrag einreichen",
        description=f"**Versicherungsnehmer:** {customer['rp_name']} (`{customer_id}`)\n\nBitte wählen Sie im Dropdown die Versicherung aus — es öffnet sich ein Formular für Betrag und Begründung.",
        color=COLOR_INFO
    )
    select_embed.add_field(name="Auszahlungsguthaben Übersicht", value=limits_text if limits_text else "Keine Daten", inline=False)
    select_embed.set_footer(text="InsuranceGuard v2 • Wählen Sie eine Versicherung aus dem Dropdown")

    view = AuszahlungSelectView(customer_id, customer)
    await interaction.response.send_message(embed=select_embed, view=view, ephemeral=True)


# Auswahlmenü für Versicherungen
class InsuranceSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=insurance,
                description=f"Monatsbeitrag: {info['price']:,.2f} €",
                value=insurance
            )
            for insurance, info in INSURANCE_TYPES.items()
        ]
        super().__init__(
            placeholder="Wählen Sie die gewünschten Versicherungen aus...",
            min_values=1,
            max_values=len(options),
            options=options,
            custom_id="insurance_select"
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = False

        total = sum(INSURANCE_TYPES[ins]["price"] for ins in self.values)
        preview_text = "\n".join(f"▸ {ins} — {INSURANCE_TYPES[ins]['price']:,.2f} €" for ins in self.values)

        preview_embed = discord.Embed(
            title="Versicherungen ausgewählt!",
            description=f"**Ausgewählte Versicherungen:**\n{preview_text}\n\n**Gesamtbeitrag (monatlich):** `{total:,.2f} €`",
            color=COLOR_INFO
        )
        preview_embed.set_footer(text="Klicken Sie auf 'Kundenakte erstellen', um fortzufahren.")
        await interaction.response.edit_message(embed=preview_embed, view=view)

class InsuranceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.selected_insurances = []
        self.confirmed = False
        self.add_item(InsuranceSelect())

        confirm_button = discord.ui.Button(
            label="Kundenakte erstellen",
            style=discord.ButtonStyle.green,
            custom_id="confirm_insurance",
            disabled=True
        )
        confirm_button.callback = self.confirm_callback
        self.add_item(confirm_button)

    async def confirm_callback(self, interaction: discord.Interaction):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

@bot.tree.command(name="kundenakte_erstellen", description="Erstellt eine neue Kundenakte im Archiv")
@app_commands.describe(
    forum_channel="Forum-Channel für Kundenakten",
    user="Discord-User des Versicherungsnehmers",
    rp_name="RP-Name des Versicherungsnehmers",
    hbpay_nummer="HBpay Kontonummer",
    economy_id="Economy-ID des Versicherungsnehmers"
)
async def create_customer(
    interaction: discord.Interaction,
    forum_channel: discord.ForumChannel,
    user: discord.Member,
    rp_name: str,
    hbpay_nummer: str,
    economy_id: str
):
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur Mitarbeiter oder die Leitungsebene können eine Kundenakte festlegen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`\n> `Mitarbeiter`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    view = InsuranceView()
    select_embed = discord.Embed(
        title="Versicherungen auswählen!",
        description="Bitte wählen Sie die gewünschten Versicherungen für den Versicherungsnehmer aus dem Dropdown-Menü aus.\n\nNach der Auswahl klicken Sie auf den Button **'Kundenakte erstellen'**, um fortzufahren.",
        color=COLOR_INFO
    )
    await interaction.response.send_message(embed=select_embed, view=view, ephemeral=True)
    await view.wait()

    if not view.confirmed:
        timeout_embed = discord.Embed(
            title="Zeitüberschreitung!",
            description="Die Auswahl wurde nicht rechtzeitig bestätigt. Bitte versuchen Sie es erneut.",
            color=COLOR_WARNING
        )
        await interaction.edit_original_response(embed=timeout_embed, view=None)
        return

    insurance_select = view.children[0]
    if not insurance_select.values:
        error_embed = discord.Embed(
            title="Keine Auswahl getroffen!",
            description="Es wurden keine Versicherungen ausgewählt.",
            color=COLOR_ERROR
        )
        await interaction.edit_original_response(embed=error_embed, view=None)
        return

    insurance_list = insurance_select.values
    logger.info(f"Kundenakte wird erstellt von User {interaction.user.id} für {rp_name}")

    try:
        customer_id = generate_customer_id()
        total_price = sum(INSURANCE_TYPES[ins]["price"] for ins in insurance_list)

        embed = discord.Embed(
            title="Versicherungsakte",
            color=COLOR_PRIMARY,
            timestamp=get_now()
        )
        embed.add_field(name="__Versicherungsnehmer__", value=f"> <:7549member:1473009494794698794> - {rp_name}\n> <:4189search:1473009466902315048> - `{customer_id}`", inline=False)
        embed.add_field(name="__Zahlungsmethoden__", value=f"> <:8312card:1473009505041256501> - `{hbpay_nummer}`\n> <:9847public:1473009530962055291> - `{economy_id}`", inline=False)
        insurance_text = "\n".join(
            f"> {ins}\n> ▸`{INSURANCE_TYPES[ins]['price']:,.2f} €/Monat`"
            for ins in insurance_list
        )
        embed.add_field(name="__Abgeschlossene Versicherungen__", value=insurance_text, inline=False)
        embed.add_field(name="__Gesamtbeitrag (monatlich)__", value=f"<:912926arrow:1473009547282092124> **`{total_price:,.2f} €`**", inline=False)
        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.add_field(name="__Aktenanlage__", value=f"> {get_now().strftime('%d.%m.%Y • %H:%M Uhr')}", inline=False)
        embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=258&height=258")

        thread = await forum_channel.create_thread(
            name=f"📁 {customer_id} | {rp_name}",
            content="",
            embed=embed
        )

        data['customers'][customer_id] = {
            "rp_name": rp_name,
            "hbpay_nummer": hbpay_nummer,
            "economy_id": economy_id,
            "versicherungen": insurance_list,
            "total_monthly_price": total_price,
            "thread_id": thread.thread.id,
            "discord_user_id": user.id,
            "created_at": get_now().isoformat(),
            "created_by": interaction.user.id,
            "status": "aktiv",
            "auszahlungen": {}
        }
        save_data(data)

        member = user
        assigned_roles = []
        for insurance in insurance_list:
            role_name = INSURANCE_TYPES[insurance]["role"]
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if not role:
                role = await interaction.guild.create_role(name=role_name, color=discord.Color.from_rgb(44, 62, 80))
                logger.info(f"Rolle erstellt: {role_name}")
            await member.add_roles(role)
            assigned_roles.append(role_name)

        add_log_entry("KUNDENAKTE_ERSTELLT", interaction.user.id, {
            "customer_id": customer_id,
            "rp_name": rp_name,
            "versicherungen": insurance_list,
            "total_price": total_price,
            "thread_id": thread.thread.id,
            "forum_channel_id": forum_channel.id,
            "forum_channel_name": forum_channel.name,
            "hbpay_nummer": hbpay_nummer,
            "economy_id": economy_id
        })

        log_embed = discord.Embed(
            title="Neue Kundenakte erstellt!",
            color=COLOR_SUCCESS,
            timestamp=get_now()
        )
        log_embed.add_field(name="__Versicherungsnehmer__", value=f"> <:7549member:1473009494794698794> - {rp_name}\n> <:4189search:1473009466902315048> - `{customer_id}`", inline=False)
        log_embed.add_field(name="__Monatsbeitrag__", value=f"> <:9654dollar:1473009529414357053> - `{total_price:,.2f} €`", inline=False)
        log_embed.add_field(name="__Thread-ID__", value=f"> <:1041searchthreads:1473009441552203889> - `{thread.thread.id}`", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Aussteller", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
        log_embed.add_field(name="__Zeitstempel__", value=f"> {get_now().strftime('%d.%m.%Y • %H:%M:%S')}", inline=False)
        log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await send_to_log_channel(interaction.guild, log_embed)

        success_embed = discord.Embed(
            title="Kundenakte erfolgreich angelegt!",
            description="Die Versicherungsakte wurde erfolgreich im System hinterlegt.",
            color=COLOR_SUCCESS
        )
        success_embed.add_field(name="__Informationen__", value=f"> <:4189search:1473009466902315048> - `{customer_id}`\n> <:1041searchthreads:1473009441552203889> - {thread.thread.mention}\n> <:9654dollar:1473009529414357053> - `{total_price:,.2f} €`", inline=False)
        success_embed.set_author(name="Automatische Bestätigungsnachricht", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
        success_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.edit_original_response(embed=success_embed, view=None)
        logger.info(f"Kundenakte {customer_id} erfolgreich erstellt")

    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Kundenakte: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="<:3518crossmark:1473009455473098894> Fehler bei der Aktenanlage!",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        try:
            await interaction.edit_original_response(embed=error_embed, view=None)
        except:
            await interaction.followup.send(embed=error_embed, ephemeral=True)

@bot.tree.command(name="rechnung_ausstellen", description="Erstellt eine Versicherungsrechnung")
@app_commands.describe(customer_id="Versicherungsnehmer-ID", channel="Channel für die Rechnungsstellung")
async def create_invoice(interaction: discord.Interaction, customer_id: str, channel: discord.TextChannel):
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur Mitarbeiter oder die Leitungsebene können Rechnungen ausstellen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`\n> `Mitarbeiter`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    logger.info(f"Rechnung wird erstellt von User {interaction.user.id} für Kunde {customer_id}")

    try:
        if customer_id not in data['customers']:
            error_embed = discord.Embed(
                title="<:3518crossmark:1473009455473098894> Kunde nicht gefunden!",
                description=f"Es existiert keine Akte mit der Versicherungsnehmer-ID `{customer_id}`.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        customer = data['customers'][customer_id]
        invoice_id = generate_invoice_id()
        betrag_netto = customer['total_monthly_price']
        steuer = betrag_netto * 0.05
        betrag_brutto = betrag_netto + steuer
        due_date = get_now() + timedelta(days=3)

        embed = discord.Embed(
            title=f"Versicherungsrechnung - {get_now().strftime('%d.%m.%Y')}",
            description="Dies ist eine Zahlungsaufforderung für ihre Versicherungsbeiträge!",
            color=COLOR_PRIMARY,
            timestamp=get_now()
        )
        embed.add_field(name="__Rechnungsinformationen__", value=f"> <:6224mail:1473009484753277130> - `{invoice_id}`")
        embed.add_field(name="__Versicherungsnehmer__", value=f"> <:7549member:1473009494794698794> - {customer['rp_name']}\n> <:4189search:1473009466902315048> - `{customer_id}`", inline=False)
        embed.add_field(name="__Zahlungsmethoden__", value=f"> <:8312card:1473009505041256501> - `{customer['hbpay_nummer']}`\n> <:9847public:1473009530962055291> - `{customer['economy_id']}`", inline=False)
        insurance_details = "\n".join(
            f"> {ins}\n> ▸ `{INSURANCE_TYPES[ins]['price']:,.2f} €`"
            for ins in customer['versicherungen']
        )
        embed.add_field(name="__Abgeschlossene Versicherungen__", value=insurance_details, inline=False)
        embed.add_field(name="__Abrechnung__", value="", inline=False)
        embed.add_field(name="Zwischensumme (Netto)", value=f"> `{betrag_netto:,.2f} €`", inline=False)
        embed.add_field(name="Steuer (5%)", value=f"> `+` `{steuer:,.2f} €`", inline=False)
        embed.add_field(name="Rechnungsbetrag (Brutto)", value=f"<:912926arrow:1473009547282092124> **`{betrag_brutto:,.2f} €`**", inline=False)
        embed.add_field(name="__Status: Zahlung ausstehend!__", value=f"> Sie haben bis zum **{due_date.strftime('%d.%m.%Y')}** Zeit diese Rechnung zu begleichen. Sollten sie diese Frist nicht einhalten, behalten wir uns weitere (rechtliche) Schritte gegen sie vor. Sollten sie Probleme bei dem Transfer des Geldes haben melden sie sich bitte im Ticket!", inline=False)
        embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")

        message = await channel.send(embed=embed)

        data['invoices'][invoice_id] = {
            "customer_id": customer_id,
            "betrag": betrag_brutto,
            "betrag_netto": betrag_netto,
            "steuer": steuer,
            "original_betrag": betrag_brutto,
            "paid": False,
            "message_id": message.id,
            "channel_id": channel.id,
            "due_date": due_date.isoformat(),
            "reminder_count": 0,
            "created_at": get_now().isoformat(),
            "created_by": interaction.user.id
        }
        save_data(data)

        add_log_entry("RECHNUNG_ERSTELLT", interaction.user.id, {
            "invoice_id": invoice_id,
            "customer_id": customer_id,
            "customer_name": customer['rp_name'],
            "betrag_netto": betrag_netto,
            "steuer": steuer,
            "betrag_brutto": betrag_brutto,
            "due_date": due_date.strftime('%d.%m.%Y'),
            "channel_id": channel.id,
            "channel_name": channel.name,
            "message_id": message.id
        })

        log_embed = discord.Embed(
            title="Neue Rechnung ausgestellt!",
            color=COLOR_INFO,
            timestamp=get_now()
        )
        log_embed.add_field(name="__Rechnungsnummer__", value=f"> <:6224mail:1473009484753277130> - `{invoice_id}`", inline=False)
        log_embed.add_field(name="__Versicherungsnehmer__", value=f"> <:7549member:1473009494794698794> - {customer['rp_name']}\n> <:4189search:1473009466902315048> - `{customer_id}`", inline=False)
        log_embed.add_field(name="__Fällig__", value=f"> {due_date.strftime('%d.%m.%Y')}", inline=False)
        log_embed.add_field(name="__Abrechnung__", value=f"> Netto: `{betrag_netto:,.2f} €`\n> Steuer (5%): `+ {steuer:,.2f} €`\n> <:912926arrow:1473009547282092124> Brutto: **`{betrag_brutto:,.2f} €`**", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Aussteller", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
        log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
        log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await send_to_log_channel(interaction.guild, log_embed)

        success_embed = discord.Embed(
            title="Rechnung erfolgreich ausgestellt!",
            description="Die Rechnung wurde erstellt und versendet.",
            color=COLOR_SUCCESS
        )
        success_embed.set_author(name="Automatische Bestätigungsnachricht", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
        success_embed.add_field(name="Rechnungsinformationen", value=f"> <:6224mail:1473009484753277130> - `{invoice_id}`\n> <:9654dollar:1473009529414357053> - `{betrag_brutto:,.2f} €`\n> <:2533warning:1473009451647762515> - {due_date.strftime('%d.%m.%Y')}", inline=False)
        success_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Rechnung: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="<:3518crossmark:1473009455473098894> Fehler bei der Rechnungsstellung!",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

@bot.tree.command(name="mahnung_ausstellen", description="Stellt eine Mahnung für eine überfällige Rechnung aus")
@app_commands.describe(invoice_id="Rechnungsnummer (z.B. RE-2412-A3F9)")
async def issue_manual_reminder(interaction: discord.Interaction, invoice_id: str):
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur Mitarbeiter oder die Leitungsebene können eine Mahnung ausstellen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`\n> `Mitarbeiter`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        if invoice_id not in data['invoices']:
            error_embed = discord.Embed(
                title="Rechnung nicht gefunden!",
                description=f"Es existiert keine Rechnung mit der Nummer `{invoice_id}`. Bitte überprüfe deine Eingabe und versuche es erneut!",
                color=COLOR_ERROR
            )
            error_embed.set_author(name="Automatische Fehlerbenachrichtigung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
            error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        invoice = data['invoices'][invoice_id]

        if invoice.get('paid', False):
            info_embed = discord.Embed(
                title="Rechnung bereits bezahlt!",
                description=f"Die Rechnung `{invoice_id}` wurde bereits als bezahlt markiert.",
                color=COLOR_INFO
            )
            info_embed.set_author(name="Automatische Infobenachrichtigung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
            info_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.followup.send(embed=info_embed, ephemeral=True)
            return

        customer = data['customers'].get(invoice['customer_id'])
        if not customer:
            error_embed = discord.Embed(
                title="Kunde nicht gefunden!",
                description="Kunde konnte nicht gefunden werden. Bitte überprüfe deine Eingabe und versuche es erneut!",
                color=COLOR_ERROR
            )
            error_embed.set_author(name="Automatische Fehlerbenachrichtigung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
            error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        reminder_count = invoice.get('reminder_count', 0) + 1
        surcharge_percent = 0
        if reminder_count == 2:
            surcharge_percent = 5
            new_amount = invoice['original_betrag'] * 1.05
            data['invoices'][invoice_id]['betrag'] = new_amount
        elif reminder_count >= 3:
            surcharge_percent = 10
            new_amount = invoice['original_betrag'] * 1.10
            data['invoices'][invoice_id]['betrag'] = new_amount
        else:
            new_amount = invoice['betrag']

        data['invoices'][invoice_id]['reminder_count'] = reminder_count
        save_data(data)
        await send_reminder(invoice_id, invoice, reminder_count, surcharge_percent)

        success_embed = discord.Embed(
            title="Mahnung erfolgreich ausgestellt!",
            description=f"Die {reminder_count}. Mahnung für Rechnung `{invoice_id}` wurde versendet.",
            color=COLOR_SUCCESS
        )
        success_embed.add_field(name="<:9654dollar:1473009529414357053> Neuer Betrag", value=f"> `{new_amount:,.2f} €`", inline=False)
        if surcharge_percent > 0:
            success_embed.add_field(name="<:2533warning:1473009451647762515> Mahngebühr", value=f"> +{surcharge_percent}%", inline=False)
        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Fehler beim Ausstellen der Mahnung: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="<:3518crossmark:1473009455473098894> Fehler!",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

@bot.tree.command(name="akte_archivieren", description="Archiviert eine Kundenakte")
@app_commands.describe(customer_id="Versicherungsnehmer-ID")
async def archive_customer(interaction: discord.Interaction, customer_id: str):
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur Mitarbeiter oder die Leitungsebene können eine Kundenakte archivieren! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`\n> `Mitarbeiter`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        if customer_id not in data['customers']:
            error_embed = discord.Embed(
                title="Kunde nicht gefunden!",
                description=f"Es existiert keine Akte mit der ID `{customer_id}`. Bitte überprüfe deine Eingabe und versuche es erneut.",
                color=COLOR_ERROR
            )
            error_embed.set_author(name="Automatische Fehlerbenachrichtigung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
            error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        customer = data['customers'][customer_id]

        if customer.get('status') == 'archiviert':
            info_embed = discord.Embed(
                title="Akte bereits archiviert!",
                description=f"Die Akte `{customer_id}` ist bereits archiviert.",
                color=COLOR_INFO
            )
            info_embed.set_author(name="Automatische Infobenachrichtigung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
            info_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await interaction.followup.send(embed=info_embed, ephemeral=True)
            return

        data['customers'][customer_id]['status'] = 'archiviert'
        data['customers'][customer_id]['archived_at'] = get_now().isoformat()
        data['customers'][customer_id]['archived_by'] = interaction.user.id
        save_data(data)

        thread_id = customer.get('thread_id')
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id)
                if thread:
                    await thread.edit(name=f"🗄️ [ARCHIV] {customer_id} | {customer['rp_name']}")
                    archive_embed = discord.Embed(
                        title="Akte archiviert!",
                        description="Diese Kundenakte wurde archiviert und ist nicht mehr aktiv.",
                        color=COLOR_WARNING,
                        timestamp=get_now()
                    )
                    archive_embed.add_field(name="<:7549member:1473009494794698794> Archiviert von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
                    archive_embed.add_field(name="<:1158refresh:1473009444077178993> Archiviert am", value=f"> {get_now().strftime('%d.%m.%Y • %H:%M Uhr')}", inline=False)
                    archive_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
                    await thread.send(embed=archive_embed)
            except Exception as e:
                logger.error(f"Fehler beim Aktualisieren des Threads: {e}")

        member = interaction.guild.get_member(customer['discord_user_id'])
        if member:
            for insurance in customer.get('versicherungen', []):
                role_name = INSURANCE_TYPES[insurance]["role"]
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if role and role in member.roles:
                    await member.remove_roles(role)

        add_log_entry("AKTE_ARCHIVIERT", interaction.user.id, {
            "customer_id": customer_id,
            "customer_name": customer['rp_name'],
            "versicherungen": customer.get('versicherungen', []),
            "archived_at": get_now().isoformat()
        })

        log_embed = discord.Embed(
            title="Kundenakte archiviert!",
            color=COLOR_WARNING,
            timestamp=get_now()
        )
        log_embed.add_field(name="<:4189search:1473009466902315048> Kunden-ID", value=f"> `{customer_id}`", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Kunde", value=f"> {customer['rp_name']}", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Archiviert von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
        log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
        log_embed.set_footer(text=f"Copyright © InsuranceGuard v2")
        await send_to_log_channel(interaction.guild, log_embed)

        success_embed = discord.Embed(
            title="Akte erfolgreich archiviert!",
            description=f"Die Kundenakte `{customer_id}` wurde archiviert.",
            color=COLOR_SUCCESS
        )
        success_embed.set_author(name="Automatische Bestätigungsnachricht", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=300&height=300")
        success_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Fehler beim Archivieren der Akte: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="<:3518crossmark:1473009455473098894> Fehler!",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

@bot.tree.command(name="rechnung_archivieren", description="Markiert eine Rechnung als bezahlt und archiviert sie")
@app_commands.describe(invoice_id="Rechnungsnummer (z.B. RE-2412-A3F9)")
async def archive_invoice(interaction: discord.Interaction, invoice_id: str):
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur Mitarbeiter oder die Leitungsebene können eine Rechnung archivieren! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`\n> `Mitarbeiter`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    logger.info(f"Rechnung wird archiviert von User {interaction.user.id}: {invoice_id}")

    try:
        if invoice_id not in data['invoices']:
            error_embed = discord.Embed(
                title="<:3518crossmark:1473009455473098894> Rechnung nicht gefunden!",
                description=f"Es existiert keine Rechnung mit der Nummer `{invoice_id}`.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        invoice = data['invoices'][invoice_id]

        if invoice.get('paid', False):
            info_embed = discord.Embed(
                title="Rechnung bereits archiviert!",
                description=f"Die Rechnung `{invoice_id}` wurde bereits als bezahlt markiert.",
                color=COLOR_INFO
            )
            await interaction.followup.send(embed=info_embed, ephemeral=True)
            return

        customer_id = invoice['customer_id']
        customer = data['customers'].get(customer_id)

        if not customer:
            error_embed = discord.Embed(
                title="<:3518crossmark:1473009455473098894> Kunde nicht gefunden!",
                description=f"Kunde `{customer_id}` konnte nicht gefunden werden.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        data['invoices'][invoice_id]['paid'] = True
        data['invoices'][invoice_id]['paid_by'] = interaction.user.id
        data['invoices'][invoice_id]['paid_at'] = get_now().isoformat()
        data['invoices'][invoice_id]['archived'] = True
        data['invoices'][invoice_id]['reminder_count'] = 0
        save_data(data)

        try:
            channel = interaction.guild.get_channel(invoice['channel_id'])
            if channel:
                message = await channel.fetch_message(invoice['message_id'])
                updated_embed = message.embeds[0]
                for i, field in enumerate(updated_embed.fields):
                    if "Status" in field.name:
                        updated_embed.set_field_at(
                            i,
                            name="Status",
                            value=f"**Bezahlt am {get_now().strftime('%d.%m.%Y • %H:%M Uhr')}**\nArchiviert von: {interaction.user.mention}",
                            inline=False
                        )
                        break
                updated_embed.color = COLOR_SUCCESS
                await message.edit(embed=updated_embed)
                logger.info(f"Rechnung {invoice_id} im Channel als bezahlt markiert")
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Rechnung im Channel: {e}")

        add_log_entry("RECHNUNG_ARCHIVIERT", interaction.user.id, {
            "invoice_id": invoice_id,
            "customer_id": customer_id,
            "customer_name": customer['rp_name'],
            "betrag": invoice['betrag'],
            "betrag_netto": invoice.get('betrag_netto', 0),
            "steuer": invoice.get('steuer', 0),
            "paid_at": get_now().isoformat(),
            "channel_id": invoice['channel_id']
        })

        log_embed = discord.Embed(
            title="Rechnung archiviert!",
            color=COLOR_SUCCESS,
            timestamp=get_now()
        )
        log_embed.add_field(name="<:6224mail:1473009484753277130> Rechnungsnummer", value=f"> `{invoice_id}`", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Versicherungsnehmer", value=f"> {customer['rp_name']}\n> `{customer_id}`", inline=False)
        log_embed.add_field(name="__Abrechnung__", value=f"> Netto: `{invoice.get('betrag_netto', 0):,.2f} €`\n> Steuer (5%): `+ {invoice.get('steuer', 0):,.2f} €`\n> <:912926arrow:1473009547282092124> Brutto: **`{invoice['betrag']:,.2f} €`**", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Archiviert von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
        log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
        log_embed.set_footer(text=f"Copyright © InsuranceGuard v2")
        await send_to_log_channel(interaction.guild, log_embed)

        # In Kundenakte eintragen
        thread_id = customer.get('thread_id')
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id)
                if thread:
                    archive_embed = discord.Embed(
                        title="Archivierte Rechnung",
                        description="Diese Rechnung wurde als bezahlt markiert und archiviert.",
                        color=COLOR_SUCCESS,
                        timestamp=get_now()
                    )
                    archive_embed.add_field(name="__Rechnungsinformationen__", value=f"> <:6224mail:1473009484753277130> - `{invoice_id}`\n> <:1158refresh:1473009444077178993> Rechnungsdatum: {datetime.fromisoformat(invoice['created_at']).strftime('%d.%m.%Y')}\n> <:3518checkmark:1473009454202228959> Zahlungsdatum: {get_now().strftime('%d.%m.%Y')}", inline=False)
                    insurance_list = customer.get('versicherungen', [])
                    insurance_text = "\n".join(f"> ▸ {ins}" for ins in insurance_list)
                    archive_embed.add_field(name="__Positionen__", value=insurance_text if insurance_text else "> Keine", inline=False)
                    archive_embed.add_field(name="__Abrechnung__", value=f"> Netto: `{invoice.get('betrag_netto', 0):,.2f} €`\n> Steuer (5%): `+ {invoice.get('steuer', 0):,.2f} €`\n> <:912926arrow:1473009547282092124> Brutto: **`{invoice['betrag']:,.2f} €`**", inline=False)
                    archive_embed.add_field(name="<:7549member:1473009494794698794> Archiviert von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`", inline=False)
                    archive_embed.set_footer(text=f"Copyright © InsuranceGuard v2 • {get_now().strftime('%d.%m.%Y • %H:%M:%S')}")
                    await thread.send(embed=archive_embed)
                    logger.info(f"Rechnung {invoice_id} in Kundenakte gepostet")
            except Exception as e:
                logger.error(f"Fehler beim Posten in Kundenakte: {e}")

        success_embed = discord.Embed(
            title="Rechnung erfolgreich archiviert!",
            description=f"Die Rechnung `{invoice_id}` wurde als bezahlt markiert und archiviert.",
            color=COLOR_SUCCESS
        )
        success_embed.add_field(name="<:7549member:1473009494794698794> Kunde", value=f"> {customer['rp_name']}", inline=False)
        success_embed.add_field(name="<:9654dollar:1473009529414357053> Betrag", value=f"> `{invoice['betrag']:,.2f} €`", inline=False)
        await interaction.followup.send(embed=success_embed, ephemeral=True)
        logger.info(f"Rechnung {invoice_id} erfolgreich archiviert von User {interaction.user.id}")

    except Exception as e:
        logger.error(f"Fehler beim Archivieren der Rechnung: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="<:3518crossmark:1473009455473098894> Fehler beim Archivieren!",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

@tasks.loop(hours=24)
async def check_invoices():
    try:
        now = get_now()
        for invoice_id, invoice_data in list(data['invoices'].items()):
            if invoice_data.get('paid', False):
                continue
            due_date = datetime.fromisoformat(invoice_data['due_date'])
            if due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=GERMANY_TZ)
            days_overdue = (now - due_date).days
            if days_overdue < 0:
                continue
            reminder_count = invoice_data.get('reminder_count', 0)
            if days_overdue == 0 and reminder_count == 0:
                await send_reminder(invoice_id, invoice_data, 1, 0)
                data['invoices'][invoice_id]['reminder_count'] = 1
                save_data(data)
            elif days_overdue == 1 and reminder_count == 1:
                new_amount = invoice_data['original_betrag'] * 1.05
                data['invoices'][invoice_id]['betrag'] = new_amount
                await send_reminder(invoice_id, invoice_data, 2, 5)
                data['invoices'][invoice_id]['reminder_count'] = 2
                save_data(data)
            elif days_overdue == 2 and reminder_count == 2:
                new_amount = invoice_data['original_betrag'] * 1.10
                data['invoices'][invoice_id]['betrag'] = new_amount
                await send_reminder(invoice_id, invoice_data, 3, 10)
                data['invoices'][invoice_id]['reminder_count'] = 3
                save_data(data)
    except Exception as e:
        logger.error(f"Fehler bei Mahnungsprüfung: {e}", exc_info=True)

@tasks.loop(hours=3)
async def auto_backup():
    global _last_data_hash
    try:
        if not config.get("log_channel_id"):
            logger.info("Auto-Backup: Kein Log-Kanal konfiguriert, überspringe.")
            return
        current_hash = _get_data_hash()
        if current_hash == _last_data_hash:
            logger.info("Auto-Backup: Keine Änderungen seit dem letzten Backup – wird übersprungen.")
            return

        import zipfile, io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if os.path.exists(DATA_FILE):
                zip_file.write(DATA_FILE, arcname="insurance_data.json")
            if os.path.exists(CONFIG_FILE):
                zip_file.write(CONFIG_FILE, arcname="bot_config.json")
        zip_buffer.seek(0)

        timestamp_str = get_now().strftime("%Y%m%d_%H%M%S")
        file = discord.File(zip_buffer, filename=f"auto_backup_{timestamp_str}.zip")

        embed = discord.Embed(
            title="Automatisches Datenbank-Backup",
            color=COLOR_PRIMARY,
            timestamp=get_now()
        )
        embed.add_field(name="<:6523information:1473009486351565024> Information", value="> Alle `3 Stunden` werden die kompletten Daten des Bots in diesen Kanal gesendet, damit es bei einem Neustart zu keinem Datenverlust kommt.", inline=False)
        embed.add_field(name="<:2141file:1473009449412071484> Enthaltene Dateien", value="> <:2141file:1473009449412071484> - `insurance_data.json`\n> <:2141file:1473009449412071484> - `bot_config.json`", inline=False)
        embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
        embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")

        for guild in bot.guilds:
            log_channel = guild.get_channel(config["log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed, file=file)
                break

        _last_data_hash = current_hash
        logger.info(f"Auto-Backup erfolgreich gesendet um {get_now().strftime('%H:%M:%S')}")

    except Exception as e:
        logger.error(f"Fehler beim automatischen Backup: {e}", exc_info=True)

async def send_reminder(invoice_id, invoice_data, reminder_number, surcharge_percent):
    """Sendet eine Mahnung"""
    try:
        for guild in bot.guilds:
            channel = guild.get_channel(invoice_data['channel_id'])
            if not channel:
                continue
            customer = data['customers'].get(invoice_data['customer_id'])
            if not customer:
                continue
            customer_user = guild.get_member(customer['discord_user_id'])
            surcharge_text = f" (+{surcharge_percent}% Mahngebühr)" if surcharge_percent > 0 else ""

            embed = discord.Embed(
                title=f"{reminder_number}. Mahnung",
                description=f"Die Rechnung `{invoice_id}` ist überfällig!",
                color=COLOR_WARNING if reminder_number < 3 else COLOR_ERROR,
                timestamp=get_now()
            )
            embed.add_field(name="__Rechnungsinformationen__", value=f"> <:6224mail:1473009484753277130> - `{invoice_id}`\n> <:7549member:1473009494794698794> - {customer['rp_name']}\n> <:2533warning:1473009451647762515> - {reminder_number}. Mahnung", inline=False)
            embed.add_field(name="__Zahlungsinformationen__", value=f"> Ursprünglicher Betrag: `{invoice_data['original_betrag']:,.2f} €`\n> <:912926arrow:1473009547282092124> Aktueller Betrag: **`{invoice_data['betrag']:,.2f} €`**{surcharge_text}", inline=False)
            embed.set_footer(text="Bitte begleichen Sie den Betrag umgehend • Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")

            if customer_user:
                await channel.send(f"{customer_user.mention}", embed=embed)
            else:
                await channel.send(embed=embed)

            log_embed = discord.Embed(
                title=f"{reminder_number}. Mahnung versendet!",
                color=COLOR_WARNING if reminder_number < 3 else COLOR_ERROR,
                timestamp=get_now()
            )
            log_embed.add_field(name="<:6224mail:1473009484753277130> Rechnungsnummer", value=f"> `{invoice_id}`", inline=False)
            log_embed.add_field(name="<:7549member:1473009494794698794> Versicherungsnehmer", value=f"> {customer['rp_name']}\n> `{invoice_data['customer_id']}`", inline=False)
            log_embed.add_field(name="<:2533warning:1473009451647762515> Mahnstufe", value=f"> {reminder_number}. Mahnung", inline=False)
            log_embed.add_field(name="<:9654dollar:1473009529414357053> Beträge", value=f"> Ursprungsbetrag: `{invoice_data['original_betrag']:,.2f} €`\n> <:912926arrow:1473009547282092124> Neuer Betrag: **`{invoice_data['betrag']:,.2f} €`**\n> Mahngebühr: {f'+{surcharge_percent}%' if surcharge_percent > 0 else 'Keine'}", inline=False)
            log_embed.add_field(name="<:1041searchthreads:1473009441552203889> Channel", value=f"> {channel.mention}", inline=False)
            log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
            log_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
            await send_to_log_channel(guild, log_embed)

            add_log_entry(f"MAHNUNG_{reminder_number}", 0, {
                "invoice_id": invoice_id,
                "customer_id": invoice_data['customer_id'],
                "customer_name": customer['rp_name'],
                "surcharge": surcharge_percent,
                "original_betrag": invoice_data['original_betrag'],
                "neuer_betrag": invoice_data['betrag'],
                "channel_id": invoice_data['channel_id']
            })
            break

    except Exception as e:
        logger.error(f"Fehler beim Senden der Mahnung: {e}", exc_info=True)

# Ticket-System Views
class KundenkontaktView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Kundenkontakt anfragen!", style=discord.ButtonStyle.secondary, custom_id="open_kundenkontakt", emoji="<:6224mail:1473009484753277130>")
    async def open_kundenkontakt(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"Kundenkontakt-Button geklickt von User {interaction.user.id}")
        await interaction.response.send_modal(TicketModal())

class SchadensmeldungView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Schadensmeldung einreichen!", style=discord.ButtonStyle.secondary, custom_id="open_schadensmeldung", emoji="<:6224mail:1473009484753277130>")
    async def open_schadensmeldung(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"Schadensmeldungs-Button geklickt von User {interaction.user.id}")
        await interaction.response.send_modal(SchadensmeldungModal())

class TicketModal(discord.ui.Modal, title="Kundenkontakt-Anfrage"):
    customer_id_input = discord.ui.TextInput(
        label="Versicherungsnehmer-ID",
        placeholder="VN-XXXXXXXX",
        required=True,
        max_length=11
    )
    reason = discord.ui.TextInput(
        label="Grund der Kontaktaufnahme",
        style=discord.TextStyle.paragraph,
        placeholder="Bitte beschreiben Sie detailliert den Anlass für die Kontaktaufnahme.",
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        logger.info(f"Ticket wird erstellt von User {interaction.user.id}")

        try:
            customer_id = self.customer_id_input.value

            if customer_id not in data['customers']:
                error_embed = discord.Embed(
                    title="<:3518crossmark:1473009455473098894> Kunde nicht gefunden!",
                    description=f"Es existiert keine Akte mit der Versicherungsnehmer-ID `{customer_id}`.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            customer = data['customers'][customer_id]
            guild = interaction.guild

            category = None
            if config.get("kundenkontakt_category_id"):
                category = guild.get_channel(config["kundenkontakt_category_id"])

            if not category:
                error_embed = discord.Embed(
                    title="<:3518crossmark:1473009455473098894> Kategorie nicht konfiguriert!",
                    description="Die Kundenkontakt-Kategorie wurde noch nicht eingerichtet.\n\nBitte nutze `/kundenkontakt_kategorie_setzen` um eine Kategorie festzulegen.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            customer_user = guild.get_member(customer['discord_user_id'])
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.get_role(MITARBEITER_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.get_role(LEITUNGSEBENE_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            if customer_user:
                overwrites[customer_user] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            ticket_channel = await category.create_text_channel(
                name=f"kontakt-{customer_id.lower()}",
                topic=f"Kundenkontakt: {customer['rp_name']} | {customer_id}",
                overwrites=overwrites
            )

            embed = discord.Embed(
                title="🎫 Support-Ticket",
                description="**Kundenkontakt-Anfrage**\n\nEin neues Support-Ticket wurde erfolgreich erstellt.",
                color=COLOR_INFO,
                timestamp=get_now()
            )
            embed.add_field(name="__Ticketinformationen__", value=f"> <:1158refresh:1473009444077178993> - {get_now().strftime('%d.%m.%Y • %H:%M')}\n> <:4189search:1473009466902315048> - `{customer_id}`", inline=False)
            embed.add_field(name="__Beteiligte Personen__", value=f"> <:7549member:1473009494794698794> Mitarbeiter: {interaction.user.mention}\n> <:7549member:1473009494794698794> Versicherungsnehmer: {customer['rp_name']}", inline=False)
            embed.add_field(name="__Anlass der Kontaktaufnahme__", value=self.reason.value, inline=False)
            insurance_info = "\n".join(f"> ▸ {ins}" for ins in customer['versicherungen'])
            embed.add_field(name="__Kundeninformationen__", value=f"{insurance_info}\n> <:9654dollar:1473009529414357053> Monatsbeitrag: `{customer['total_monthly_price']:,.2f} €`\n> <:8312card:1473009505041256501> Kartennummer: `{customer['hbpay_nummer']}`\n> <:9847public:1473009530962055291> Economy-ID: `{customer['economy_id']}`", inline=False)
            embed.set_footer(text="Nutzen Sie den Button unten, um dieses Ticket zu schließen • Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")

            close_view = TicketCloseView(ticket_channel.id, customer_id)
            mentions = [interaction.user.mention]
            if customer_user:
                mentions.append(customer_user.mention)
            await ticket_channel.send(" ".join(mentions), embed=embed, view=close_view)

            add_log_entry("TICKET_ERSTELLT", interaction.user.id, {
                "customer_id": customer_id,
                "customer_name": customer['rp_name'],
                "channel_id": ticket_channel.id,
                "channel_name": ticket_channel.name,
                "reason": self.reason.value[:100]
            })

            log_embed = discord.Embed(
                title="Neues Support-Ticket!",
                color=COLOR_INFO,
                timestamp=get_now()
            )
            log_embed.add_field(name="<:4748ticket:1473009472422154311> Ticket-Channel", value=f"> {ticket_channel.mention}", inline=False)
            log_embed.add_field(name="<:7549member:1473009494794698794> Versicherungsnehmer", value=f"> {customer['rp_name']}\n> `{customer_id}`", inline=False)
            log_embed.add_field(name="<:7549member:1473009494794698794> Erstellt von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
            log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
            log_embed.set_footer(text=f"Copyright © InsuranceGuard v2")
            await send_to_log_channel(interaction.guild, log_embed)

            success_embed = discord.Embed(
                title="Ticket erfolgreich erstellt!",
                description="Die Kundenkontakt-Anfrage wurde erstellt.",
                color=COLOR_SUCCESS
            )
            success_embed.add_field(name="<:4748ticket:1473009472422154311> Ticket-Channel", value=f"> {ticket_channel.mention}", inline=False)
            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Tickets: {e}", exc_info=True)
            error_embed = discord.Embed(
                title="<:3518crossmark:1473009455473098894> Fehler bei der Ticket-Erstellung!",
                description=f"Es ist ein Fehler aufgetreten: {str(e)}",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

class SchadensmeldungModal(discord.ui.Modal, title="Schadensmeldung einreichen"):
    customer_id_input = discord.ui.TextInput(
        label="Versicherungsnehmer-ID",
        placeholder="VN-24123456",
        required=True,
        max_length=20
    )
    geschaedigter = discord.ui.TextInput(
        label="Geschädigter (RP-Name)",
        placeholder="Max Mustermann",
        required=True,
        max_length=100
    )
    taeter = discord.ui.TextInput(
        label="Täter (RP-Name)",
        placeholder="John Doe",
        required=True,
        max_length=100
    )
    beschreibung = discord.ui.TextInput(
        label="Beschreibung des Vorfalls",
        style=discord.TextStyle.paragraph,
        placeholder="Bitte beschreiben Sie den Vorfall so detailliert wie möglich...",
        required=True,
        max_length=1000
    )
    rechnung = discord.ui.TextInput(
        label="Rechnung/Zahlungsnachweis",
        placeholder="Rechnungsnummer oder Link zum Nachweis",
        required=True,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        logger.info(f"Schadensmeldung wird erstellt von User {interaction.user.id}")

        try:
            customer_id = self.customer_id_input.value

            if customer_id not in data['customers']:
                error_embed = discord.Embed(
                    title="<:3518crossmark:1473009455473098894> Kunde nicht gefunden!",
                    description=f"Es existiert keine Akte mit der Versicherungsnehmer-ID `{customer_id}`.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            customer = data['customers'][customer_id]
            guild = interaction.guild

            category = None
            if config.get("schadensmeldung_category_id"):
                category = guild.get_channel(config["schadensmeldung_category_id"])

            if not category:
                error_embed = discord.Embed(
                    title="<:3518crossmark:1473009455473098894> Kategorie nicht konfiguriert!",
                    description="Die Schadensmeldungs-Kategorie wurde noch nicht eingerichtet.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.get_role(MITARBEITER_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.get_role(LEITUNGSEBENE_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            customer_user = guild.get_member(customer['discord_user_id'])
            if customer_user:
                overwrites[customer_user] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            ticket_channel = await category.create_text_channel(
                name=f"schaden-{customer_id.lower()}",
                topic=f"Schadensmeldung: {customer['rp_name']} | {customer_id}",
                overwrites=overwrites
            )

            embed = discord.Embed(
                title="⚠️ Schadensmeldung",
                description="**Eine neue Schadensmeldung wurde eingereicht**\n\nBitte prüfen Sie die Angaben und bearbeiten Sie den Fall zeitnah.",
                color=COLOR_DAMAGE,
                timestamp=get_now()
            )
            embed.add_field(name="__Schadensfallinformationen__", value=f"> <:7549member:1473009494794698794> Kunde: {customer['rp_name']} (`{customer_id}`)\n> <:7549member:1473009494794698794> Gemeldet von: {interaction.user.mention}", inline=False)
            embed.add_field(name="__Beteiligte Personen__", value=f"> <:7549member:1473009494794698794> Geschädigter: {self.geschaedigter.value}\n> <:7549member:1473009494794698794> Täter: {self.taeter.value}", inline=False)
            embed.add_field(name="__Beschreibung__", value=self.beschreibung.value, inline=False)
            embed.add_field(name="__Nachweis__", value=f"> {self.rechnung.value}", inline=False)
            embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")

            close_view = TicketCloseView(ticket_channel.id, customer_id)
            await ticket_channel.send(f"{interaction.user.mention}", embed=embed, view=close_view)

            success_embed = discord.Embed(
                title="Schadensmeldung erfolgreich eingereicht!",
                description=f"Ihre Schadensmeldung wurde erstellt: {ticket_channel.mention}",
                color=COLOR_SUCCESS
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Fehler: {e}")
            await interaction.followup.send(f"Fehler: {e}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self, channel_id, customer_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.customer_id = customer_id

    @discord.ui.button(label="Ticket schließen", style=discord.ButtonStyle.danger, custom_id="close_ticket", emoji="<:3518crossmark:1473009455473098894>")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_mitarbeiter(interaction):
            error_embed = discord.Embed(
                title="Zugriff verweigert!",
                description="> Nur Mitarbeiter und Leitungsebene können Tickets schließen.",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        channel = interaction.channel
        close_embed = discord.Embed(
            title="Ticket wird geschlossen!",
            description=f"Dieses Ticket wird in 5 Sekunden geschlossen und archiviert.\n\n> <:7549member:1473009494794698794> Geschlossen von: {interaction.user.mention}",
            color=COLOR_WARNING,
            timestamp=get_now()
        )
        close_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=close_embed)

        log_embed = discord.Embed(
            title="Support-Ticket geschlossen!",
            color=COLOR_WARNING,
            timestamp=get_now()
        )
        log_embed.add_field(name="<:4748ticket:1473009472422154311> Ticket-Channel", value=f"> {channel.mention}\n> `{channel.name}`", inline=False)
        log_embed.add_field(name="<:4189search:1473009466902315048> Kunden-ID", value=f"> `{self.customer_id}`", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Geschlossen von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
        log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
        log_embed.set_footer(text=f"Copyright © InsuranceGuard v2")
        await send_to_log_channel(interaction.guild, log_embed)

        add_log_entry("TICKET_GESCHLOSSEN", interaction.user.id, {
            "customer_id": self.customer_id,
            "channel_id": self.channel_id,
            "channel_name": channel.name,
            "closed_at": get_now().isoformat()
        })

        import asyncio
        await asyncio.sleep(5)
        await channel.delete(reason=f"Ticket geschlossen von {interaction.user}")

@bot.tree.command(name="add", description="Fügt eine Person zum aktuellen Ticket hinzu")
@app_commands.describe(user="Der User, der hinzugefügt werden soll")
async def add_user_to_ticket(interaction: discord.Interaction, user: discord.Member):
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur Mitarbeiter oder die Leitungsebene können Personen zu einem Ticket hinzufügen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`\n> `Mitarbeiter`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    if not (interaction.channel.name.startswith("kontakt-") or interaction.channel.name.startswith("schaden-")):
        return await interaction.response.send_message("<:3518crossmark:1473009455473098894> Dieser Befehl kann nur in Ticket-Channels genutzt werden.", ephemeral=True)

    await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)

    embed = discord.Embed(
        title="Person hinzugefügt!",
        description=f"> {interaction.user.mention} hat {user.mention} zum Ticket hinzugefügt.",
        color=COLOR_SUCCESS
    )
    embed.set_author(name="Manuelle Ticketbearbeitung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473693772415238338/8879-edit.png?ex=699723c7&is=6995d247&hm=54021e8ead61dbbbc69fee66c106d13bae3f13f8e0443bc1ae0972a19efbddf9&=&format=webp&quality=lossless&width=250&height=250")
    embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove", description="Entfernt eine Person vom aktuellen Ticket")
@app_commands.describe(user="Der User, der entfernt werden soll")
async def remove_user_from_ticket(interaction: discord.Interaction, user: discord.Member):
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur Mitarbeiter oder die Leitungsebene können Personen aus einem Ticket entfernen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`\n> `Mitarbeiter`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    if not (interaction.channel.name.startswith("kontakt-") or interaction.channel.name.startswith("schaden-")):
        return await interaction.response.send_message("<:3518crossmark:1473009455473098894> Dieser Befehl kann nur in Ticket-Channels genutzt werden.", ephemeral=True)

    await interaction.channel.set_permissions(user, overwrite=None)

    embed = discord.Embed(
        title="Person entfernt!",
        description=f"> {interaction.user.mention} hat {user.mention} aus dem Ticket entfernt!",
        color=COLOR_WARNING
    )
    embed.set_author(name="Manuelle Ticketbearbeitung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473693772415238338/8879-edit.png?ex=699723c7&is=6995d247&hm=54021e8ead61dbbbc69fee66c106d13bae3f13f8e0443bc1ae0972a19efbddf9&=&format=webp&quality=lossless&width=250&height=250")
    embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="kundenkontakt_setup", description="Richtet das Kundenkontakt-System ein")
@app_commands.describe(channel="Channel für das Kundenkontakt-Panel")
async def setup_kundenkontakt(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann das Kundenkontakt-System Setup durchführen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    logger.info(f"Kundenkontakt-System wird eingerichtet von User {interaction.user.id} in Channel {channel.id}")

    try:
        config["kundenkontakt_channel_id"] = channel.id
        save_config(config)

        embed = discord.Embed(
            title="Kundenkontakt",
            description="Liebe Mitarbeiter:innen,\n> hier können sie mit unseren Kunden kontakt aufnehmen, um ihnen eine Rechnung auszustellen, sie über Änderungen, etc. zu informieren.",
            color=COLOR_PRIMARY,
            timestamp=get_now()
        )
        embed.add_field(name="__Wie funktioniert das System?__",
            value=(
                "> 1. Klicken Sie unten auf den Button!\n"
                "> 2. Geben Sie die Kunden-ID ein!\n"
                "> 3. Beschreiben Sie einen detaillierten Kontaktgrund!\n"
                "> 4. Ein privater Ticket-Channel wird erstellt!\n"), inline=False)
        embed.add_field(name="__Was bringt mir das System?__",
            value=(
                "> ▸ Automatischer privater Kanal in einer separaten Kategorie!\n"
                "> ▸ Kanalname: `kontakt-[kunden-id]`\n"
                "> ▸ Versicherungsnehmer wird automatisch benachrichtigt!\n"
                "> ▸ Alle Kundeninformationen direkt verfügbar!\n"), inline=False)
        embed.add_field(name="__Was muss ich beim Verwenden beachten?__",
            value=(
                "> ▸ Gültige **Kunden-ID** erforderlich!\n"
                "> ▸ Kontaktgrund **detailliert** beschreiben!\n"
                "> ▸ Nur für **Mitarbeiter** und **Leitungsebene**!\n"), inline=False)
        embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")

        view = KundenkontaktView()
        await channel.send(embed=embed, view=view)

        success_embed = discord.Embed(
            title="<:3518checkmark:1473009454202228959> Kundenkontakt-System aktiviert!",
            description=f"Das Kundenkontakt-System wurde erfolgreich in {channel.mention} eingerichtet.",
            color=COLOR_SUCCESS
        )
        await interaction.response.send_message(embed=success_embed, ephemeral=True)

        add_log_entry("KUNDENKONTAKT_SYSTEM_SETUP", interaction.user.id, {
            "channel_id": channel.id, "channel_name": channel.name,
            "guild_id": interaction.guild.id, "guild_name": interaction.guild.name
        })

        log_embed = discord.Embed(
            title="Kundenkontakt-System eingerichtet!",
            color=COLOR_INFO,
            timestamp=get_now()
        )
        log_embed.add_field(name="<:4748ticket:1473009472422154311> Panel-Channel", value=f"> {channel.mention}\n> - `{channel.name}`\n> - `{channel.id}`", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Eingerichtet von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
        log_embed.add_field(name="<:9847public:1473009530962055291> Serverinformationen", value=f"> - `{interaction.guild.name}`\n> - `{interaction.guild.id}`", inline=False)
        log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
        log_embed.set_footer(text=f"Copyright © InsuranceGuard v2")
        await send_to_log_channel(interaction.guild, log_embed)

    except Exception as e:
        logger.error(f"Fehler beim Einrichten des Kundenkontakt-Systems: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="<:3518crossmark:1473009455473098894> Fehler beim Setup!",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

@bot.tree.command(name="schadensmeldung_setup", description="Richtet das Schadensmeldungs-System ein")
@app_commands.describe(channel="Channel für das Schadensmeldungs-Panel")
async def setup_schadensmeldung(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann das Schadensmeldungs-System Setup durchführen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    logger.info(f"Schadensmeldungs-System wird eingerichtet von User {interaction.user.id} in Channel {channel.id}")

    try:
        config["schadensmeldung_channel_id"] = channel.id
        save_config(config)

        embed = discord.Embed(
            title="Schadensmeldung",
            description="Liebe Versicherungsnehmer:innen,\n> hier können sie Schadensmeldungen einreichen, welche sie hier gerne wieder erstattet haben wollen.",
            color=COLOR_PRIMARY,
            timestamp=get_now()
        )
        embed.add_field(name="__Wie funktioniert das System?__",
            value=(
                "> 1. Klicken Sie auf den Button unten!\n"
                "> 2. Geben Sie Ihre Kunden-ID ein!\n"
                "> 3. Füllen Sie das Schadensmeldungs-Formular aus!\n"
                "> 4. Ein Schadensfall-Ticket wird erstellt!\n"), inline=False)
        embed.add_field(name="__Welche Angaben sind erforderlich?__",
            value=(
                "> ▸ **Kunden-ID** (Ihre Versicherungsnehmer-ID)\n"
                "> ▸ **Geschädigter** (RP-Name)\n"
                "> ▸ **Täter** (RP-Name)\n"
                "> ▸ **Vorfallbeschreibung** (detailliert)\n"
                "> ▸ **Rechnung/Nachweis** (Nummer oder Link)\n"), inline=False)
        embed.add_field(name="__Was bringt mir das System?__",
            value=(
                "> ▸ Privater Kanal in **Schadensmeldungen**\n"
                "> ▸ Kanal-Name: `schaden-[kunden-id]`\n"
                "> ▸ Mitarbeiter werden automatisch benachrichtigt\n"
                "> ▸ Eindeutige Schadensnummer wird vergeben!"), inline=False)
        embed.add_field(name="__Was muss ich beim Verwenden beachten?__",
            value=(
                "> ▸ Nur **Ihre eigene Kunden-ID** verwenden!\n"
                "> ▸ Vorfall **so detailliert wie möglich** beschreiben!\n"
                "> ▸ **Nachweise** beifügen (Rechnungen, Fotos, etc.)!"), inline=False)
        embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")

        view = SchadensmeldungView()
        await channel.send(embed=embed, view=view)

        success_embed = discord.Embed(
            title="<:3518checkmark:1473009454202228959> Schadensmeldungs-System aktiviert!",
            description=f"Das Schadensmeldungs-System wurde erfolgreich in {channel.mention} eingerichtet.",
            color=COLOR_SUCCESS
        )
        await interaction.response.send_message(embed=success_embed, ephemeral=True)

        add_log_entry("SCHADENSMELDUNG_SYSTEM_SETUP", interaction.user.id, {
            "channel_id": channel.id, "channel_name": channel.name,
            "guild_id": interaction.guild.id, "guild_name": interaction.guild.name
        })

        log_embed = discord.Embed(
            title="Schadensmeldungs-System eingerichtet!",
            color=COLOR_INFO,
            timestamp=get_now()
        )
        log_embed.add_field(name="<:4748ticket:1473009472422154311> Panel-Channel", value=f"> {channel.mention}\n> - `{channel.name}`\n> - `{channel.id}`", inline=False)
        log_embed.add_field(name="<:7549member:1473009494794698794> Eingerichtet von", value=f"> {interaction.user.mention}\n> - `{interaction.user.name}`\n> - `{interaction.user.id}`", inline=False)
        log_embed.add_field(name="<:9847public:1473009530962055291> Serverinformationen", value=f"> - `{interaction.guild.name}`\n> - `{interaction.guild.id}`", inline=False)
        log_embed.add_field(name="<:1158refresh:1473009444077178993> Zeitstempel", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}", inline=False)
        log_embed.set_footer(text=f"Copyright © InsuranceGuard v2")
        await send_to_log_channel(interaction.guild, log_embed)

    except Exception as e:
        logger.error(f"Fehler beim Einrichten des Schadensmeldungs-Systems: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="<:3518crossmark:1473009455473098894> Fehler beim Setup!",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

@bot.tree.command(name="logs_anzeigen", description="Zeigt die letzten Bot-Aktivitäten an")
@app_commands.describe(anzahl="Anzahl der anzuzeigenden Log-Einträge (Standard: 10)")
async def show_logs(interaction: discord.Interaction, anzahl: int = 10):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="Zugriff verweigert!",
            description="> Nur die Leitungsebene kann sich die Logs anzeigen lassen! Sollte ein Problem vorliegen wende dich an die Leitungsebene in [#kontaktbüro](https://discord.com/channels/1408794976615268384/1408814352538009780).",
            color=COLOR_ERROR
        )
        error_embed.set_author(name="Automatische Berechtigungsprüfung", icon_url="https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250")
        error_embed.add_field(name="<:7842privacy:1473009500775776256> Benötigte Berechtigung", value="> `Leitungsebene`", inline=False)
        error_embed.set_footer(text="Copyright © InsuranceGuard v2", icon_url="https://images-ext-1.discordapp.net/external/apH8DmRAkI4ThoO_8isatg__epwxlBRj4YKfqu5DB2E/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1452736308077133935/f059c923cd5a8e10650f706126df6549.png?format=webp&quality=lossless&width=309&height=309")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    logger.info(f"Logs werden abgerufen von User {interaction.user.id}")
    await interaction.response.defer(ephemeral=True)

    try:
        if not data['logs']:
            info_embed = discord.Embed(
                title="Keine Logs vorhanden!",
                description="Es sind noch keine Aktivitäten protokolliert worden.",
                color=COLOR_INFO
            )
            await interaction.followup.send(embed=info_embed, ephemeral=True)
            return

        recent_logs = data['logs'][-anzahl:]
        recent_logs.reverse()

        embed = discord.Embed(
            title="System-Aktivitätsprotokoll",
            description=f"**Letzte {len(recent_logs)} Systemaktivitäten**",
            color=COLOR_PRIMARY,
            timestamp=get_now()
        )

        action_emojis = {
            "KUNDENAKTE_ERSTELLT": "<:6523information:1473009486351565024>",
            "RECHNUNG_ERSTELLT": "<:6224mail:1473009484753277130>",
            "RECHNUNG_BEZAHLT": "<:9654dollar:1473009529414357053>",
            "RECHNUNG_ARCHIVIERT": "<:1041searchthreads:1473009441552203889>",
            "MAHNUNG_1": "<:2533warning:1473009451647762515>",
            "MAHNUNG_2": "<:2533warning:1473009451647762515>",
            "MAHNUNG_3": "<:2533warning:1473009451647762515>",
            "TICKET_ERSTELLT": "<:4748ticket:1473009472422154311>",
            "TICKET_GESCHLOSSEN": "<:4748ticket:1473009472422154311>",
            "SCHADENSMELDUNG_ERSTELLT": "<:4748ticket:1473009472422154311>",
            "AKTE_ARCHIVIERT": "<:1041searchthreads:1473009441552203889>",
            "AUSZAHLUNG_EINGEREICHT": "💰",
            "AUSZAHLUNG_BESTAETIGT": "✅",
            "AUSZAHLUNG_ABGELEHNT": "❌",
            "AUSZAHLUNG_KANAL_GESETZT": "<:8586slashcommand:1473009513006366771>",
        }

        action_names = {
            "KUNDENAKTE_ERSTELLT": "Kundenakte erstellt",
            "RECHNUNG_ERSTELLT": "Rechnung ausgestellt",
            "RECHNUNG_BEZAHLT": "Rechnung bezahlt",
            "RECHNUNG_ARCHIVIERT": "Rechnung archiviert",
            "MAHNUNG_1": "1. Mahnung versendet",
            "MAHNUNG_2": "2. Mahnung (+5%)",
            "MAHNUNG_3": "3. Mahnung (+10%)",
            "TICKET_ERSTELLT": "Ticket erstellt",
            "TICKET_GESCHLOSSEN": "Ticket geschlossen",
            "SCHADENSMELDUNG_ERSTELLT": "Schadensmeldung eingereicht",
            "AKTE_ARCHIVIERT": "Akte archiviert",
            "AUSZAHLUNG_EINGEREICHT": "Auszahlungsantrag eingereicht",
            "AUSZAHLUNG_BESTAETIGT": "Auszahlung bestätigt",
            "AUSZAHLUNG_ABGELEHNT": "Auszahlung abgelehnt",
            "AUSZAHLUNG_KANAL_GESETZT": "Auszahlungs-Kanal konfiguriert",
        }

        for idx, log in enumerate(recent_logs, 1):
            timestamp = datetime.fromisoformat(log['timestamp']).strftime('%d.%m.%Y • %H:%M:%S')
            user = interaction.guild.get_member(log['user_id']) if log['user_id'] != 0 else None
            user_name = user.mention if user else "🤖 **System**"

            action = log['action']
            emoji = action_emojis.get(action, "📌")
            action_display = action_names.get(action, action)

            details_list = []
            for k, v in log['details'].items():
                if k == 'reason':
                    continue
                if k == 'customer_id':
                    details_list.append(f"Kunden-ID: `{v}`")
                elif k == 'customer_name':
                    details_list.append(f"Kunde: **{v}**")
                elif k == 'invoice_id':
                    details_list.append(f"Rechnung: `{v}`")
                elif k == 'auszahlung_id':
                    details_list.append(f"Auszahlung: `{v}`")
                elif k == 'versicherung':
                    details_list.append(f"Versicherung: {v}")
                elif k == 'channel_name':
                    details_list.append(f"Channel: {v}")
                elif 'betrag' in k.lower() or 'price' in k.lower():
                    if isinstance(v, (int, float)):
                        details_list.append(f"{k.replace('_', ' ').title()}: **{v:,.2f} €**")
                elif k == 'versicherungen':
                    if isinstance(v, list) and v:
                        details_list.append(f"Versicherungen: {len(v)} Verträge")

            details_text = "\n".join(f"> {d}" for d in details_list[:5]) if details_list else "> —"

            embed.add_field(
                name=f"{emoji} {action_display}",
                value=(f"> **{timestamp}**\n> {user_name}\n{details_text}"),
                inline=False
            )

        embed.set_footer(
            text=f"Angefordert von {interaction.user.display_name} • Copyright © InsuranceGuard v2",
            icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Fehler beim Anzeigen der Logs: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="Fehler beim Laden der Logs!",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

# Für Render: Keep-Alive mit Flask
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "InsuranceGuard v2 läuft erfolgreich!"

@app.route('/health')
def health():
    return {"status": "healthy", "bot": bot.user.name if bot.user else "starting"}

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Bot starten
if __name__ == "__main__":
    keep_alive()
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("DISCORD_TOKEN nicht gefunden! Bitte in Render-Umgebungsvariablen setzen.")
    else:
        logger.info("Bot wird gestartet...")
        bot.run(token)
