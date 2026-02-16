import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
import logging
import random
import string
import shutil
import re

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
BACKUP_DIR = "backups"

# Backup-Verzeichnis erstellen
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

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
            data = json.load(f)
            # Migration für alte Datenstrukturen
            if "auszahlungen" not in data:
                data["auszahlungen"] = {}
            if "backup_config" not in data:
                data["backup_config"] = {"enabled": False, "channel_id": None, "interval": "24h", "interval_minutes": 1440, "last_backup": datetime.now().isoformat()}
            # Versicherungsguthaben zu Kunden hinzufügen wenn nicht vorhanden
            for customer_id, customer in data.get("customers", {}).items():
                if "guthaben" not in customer:
                    customer["guthaben"] = 50000.00  # Standard: 50.000€
                if "guthaben_history" not in customer:
                    customer["guthaben_history"] = []
            return data
    logger.warning("Keine Datendatei gefunden, erstelle neue Datenstruktur")
    return {
        "customers": {}, 
        "invoices": {}, 
        "logs": [], 
        "schadensmeldungen": {},
        "auszahlungen": {},
        "backup_config": {"enabled": False, "channel_id": None, "interval": "24h", "interval_minutes": 1440, "last_backup": datetime.now().isoformat()}
    }

def save_data(data_to_save):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)
    logger.info("Daten erfolgreich gespeichert")

def create_backup():
    """Erstellt ein Backup der Datenbank"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
        shutil.copy2(DATA_FILE, backup_file)
        logger.info(f"Backup erstellt: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des Backups: {e}")
        return None

def parse_time_interval(interval_str):
    """Konvertiert Zeitangaben wie '1h', '30m', '7d' in Minuten"""
    match = re.match(r'(\d+)([mhdw])', interval_str.lower())
    if not match:
        return None
    
    value, unit = match.groups()
    value = int(value)
    
    if unit == 'm':
        return value
    elif unit == 'h':
        return value * 60
    elif unit == 'd':
        return value * 60 * 24
    elif unit == 'w':
        return value * 60 * 24 * 7
    return None

def generate_customer_id():
    """Generiert eine komplexe Kunden-ID"""
    prefix = "VN"
    year = datetime.now().strftime("%y")
    random_part = ''.join(random.choices(string.digits, k=6))
    return f"{prefix}-{year}{random_part}"

def generate_invoice_id():
    """Generiert eine komplexe Rechnungs-ID"""
    prefix = "RE"
    year = datetime.now().strftime("%y")
    month = datetime.now().strftime("%m")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{year}{month}-{random_part}"

def generate_schaden_id():
    """Generiert eine Schadensmeldungs-ID"""
    prefix = "SM"
    year = datetime.now().strftime("%y")
    month = datetime.now().strftime("%m")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{year}{month}-{random_part}"

def generate_auszahlung_id():
    """Generiert eine Auszahlungs-ID"""
    prefix = "AZ"
    year = datetime.now().strftime("%y")
    month = datetime.now().strftime("%m")
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

def add_log_entry(action, user_id, details):
    """Fügt einen Log-Eintrag hinzu"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "user_id": user_id,
        "details": details
    }
    data['logs'].append(log_entry)
    save_data(data)
    logger.info(f"Log erstellt: {action} von User {user_id}")

def add_guthaben_history(customer_id, betrag, typ, beschreibung, user_id):
    """Fügt einen Eintrag zur Guthaben-Historie hinzu"""
    if customer_id not in data['customers']:
        return

    if 'guthaben_history' not in data['customers'][customer_id]:
        data['customers'][customer_id]['guthaben_history'] = []

    entry = {
        "timestamp": datetime.now().isoformat(),
        "betrag": betrag,
        "typ": typ,  # "auszahlung", "aufladung", "abzug"
        "beschreibung": beschreibung,
        "user_id": user_id,
        "guthaben_nach": data['customers'][customer_id]['guthaben']
    }
    data['customers'][customer_id]['guthaben_history'].append(entry)
    save_data(data)

data = load_data()

# Versicherungstypen mit Preisen und zugehörigen Rollen
INSURANCE_TYPES = {
    "Krankenversicherung (Gesetzlich)": {"price": 3000.00, "role": "Krankenversicherung"},
    "Krankenversicherung (Privat)": {"price": 5000.00, "role": "Krankenversicherung"},
    "Haftpflichtversicherung": {"price": 3000.00, "role": "Haftpflichtversicherung"},
    "Hausratversicherung": {"price": 10000.00, "role": "Hausratversicherung"},
    "Kfz-Versicherung": {"price": 3000.00, "role": "Kfz-Versicherung"},
    "Rechtsschutzversicherung": {"price": 3000.00, "role": "Rechtsschutzversicherung"},
    "Berufsunfähigkeitsversicherung": {"price": 6000.00, "role": "Berufsunfähigkeitsversicherung"}
}

# Farbschema
COLOR_PRIMARY = 0x2C3E50
COLOR_SUCCESS = 0x27AE60
COLOR_WARNING = 0xE67E22
COLOR_ERROR = 0xC0392B
COLOR_INFO = 0x3498DB
COLOR_DAMAGE = 0xE74C3C

# Rollen-IDs
MITARBEITER_ROLE_ID = 1234567890  # HIER DIE RICHTIGE ROLLEN-ID EINTRAGEN!
LEITUNGSEBENE_ROLE_ID = 9876543210  # HIER DIE RICHTIGE ROLLEN-ID EINTRAGEN!

# Hilfsfunktionen für Berechtigungen
def is_mitarbeiter(interaction: discord.Interaction) -> bool:
    """Prüft ob User Mitarbeiter oder Leitung ist"""
    mitarbeiter_role = interaction.guild.get_role(MITARBEITER_ROLE_ID)
    leitungsebene_role = interaction.guild.get_role(LEITUNGSEBENE_ROLE_ID)

    return (mitarbeiter_role and mitarbeiter_role in interaction.user.roles) or \
           (leitungsebene_role and leitungsebene_role in interaction.user.roles)

def is_leitungsebene(interaction: discord.Interaction) -> bool:
    """Prüft ob User Leitungsebene ist"""
    leitungsebene_role = interaction.guild.get_role(LEITUNGSEBENE_ROLE_ID)
    return leitungsebene_role and leitungsebene_role in interaction.user.roles

@bot.event
async def on_ready():
    logger.info(f'{bot.user} erfolgreich gestartet')

    # Persistente Views registrieren damit alle Buttons funktionieren
    bot.add_view(KundenkontaktView())
    bot.add_view(SchadensmeldungView())
    bot.add_view(TicketCloseView(0, ""))  # Dummy-View für Custom-IDs
    logger.info("Persistente Views registriert - Alle Buttons funktionieren nun")

    try:
        synced = await bot.tree.sync()
        logger.info(f'{len(synced)} Slash Commands synchronisiert')
        check_invoices.start()  # Mahnung-System starten
        auto_backup.start()  # Auto-Backup starten
    except Exception as e:
        logger.error(f'Fehler beim Synchronisieren der Commands: {e}')

# BACKUP COMMANDS

