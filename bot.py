import os
import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
 
# ============================================================
# CLÉS API (variables d'environnement sur Render)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Ex: https://ton-app.onrender.com
PORT = int(os.environ.get("PORT", 8443))
# ============================================================
 
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
 
# Mémoire de session par utilisateur
user_sessions = {}
 
def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {"format": None}
    return user_sessions[user_id]
 
# ============================================================
# COMMANDE /start
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """♠️ Bienvenue sur GTO Poker Bot
 
Ton assistant stratégique en temps réel.
Analyse GTO + exploitative en 3 secondes.
 
━━━━━━━━━━━━━━━
🚀 DÉMARRAGE RAPIDE
 
1️⃣ Choisis ton format :
/format cash
/format mtt 40bb bulle
/format spin
 
2️⃣ Envoie ta main en une ligne :
POS/POS | CARTES | BOARD | ACTION/POT | STACK | READ
 
3️⃣ Reçois ton analyse instantanée
━━━━━━━━━━━━━━━
📋 EXEMPLE CONCRET
 
Tu es BTN, adversaire BB
Tu as A♠K♦, flop K♥7♣2♦
Il cbet 5BB, pot 10BB, stacks 50BB
C'est un fish
 
👉 Envoie :
BTN/BB | AKs | K72r | cbet5/10 | 50bb | fish
 
━━━━━━━━━━━━━━━
📌 COMMANDES DISPONIBLES
 
/start → ce guide
/format → choisir cash, mtt ou spin
/aide → toutes les abréviations
/stat → comprendre vpip, af, 3bet
━━━━━━━━━━━━━━━
⚡ Prêt ? Commence par /format"""
    await update.message.reply_text(msg)
 
# ============================================================
# COMMANDE /format
# ============================================================
async def format_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    args = context.args
 
    if not args:
        current = session["format"] or "Non défini"
        await update.message.reply_text(
            f"📌 Format actuel : {current}\n\n"
            "Choisis ton format :\n"
            "/format cash\n"
            "/format mtt [stack] [phase]\n"
            "/format spin\n\n"
            "Exemple MTT : /format mtt 40bb bulle"
        )
        return
 
    fmt = args[0].lower()
 
    if fmt == "cash":
        session["format"] = "cash"
        await update.message.reply_text(
            "✅ Mode activé : CASH GAME\n\n"
            "📊 Paramètres :\n"
            "· Stacks profonds 100BB+\n"
            "· Analyse GTO pure + exploitative\n"
            "· EV long terme prioritaire\n"
            "· ICM désactivé\n\n"
            "Envoie ta première main 🃏"
        )
 
    elif fmt == "mtt":
        stack = args[1] if len(args) > 1 else "?"
        phase = args[2] if len(args) > 2 else "?"
        session["format"] = f"mtt_{stack}_{phase}"
        icm = "🔴 Très haute" if phase in ["bulle", "ft"] else "🟡 Moyenne"
        await update.message.reply_text(
            f"✅ Mode activé : MTT\n\n"
            f"📊 Paramètres :\n"
            f"· Stack : {stack}\n"
            f"· Phase : {phase}\n"
            f"· ICM pressure : {icm}\n"
            f"· Ranges adaptées à la phase\n\n"
            "Envoie ta première main 🃏"
        )
 
    elif fmt == "spin":
        session["format"] = "spin"
        await update.message.reply_text(
            "✅ Mode activé : SPIN & GO\n\n"
            "📊 Paramètres :\n"
            "· Mode push/fold mathématique\n"
            "· Stacks courts 25BB max\n"
            "· Réponse : PUSH ou FOLD\n\n"
            "Envoie ta première main 🃏"
        )
 
    else:
        await update.message.reply_text(
            "❌ Format non reconnu.\n\n"
            "Utilise :\n"
            "/format cash\n"
            "/format mtt [stack] [phase]\n"
            "/format spin"
        )
 
# ============================================================
# COMMANDE /aide
# ============================================================
async def aide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """📖 ABRÉVIATIONS
 
📍 Positions
UTG · UTG+1 · MP · HJ · CO · BTN · SB · BB
 
🃏 Cartes
s = suited (ex: AKs)
o = offsuit (ex: AKo)
 
🎴 Board
r = rainbow · dd = 2 couleurs
fd = flushdraw · sd = straightdraw
Turn : "K72r t8" — River : "K72r t8 r3"
 
⚔️ Actions
cbet · donk · 3bet · jam · check · raise
+ montant/pot en BB (ex: cbet5/10)
 
🧠 Reads
fish · reg · nit · lag · tag
 
📊 Stats (optionnel)
vpip30 · af2 · 3bet8
 
━━━━━━━━━━━━━━━
✏️ FORMAT COMPLET
POS/POS | CARTES | BOARD | ACTION/POT | STACK | READ
 
Exemple :
BTN/BB | AKs | K72r | cbet5/10 | 50bb | fish·vpip70"""
    await update.message.reply_text(msg)
 
