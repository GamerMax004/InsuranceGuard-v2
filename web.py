"""
InsuranceGuard v2 - WEB DASHBOARD
Vollständiges Dashboard für Render Deployment

Deploy mit: gunicorn web:app
URL: https://insuranceguard-v2.onrender.com
"""

from flask import Flask, render_template, redirect, url_for, session, request, flash
from requests_oauthlib import OAuth2Session
import json
import os
from datetime import datetime
from functools import wraps
import secrets
import requests
import logging

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask App
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# Discord OAuth2 Konfiguration
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', 'https://insuranceguard-v2.onrender.com/callback')
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')

DISCORD_API_BASE_URL = 'https://discord.com/api/v10'
AUTHORIZATION_BASE_URL = DISCORD_API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = DISCORD_API_BASE_URL + '/oauth2/token'

# Rollen-IDs (MÜSSEN MIT main.py ÜBEREINSTIMMEN!)
MITARBEITER_ROLE_ID = int(os.getenv('MITARBEITER_ROLE_ID', '1234567890'))
LEITUNGSEBENE_ROLE_ID = int(os.getenv('LEITUNGSEBENE_ROLE_ID', '9876543210'))
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', '0'))

# Datenbank - Render Disk Support
if os.path.exists('/data'):
    DATA_DIR = '/data'
    logger.info("📁 Using Render Disk: /data/")
else:
    DATA_DIR = '.'
    logger.info("📁 Using local directory")

DATA_FILE = os.path.join(DATA_DIR, "insurance_data.json")
CONFIG_FILE = os.path.join(DATA_DIR, "bot_config.json")

def load_data():
    """Lädt die Versicherungsdaten"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✅ Daten geladen: {len(data.get('customers', {}))} Kunden")
                return data
    except Exception as e:
        logger.error(f"❌ Fehler beim Laden: {e}")
    
    logger.warning("⚠️ Keine Datenbank gefunden, erstelle neue")
    return {
        "customers": {},
        "invoices": {},
        "logs": [],
        "schadensmeldungen": {},
        "auszahlungen": {},
        "backup_config": {}
    }

def save_data(data):
    """Speichert die Versicherungsdaten"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info("✅ Daten gespeichert")
    except Exception as e:
        logger.error(f"❌ Fehler beim Speichern: {e}")

def generate_auszahlung_id():
    """Generiert eine Auszahlungs-ID"""
    import random, string
    prefix = "AZ"
    year = datetime.now().strftime("%y")
    month = datetime.now().strftime("%m")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{year}{month}-{random_part}"

def add_guthaben_history(customer_id, betrag, typ, beschreibung, user_id):
    """Fügt einen Eintrag zur Guthaben-Historie hinzu"""
    data = load_data()
    if customer_id not in data['customers']:
        logger.warning(f"⚠️ Kunde {customer_id} nicht gefunden")
        return
    
    if 'guthaben_history' not in data['customers'][customer_id]:
        data['customers'][customer_id]['guthaben_history'] = []
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "betrag": betrag,
        "typ": typ,
        "beschreibung": beschreibung,
        "user_id": user_id,
        "guthaben_nach": data['customers'][customer_id]['guthaben']
    }
    data['customers'][customer_id]['guthaben_history'].append(entry)
    save_data(data)
    logger.info(f"✅ Guthaben-Historie: {typ} {betrag}€ für {customer_id}")

# OAuth2 Helper
def token_updater(token):
    session['oauth2_token'] = token

def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=DISCORD_CLIENT_ID,
        token=token,
        state=state,
        scope=scope,
        redirect_uri=DISCORD_REDIRECT_URI,
        auto_refresh_kwargs={
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
        },
        auto_refresh_url=TOKEN_URL,
        token_updater=token_updater
    )

def get_user_info(token):
    """Holt Discord User Informationen"""
    try:
        discord = make_session(token=token)
        user = discord.get(DISCORD_API_BASE_URL + '/users/@me').json()
        logger.info(f"✅ User-Info abgerufen: {user.get('username', 'Unknown')}")
        return user
    except Exception as e:
        logger.error(f"❌ Fehler bei get_user_info: {e}")
        return None