@bot.tree.command(name="backup", description="Konfiguriert automatische Backups")
@app_commands.describe(
    kanal="Channel für Backup-Dateien",
    zeit="Backup-Intervall (z.B. 30m, 1h, 6h, 1d, 1w)"
)
async def setup_backup(interaction: discord.Interaction, kanal: discord.TextChannel, zeit: str):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann Backups konfigurieren.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    interval_minutes = parse_time_interval(zeit)
    if not interval_minutes:
        error_embed = discord.Embed(
            title="❌ Ungültiges Zeitformat",
            description="Bitte verwende ein gültiges Format: `30m`, `1h`, `6h`, `1d`, `1w`",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    data['backup_config'] = {
        "enabled": True,
        "channel_id": kanal.id,
        "interval": zeit,
        "interval_minutes": interval_minutes,
        "last_backup": datetime.now().isoformat()
    }
    save_data(data)

    # Sofortiges Backup erstellen
    backup_file = create_backup()
    if backup_file:
        await kanal.send(
            f"🔄 **Backup-System aktiviert**\n\n"
            f"**Intervall:** Alle {zeit}\n"
            f"**Erstes Backup:** {datetime.now().strftime('%d.%m.%Y • %H:%M:%S')}",
            file=discord.File(backup_file)
        )

    success_embed = discord.Embed(
        title="✅ Backup-System konfiguriert",
        description=f"Automatische Backups werden alle **{zeit}** in {kanal.mention} gesendet.",
        color=COLOR_SUCCESS
    )
    success_embed.add_field(name="📁 Backup-Channel", value=kanal.mention, inline=True)
    success_embed.add_field(name="⏰ Intervall", value=zeit, inline=True)

    await interaction.response.send_message(embed=success_embed, ephemeral=True)

    log_embed = discord.Embed(
        title="⚙️ Backup-System konfiguriert",
        color=COLOR_INFO,
        timestamp=datetime.now()
    )
    log_embed.add_field(name="📁 Backup-Channel", value=kanal.mention, inline=True)
    log_embed.add_field(name="⏰ Intervall", value=zeit, inline=True)
    log_embed.add_field(name="👤 Konfiguriert von", value=interaction.user.mention, inline=True)
    await send_to_log_channel(interaction.guild, log_embed)

@bot.tree.command(name="backup_now", description="Erstellt sofort ein manuelles Backup")
async def backup_now(interaction: discord.Interaction):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann Backups erstellen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    backup_file = create_backup()
    if not backup_file:
        error_embed = discord.Embed(
            title="❌ Backup fehlgeschlagen",
            description="Das Backup konnte nicht erstellt werden.",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)
        return

    success_embed = discord.Embed(
        title="✅ Backup erstellt",
        description=f"Backup-Datei wurde erfolgreich erstellt.",
        color=COLOR_SUCCESS,
        timestamp=datetime.now()
    )

    await interaction.followup.send(
        embed=success_embed,
        file=discord.File(backup_file),
        ephemeral=True
    )

@bot.tree.command(name="reload", description="Lädt eine Backup-Datei und stellt Daten wieder her")
@app_commands.describe(datei="Backup-Datei (.json)")
async def reload_backup(interaction: discord.Interaction, datei: discord.Attachment):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann Backups wiederherstellen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    if not datei.filename.endswith('.json'):
        error_embed = discord.Embed(
            title="❌ Ungültiges Dateiformat",
            description="Bitte lade eine .json Datei hoch.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        # Backup der aktuellen Daten vor Reload
        current_backup = create_backup()

        # Datei herunterladen
        backup_data = await datei.read()
        backup_json = json.loads(backup_data.decode('utf-8'))

        # Validierung der Datenstruktur
        required_keys = ["customers", "invoices", "logs"]
        if not all(key in backup_json for key in required_keys):
            error_embed = discord.Embed(
                title="❌ Ungültige Backup-Datei",
                description="Die Datei enthält nicht alle erforderlichen Daten.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        # Daten wiederherstellen
        global data
        data = backup_json
        save_data(data)

        success_embed = discord.Embed(
            title="✅ Daten erfolgreich wiederhergestellt",
            description=f"Das Backup wurde erfolgreich geladen.\n\n**Vorheriges Backup:** `{os.path.basename(current_backup)}`",
            color=COLOR_SUCCESS,
            timestamp=datetime.now()
        )
        success_embed.add_field(name="📋 Kunden", value=str(len(data.get('customers', {}))), inline=True)
        success_embed.add_field(name="🧾 Rechnungen", value=str(len(data.get('invoices', {}))), inline=True)
        success_embed.add_field(name="📊 Log-Einträge", value=str(len(data.get('logs', []))), inline=True)

        await interaction.followup.send(embed=success_embed, ephemeral=True)

        log_embed = discord.Embed(
            title="🔄 Datenbank wiederhergestellt",
            description=f"**Ein Backup wurde eingespielt**\n\nVorheriges Backup gesichert: `{current_backup}`",
            color=COLOR_WARNING,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="👤 Wiederhergestellt von", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="📄 Datei", value=datei.filename, inline=True)
        await send_to_log_channel(interaction.guild, log_embed)

        add_log_entry(
            "BACKUP_WIEDERHERGESTELLT",
            interaction.user.id,
            {
                "datei": datei.filename,
                "kunden_count": len(data.get('customers', {})),
                "rechnungen_count": len(data.get('invoices', {}))
            }
        )

    except json.JSONDecodeError:
        error_embed = discord.Embed(
            title="❌ Fehler beim Laden",
            description="Die Datei konnte nicht als JSON gelesen werden.",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)
    except Exception as e:
        logger.error(f"Fehler beim Wiederherstellen: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler",
            description=f"Ein Fehler ist aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

@tasks.loop(minutes=1)
async def auto_backup():
    """Automatisches Backup-System"""
    try:
        backup_config = data.get('backup_config', {})
        if not backup_config.get('enabled', False):
            return

        last_backup = datetime.fromisoformat(backup_config.get('last_backup', datetime.now().isoformat()))
        interval_minutes = backup_config.get('interval_minutes', 1440)  # Standard: 24h

        if (datetime.now() - last_backup).total_seconds() >= interval_minutes * 60:
            backup_file = create_backup()
            if backup_file and backup_config.get('channel_id'):
                for guild in bot.guilds:
                    channel = guild.get_channel(backup_config['channel_id'])
                    if channel:
                        await channel.send(
                            f"🔄 **Automatisches Backup**\n"
                            f"**Zeitpunkt:** {datetime.now().strftime('%d.%m.%Y • %H:%M:%S')}\n"
                            f"**Nächstes Backup:** In {backup_config.get('interval', '24h')}",
                            file=discord.File(backup_file)
                        )
                        break

            data['backup_config']['last_backup'] = datetime.now().isoformat()
            save_data(data)

    except Exception as e:
        logger.error(f"Fehler beim Auto-Backup: {e}", exc_info=True)

# Auszahlungs-Channel setzen
@bot.tree.command(name="auszahlung_channel_setzen", description="Setzt den Channel für Auszahlungs-Benachrichtigungen")
@app_commands.describe(channel="Channel für Auszahlungs-Pings")
async def set_auszahlung_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann den Auszahlungs-Channel festlegen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    config["auszahlung_channel_id"] = channel.id
    save_config(config)

    success_embed = discord.Embed(
        title="✅ Auszahlungs-Channel konfiguriert",
        description=f"Auszahlungs-Benachrichtigungen werden nun in {channel.mention} gesendet.",
        color=COLOR_SUCCESS
    )
    await interaction.response.send_message(embed=success_embed, ephemeral=True)

# Log-Channel einrichten - NUR SERVER OWNER
@bot.tree.command(name="log_channel_setzen", description="Setzt den Channel für System-Logs")
@app_commands.describe(channel="Der Channel für Log-Nachrichten")
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    # Prüfung: Nur Leitungsebene
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann den Log-Channel festlegen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    config["log_channel_id"] = channel.id
    save_config(config)

    success_embed = discord.Embed(
        title="✅ Log-Channel konfiguriert",
        description=f"Alle System-Logs werden nun in {channel.mention} gesendet.",
        color=COLOR_SUCCESS
    )
    await interaction.response.send_message(embed=success_embed, ephemeral=True)

    # Verbesserter Log
    log_embed = discord.Embed(
        title="⚙️ System-Konfiguration",
        description="**Log-Channel wurde erfolgreich konfiguriert**",
        color=COLOR_INFO,
        timestamp=datetime.now()
    )
    log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
    log_embed.add_field(name="📋 Aktion", value="Log-Channel festgelegt", inline=False)
    log_embed.add_field(name="📍 Log-Channel", value=f"{channel.mention}", inline=True)
    log_embed.add_field(name="👤 Konfiguriert von", value=f"{interaction.user.mention}", inline=True)
    log_embed.add_field(name="🏢 Server", value=f"{interaction.guild.name}", inline=True)
    log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
    log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S Uhr'), inline=True)
    log_embed.add_field(name="🆔 Channel-ID", value=f"`{channel.id}`", inline=True)
    log_embed.set_footer(text=f"InsuranceGuard v2 • User-ID: {interaction.user.id}")
    await send_to_log_channel(interaction.guild, log_embed)

    add_log_entry(
        "LOG_CHANNEL_GESETZT",
        interaction.user.id,
        {
            "channel_id": channel.id,
            "channel_name": channel.name,
            "guild_id": interaction.guild.id,
            "guild_name": interaction.guild.name
        }
    )

    logger.info(f"Log-Channel auf {channel.id} gesetzt von User {interaction.user.id}")

# Kundenkontakt-Kategorie setzen - NUR LEITUNGSEBENE
@bot.tree.command(name="kundenkontakt_kategorie_setzen", description="Setzt die Kategorie für Kundenkontakt-Tickets")
@app_commands.describe(category="Die Kategorie für Kundenkontakt-Tickets")
async def set_kundenkontakt_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    # Prüfung: Nur Leitungsebene
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann die Kundenkontakt-Kategorie festlegen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    config["kundenkontakt_category_id"] = category.id
    save_config(config)

    success_embed = discord.Embed(
        title="✅ Kundenkontakt-Kategorie konfiguriert",
        description=f"Alle Kundenkontakt-Tickets werden nun in der Kategorie **{category.name}** erstellt.",
        color=COLOR_SUCCESS
    )
    await interaction.response.send_message(embed=success_embed, ephemeral=True)

    # Log
    log_embed = discord.Embed(
        title="⚙️ System-Konfiguration",
        description="**Kundenkontakt-Kategorie wurde erfolgreich konfiguriert**",
        color=COLOR_INFO,
        timestamp=datetime.now()
    )
    log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
    log_embed.add_field(name="📋 Aktion", value="Kundenkontakt-Kategorie festgelegt", inline=False)
    log_embed.add_field(name="📂 Kategorie", value=f"{category.name}", inline=True)
    log_embed.add_field(name="👤 Konfiguriert von", value=f"{interaction.user.mention}", inline=True)
    log_embed.add_field(name="🏢 Server", value=f"{interaction.guild.name}", inline=True)
    log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
    log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S Uhr'), inline=True)
    log_embed.add_field(name="🆔 Kategorie-ID", value=f"`{category.id}`", inline=True)
    log_embed.set_footer(text=f"InsuranceGuard v2 • User-ID: {interaction.user.id}")
    await send_to_log_channel(interaction.guild, log_embed)

    add_log_entry(
        "KUNDENKONTAKT_KATEGORIE_GESETZT",
        interaction.user.id,
        {
            "category_id": category.id,
            "category_name": category.name,
            "guild_id": interaction.guild.id,
            "guild_name": interaction.guild.name
        }
    )

    logger.info(f"Kundenkontakt-Kategorie auf {category.id} gesetzt von User {interaction.user.id}")

# Schadensmeldung-Kategorie setzen - NUR LEITUNGSEBENE
@bot.tree.command(name="schadensmeldung_kategorie_setzen", description="Setzt die Kategorie für Schadensmeldungs-Tickets")
@app_commands.describe(category="Die Kategorie für Schadensmeldungs-Tickets")
async def set_schadensmeldung_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    # Prüfung: Nur Leitungsebene
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann die Schadensmeldung-Kategorie festlegen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    config["schadensmeldung_category_id"] = category.id
    save_config(config)

    success_embed = discord.Embed(
        title="✅ Schadensmeldung-Kategorie konfiguriert",
        description=f"Alle Schadensmeldungs-Tickets werden nun in der Kategorie **{category.name}** erstellt.",
        color=COLOR_SUCCESS
    )
    await interaction.response.send_message(embed=success_embed, ephemeral=True)

    # Log
    log_embed = discord.Embed(
        title="⚙️ System-Konfiguration",
        description="**Schadensmeldung-Kategorie wurde erfolgreich konfiguriert**",
        color=COLOR_INFO,
        timestamp=datetime.now()
    )
    log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
    log_embed.add_field(name="📋 Aktion", value="Schadensmeldung-Kategorie festgelegt", inline=False)
    log_embed.add_field(name="📂 Kategorie", value=f"{category.name}", inline=True)
    log_embed.add_field(name="👤 Konfiguriert von", value=f"{interaction.user.mention}", inline=True)
    log_embed.add_field(name="🏢 Server", value=f"{interaction.guild.name}", inline=True)
    log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
    log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S Uhr'), inline=True)
    log_embed.add_field(name="🆔 Kategorie-ID", value=f"`{category.id}`", inline=True)
    log_embed.set_footer(text=f"InsuranceGuard v2 • User-ID: {interaction.user.id}")
    await send_to_log_channel(interaction.guild, log_embed)

    add_log_entry(
        "SCHADENSMELDUNG_KATEGORIE_GESETZT",
        interaction.user.id,
        {
            "category_id": category.id,
            "category_name": category.name,
            "guild_id": interaction.guild.id,
            "guild_name": interaction.guild.name
        }
    )

    logger.info(f"Schadensmeldung-Kategorie auf {category.id} gesetzt von User {interaction.user.id}")

# Auswahlmenü für Versicherungen
class InsuranceSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=insurance,
                description=f"Monatsbeitrag: {data['price']:,.2f} €",
                value=insurance
            )
            for insurance, data in INSURANCE_TYPES.items()
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
            title="✅ Versicherungen ausgewählt",
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

# Kundenakte erstellen - NUR MITARBEITER
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
    # Prüfung: Nur Mitarbeiter oder Leitung
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur Mitarbeiter und Leitungsebene können Kundenakten erstellen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    view = InsuranceView()

    select_embed = discord.Embed(
        title="📋 Versicherungen auswählen",
        description="Bitte wählen Sie die gewünschten Versicherungen für den Versicherungsnehmer aus dem Dropdown-Menü aus.\n\nNach der Auswahl klicken Sie auf den Button **'Kundenakte erstellen'**, um fortzufahren.",
        color=COLOR_INFO
    )

    await interaction.response.send_message(embed=select_embed, view=view, ephemeral=True)
    await view.wait()

    if not view.confirmed:
        timeout_embed = discord.Embed(
            title="⏱️ Zeitüberschreitung",
            description="Die Auswahl wurde nicht rechtzeitig bestätigt. Bitte versuchen Sie es erneut.",
            color=COLOR_WARNING
        )
        await interaction.edit_original_response(embed=timeout_embed, view=None)
        return

    insurance_select = view.children[0]
    if not insurance_select.values:
        error_embed = discord.Embed(
            title="❌ Keine Auswahl getroffen",
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
            title="📋 Versicherungsakte",
            color=COLOR_PRIMARY,
            timestamp=datetime.now()
        )
        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.add_field(name="🆔 Kunden-ID", value=f"`{customer_id}`", inline=True)
        embed.add_field(name="👤 Versicherungsnehmer", value=rp_name, inline=True)
        embed.add_field(name="‎", value="‎", inline=True)
        embed.add_field(name="💳 HBpay", value=f"`{hbpay_nummer}`", inline=True)
        embed.add_field(name="🏦 Economy-ID", value=f"`{economy_id}`", inline=True)
        embed.add_field(name="‎", value="‎", inline=True)

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        insurance_text = "\n".join(
            f"▸ {ins}\n   `{INSURANCE_TYPES[ins]['price']:,.2f} €/Monat`" 
            for ins in insurance_list
        )
        embed.add_field(name="📑 Abgeschlossene Versicherungen", value=insurance_text, inline=False)
        embed.add_field(name="💰 Gesamtbeitrag (monatlich)", value=f"**{total_price:,.2f} €**", inline=False)

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.add_field(
            name="📌 Aktenanlage",
            value=f"**Bearbeiter:** {interaction.user.mention}\n**Datum:** {datetime.now().strftime('%d.%m.%Y • %H:%M Uhr')}",
            inline=False
        )
        embed.set_footer(text=f"InsuranceGuard v2 • Status: Aktiv")

        thread = await forum_channel.create_thread(
            name=f"📁 {customer_id} | {rp_name}",
            content="**Versicherungsakte**",
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
            "created_at": datetime.now().isoformat(),
            "created_by": interaction.user.id,
            "status": "aktiv"
        }
        save_data(data)

        member = user  # Änderung: Rollen werden dem angegebenen User zugewiesen
        assigned_roles = []
        for insurance in insurance_list:
            role_name = INSURANCE_TYPES[insurance]["role"]
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if not role:
                role = await interaction.guild.create_role(
                    name=role_name,
                    color=discord.Color.from_rgb(44, 62, 80)
                )
                logger.info(f"Rolle erstellt: {role_name}")
            await member.add_roles(role)
            assigned_roles.append(role_name)

        add_log_entry(
            "KUNDENAKTE_ERSTELLT",
            interaction.user.id,
            {
                "customer_id": customer_id,
                "rp_name": rp_name,
                "versicherungen": insurance_list,
                "total_price": total_price,
                "thread_id": thread.thread.id,
                "forum_channel_id": forum_channel.id,
                "forum_channel_name": forum_channel.name,
                "hbpay_nummer": hbpay_nummer,
                "economy_id": economy_id
            }
        )

        # Verbesserter Log
        log_embed = discord.Embed(
            title="📋 Neue Kundenakte erstellt",
            description="**Eine neue Versicherungsakte wurde erfolgreich im System angelegt**",
            color=COLOR_SUCCESS,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="🆔 Kunden-ID", value=f"`{customer_id}`", inline=True)
        log_embed.add_field(name="👤 Name", value=rp_name, inline=True)
        log_embed.add_field(name="💰 Monatsbeitrag", value=f"`{total_price:,.2f} €`", inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="📑 Versicherungen", value=f"{len(insurance_list)} Verträge\n" + "\n".join(f"▸ {ins}" for ins in insurance_list), inline=False)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="💳 HBpay", value=f"`{hbpay_nummer}`", inline=True)
        log_embed.add_field(name="🏦 Economy-ID", value=f"`{economy_id}`", inline=True)
        log_embed.add_field(name="📁 Thread-ID", value=f"`{thread.thread.id}`", inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="👤 Erstellt von", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="📍 Forum-Channel", value=f"{forum_channel.mention}", inline=True)
        log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
        log_embed.set_footer(text=f"InsuranceGuard v2 • User-ID: {interaction.user.id}")
        await send_to_log_channel(interaction.guild, log_embed)

        success_embed = discord.Embed(
            title="✅ Kundenakte erfolgreich angelegt",
            description="Die Versicherungsakte wurde erfolgreich im System hinterlegt.",
            color=COLOR_SUCCESS
        )
        success_embed.add_field(name="🆔 Kunden-ID", value=f"`{customer_id}`", inline=True)
        success_embed.add_field(name="📁 Aktenarchiv", value=thread.thread.mention, inline=True)
        success_embed.add_field(name="💰 Monatsbeitrag", value=f"`{total_price:,.2f} €`", inline=True)

        await interaction.edit_original_response(embed=success_embed, view=None)
        logger.info(f"Kundenakte {customer_id} erfolgreich erstellt")

    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Kundenakte: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler bei der Aktenanlage",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        try:
            await interaction.edit_original_response(embed=error_embed, view=None)
        except:
            await interaction.followup.send(embed=error_embed, ephemeral=True)

# Rechnung erstellen - NUR MITARBEITER - VERBESSERTES DESIGN
@bot.tree.command(name="rechnung_ausstellen", description="Erstellt eine Versicherungsrechnung")
@app_commands.describe(
    customer_id="Versicherungsnehmer-ID",
    channel="Channel für die Rechnungsstellung"
)
async def create_invoice(
    interaction: discord.Interaction,
    customer_id: str,
    channel: discord.TextChannel
):
    # Prüfung: Nur Mitarbeiter oder Leitung
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur Mitarbeiter und Leitungsebene können Rechnungen ausstellen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    logger.info(f"Rechnung wird erstellt von User {interaction.user.id} für Kunde {customer_id}")

    try:
        if customer_id not in data['customers']:
            error_embed = discord.Embed(
                title="❌ Kunde nicht gefunden",
                description=f"Es existiert keine Akte mit der Versicherungsnehmer-ID `{customer_id}`.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        customer = data['customers'][customer_id]
        invoice_id = generate_invoice_id()
        betrag_netto = customer['total_monthly_price']

        # 5% Steuer
        steuer = betrag_netto * 0.05
        betrag_brutto = betrag_netto + steuer

        # Zahlungsfrist: 3 Tage
        due_date = datetime.now() + timedelta(days=3)

        # VERBESSERTES RECHNUNGS-DESIGN
        embed = discord.Embed(
            title="🧾 Versicherungsrechnung",
            description="**Zahlungsaufforderung für Versicherungsbeiträge**",
            color=COLOR_PRIMARY,
            timestamp=datetime.now()
        )
        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.add_field(name="📄 Rechnungsnummer", value=f"`{invoice_id}`", inline=True)
        embed.add_field(name="📅 Rechnungsdatum", value=datetime.now().strftime('%d.%m.%Y'), inline=True)
        embed.add_field(name="⏰ Fällig am", value=f"**{due_date.strftime('%d.%m.%Y')}**", inline=True)

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**👤 Versicherungsnehmer**", inline=False)
        embed.add_field(name="Name", value=customer['rp_name'], inline=True)
        embed.add_field(name="Kunden-ID", value=f"`{customer_id}`", inline=True)
        embed.add_field(name="‎", value="‎", inline=True)

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**💳 Zahlungsinformationen**", inline=False)
        embed.add_field(name="HBpay Nummer", value=f"`{customer['hbpay_nummer']}`", inline=True)
        embed.add_field(name="Economy-ID", value=f"`{customer['economy_id']}`", inline=True)
        embed.add_field(name="‎", value="‎", inline=True)

        insurance_details = "\n".join(
            f"▸ {ins}\n   💰 `{INSURANCE_TYPES[ins]['price']:,.2f} €`" 
            for ins in customer['versicherungen']
        )
        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**📑 Versicherte Positionen**", inline=False)
        embed.add_field(name="", value=insurance_details, inline=False)

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**💵 Zahlungssumme**", inline=False)
        embed.add_field(name="Zwischensumme (Netto)", value=f"`{betrag_netto:,.2f} €`", inline=True)
        embed.add_field(name="Steuer (5%)", value=f"`{steuer:,.2f} €`", inline=True)
        embed.add_field(name="**Rechnungsbetrag**", value=f"**`{betrag_brutto:,.2f} €`**", inline=True)

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.add_field(name="📊 Status", value="⏳ **Zahlung ausstehend**", inline=False)
        embed.set_footer(text=f"Ausgestellt von {interaction.user.display_name} • InsuranceGuard v2")

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
            "created_at": datetime.now().isoformat(),
            "created_by": interaction.user.id
        }
        save_data(data)

        add_log_entry(
            "RECHNUNG_ERSTELLT",
            interaction.user.id,
            {
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
            }
        )

        # Verbesserter Log
        log_embed = discord.Embed(
            title="🧾 Neue Rechnung ausgestellt",
            description="**Eine neue Versicherungsrechnung wurde erfolgreich erstellt**",
            color=COLOR_INFO,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="📄 Rechnungsnummer", value=f"`{invoice_id}`", inline=True)
        log_embed.add_field(name="👤 Kunde", value=f"{customer['rp_name']}\n`{customer_id}`", inline=True)
        log_embed.add_field(name="⏰ Fällig am", value=due_date.strftime('%d.%m.%Y'), inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="💵 Nettobetrag", value=f"`{betrag_netto:,.2f} €`", inline=True)
        log_embed.add_field(name="📊 Steuer (5%)", value=f"`{steuer:,.2f} €`", inline=True)
        log_embed.add_field(name="💰 Bruttobetrag", value=f"**`{betrag_brutto:,.2f} €`**", inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="👤 Ausgestellt von", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="📍 Channel", value=f"{channel.mention}", inline=True)
        log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
        log_embed.add_field(name="📊 Status", value="⏳ Zahlung ausstehend", inline=True)
        log_embed.set_footer(text=f"InsuranceGuard v2 • Invoice-ID: {invoice_id}")
        await send_to_log_channel(interaction.guild, log_embed)

        success_embed = discord.Embed(
            title="✅ Rechnung erfolgreich ausgestellt",
            description="Die Rechnung wurde erstellt und versendet.",
            color=COLOR_SUCCESS
        )
        success_embed.add_field(name="📄 Rechnungsnummer", value=f"`{invoice_id}`", inline=True)
        success_embed.add_field(name="💰 Betrag (Brutto)", value=f"`{betrag_brutto:,.2f} €`", inline=True)
        success_embed.add_field(name="⏰ Fällig am", value=due_date.strftime('%d.%m.%Y'), inline=True)

        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Rechnung: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler bei der Rechnungsstellung",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

# Mahnung manuell ausstellen - NEU
@bot.tree.command(name="mahnung_ausstellen", description="Stellt eine Mahnung für eine überfällige Rechnung aus")
@app_commands.describe(invoice_id="Rechnungsnummer (z.B. RE-2412-A3F9)")
async def issue_manual_reminder(interaction: discord.Interaction, invoice_id: str):
    # Prüfung: Nur Mitarbeiter oder Leitung
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur Mitarbeiter und Leitungsebene können Mahnungen ausstellen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        if invoice_id not in data['invoices']:
            error_embed = discord.Embed(
                title="❌ Rechnung nicht gefunden",
                description=f"Es existiert keine Rechnung mit der Nummer `{invoice_id}`.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        invoice = data['invoices'][invoice_id]

        if invoice.get('paid', False):
            info_embed = discord.Embed(
                title="ℹ️ Rechnung bereits bezahlt",
                description=f"Die Rechnung `{invoice_id}` wurde bereits als bezahlt markiert.",
                color=COLOR_INFO
            )
            await interaction.followup.send(embed=info_embed, ephemeral=True)
            return

        customer = data['customers'].get(invoice['customer_id'])
        if not customer:
            error_embed = discord.Embed(
                title="❌ Kunde nicht gefunden",
                description="Kunde konnte nicht gefunden werden.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        # Mahnstufe erhöhen
        reminder_count = invoice.get('reminder_count', 0) + 1

        # Mahngebühren berechnen
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

        # Mahnung senden
        await send_reminder(invoice_id, invoice, reminder_count, surcharge_percent)

        success_embed = discord.Embed(
            title="✅ Mahnung erfolgreich ausgestellt",
            description=f"Die {reminder_count}. Mahnung für Rechnung `{invoice_id}` wurde versendet.",
            color=COLOR_SUCCESS
        )
        success_embed.add_field(name="💰 Neuer Betrag", value=f"`{new_amount:,.2f} €`", inline=True)
        if surcharge_percent > 0:
            success_embed.add_field(name="📈 Mahngebühr", value=f"+{surcharge_percent}%", inline=True)

        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Fehler beim Ausstellen der Mahnung: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

# Akte archivieren - NEU
@bot.tree.command(name="akte_archivieren", description="Archiviert eine Kundenakte")
@app_commands.describe(customer_id="Versicherungsnehmer-ID")
async def archive_customer(interaction: discord.Interaction, customer_id: str):
    # Prüfung: Nur Mitarbeiter oder Leitung
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur Mitarbeiter und Leitungsebene können Akten archivieren.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        if customer_id not in data['customers']:
            error_embed = discord.Embed(
                title="❌ Kunde nicht gefunden",
                description=f"Es existiert keine Akte mit der ID `{customer_id}`.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        customer = data['customers'][customer_id]

        if customer.get('status') == 'archiviert':
            info_embed = discord.Embed(
                title="ℹ️ Akte bereits archiviert",
                description=f"Die Akte `{customer_id}` ist bereits archiviert.",
                color=COLOR_INFO
            )
            await interaction.followup.send(embed=info_embed, ephemeral=True)
            return

        # Status auf archiviert setzen
        data['customers'][customer_id]['status'] = 'archiviert'
        data['customers'][customer_id]['archived_at'] = datetime.now().isoformat()
        data['customers'][customer_id]['archived_by'] = interaction.user.id
        save_data(data)

        # Thread umbenennen
        thread_id = customer.get('thread_id')
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id)
                if thread:
                    await thread.edit(name=f"🗄️ [ARCHIV] {customer_id} | {customer['rp_name']}")

                    # Archivierungs-Nachricht im Thread
                    archive_embed = discord.Embed(
                        title="🗄️ Akte archiviert",
                        description="Diese Kundenakte wurde archiviert und ist nicht mehr aktiv.",
                        color=COLOR_WARNING,
                        timestamp=datetime.now()
                    )
                    archive_embed.add_field(name="Archiviert von", value=interaction.user.mention, inline=True)
                    archive_embed.add_field(name="Archiviert am", value=datetime.now().strftime('%d.%m.%Y • %H:%M Uhr'), inline=True)
                    await thread.send(embed=archive_embed)
            except Exception as e:
                logger.error(f"Fehler beim Aktualisieren des Threads: {e}")

        # Rollen entfernen
        member = interaction.guild.get_member(customer['discord_user_id'])
        if member:
            for insurance in customer.get('versicherungen', []):
                role_name = INSURANCE_TYPES[insurance]["role"]
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if role and role in member.roles:
                    await member.remove_roles(role)

        add_log_entry(
            "AKTE_ARCHIVIERT",
            interaction.user.id,
            {
                "customer_id": customer_id,
                "customer_name": customer['rp_name'],
                "versicherungen": customer.get('versicherungen', []),
                "archived_at": datetime.now().isoformat()
            }
        )

        # Log
        log_embed = discord.Embed(
            title="🗄️ Kundenakte archiviert",
            description="**Eine Kundenakte wurde archiviert**",
            color=COLOR_WARNING,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="🆔 Kunden-ID", value=f"`{customer_id}`", inline=True)
        log_embed.add_field(name="👤 Kunde", value=customer['rp_name'], inline=True)
        log_embed.add_field(name="📊 Status", value="Archiviert", inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="👤 Archiviert von", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
        log_embed.set_footer(text=f"InsuranceGuard v2 • Customer-ID: {customer_id}")
        await send_to_log_channel(interaction.guild, log_embed)

        success_embed = discord.Embed(
            title="✅ Akte erfolgreich archiviert",
            description=f"Die Kundenakte `{customer_id}` wurde archiviert.",
            color=COLOR_SUCCESS
        )
        success_embed.add_field(name="👤 Kunde", value=customer['rp_name'], inline=True)
        success_embed.add_field(name="📊 Status", value="Archiviert", inline=True)

        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Fehler beim Archivieren der Akte: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

# Rechnung archivieren - MIT KUNDENAKTE-POST UND CHANNEL-UPDATE
@bot.tree.command(name="rechnung_archivieren", description="Markiert eine Rechnung als bezahlt und archiviert sie")
@app_commands.describe(invoice_id="Rechnungsnummer (z.B. RE-2412-A3F9)")
async def archive_invoice(interaction: discord.Interaction, invoice_id: str):
    # Prüfung: Nur Mitarbeiter oder Leitung
    if not is_mitarbeiter(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur Mitarbeiter und Leitungsebene können Rechnungen archivieren.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    logger.info(f"Rechnung wird archiviert von User {interaction.user.id}: {invoice_id}")

    try:
        if invoice_id not in data['invoices']:
            error_embed = discord.Embed(
                title="❌ Rechnung nicht gefunden",
                description=f"Es existiert keine Rechnung mit der Nummer `{invoice_id}`.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        invoice = data['invoices'][invoice_id]

        if invoice.get('paid', False):
            info_embed = discord.Embed(
                title="ℹ️ Rechnung bereits archiviert",
                description=f"Die Rechnung `{invoice_id}` wurde bereits als bezahlt markiert.",
                color=COLOR_INFO
            )
            await interaction.followup.send(embed=info_embed, ephemeral=True)
            return

        customer_id = invoice['customer_id']
        customer = data['customers'].get(customer_id)

        if not customer:
            error_embed = discord.Embed(
                title="❌ Kunde nicht gefunden",
                description=f"Kunde `{customer_id}` konnte nicht gefunden werden.",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        # Rechnung als bezahlt markieren
        data['invoices'][invoice_id]['paid'] = True
        data['invoices'][invoice_id]['paid_by'] = interaction.user.id
        data['invoices'][invoice_id]['paid_at'] = datetime.now().isoformat()
        data['invoices'][invoice_id]['archived'] = True
        data['invoices'][invoice_id]['reminder_count'] = 0
        save_data(data)

        # Rechnung im Channel als bezahlt aktualisieren
        try:
            channel = interaction.guild.get_channel(invoice['channel_id'])
            if channel:
                message = await channel.fetch_message(invoice['message_id'])
                updated_embed = message.embeds[0]

                for i, field in enumerate(updated_embed.fields):
                    if "Status" in field.name:
                        updated_embed.set_field_at(
                            i,
                            name="📊 Status",
                            value=f"✅ **Bezahlt am {datetime.now().strftime('%d.%m.%Y • %H:%M Uhr')}**\nArchiviert von: {interaction.user.mention}",
                            inline=False
                        )
                        break

                updated_embed.color = COLOR_SUCCESS
                await message.edit(embed=updated_embed)
                logger.info(f"Rechnung {invoice_id} im Channel als bezahlt markiert")
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Rechnung im Channel: {e}")

        add_log_entry(
            "RECHNUNG_ARCHIVIERT",
            interaction.user.id,
            {
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "customer_name": customer['rp_name'],
                "betrag": invoice['betrag'],
                "betrag_netto": invoice.get('betrag_netto', 0),
                "steuer": invoice.get('steuer', 0),
                "paid_at": datetime.now().isoformat(),
                "channel_id": invoice['channel_id']
            }
        )

        # Verbesserter Log
        log_embed = discord.Embed(
            title="📦 Rechnung archiviert",
            description="**Eine Rechnung wurde erfolgreich als bezahlt markiert**",
            color=COLOR_SUCCESS,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="📄 Rechnungsnummer", value=f"`{invoice_id}`", inline=True)
        log_embed.add_field(name="👤 Kunde", value=f"{customer['rp_name']}\n`{customer_id}`", inline=True)
        log_embed.add_field(name="📅 Archiviert am", value=datetime.now().strftime('%d.%m.%Y • %H:%M'), inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="💵 Netto", value=f"`{invoice.get('betrag_netto', 0):,.2f} €`", inline=True)
        log_embed.add_field(name="📊 Steuer (5%)", value=f"`{invoice.get('steuer', 0):,.2f} €`", inline=True)
        log_embed.add_field(name="💰 Brutto", value=f"**`{invoice['betrag']:,.2f} €`**", inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="👤 Archiviert von", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="📍 Channel", value=f"<#{invoice['channel_id']}>", inline=True)
        log_embed.add_field(name="📊 Status", value="✅ Bezahlt & Archiviert", inline=True)
        log_embed.set_footer(text=f"InsuranceGuard v2 • Invoice-ID: {invoice_id}")
        await send_to_log_channel(interaction.guild, log_embed)

        # Rechnung in Kundenakte posten
        thread_id = customer.get('thread_id')
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id)
                if thread:
                    archive_embed = discord.Embed(
                        title="📦 Archivierte Rechnung",
                        description="Diese Rechnung wurde als bezahlt markiert und archiviert.",
                        color=COLOR_SUCCESS,
                        timestamp=datetime.now()
                    )
                    archive_embed.add_field(name="📄 Rechnungsnummer", value=f"`{invoice_id}`", inline=True)
                    archive_embed.add_field(name="📅 Rechnungsdatum", value=datetime.fromisoformat(invoice['created_at']).strftime('%d.%m.%Y'), inline=True)
                    archive_embed.add_field(name="✅ Zahlungsdatum", value=datetime.now().strftime('%d.%m.%Y'), inline=True)

                    insurance_list = customer.get('versicherungen', [])
                    insurance_text = "\n".join(f"▸ {ins}" for ins in insurance_list)
                    archive_embed.add_field(name="📑 Positionen", value=insurance_text if insurance_text else "Keine", inline=False)

                    archive_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
                    archive_embed.add_field(name="💵 Nettobetrag", value=f"`{invoice.get('betrag_netto', 0):,.2f} €`", inline=True)
                    archive_embed.add_field(name="📊 Steuer (5%)", value=f"`{invoice.get('steuer', 0):,.2f} €`", inline=True)
                    archive_embed.add_field(name="**💰 Bruttobetrag**", value=f"**`{invoice['betrag']:,.2f} €`**", inline=True)

                    archive_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
                    archive_embed.add_field(name="📊 Status", value="✅ Bezahlt", inline=True)
                    archive_embed.add_field(name="👤 Archiviert von", value=interaction.user.mention, inline=True)
                    archive_embed.set_footer(text=f"InsuranceGuard v2 • {datetime.now().strftime('%d.%m.%Y • %H:%M:%S')}")

                    await thread.send(embed=archive_embed)
                    logger.info(f"Rechnung {invoice_id} in Kundenakte gepostet")
            except Exception as e:
                logger.error(f"Fehler beim Posten in Kundenakte: {e}")

        success_embed = discord.Embed(
            title="✅ Rechnung erfolgreich archiviert",
            description=f"Die Rechnung `{invoice_id}` wurde als bezahlt markiert und archiviert.",
            color=COLOR_SUCCESS
        )
        success_embed.add_field(name="👤 Kunde", value=customer['rp_name'], inline=True)
        success_embed.add_field(name="💰 Betrag", value=f"`{invoice['betrag']:,.2f} €`", inline=True)
        success_embed.add_field(name="📊 Status", value="✅ Archiviert", inline=True)

        await interaction.followup.send(embed=success_embed, ephemeral=True)
        logger.info(f"Rechnung {invoice_id} erfolgreich archiviert von User {interaction.user.id}")

    except Exception as e:
        logger.error(f"Fehler beim Archivieren der Rechnung: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler beim Archivieren",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

# Mahnungs-System
@tasks.loop(hours=24)
async def check_invoices():
    """Überprüft täglich alle Rechnungen und sendet Mahnungen"""
    try:
        now = datetime.now()
        for invoice_id, invoice_data in list(data['invoices'].items()):
            if invoice_data.get('paid', False):
                continue

            due_date = datetime.fromisoformat(invoice_data['due_date'])
            days_overdue = (now - due_date).days

            if days_overdue < 0:
                continue

            reminder_count = invoice_data.get('reminder_count', 0)

            # Erste Mahnung (Tag 0 nach Fälligkeit)
            if days_overdue == 0 and reminder_count == 0:
                await send_reminder(invoice_id, invoice_data, 1, 0)
                data['invoices'][invoice_id]['reminder_count'] = 1
                save_data(data)

            # Zweite Mahnung (Tag 1, +5%)
            elif days_overdue == 1 and reminder_count == 1:
                new_amount = invoice_data['original_betrag'] * 1.05
                data['invoices'][invoice_id]['betrag'] = new_amount
                await send_reminder(invoice_id, invoice_data, 2, 5)
                data['invoices'][invoice_id]['reminder_count'] = 2
                save_data(data)

            # Dritte Mahnung (Tag 2, +10% vom Original)
            elif days_overdue == 2 and reminder_count == 2:
                new_amount = invoice_data['original_betrag'] * 1.10
                data['invoices'][invoice_id]['betrag'] = new_amount
                await send_reminder(invoice_id, invoice_data, 3, 10)
                data['invoices'][invoice_id]['reminder_count'] = 3
                save_data(data)

    except Exception as e:
        logger.error(f"Fehler bei Mahnungsprüfung: {e}", exc_info=True)

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
                title=f"⚠️ {reminder_number}. Mahnung",
                description=f"**Die Rechnung `{invoice_id}` ist überfällig**",
                color=COLOR_WARNING if reminder_number < 3 else COLOR_ERROR,
                timestamp=datetime.now()
            )
            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            embed.add_field(name="📄 Rechnungsnummer", value=f"`{invoice_id}`", inline=True)
            embed.add_field(name="👤 Kunde", value=customer['rp_name'], inline=True)
            embed.add_field(name="⚠️ Mahnstufe", value=f"{reminder_number}. Mahnung", inline=True)
            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            embed.add_field(name="💵 Ursprünglicher Betrag", value=f"`{invoice_data['original_betrag']:,.2f} €`", inline=True)
            embed.add_field(name="💰 Aktueller Betrag", value=f"**`{invoice_data['betrag']:,.2f} €`**{surcharge_text}", inline=True)
            if surcharge_percent > 0:
                embed.add_field(name="📈 Mahngebühr", value=f"+{surcharge_percent}%", inline=True)
            embed.set_footer(text="Bitte begleichen Sie den Betrag umgehend • InsuranceGuard v2")

            if customer_user:
                await channel.send(f"{customer_user.mention}", embed=embed)
            else:
                await channel.send(embed=embed)

            # Verbesserter Log
            log_embed = discord.Embed(
                title=f"📨 {reminder_number}. Mahnung versendet",
                description="**Eine Zahlungserinnerung wurde automatisch versendet**",
                color=COLOR_WARNING if reminder_number < 3 else COLOR_ERROR,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            log_embed.add_field(name="📄 Rechnungsnummer", value=f"`{invoice_id}`", inline=True)
            log_embed.add_field(name="👤 Kunde", value=f"{customer['rp_name']}\n`{invoice_data['customer_id']}`", inline=True)
            log_embed.add_field(name="⚠️ Mahnstufe", value=f"{reminder_number}. Mahnung", inline=True)
            log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            log_embed.add_field(name="💵 Ursprungsbetrag", value=f"`{invoice_data['original_betrag']:,.2f} €`", inline=True)
            log_embed.add_field(name="💰 Neuer Betrag", value=f"**`{invoice_data['betrag']:,.2f} €`**", inline=True)
            if surcharge_percent > 0:
                log_embed.add_field(name="📈 Mahngebühr", value=f"+{surcharge_percent}%", inline=True)
            else:
                log_embed.add_field(name="📈 Mahngebühr", value="Keine", inline=True)
            log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            log_embed.add_field(name="📍 Channel", value=f"{channel.mention}", inline=True)
            log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
            log_embed.set_footer(text="Automatisch generiert • InsuranceGuard v2")
            await send_to_log_channel(guild, log_embed)

            add_log_entry(
                f"MAHNUNG_{reminder_number}",
                0,
                {
                    "invoice_id": invoice_id,
                    "customer_id": invoice_data['customer_id'],
                    "customer_name": customer['rp_name'],
                    "surcharge": surcharge_percent,
                    "original_betrag": invoice_data['original_betrag'],
                    "neuer_betrag": invoice_data['betrag'],
                    "channel_id": invoice_data['channel_id']
                }
            )

            break

    except Exception as e:
        logger.error(f"Fehler beim Senden der Mahnung: {e}", exc_info=True)

# Kundenkontakt-View - SEPARATER BUTTON
# Ticket-System Views - SEPARATE BUTTONS
class KundenkontaktView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Kundenkontakt anfragen", style=discord.ButtonStyle.primary, custom_id="open_kundenkontakt", emoji="📞")
    async def open_kundenkontakt(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"Kundenkontakt-Button geklickt von User {interaction.user.id}")
        await interaction.response.send_modal(TicketModal())

class SchadensmeldungView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Schadensmeldung einreichen", style=discord.ButtonStyle.danger, custom_id="open_schadensmeldung", emoji="⚠️")
    async def open_schadensmeldung(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"Schadensmeldungs-Button geklickt von User {interaction.user.id}")
        await interaction.response.send_modal(SchadensmeldungModal())

class TicketModal(discord.ui.Modal, title="Kundenkontakt-Anfrage"):
    customer_id_input = discord.ui.TextInput(
        label="Versicherungsnehmer-ID",
        placeholder="VN-24123456",
        required=True,
        max_length=20
    )

    reason = discord.ui.TextInput(
        label="Grund der Kontaktaufnahme",
        style=discord.TextStyle.paragraph,
        placeholder="Bitte beschreiben Sie detailliert den Anlass für die Kontaktaufnahme...",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        logger.info(f"Ticket wird erstellt von User {interaction.user.id}")

        try:
            customer_id = self.customer_id_input.value

            if customer_id not in data['customers']:
                error_embed = discord.Embed(
                    title="❌ Kunde nicht gefunden",
                    description=f"Es existiert keine Akte mit der Versicherungsnehmer-ID `{customer_id}`.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            customer = data['customers'][customer_id]
            guild = interaction.guild

            # Kategorie aus Config holen oder erstellen
            category = None
            if config.get("kundenkontakt_category_id"):
                category = guild.get_channel(config["kundenkontakt_category_id"])

            if not category:
                error_embed = discord.Embed(
                    title="❌ Kategorie nicht konfiguriert",
                    description="Die Kundenkontakt-Kategorie wurde noch nicht eingerichtet.\n\nBitte nutze `/kundenkontakt_kategorie_setzen` um eine Kategorie festzulegen.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            ticket_channel = await category.create_text_channel(
                name=f"kontakt-{customer_id.lower()}",
                topic=f"Kundenkontakt: {customer['rp_name']} | {customer_id}"
            )

            customer_user = guild.get_member(customer['discord_user_id'])

            # VERBESSERTES TICKET-EMBED
            embed = discord.Embed(
                title="🎫 Support-Ticket",
                description="**Kundenkontakt-Anfrage**\n\nEin neues Support-Ticket wurde erfolgreich erstellt.",
                color=COLOR_INFO,
                timestamp=datetime.now()
            )

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            embed.add_field(name="📊 Status", value="🟢 **Offen**", inline=True)
            embed.add_field(name="📅 Erstellt am", value=datetime.now().strftime('%d.%m.%Y • %H:%M'), inline=True)
            embed.add_field(name="🆔 Kunden-ID", value=f"`{customer_id}`", inline=True)

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**👥 Beteiligte Personen**", inline=False)
            embed.add_field(name="👤 Mitarbeiter", value=f"{interaction.user.mention}", inline=True)
            embed.add_field(name="👤 Versicherungsnehmer", value=f"{customer['rp_name']}", inline=True)
            embed.add_field(name="‎", value="‎", inline=True)

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**📝 Anlass der Kontaktaufnahme**", inline=False)
            embed.add_field(name="", value=self.reason.value, inline=False)

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**📋 Kundeninformationen**", inline=False)
            insurance_info = "\n".join(f"▸ {ins}" for ins in customer['versicherungen'])
            embed.add_field(name="📑 Versicherungen", value=insurance_info, inline=False)
            embed.add_field(name="💰 Monatsbeitrag", value=f"`{customer['total_monthly_price']:,.2f} €`", inline=True)
            embed.add_field(name="💳 HBpay", value=f"`{customer['hbpay_nummer']}`", inline=True)
            embed.add_field(name="🏦 Economy-ID", value=f"`{customer['economy_id']}`", inline=True)

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            embed.set_footer(text="Nutzen Sie den Button unten, um dieses Ticket zu schließen • InsuranceGuard v2")

            close_view = TicketCloseView(ticket_channel.id, customer_id)

            mentions = [interaction.user.mention]
            if customer_user:
                mentions.append(customer_user.mention)

            await ticket_channel.send(" ".join(mentions), embed=embed, view=close_view)

            add_log_entry(
                "TICKET_ERSTELLT",
                interaction.user.id,
                {
                    "customer_id": customer_id,
                    "customer_name": customer['rp_name'],
                    "channel_id": ticket_channel.id,
                    "channel_name": ticket_channel.name,
                    "reason": self.reason.value[:100]
                }
            )

            # Verbesserter Log
            log_embed = discord.Embed(
                title="🎫 Neues Support-Ticket",
                description="**Ein neues Kundenkontakt-Ticket wurde erstellt**",
                color=COLOR_INFO,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            log_embed.add_field(name="📍 Ticket-Channel", value=f"{ticket_channel.mention}", inline=True)
            log_embed.add_field(name="👤 Kunde", value=f"{customer['rp_name']}\n`{customer_id}`", inline=True)
            log_embed.add_field(name="📊 Status", value="🟢 Offen", inline=True)
            log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            log_embed.add_field(name="👤 Erstellt von", value=f"{interaction.user.mention}", inline=True)
            log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
            log_embed.set_footer(text=f"InsuranceGuard v2 • Channel-ID: {ticket_channel.id}")
            await send_to_log_channel(interaction.guild, log_embed)

            success_embed = discord.Embed(
                title="✅ Ticket erfolgreich erstellt",
                description="Die Kundenkontakt-Anfrage wurde erstellt.",
                color=COLOR_SUCCESS
            )
            success_embed.add_field(name="📍 Ticket-Channel", value=ticket_channel.mention, inline=True)

            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Tickets: {e}", exc_info=True)
            error_embed = discord.Embed(
                title="❌ Fehler bei der Ticket-Erstellung",
                description=f"Es ist ein Fehler aufgetreten: {str(e)}",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

# Schadensmeldungs-Modal Handler - NEU
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
                    title="❌ Kunde nicht gefunden",
                    description=f"Es existiert keine Akte mit der Versicherungsnehmer-ID `{customer_id}`.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            customer = data['customers'][customer_id]

            # Prüfen ob User auch wirklich der Kunde ist
            if customer['discord_user_id'] != interaction.user.id:
                error_embed = discord.Embed(
                    title="❌ Zugriff verweigert",
                    description="Sie können nur Schadensmeldungen für Ihre eigene Kundenakte einreichen.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            guild = interaction.guild

            # Kategorie aus Config holen oder erstellen
            category = None
            if config.get("schadensmeldung_category_id"):
                category = guild.get_channel(config["schadensmeldung_category_id"])

            if not category:
                error_embed = discord.Embed(
                    title="❌ Kategorie nicht konfiguriert",
                    description="Die Schadensmeldung-Kategorie wurde noch nicht eingerichtet.\n\nBitte kontaktiere die Leitungsebene, damit sie `/schadensmeldung_kategorie_setzen` nutzt.",
                    color=COLOR_ERROR
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            schaden_id = generate_schaden_id()

            ticket_channel = await category.create_text_channel(
                name=f"schaden-{customer_id.lower()}",
                topic=f"Schadensmeldung: {customer['rp_name']} | {customer_id} | {schaden_id}"
            )

            # Schadensmeldungs-Embed
            embed = discord.Embed(
                title="⚠️ Schadensmeldung",
                description="**Eine neue Schadensmeldung wurde eingereicht**\n\nBitte prüfen Sie die Angaben und bearbeiten Sie den Fall zeitnah.",
                color=COLOR_DAMAGE,
                timestamp=datetime.now()
            )

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            embed.add_field(name="🆔 Schadensnummer", value=f"`{schaden_id}`", inline=True)
            embed.add_field(name="📊 Status", value="🟡 **Offen**", inline=True)
            embed.add_field(name="📅 Gemeldet am", value=datetime.now().strftime('%d.%m.%Y • %H:%M'), inline=True)

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**👤 Versicherungsnehmer**", inline=False)
            embed.add_field(name="Name", value=customer['rp_name'], inline=True)
            embed.add_field(name="Kunden-ID", value=f"`{customer_id}`", inline=True)
            embed.add_field(name="Gemeldet von", value=interaction.user.mention, inline=True)

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**⚠️ Vorfall-Details**", inline=False)
            embed.add_field(name="👤 Geschädigter", value=self.geschaedigter.value, inline=True)
            embed.add_field(name="🔴 Täter", value=self.taeter.value, inline=True)
            embed.add_field(name="‎", value="‎", inline=True)

            embed.add_field(name="📝 Beschreibung des Vorfalls", value=self.beschreibung.value, inline=False)
            embed.add_field(name="🧾 Rechnung/Nachweis", value=self.rechnung.value, inline=False)

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━\n**📋 Versicherungsinformationen**", inline=False)
            insurance_info = "\n".join(f"▸ {ins}" for ins in customer['versicherungen'])
            embed.add_field(name="📑 Versicherungen", value=insurance_info, inline=False)
            embed.add_field(name="💳 HBpay", value=f"`{customer['hbpay_nummer']}`", inline=True)
            embed.add_field(name="🏦 Economy-ID", value=f"`{customer['economy_id']}`", inline=True)

            embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            embed.set_footer(text="Schadensmeldung • InsuranceGuard v2")

            # Mitarbeiter-Rolle pingen
            mitarbeiter_role = interaction.guild.get_role(MITARBEITER_ROLE_ID)

            close_view = TicketCloseView(ticket_channel.id, customer_id)

            if mitarbeiter_role:
                await ticket_channel.send(f"{mitarbeiter_role.mention} {interaction.user.mention}", embed=embed, view=close_view)
            else:
                await ticket_channel.send(interaction.user.mention, embed=embed, view=close_view)

            # Schadensmeldung speichern
            data['schadensmeldungen'][schaden_id] = {
                "customer_id": customer_id,
                "customer_name": customer['rp_name'],
                "geschaedigter": self.geschaedigter.value,
                "taeter": self.taeter.value,
                "beschreibung": self.beschreibung.value,
                "rechnung": self.rechnung.value,
                "status": "offen",
                "channel_id": ticket_channel.id,
                "created_at": datetime.now().isoformat(),
                "created_by": interaction.user.id
            }
            save_data(data)

            add_log_entry(
                "SCHADENSMELDUNG_ERSTELLT",
                interaction.user.id,
                {
                    "schaden_id": schaden_id,
                    "customer_id": customer_id,
                    "customer_name": customer['rp_name'],
                    "geschaedigter": self.geschaedigter.value,
                    "taeter": self.taeter.value,
                    "channel_id": ticket_channel.id
                }
            )

            # Log
            log_embed = discord.Embed(
                title="⚠️ Neue Schadensmeldung",
                description="**Eine neue Schadensmeldung wurde eingereicht**",
                color=COLOR_DAMAGE,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            log_embed.add_field(name="🆔 Schadensnummer", value=f"`{schaden_id}`", inline=True)
            log_embed.add_field(name="👤 Kunde", value=f"{customer['rp_name']}\n`{customer_id}`", inline=True)
            log_embed.add_field(name="📊 Status", value="🟡 Offen", inline=True)
            log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            log_embed.add_field(name="👤 Geschädigter", value=self.geschaedigter.value, inline=True)
            log_embed.add_field(name="🔴 Täter", value=self.taeter.value, inline=True)
            log_embed.add_field(name="📍 Ticket-Channel", value=f"{ticket_channel.mention}", inline=True)
            log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
            log_embed.add_field(name="👤 Gemeldet von", value=f"{interaction.user.mention}", inline=True)
            log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
            log_embed.set_footer(text=f"InsuranceGuard v2 • Schaden-ID: {schaden_id}")
            await send_to_log_channel(interaction.guild, log_embed)

            success_embed = discord.Embed(
                title="✅ Schadensmeldung erfolgreich eingereicht",
                description="Ihre Schadensmeldung wurde erfolgreich erstellt und wird von unseren Mitarbeitern bearbeitet.",
                color=COLOR_SUCCESS
            )
            success_embed.add_field(name="🆔 Schadensnummer", value=f"`{schaden_id}`", inline=True)
            success_embed.add_field(name="📍 Ticket-Channel", value=ticket_channel.mention, inline=True)

            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Schadensmeldung: {e}", exc_info=True)
            error_embed = discord.Embed(
                title="❌ Fehler",
                description=f"Es ist ein Fehler aufgetreten: {str(e)}",
                color=COLOR_ERROR
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self, channel_id, customer_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.customer_id = customer_id

    @discord.ui.button(label="Ticket schließen", style=discord.ButtonStyle.danger, custom_id="close_ticket", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Nur Mitarbeiter oder Leitung können Tickets schließen
        if not is_mitarbeiter(interaction):
            error_embed = discord.Embed(
                title="❌ Zugriff verweigert",
                description="Nur Mitarbeiter und Leitungsebene können Tickets schließen.",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        channel = interaction.channel

        close_embed = discord.Embed(
            title="🔒 Ticket wird geschlossen",
            description=f"Dieses Ticket wird in 5 Sekunden geschlossen und archiviert.\n\n**Geschlossen von:** {interaction.user.mention}",
            color=COLOR_WARNING,
            timestamp=datetime.now()
        )

        await interaction.response.send_message(embed=close_embed)

        # Verbesserter Log
        log_embed = discord.Embed(
            title="🔒 Support-Ticket geschlossen",
            description="**Ein Mitarbeiter hat ein Support-Ticket geschlossen**",
            color=COLOR_WARNING,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="📍 Ticket-Channel", value=f"{channel.mention}\n`{channel.name}`", inline=True)
        log_embed.add_field(name="🆔 Kunden-ID", value=f"`{self.customer_id}`", inline=True)
        log_embed.add_field(name="📊 Status", value="🔴 Geschlossen", inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="👤 Geschlossen von", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
        log_embed.set_footer(text=f"InsuranceGuard v2 • Channel-ID: {self.channel_id}")
        await send_to_log_channel(interaction.guild, log_embed)

        add_log_entry(
            "TICKET_GESCHLOSSEN",
            interaction.user.id,
            {
                "customer_id": self.customer_id,
                "channel_id": self.channel_id,
                "channel_name": channel.name,
                "closed_at": datetime.now().isoformat()
            }
        )

        import asyncio
        await asyncio.sleep(5)
        await channel.delete(reason=f"Ticket geschlossen von {interaction.user}")

# Kundenkontakt-System Setup - NUR LEITUNGSEBENE
@bot.tree.command(name="kundenkontakt_setup", description="Richtet das Kundenkontakt-System ein")
@app_commands.describe(channel="Channel für das Kundenkontakt-Panel")
async def setup_kundenkontakt(interaction: discord.Interaction, channel: discord.TextChannel):
    # Prüfung: Nur Leitungsebene
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann das Kundenkontakt-System einrichten.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    logger.info(f"Kundenkontakt-System wird eingerichtet von User {interaction.user.id} in Channel {channel.id}")

    try:
        # Speichere Channel-ID
        config["kundenkontakt_channel_id"] = channel.id
        save_config(config)

        embed = discord.Embed(
            title="📞 Kundenkontakt-System",
            description="**Für Mitarbeiter und Leitungsebene**\n\nErstellen Sie professionelle Kundenkontakt-Tickets für die direkte Kommunikation mit Versicherungsnehmern.",
            color=COLOR_PRIMARY,
            timestamp=datetime.now()
        )

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

        embed.add_field(
            name="📋 So funktioniert's",
            value=(
                "```\n"
                "1. Klicken Sie auf den Button unten\n"
                "2. Geben Sie die Kunden-ID ein\n"
                "3. Beschreiben Sie den Kontaktgrund\n"
                "4. Ein privater Ticket-Channel wird erstellt\n"
                "```"
            ),
            inline=False
        )

        embed.add_field(
            name="✨ Features",
            value=(
                "▸ Automatischer privater Channel in **Kundenkontakt-Tickets**\n"
                "▸ Channel-Name: `kontakt-[kunden-id]`\n"
                "▸ Versicherungsnehmer wird automatisch benachrichtigt\n"
                "▸ Alle Kundeninformationen direkt verfügbar\n\u200b"
            ),
            inline=False
        )

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

        embed.add_field(
            name="⚠️ Wichtig",
            value=(
                "▸ Gültige **Kunden-ID** erforderlich\n"
                "▸ Kontaktgrund **detailliert** beschreiben\n"
                "▸ Nur für **Mitarbeiter** und **Leitungsebene**\n\u200b"
            ),
            inline=False
        )

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.set_footer(
            text="InsuranceGuard v2 • Kundenkontakt-System",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )

        view = KundenkontaktView()
        await channel.send(embed=embed, view=view)

        success_embed = discord.Embed(
            title="✅ Kundenkontakt-System aktiviert",
            description=f"Das Kundenkontakt-System wurde erfolgreich in {channel.mention} eingerichtet.",
            color=COLOR_SUCCESS
        )
        await interaction.response.send_message(embed=success_embed, ephemeral=True)

        add_log_entry(
            "KUNDENKONTAKT_SYSTEM_SETUP",
            interaction.user.id,
            {
                "channel_id": channel.id,
                "channel_name": channel.name,
                "guild_id": interaction.guild.id,
                "guild_name": interaction.guild.name
            }
        )

        # Log
        log_embed = discord.Embed(
            title="⚙️ Kundenkontakt-System eingerichtet",
            description="**Das Kundenkontakt-System wurde erfolgreich konfiguriert**",
            color=COLOR_INFO,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="📍 Panel-Channel", value=f"{channel.mention}", inline=True)
        log_embed.add_field(name="📊 Status", value="✅ Aktiv", inline=True)
        log_embed.add_field(name="🆔 Channel-ID", value=f"`{channel.id}`", inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="👤 Eingerichtet von", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="🏢 Server", value=f"{interaction.guild.name}", inline=True)
        log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
        log_embed.set_footer(text=f"InsuranceGuard v2 • Channel-ID: {channel.id}")
        await send_to_log_channel(interaction.guild, log_embed)

    except Exception as e:
        logger.error(f"Fehler beim Einrichten des Kundenkontakt-Systems: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler beim Setup",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

# Schadensmeldungs-System Setup - NUR LEITUNGSEBENE
@bot.tree.command(name="schadensmeldung_setup", description="Richtet das Schadensmeldungs-System ein")
@app_commands.describe(channel="Channel für das Schadensmeldungs-Panel")
async def setup_schadensmeldung(interaction: discord.Interaction, channel: discord.TextChannel):
    # Prüfung: Nur Leitungsebene
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann das Schadensmeldungs-System einrichten.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    logger.info(f"Schadensmeldungs-System wird eingerichtet von User {interaction.user.id} in Channel {channel.id}")

    try:
        # Speichere Channel-ID
        config["schadensmeldung_channel_id"] = channel.id
        save_config(config)

        embed = discord.Embed(
            title="⚠️ Schadensmeldungs-System",
            description="**Für Versicherungsnehmer**\n\nReichen Sie hier Schadensmeldungen für versicherte Schadensfälle ein.",
            color=COLOR_DAMAGE,
            timestamp=datetime.now()
        )

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

        embed.add_field(
            name="📋 So funktioniert's",
            value=(
                "```\n"
                "1. Klicken Sie auf den Button unten\n"
                "2. Geben Sie Ihre Kunden-ID ein\n"
                "3. Füllen Sie das Schadensmeldungs-Formular aus\n"
                "4. Ein Schadensfall-Ticket wird erstellt\n"
                "```"
            ),
            inline=False
        )

        embed.add_field(
            name="📝 Erforderliche Angaben",
            value=(
                "▸ **Kunden-ID** (Ihre Versicherungsnehmer-ID)\n"
                "▸ **Geschädigter** (RP-Name)\n"
                "▸ **Täter** (RP-Name)\n"
                "▸ **Vorfallbeschreibung** (detailliert)\n"
                "▸ **Rechnung/Nachweis** (Nummer oder Link)\n\u200b"
            ),
            inline=False
        )

        embed.add_field(
            name="✨ Automatische Bearbeitung",
            value=(
                "▸ Privater Channel in **Schadensmeldungen**\n"
                "▸ Channel-Name: `schaden-[kunden-id]`\n"
                "▸ Mitarbeiter werden automatisch benachrichtigt\n"
                "▸ Eindeutige Schadensnummer wird vergeben\n\u200b"
            ),
            inline=False
        )

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

        embed.add_field(
            name="⚠️ Wichtig",
            value=(
                "▸ Nur **Ihre eigene Kunden-ID** verwenden\n"
                "▸ Vorfall **so detailliert wie möglich** beschreiben\n"
                "▸ **Nachweise** beifügen (Rechnungen, Fotos, etc.)\n\u200b"
            ),
            inline=False
        )

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.set_footer(
            text="InsuranceGuard v2 • Schadensmeldungs-System",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )

        view = SchadensmeldungView()
        await channel.send(embed=embed, view=view)

        success_embed = discord.Embed(
            title="✅ Schadensmeldungs-System aktiviert",
            description=f"Das Schadensmeldungs-System wurde erfolgreich in {channel.mention} eingerichtet.",
            color=COLOR_SUCCESS
        )
        await interaction.response.send_message(embed=success_embed, ephemeral=True)

        add_log_entry(
            "SCHADENSMELDUNG_SYSTEM_SETUP",
            interaction.user.id,
            {
                "channel_id": channel.id,
                "channel_name": channel.name,
                "guild_id": interaction.guild.id,
                "guild_name": interaction.guild.name
            }
        )

        # Log
        log_embed = discord.Embed(
            title="⚙️ Schadensmeldungs-System eingerichtet",
            description="**Das Schadensmeldungs-System wurde erfolgreich konfiguriert**",
            color=COLOR_INFO,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="📍 Panel-Channel", value=f"{channel.mention}", inline=True)
        log_embed.add_field(name="📊 Status", value="✅ Aktiv", inline=True)
        log_embed.add_field(name="🆔 Channel-ID", value=f"`{channel.id}`", inline=True)
        log_embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        log_embed.add_field(name="👤 Eingerichtet von", value=f"{interaction.user.mention}", inline=True)
        log_embed.add_field(name="🏢 Server", value=f"{interaction.guild.name}", inline=True)
        log_embed.add_field(name="🕐 Zeitstempel", value=datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), inline=True)
        log_embed.set_footer(text=f"InsuranceGuard v2 • Channel-ID: {channel.id}")
        await send_to_log_channel(interaction.guild, log_embed)

    except Exception as e:
        logger.error(f"Fehler beim Einrichten des Schadensmeldungs-Systems: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler beim Setup",
            description=f"Es ist ein Fehler aufgetreten: {str(e)}",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

# Log anzeigen - NUR LEITUNG - VERBESSERT
@bot.tree.command(name="logs_anzeigen", description="Zeigt die letzten Bot-Aktivitäten an")
@app_commands.describe(anzahl="Anzahl der anzuzeigenden Log-Einträge (Standard: 10)")
async def show_logs(interaction: discord.Interaction, anzahl: int = 10):
    # Prüfung: Nur Leitungsebene
    if not is_leitungsebene(interaction):
        error_embed = discord.Embed(
            title="❌ Zugriff verweigert",
            description="Nur die Leitungsebene kann die System-Logs einsehen.",
            color=COLOR_ERROR
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    logger.info(f"Logs werden abgerufen von User {interaction.user.id}")

    await interaction.response.defer(ephemeral=True)

    try:
        if not data['logs']:
            info_embed = discord.Embed(
                title="ℹ️ Keine Logs vorhanden",
                description="Es sind noch keine Aktivitäten protokolliert worden.",
                color=COLOR_INFO
            )
            await interaction.followup.send(embed=info_embed, ephemeral=True)
            return

        recent_logs = data['logs'][-anzahl:]
        recent_logs.reverse()

        embed = discord.Embed(
            title="📊 System-Aktivitätsprotokoll",
            description=f"**Letzte {len(recent_logs)} Systemaktivitäten**\n\nEine detaillierte Übersicht aller protokollierten Bot-Aktionen.",
            color=COLOR_PRIMARY,
            timestamp=datetime.now()
        )

        # Emoji-Mapping für verschiedene Aktionen
        action_emojis = {
            "KUNDENAKTE_ERSTELLT": "📋",
            "RECHNUNG_ERSTELLT": "🧾",
            "RECHNUNG_BEZAHLT": "💰",
            "RECHNUNG_ARCHIVIERT": "📦",
            "MAHNUNG_1": "⚠️",
            "MAHNUNG_2": "🔶",
            "MAHNUNG_3": "🔴",
            "TICKET_ERSTELLT": "🎫",
            "TICKET_GESCHLOSSEN": "🔒",
            "SCHADENSMELDUNG_ERSTELLT": "⚠️",
            "AKTE_ARCHIVIERT": "🗄️",
            "TICKET_SYSTEM_SETUP": "⚙️",
            "LOG_CHANNEL_GESETZT": "⚙️",
            "KUNDENKONTAKT_KATEGORIE_GESETZT": "📂",
            "SCHADENSMELDUNG_KATEGORIE_GESETZT": "📂"
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
            "TICKET_SYSTEM_SETUP": "Ticket-System eingerichtet",
            "LOG_CHANNEL_GESETZT": "Log-Channel konfiguriert",
            "KUNDENKONTAKT_KATEGORIE_GESETZT": "Kundenkontakt-Kategorie konfiguriert",
            "SCHADENSMELDUNG_KATEGORIE_GESETZT": "Schadensmeldung-Kategorie konfiguriert"
        }

        for idx, log in enumerate(recent_logs, 1):
            timestamp = datetime.fromisoformat(log['timestamp']).strftime('%d.%m.%Y • %H:%M:%S')
            user = interaction.guild.get_member(log['user_id']) if log['user_id'] != 0 else None
            user_name = user.mention if user else "🤖 **System**"

            action = log['action']
            emoji = action_emojis.get(action, "📌")
            action_display = action_names.get(action, action)

            # Details formatieren mit mehr Informationen
            details_list = []
            for k, v in log['details'].items():
                if k == 'reason':
                    continue
                if k == 'customer_id':
                    details_list.append(f"🆔 Kunden-ID: `{v}`")
                elif k == 'customer_name':
                    details_list.append(f"👤 Kunde: **{v}**")
                elif k == 'invoice_id':
                    details_list.append(f"📄 Rechnung: `{v}`")
                elif k == 'schaden_id':
                    details_list.append(f"⚠️ Schaden: `{v}`")
                elif k == 'channel_name':
                    details_list.append(f"📍 Channel: {v}")
                elif k == 'geschaedigter':
                    details_list.append(f"👤 Geschädigter: {v}")
                elif k == 'taeter':
                    details_list.append(f"🔴 Täter: {v}")
                elif 'betrag' in k.lower() or 'price' in k.lower():
                    if isinstance(v, (int, float)):
                        details_list.append(f"💰 {k.replace('_', ' ').title()}: **{v:,.2f} €**")
                elif k == 'versicherungen':
                    if isinstance(v, list) and v:
                        details_list.append(f"📑 Versicherungen: {len(v)} Verträge")
                elif k == 'due_date':
                    details_list.append(f"⏰ Fällig: {v}")
                elif k == 'surcharge':
                    if v > 0:
                        details_list.append(f"📈 Mahngebühr: +{v}%")

            details_text = "\n".join(f"{d}" for d in details_list[:5]) if details_list else "—"  # Max 5 Details

            embed.add_field(
                name=f"{emoji} {action_display}",
                value=(
                    f"🕐 **{timestamp}**\n"
                    f"👤 {user_name}\n"
                    f"{details_text}\n"
                    f"━━━━━━━━━━━━━━━━━"
                ),
                inline=False
            )

        embed.add_field(name="", value="━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.set_footer(
            text=f"Angefordert von {interaction.user.display_name} • InsuranceGuard v2",
            icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Fehler beim Anzeigen der Logs: {e}", exc_info=True)
        error_embed = discord.Embed(
            title="❌ Fehler beim Laden der Logs",
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
    return "Insurance Bot läuft erfolgreich!"

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
    keep_alive()  # Webserver für Render

    # Token aus Umgebungsvariable
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("DISCORD_TOKEN nicht gefunden! Bitte in Render-Umgebungsvariablen setzen.")
    else:
        logger.info("Bot wird gestartet...")
        bot.run(token)