# ============================================================
# COMMANDE /stat
# ============================================================
async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """📊 COMPRENDRE LES STATS
 
VPIP (% mains jouées)
< 20 = nit/tight
20-30 = reg standard
> 40 = fish/loose
 
AF (Agressivité)
< 2 = passif
2-3 = équilibré
> 3 = très agressif
 
3BET (% de 3bet)
< 5 = tight
5-8 = standard
> 8 = très agressif/bluffeur
 
━━━━━━━━━━━━━━━
💡 Plus tu donnes de stats,
plus l'analyse est précise.
 
Exemple avec stats :
BTN/BB | AKs | K72r | cbet5/10 | 50bb | reg·vpip24·af3·3bet6"""
    await update.message.reply_text(msg)
 
# ============================================================
# ANALYSE D'UNE MAIN
# ============================================================
async def analyze_hand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    text = update.message.text.strip()
 
    if not session["format"]:
        await update.message.reply_text(
            "⚠️ Choisis d'abord ton format :\n\n"
            "/format cash\n"
            "/format mtt [stack] [phase]\n"
            "/format spin"
        )
        return
 
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 4:
        await update.message.reply_text(
            "❌ Format incomplet.\n\n"
            "Format attendu :\n"
            "POS/POS | CARTES | BOARD | ACTION/POT | STACK | READ\n\n"
            "Tape /aide pour les abréviations."
        )
        return
 
    fmt = session["format"]
    if fmt == "cash":
        format_context = "Cash game, stacks profonds 100BB+. Analyse GTO pure + exploitative. Priorité EV long terme. Pas d'ICM."
    elif fmt == "spin":
        format_context = "Spin & Go, stacks courts. Mode PUSH/FOLD mathématique uniquement. Réponse PUSH ou FOLD + equity requise."
    elif fmt.startswith("mtt"):
        parts_fmt = fmt.split("_")
        stack = parts_fmt[1] if len(parts_fmt) > 1 else "?"
        phase = parts_fmt[2] if len(parts_fmt) > 2 else "?"
        icm = "très haute" if phase in ["bulle", "ft"] else "moyenne"
        format_context = f"Tournoi MTT, stack {stack}, phase {phase}, pression ICM {icm}. Intégrer ICM dans la décision."
    else:
        format_context = "Cash game standard."
 
    prompt = f"""Tu es un expert poker GTO de haut niveau. Analyse cette situation en tenant compte du format de jeu.
 
FORMAT DE JEU : {format_context}
 
MAIN SOUMISE : {text}
 
Réponds UNIQUEMENT avec ce format exact, sans rien ajouter :
♠ DÉCISION : [FOLD/CALL/RAISE/BET/CHECK ou PUSH/FOLD]
📐 Sizing : [montant exact en BB ou N/A]
📊 Pot odds : [%] | Equity min : [%] | SPR : [valeur]
🎯 GTO : [fréquences ex: raise 70% / call 30%]
⚡ Exploit : [ajustement selon le read en 1 phrase]
🔑 Facteur clé : [1 phrase maximum]
⚠️ Attention : [piège ou erreur fréquente en 1 phrase]
 
Règles :
- Maximum 8 lignes
- Sois précis et direct
- Adapte l'analyse au format de jeu et aux reads fournis
- Si spin : réponse PUSH/FOLD uniquement avec % equity"""
 
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        result = response.content[0].text
        await update.message.reply_text(result)
 
    except Exception as e:
        await update.message.reply_text(
            "❌ Erreur d'analyse. Réessaie dans quelques secondes."
        )
 
# ============================================================
# LANCEMENT DU BOT — WEBHOOK (requis pour Render)
# ============================================================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("format", format_cmd))
    app.add_handler(CommandHandler("aide", aide))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_hand))
 
    print(f"Bot démarré en mode WEBHOOK sur le port {PORT} ✅")
 
    # Webhook : Telegram envoie les updates à ton URL Render
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{WEBHOOK_URL}/webhook",
        url_path="webhook",
    )
 
if __name__ == "__main__":
    main()
 