def get_user_roles(user_id):
    """Holt die Rollen eines Users im Server"""
    try:
        headers = {'Authorization': f'Bot {DISCORD_BOT_TOKEN}'}
        response = requests.get(
            f'{DISCORD_API_BASE_URL}/guilds/{GUILD_ID}/members/{user_id}',
            headers=headers
        )
        if response.status_code == 200:
            member_data = response.json()
            roles = [int(role_id) for role_id in member_data.get('roles', [])]
            logger.info(f"✅ Rollen abgerufen für User {user_id}: {len(roles)} Rollen")
            return roles
        else:
            logger.warning(f"⚠️ Rollen-Abfrage fehlgeschlagen: Status {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Fehler bei get_user_roles: {e}")
    return []

def send_discord_notification(message, embed_data=None):
    """Sendet eine Benachrichtigung an den Auszahlungs-Channel"""
    try:
        if not os.path.exists(CONFIG_FILE):
            logger.warning("⚠️ Config-Datei nicht gefunden")
            return False
        
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        channel_id = config.get('auszahlung_channel_id')
        if not channel_id:
            logger.warning("⚠️ Auszahlungs-Channel nicht konfiguriert")
            return False
        
        headers = {
            'Authorization': f'Bot {DISCORD_BOT_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        payload = {'content': message}
        if embed_data:
            payload['embeds'] = [embed_data]
        
        response = requests.post(
            f'{DISCORD_API_BASE_URL}/channels/{channel_id}/messages',
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            logger.info("✅ Discord-Benachrichtigung gesendet")
            return True
        else:
            logger.warning(f"⚠️ Discord-Benachrichtigung fehlgeschlagen: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Fehler bei send_discord_notification: {e}")
        return False

def send_dm_to_user(user_id, embed_data):
    """Sendet eine DM an einen User"""
    try:
        headers = {
            'Authorization': f'Bot {DISCORD_BOT_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # DM Channel erstellen
        dm_response = requests.post(
            f'{DISCORD_API_BASE_URL}/users/{user_id}/channels',
            headers=headers,
            json={'recipient_id': str(user_id)}
        )
        
        if dm_response.status_code == 200:
            dm_channel = dm_response.json()
            
            # DM senden
            msg_response = requests.post(
                f'{DISCORD_API_BASE_URL}/channels/{dm_channel["id"]}/messages',
                headers=headers,
                json={'embeds': [embed_data]}
            )
            
            if msg_response.status_code == 200:
                logger.info(f"✅ DM gesendet an User {user_id}")
                return True
    except Exception as e:
        logger.error(f"❌ Fehler bei send_dm_to_user: {e}")
    return False

# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'oauth2_token' not in session:
            flash('Bitte melde dich an.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def mitarbeiter_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'oauth2_token' not in session:
            flash('Bitte melde dich an.', 'warning')
            return redirect(url_for('login'))
        
        user_roles = session.get('user_roles', [])
        if MITARBEITER_ROLE_ID not in user_roles and LEITUNGSEBENE_ROLE_ID not in user_roles:
            flash('Zugriff verweigert. Nur für Mitarbeiter.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def leitungsebene_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'oauth2_token' not in session:
            flash('Bitte melde dich an.', 'warning')
            return redirect(url_for('login'))
        
        user_roles = session.get('user_roles', [])
        if LEITUNGSEBENE_ROLE_ID not in user_roles:
            flash('Zugriff verweigert. Nur für Leitungsebene.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# FLASK ROUTES
# ============================================

@app.route('/')
def index():
    """Startseite"""
    if 'oauth2_token' not in session:
        return render_template('index.html', logged_in=False)
    
    user = session.get('user')
    user_roles = session.get('user_roles', [])
    
    is_mitarbeiter = MITARBEITER_ROLE_ID in user_roles
    is_leitung = LEITUNGSEBENE_ROLE_ID in user_roles
    
    return render_template(
        'index.html',
        logged_in=True,
        user=user,
        is_mitarbeiter=is_mitarbeiter,
        is_leitung=is_leitung
    )

@app.route('/login')
def login():
    """Discord OAuth2 Login"""
    scope = ['identify', 'guilds', 'guilds.members.read']
    discord = make_session(scope=scope)
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth2_state'] = state
    logger.info("🔐 Login initiiert")
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    """OAuth2 Callback"""
    try:
        if request.values.get('error'):
            error = request.values.get('error')
            logger.warning(f"⚠️ OAuth Error: {error}")
            flash('Login fehlgeschlagen. Bitte erneut versuchen.', 'error')
            return redirect(url_for('index'))
        
        discord = make_session(state=session.get('oauth2_state'))
        token = discord.fetch_token(
            TOKEN_URL,
            client_secret=DISCORD_CLIENT_SECRET,
            authorization_response=request.url
        )
        
        session['oauth2_token'] = token
        
        user = get_user_info(token)
        if not user:
            flash('Fehler beim Abrufen der Benutzerinformationen.', 'error')
            return redirect(url_for('index'))
        
        session['user'] = user
        session['user_roles'] = get_user_roles(user['id'])
        
        logger.info(f"✅ Login erfolgreich: {user.get('username')}")
        flash(f'Willkommen, {user.get("username")}!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"❌ Callback Error: {e}")
        flash('Login fehlgeschlagen. Bitte erneut versuchen.', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    """Logout"""
    username = session.get('user', {}).get('username', 'User')
    session.clear()
    logger.info(f"👋 Logout: {username}")
    flash('Erfolgreich abgemeldet.', 'success')
    return redirect(url_for('index'))

@app.route('/kunde')
@login_required
def kunde_dashboard():
    """Kunden-Dashboard"""
    user = session.get('user')
    user_id = user['id']
    
    data = load_data()
    
    # Finde Kundenakte
    customer_data = None
    customer_id = None
    for cid, customer in data['customers'].items():
        if str(customer['discord_user_id']) == str(user_id):
            customer_data = customer
            customer_id = cid
            break
    
    if not customer_data:
        logger.warning(f"⚠️ Keine Kundenakte für User {user_id}")
        return render_template('kunde.html', no_account=True)
    
    # Guthaben-Historie
    guthaben_history = customer_data.get('guthaben_history', [])
    guthaben_history_copy = guthaben_history.copy()
    guthaben_history_copy.reverse()
    
    logger.info(f"✅ Kunde-Dashboard geladen: {customer_id}")
    return render_template(
        'kunde.html',
        customer=customer_data,
        customer_id=customer_id,
        guthaben_history=guthaben_history_copy[:20]
    )

@app.route('/mitarbeiter')
@mitarbeiter_required
def mitarbeiter_dashboard():
    """Mitarbeiter-Dashboard"""
    data = load_data()
    
    total_customers = len(data['customers'])
    active_customers = sum(1 for c in data['customers'].values() if c.get('status') == 'aktiv')
    pending_auszahlungen = sum(1 for a in data.get('auszahlungen', {}).values() if a.get('status') == 'pending')
    
    logger.info(f"✅ Mitarbeiter-Dashboard: {total_customers} Kunden")
    return render_template(
        'mitarbeiter.html',
        total_customers=total_customers,
        active_customers=active_customers,
        pending_auszahlungen=pending_auszahlungen
    )

@app.route('/mitarbeiter/kunde-suchen', methods=['GET', 'POST'])
@mitarbeiter_required
def kunde_suchen():
    """Kunden suchen"""
    if request.method == 'POST':
        search_query = request.form.get('search', '').strip()
        data = load_data()
        
        results = []
        for customer_id, customer in data['customers'].items():
            if (search_query.lower() in customer_id.lower() or
                search_query.lower() in customer['rp_name'].lower() or
                search_query in str(customer.get('discord_user_id', ''))):
                results.append({
                    'customer_id': customer_id,
                    'customer': customer
                })
        
        logger.info(f"🔍 Suche: '{search_query}' -> {len(results)} Ergebnisse")
        return render_template('kunde_suchen.html', results=results, search_query=search_query)
    
    return render_template('kunde_suchen.html')

@app.route('/mitarbeiter/kunde/<customer_id>')
@mitarbeiter_required
def kunde_details(customer_id):
    """Kunden-Details für Mitarbeiter"""
    data = load_data()
    
    if customer_id not in data['customers']:
        flash('Kunde nicht gefunden.', 'error')
        logger.warning(f"⚠️ Kunde nicht gefunden: {customer_id}")
        return redirect(url_for('kunde_suchen'))
    
    customer = data['customers'][customer_id]
    guthaben_history = customer.get('guthaben_history', [])
    guthaben_history_copy = guthaben_history.copy()
    guthaben_history_copy.reverse()
    
    # Auszahlungen dieses Kunden
    customer_auszahlungen = {
        aid: ausz for aid, ausz in data.get('auszahlungen', {}).items()
        if ausz.get('customer_id') == customer_id
    }
    
    logger.info(f"✅ Kunde-Details: {customer_id}")
    return render_template(
        'kunde_details.html',
        customer_id=customer_id,
        customer=customer,
        guthaben_history=guthaben_history_copy[:50],
        auszahlungen=customer_auszahlungen
    )

@app.route('/mitarbeiter/auszahlung-erstellen/<customer_id>', methods=['POST'])
@mitarbeiter_required
def auszahlung_erstellen(customer_id):
    """Erstellt eine neue Auszahlung"""
    data = load_data()
    
    if customer_id not in data['customers']:
        flash('Kunde nicht gefunden.', 'error')
        return redirect(url_for('kunde_suchen'))
    
    try:
        betrag = float(request.form.get('betrag', 0))
        beschreibung = request.form.get('beschreibung', '')
    except ValueError:
        flash('Ungültiger Betrag.', 'error')
        return redirect(url_for('kunde_details', customer_id=customer_id))
    
    if betrag <= 0:
        flash('Betrag muss größer als 0 sein.', 'error')
        return redirect(url_for('kunde_details', customer_id=customer_id))
    
    customer = data['customers'][customer_id]
    
    if betrag > customer.get('guthaben', 0):
        flash('Nicht genug Guthaben verfügbar.', 'error')
        return redirect(url_for('kunde_details', customer_id=customer_id))
    
    # Auszahlung erstellen
    auszahlung_id = generate_auszahlung_id()
    user = session.get('user')
    
    if 'auszahlungen' not in data:
        data['auszahlungen'] = {}
    
    data['auszahlungen'][auszahlung_id] = {
        'customer_id': customer_id,
        'customer_name': customer['rp_name'],
        'betrag': betrag,
        'beschreibung': beschreibung,
        'status': 'pending',
        'erstellt_von': user['id'],
        'erstellt_von_name': user['username'],
        'erstellt_am': datetime.now().isoformat(),
        'genehmigt_von': None,
        'genehmigt_am': None
    }
    
    save_data(data)
    
    # Discord Benachrichtigung
    embed = {
        'title': '💰 Neue Auszahlungsanfrage',
        'color': 0xE67E22,
        'fields': [
            {'name': '🆔 Auszahlungs-ID', 'value': f'`{auszahlung_id}`', 'inline': True},
            {'name': '👤 Kunde', 'value': f'{customer["rp_name"]}\n`{customer_id}`', 'inline': True},
            {'name': '💰 Betrag', 'value': f'**{betrag:,.2f} €**', 'inline': True},
            {'name': '📝 Beschreibung', 'value': beschreibung, 'inline': False},
            {'name': '👤 Erstellt von', 'value': f'{user["username"]}', 'inline': True},
            {'name': '🕐 Zeitstempel', 'value': datetime.now().strftime('%d.%m.%Y • %H:%M:%S'), 'inline': True}
        ],
        'footer': {'text': f'Dashboard • Auszahlung {auszahlung_id}'}
    }
    
    send_discord_notification(f'<@&{LEITUNGSEBENE_ROLE_ID}>', embed)
    
    logger.info(f"✅ Auszahlung erstellt: {auszahlung_id} ({betrag}€)")
    flash(f'Auszahlung {auszahlung_id} wurde erstellt und wartet auf Genehmigung.', 'success')
    return redirect(url_for('kunde_details', customer_id=customer_id))

@app.route('/mitarbeiter/guthaben-aufladen/<customer_id>', methods=['POST'])
@mitarbeiter_required
def guthaben_aufladen(customer_id):
    """Lädt Guthaben für einen Kunden auf"""
    data = load_data()
    
    if customer_id not in data['customers']:
        flash('Kunde nicht gefunden.', 'error')
        return redirect(url_for('kunde_suchen'))
    
    try:
        betrag = float(request.form.get('betrag', 0))
        beschreibung = request.form.get('beschreibung', 'Guthaben-Aufladung durch Mitarbeiter')
    except ValueError:
        flash('Ungültiger Betrag.', 'error')
        return redirect(url_for('kunde_details', customer_id=customer_id))
    
    if betrag <= 0:
        flash('Betrag muss größer als 0 sein.', 'error')
        return redirect(url_for('kunde_details', customer_id=customer_id))
    
    user = session.get('user')
    
    # Guthaben erhöhen
    data['customers'][customer_id]['guthaben'] = data['customers'][customer_id].get('guthaben', 0) + betrag
    
    # Historie
    add_guthaben_history(customer_id, betrag, 'aufladung', beschreibung, user['id'])
    
    logger.info(f"✅ Guthaben aufgeladen: {customer_id} +{betrag}€")
    flash(f'{betrag:,.2f} € wurden erfolgreich aufgeladen.', 'success')
    return redirect(url_for('kunde_details', customer_id=customer_id))

@app.route('/leitung')
@leitungsebene_required
def leitung_dashboard():
    """Leitungsebene Dashboard"""
    data = load_data()
    
    total_customers = len(data['customers'])
    total_guthaben = sum(c.get('guthaben', 0) for c in data['customers'].values())
    pending_auszahlungen = {
        aid: ausz for aid, ausz in data.get('auszahlungen', {}).items()
        if ausz.get('status') == 'pending'
    }
    
    logger.info(f"✅ Leitungs-Dashboard: {len(pending_auszahlungen)} offene Auszahlungen")
    return render_template(
        'leitung.html',
        total_customers=total_customers,
        total_guthaben=total_guthaben,
        pending_auszahlungen=pending_auszahlungen
    )

@app.route('/leitung/auszahlung-genehmigen/<auszahlung_id>', methods=['POST'])
@leitungsebene_required
def auszahlung_genehmigen(auszahlung_id):
    """Genehmigt eine Auszahlung"""
    data = load_data()
    
    if auszahlung_id not in data.get('auszahlungen', {}):
        flash('Auszahlung nicht gefunden.', 'error')
        return redirect(url_for('leitung_dashboard'))
    
    auszahlung = data['auszahlungen'][auszahlung_id]
    
    if auszahlung['status'] != 'pending':
        flash('Auszahlung wurde bereits bearbeitet.', 'warning')
        return redirect(url_for('leitung_dashboard'))
    
    customer_id = auszahlung['customer_id']
    betrag = auszahlung['betrag']
    
    if customer_id not in data['customers']:
        flash('Kunde nicht gefunden.', 'error')
        return redirect(url_for('leitung_dashboard'))
    
    customer = data['customers'][customer_id]
    
    if betrag > customer.get('guthaben', 0):
        flash('Nicht genug Guthaben verfügbar.', 'error')
        return redirect(url_for('leitung_dashboard'))
    
    user = session.get('user')
    
    # Guthaben abziehen
    data['customers'][customer_id]['guthaben'] -= betrag
    
    # Auszahlung genehmigen
    data['auszahlungen'][auszahlung_id]['status'] = 'genehmigt'
    data['auszahlungen'][auszahlung_id]['genehmigt_von'] = user['id']
    data['auszahlungen'][auszahlung_id]['genehmigt_von_name'] = user['username']
    data['auszahlungen'][auszahlung_id]['genehmigt_am'] = datetime.now().isoformat()
    
    # Historie
    beschreibung = f"Auszahlung genehmigt: {auszahlung.get('beschreibung', 'Keine Beschreibung')}"
    add_guthaben_history(customer_id, -betrag, 'auszahlung', beschreibung, user['id'])
    
    # Prüfe ob Guthaben auf 0€ gefallen ist
    neues_guthaben = data['customers'][customer_id]['guthaben']
    if neues_guthaben <= 0:
        # DM an Kunden senden
        embed = {
            'title': '⚠️ Versicherungsguthaben aufgebraucht',
            'description': 'Ihr Versicherungsguthaben ist aufgebraucht.',
            'color': 0xE74C3C,
            'fields': [
                {'name': '💰 Aktuelles Guthaben', 'value': '**0,00 €**', 'inline': True},
                {'name': '📋 Hinweis', 'value': 'Bitte wenden Sie sich an unsere Versicherung für eine Aufladung.', 'inline': False}
            ]
        }
        send_dm_to_user(customer['discord_user_id'], embed)
        logger.warning(f"⚠️ Guthaben aufgebraucht: {customer_id}")
    
    logger.info(f"✅ Auszahlung genehmigt: {auszahlung_id}")
    flash(f'Auszahlung {auszahlung_id} wurde genehmigt.', 'success')
    return redirect(url_for('leitung_dashboard'))

@app.route('/leitung/auszahlung-ablehnen/<auszahlung_id>', methods=['POST'])
@leitungsebene_required
def auszahlung_ablehnen(auszahlung_id):
    """Lehnt eine Auszahlung ab"""
    data = load_data()
    
    if auszahlung_id not in data.get('auszahlungen', {}):
        flash('Auszahlung nicht gefunden.', 'error')
        return redirect(url_for('leitung_dashboard'))
    
    auszahlung = data['auszahlungen'][auszahlung_id]
    
    if auszahlung['status'] != 'pending':
        flash('Auszahlung wurde bereits bearbeitet.', 'warning')
        return redirect(url_for('leitung_dashboard'))
    
    user = session.get('user')
    grund = request.form.get('grund', 'Kein Grund angegeben')
    
    data['auszahlungen'][auszahlung_id]['status'] = 'abgelehnt'
    data['auszahlungen'][auszahlung_id]['abgelehnt_von'] = user['id']
    data['auszahlungen'][auszahlung_id]['abgelehnt_von_name'] = user['username']
    data['auszahlungen'][auszahlung_id]['abgelehnt_am'] = datetime.now().isoformat()
    data['auszahlungen'][auszahlung_id]['ablehnungsgrund'] = grund
    
    save_data(data)
    
    logger.info(f"✅ Auszahlung abgelehnt: {auszahlung_id}")
    flash(f'Auszahlung {auszahlung_id} wurde abgelehnt.', 'warning')
    return redirect(url_for('leitung_dashboard'))

@app.route('/health')
def health():
    """Health Check Endpoint"""
    data = load_data()
    return {
        'status': 'healthy',
        'service': 'insuranceguard-dashboard',
        'customers': len(data.get('customers', {})),
        'timestamp': datetime.now().isoformat()
    }, 200

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    
    logger.info("=" * 60)
    logger.info("🛡️  InsuranceGuard v2 Dashboard")
    logger.info("=" * 60)
    logger.info(f"🌐 Starting on port {port}")
    logger.info(f"📁 Data directory: {DATA_DIR}")
    logger.info(f"🔗 Redirect URI: {DISCORD_REDIRECT_URI}")
    logger.info(f"🆔 Client ID: {DISCORD_CLIENT_ID[:10]}...")
    logger.info(f"🔑 Bot Token: {'✅ Set' if DISCORD_BOT_TOKEN else '❌ Missing'}")
    logger.info("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
