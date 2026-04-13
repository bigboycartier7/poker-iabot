import os
import re
import json
import random
import base64
import anthropic
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
 
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
 
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
 
ADMIN_ID = 1854985221
DAILY_LIMIT_TEXT = 25
DAILY_LIMIT_IMAGE = 5
DATA_FILE = "sessions.json"
 
user_sessions = {}
user_limits = {}
user_history = {}
user_bilan = {}
 
def save_data():
    try:
        data = {}
        for uid, session in user_sessions.items():
            data[str(uid)] = {
                "format": session.get("format"),
                "focus": session.get("focus", False)
            }
        with open(DATA_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass
 
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            for uid, session in data.items():
                user_sessions[int(uid)] = {
                    "format": session.get("format"),
                    "focus": session.get("focus", False),
                    "hand": {},
                    "step": None
                }
    except:
        pass
 
def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {"format": None, "focus": False, "hand": {}, "step": None}
    return user_sessions[user_id]
 
def get_history(user_id):
    if user_id not in user_history:
        user_history[user_id] = []
    return user_history[user_id]
 
def get_bilan(user_id):
    if user_id not in user_bilan:
        user_bilan[user_id] = {"total": 0, "gagne": 0, "perdu": 0, "pending_id": None}
    return user_bilan[user_id]
 
def add_to_history(user_id, hand, decision):
    history = get_history(user_id)
    entry = {
        "time": datetime.now().strftime("%H:%M"),
        "cartes": hand.get("cards", "?"),
        "board": hand.get("board", "preflop"),
        "street": hand.get("street", "?"),
        "positions": hand.get("mypos", "?") + "/" + hand.get("villainpos", "?"),
        "decision": decision
    }
    history.append(entry)
    if len(history) > 5:
        history.pop(0)
 
def get_limits(user_id):
    if user_id == ADMIN_ID:
        return True, 999, True, 999
    now = datetime.now()
    if user_id not in user_limits:
        user_limits[user_id] = {"text_count": 0, "image_count": 0, "reset": now + timedelta(hours=24)}
    if now > user_limits[user_id]["reset"]:
        user_limits[user_id] = {"text_count": 0, "image_count": 0, "reset": now + timedelta(hours=24)}
    text_left = DAILY_LIMIT_TEXT - user_limits[user_id]["text_count"]
    image_left = DAILY_LIMIT_IMAGE - user_limits[user_id]["image_count"]
    return text_left > 0, text_left, image_left > 0, image_left
 
def increment_text(user_id):
    if user_id == ADMIN_ID:
        return
    user_limits[user_id]["text_count"] += 1
 
def increment_image(user_id):
    if user_id == ADMIN_ID:
        return
    user_limits[user_id]["image_count"] += 1
 
def get_time_left(user_id):
    if user_id not in user_limits:
        return "24h00min"
    attente = user_limits[user_id]["reset"] - datetime.now()
    heures = int(attente.seconds / 3600)
    minutes = int((attente.seconds % 3600) / 60)
    return str(heures) + "h" + str(minutes) + "min"
 
def get_range_estimate(read, vpip=None, af=None, three_bet=None):
    read = read.lower()
    if vpip is not None:
        if vpip < 15:
            strong, medium, bluff, profil = 80, 15, 5, "ULTRA NIT (vpip " + str(vpip) + ")"
        elif vpip < 22:
            strong, medium, bluff, profil = 55, 33, 12, "NIT (vpip " + str(vpip) + ")"
        elif vpip < 30:
            strong, medium, bluff, profil = 35, 40, 25, "REG (vpip " + str(vpip) + ")"
        elif vpip < 40:
            strong, medium, bluff, profil = 25, 35, 40, "LAG (vpip " + str(vpip) + ")"
        else:
            strong, medium, bluff, profil = 20, 35, 45, "FISH (vpip " + str(vpip) + ")"
        if af is not None:
            if af < 2:
                bluff = max(0, bluff - 10)
                strong += 5
            elif af > 3:
                bluff = min(60, bluff + 10)
                strong = max(10, strong - 5)
        if three_bet is not None:
            if three_bet > 8:
                bluff = min(60, bluff + 8)
            elif three_bet < 4:
                bluff = max(0, bluff - 8)
                strong += 5
        total = strong + medium + bluff
        medium += 100 - total
        return profil, strong, medium, bluff
    ranges = {
        "nit": ("NIT", 80, 15, 5),
        "fish": ("FISH", 30, 30, 40),
        "lag": ("LAG", 25, 35, 40),
        "tag": ("TAG", 45, 35, 20),
        "reg": ("REG", 35, 40, 25),
        "inconnu": ("INCONNU", 35, 35, 30),
    }
    profil, strong, medium, bluff = ranges.get(read, ("INCONNU", 35, 35, 30))
    return profil, strong, medium, bluff
 
def get_bluff_index(board, cards, read):
    score = 5
    read = read.lower()
    board = board.lower()
    cards = cards.lower()
 
    if read in ["nit", "tag"]:
        score -= 3
    elif read in ["fish", "lag"]:
        score += 2
 
    if "r" in board and "fd" not in board and "sd" not in board:
        score += 1
    if "fd" in board or "dd" in board:
        score -= 1
    if "a" in cards:
        score += 1
    if "k" in cards:
        score += 1
 
    score = max(0, min(10, score))
 
    if score <= 3:
        label = "Faible - Evite le bluff"
    elif score <= 6:
        label = "Moyen - Bluff selectif"
    else:
        label = "Eleve - Bonne opportunite"
 
    return score, label
 
def get_randomizer(gto_text, decision_principale=None):
    de = random.randint(1, 100)
    matches = re.findall(r'(\w+)\s+(\d+)%', gto_text.lower())
    if matches:
        action = matches[0][0].upper()
        freq = int(matches[0][1])
        action_finale = action if de <= freq else "ACTION ALTERNATIVE"
        return de, freq, action, action_finale
    if decision_principale:
        return de, 100, decision_principale, decision_principale
    return de, 50, "ACTION", "ACTION"
 
def parse_stats(read_str):
    vpip = af = three_bet = None
    vpip_match = re.search(r'vpip(\d+)', read_str.lower())
    af_match = re.search(r'af(\d+)', read_str.lower())
    bet_match = re.search(r'3bet(\d+)', read_str.lower())
    if vpip_match:
        vpip = int(vpip_match.group(1))
    if af_match:
        af = int(af_match.group(1))
    if bet_match:
        three_bet = int(bet_match.group(1))
    read_clean = re.sub(r'vpip\d+|af\d+|3bet\d+', '', read_str).strip()
    return read_clean, vpip, af, three_bet
 
def result_keyboard(hand_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Gagne", callback_data="win_" + str(hand_id)),
         InlineKeyboardButton("Perdu", callback_data="lose_" + str(hand_id))]
    ])
 
def pos_keyboard(prefix):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("UTG", callback_data=prefix+"UTG"),
         InlineKeyboardButton("UTG+1", callback_data=prefix+"UTG+1"),
         InlineKeyboardButton("MP", callback_data=prefix+"MP"),
         InlineKeyboardButton("HJ", callback_data=prefix+"HJ")],
        [InlineKeyboardButton("CO", callback_data=prefix+"CO"),
         InlineKeyboardButton("BTN", callback_data=prefix+"BTN"),
         InlineKeyboardButton("SB", callback_data=prefix+"SB"),
         InlineKeyboardButton("BB", callback_data=prefix+"BB")]
    ])
 
def street_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Preflop", callback_data="s_preflop"),
         InlineKeyboardButton("Flop", callback_data="s_flop")],
        [InlineKeyboardButton("Turn", callback_data="s_turn"),
         InlineKeyboardButton("River", callback_data="s_river")]
    ])
 
def stack_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("15bb", callback_data="bb_15"),
         InlineKeyboardButton("25bb", callback_data="bb_25"),
         InlineKeyboardButton("50bb", callback_data="bb_50"),
         InlineKeyboardButton("75bb", callback_data="bb_75")],
        [InlineKeyboardButton("100bb", callback_data="bb_100"),
         InlineKeyboardButton("150bb", callback_data="bb_150"),
         InlineKeyboardButton("200bb", callback_data="bb_200")]
    ])
 
def read_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Fish", callback_data="r_fish"),
         InlineKeyboardButton("Reg", callback_data="r_reg"),
         InlineKeyboardButton("Nit", callback_data="r_nit")],
        [InlineKeyboardButton("LAG", callback_data="r_lag"),
         InlineKeyboardButton("TAG", callback_data="r_tag"),
         InlineKeyboardButton("Inconnu", callback_data="r_inconnu")]
    ])
 
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*GTO Poker Bot*\n\n"
        "Ton coach strategique en temps reel.\n\n"
        "*COMMANDES*\n"
        "/m analyser une main\n"
        "/photo capture d ecran\n"
        "/focus mode minimaliste ON/OFF\n"
        "/bilan statistiques de session\n"
        "/historique 5 dernieres mains\n"
        "/format cash mtt spin\n"
        "/reset remettre a zero\n"
        "/aide lexique complet\n"
        "/stat comprendre vpip af 3bet",
        parse_mode='Markdown'
    )
 
async def focus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    session["focus"] = not session.get("focus", False)
    save_data()
    if session["focus"]:
        await update.message.reply_text(
            "*Mode Focus ON*\n"
            "Reponses ultra-minimalistes activees.\n"
            "Format : DECISION | SIZING | RANGE | DE GTO\n\n"
            "Tape /focus pour desactiver.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "*Mode Focus OFF*\n"
            "Analyse complete reactive.\n\n"
            "Tape /focus pour reactiver.",
            parse_mode='Markdown'
        )
 
async def bilan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bilan = get_bilan(user_id)
    total = bilan["total"]
    gagne = bilan["gagne"]
    perdu = bilan["perdu"]
    if total == 0:
        await update.message.reply_text(
            "*Bilan de session*\n\nAucune main enregistree pour l instant.\nTape /m pour commencer !",
            parse_mode='Markdown'
        )
        return
    taux = round((gagne / total) * 100) if total > 0 else 0
    non_renseigne = total - gagne - perdu
    await update.message.reply_text(
        "*Bilan de Session*\n\n"
        "Mains jouees : " + str(total) + "\n"
        "Gagnees : " + str(gagne) + "\n"
        "Perdues : " + str(perdu) + "\n"
        "Non renseignees : " + str(non_renseigne) + "\n\n"
        "*Taux de succes : " + str(taux) + "%*\n\n"
        + ("Excellente session ! Continue comme ca." if taux >= 60
           else "Session correcte, reste concentre." if taux >= 40
           else "Session difficile, analyse tes erreurs avec /historique."),
        parse_mode='Markdown'
    )
 
async def m_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text_ok, text_left, image_ok, image_left = get_limits(user_id)
    if not text_ok:
        await update.message.reply_text(
            "*Limite atteinte* : " + str(DAILY_LIMIT_TEXT) + "/" + str(DAILY_LIMIT_TEXT) + " analyses\n"
            "Renouvellement dans " + get_time_left(user_id) + "\n"
            "Il te reste " + str(image_left) + " analyses photo via /photo",
            parse_mode='Markdown'
        )
        return
    session = get_session(user_id)
    session["hand"] = {}
    session["step"] = "mypos"
    await update.message.reply_text(
        "*Nouvelle main - Etape 1/6*\nTa position :",
        reply_markup=pos_keyboard("mypos_"),
        parse_mode='Markdown'
    )
 
async def photo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text_ok, text_left, image_ok, image_left = get_limits(user_id)
    if not image_ok:
        await update.message.reply_text(
            "*Limite photos atteinte* : " + str(DAILY_LIMIT_IMAGE) + "/" + str(DAILY_LIMIT_IMAGE) + "\n"
            "Renouvellement dans " + get_time_left(user_id) + "\n"
            "Il te reste " + str(text_left) + " analyses boutons via /m",
            parse_mode='Markdown'
        )
        return
    session = get_session(user_id)
    session["step"] = "waiting_photo"
    await update.message.reply_text(
        "*Envoie ta capture d ecran*\n\n"
        "Le bot va lire automatiquement :\n"
        "- Tes cartes et le board\n"
        "- Les positions et stacks\n"
        "- L action en cours\n\n"
        "Il te restera *" + str(image_left) + "* analyse(s) photo apres celle-ci.",
        parse_mode='Markdown'
    )
 
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    session["hand"] = {}
    session["step"] = None
    await update.message.reply_text("Main remise a zero.\nTape /m ou /photo pour recommencer !")
 
async def historique_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_history(user_id)
    if not history:
        await update.message.reply_text("Aucune main analysee.\nTape /m pour commencer !")
        return
    msg = "*Tes 5 dernieres mains*\n\n"
    for i, entry in enumerate(reversed(history), 1):
        msg += (str(i) + ". " + entry["time"] + " - " + entry["positions"] + "\n"
                "Cartes : " + entry["cartes"] + " | " + entry["street"] + "\n"
                "Board : " + entry["board"] + "\n"
                "Decision : *" + entry["decision"] + "*\n\n")
    await update.message.reply_text(msg, parse_mode='Markdown')
 
async def format_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    args = context.args
    if not args:
        current = session["format"] or "Non defini"
        await update.message.reply_text("Format actuel : " + current + "\n\n/format cash\n/format mtt [stack] [phase]\n/format spin")
        return
    fmt = args[0].lower()
    if fmt == "cash":
        session["format"] = "cash"
        save_data()
        await update.message.reply_text("*Mode CASH GAME active*\nTape /m pour analyser !", parse_mode='Markdown')
    elif fmt == "mtt":
        stack = args[1] if len(args) > 1 else "?"
        phase = args[2] if len(args) > 2 else "?"
        session["format"] = "mtt_" + stack + "_" + phase
        save_data()
        await update.message.reply_text("*Mode MTT active*\nStack : " + stack + " | Phase : " + phase + "\nTape /m pour analyser !", parse_mode='Markdown')
    elif fmt == "spin":
        session["format"] = "spin"
        save_data()
        await update.message.reply_text("*Mode SPIN & GO active*\nTape /m pour analyser !", parse_mode='Markdown')
    else:
        await update.message.reply_text("/format cash\n/format mtt [stack] [phase]\n/format spin")
 
async def aide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*GUIDE COMPLET + LEXIQUE*\n\n"
        "*POSITIONS*\n"
        "UTG : 1er a parler, position difficile\n"
        "MP : position intermediaire\n"
        "HJ : 2 places avant le bouton\n"
        "CO : juste avant le bouton\n"
        "BTN : meilleure position, parle en dernier\n"
        "SB : mise forcee, parle en 1er apres flop\n"
        "BB : mise forcee double\n\n"
        "*CARTES*\n"
        "s = suited = meme couleur (AKs)\n"
        "o = offsuit = couleurs diff (AKo)\n\n"
        "*BOARD*\n"
        "r = rainbow, fd = flushdraw, sd = straightdraw\n"
        "dd = 2 couleurs, t = turn, r = river\n\n"
        "*ACTIONS*\n"
        "Check : passer sans miser\n"
        "Call : suivre la mise\n"
        "Fold : abandonner\n"
        "Raise/3bet/4bet : relances successives\n"
        "Jam : tapis total\n"
        "Cbet : mise continuation preflop\n"
        "Donk : miser hors de position\n\n"
        "*PROFILS*\n"
        "Fish : joueur faible, joue trop\n"
        "Reg : joueur regulier competent\n"
        "Nit : ultra serre, zero bluff\n"
        "TAG : serre mais agressif\n"
        "LAG : large et tres agressif\n\n"
        "*TERMES GTO*\n"
        "GTO : strategie mathematiquement parfaite\n"
        "EV : gain moyen attendu\n"
        "ICM : pression tournoi\n"
        "SPR : rapport stack/pot\n"
        "Equity : proba de gagner en %\n"
        "Pot odds : rapport mise/pot\n"
        "Range : toutes les mains possibles\n"
        "Fold equity : chance de faire folder\n"
        "Bloqueur : carte qui reduit la range adverse\n\n"
        "*STATS AVANCEES*\n"
        "Apres le read : vpip24 af3 3bet6\n"
        "Calcul de range precise !\n\n"
        "*LIMITES*\n"
        "Analyses boutons : 25/24h\n"
        "Analyses photo : 5/24h",
        parse_mode='Markdown'
    )
 
async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*COMPRENDRE LES STATS*\n\n"
        "*VPIP*\n"
        "moins de 15 = ultra nit\n"
        "15-22 = nit\n"
        "22-30 = reg\n"
        "30-40 = lag\n"
        "plus de 40 = fish\n\n"
        "*AF (Agressivite)*\n"
        "moins de 2 = passif\n"
        "2-3 = equilibre\n"
        "plus de 3 = tres agressif\n\n"
        "*3BET*\n"
        "moins de 4 = tight\n"
        "4-8 = standard\n"
        "plus de 8 = tres agressif",
        parse_mode='Markdown'
    )
 
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = get_session(user_id)
    data = query.data
 
    if data.startswith("win_"):
        bilan = get_bilan(user_id)
        bilan["gagne"] += 1
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="Gagne enregistre ! /bilan pour tes stats.")
        return
 
    if data.startswith("lose_"):
        bilan = get_bilan(user_id)
        bilan["perdu"] += 1
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="Perdu enregistre. Analyse tes erreurs avec /historique.")
        return
 
    if data.startswith("mypos_"):
        pos = data.replace("mypos_", "")
        session["hand"]["mypos"] = pos
        session["step"] = "villainpos"
        await query.edit_message_text(
            "Ta position : *" + pos + "*\n\nEtape 2/6\nPosition adverse :",
            reply_markup=pos_keyboard("vpos_"),
            parse_mode='Markdown'
        )
    elif data.startswith("vpos_"):
        pos = data.replace("vpos_", "")
        session["hand"]["villainpos"] = pos
        session["step"] = "cards"
        await query.edit_message_text(
            "Ta position : " + session["hand"]["mypos"] + "\n"
            "Position adverse : *" + pos + "*\n\n"
            "Etape 3/6\nTape tes 2 cartes :\n"
            "ex: AKs - QQ - T9o",
            parse_mode='Markdown'
        )
    elif data.startswith("s_"):
        street = data.replace("s_", "")
        session["hand"]["street"] = street
        if street == "preflop":
            session["step"] = "action"
            await query.edit_message_text(
                "Street : *Preflop*\n\nEtape 5/6\nTape l action adverse :\n"
                "ex: open - 3bet9/3 - jam - check",
                parse_mode='Markdown'
            )
        else:
            session["step"] = "board"
            await query.edit_message_text(
                "Street : *" + street + "*\n\nEtape 5/6\nTape le board :\n"
                "ex: K72r - 952dd - K72r t8",
                parse_mode='Markdown'
            )
    elif data.startswith("bb_"):
        stack = data.replace("bb_", "") + "bb"
        session["hand"]["stack"] = stack
        session["step"] = "read"
        await query.edit_message_text(
            "Stack : *" + stack + "*\n\nEtape 6/6\nRead adversaire :",
            reply_markup=read_keyboard(),
            parse_mode='Markdown'
        )
    elif data.startswith("r_"):
        read = data.replace("r_", "")
        session["hand"]["read"] = read
        session["hand"]["stats_str"] = ""
        session["step"] = "done"
        await query.edit_message_text("Analyse en cours...")
        await run_analysis(query, user_id, session)
 
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    text_ok, text_left, image_ok, image_left = get_limits(user_id)
 
    if not image_ok:
        await update.message.reply_text("Limite photos atteinte. Renouvellement dans " + get_time_left(user_id))
        return
    if session.get("step") != "waiting_photo":
        await update.message.reply_text("Tape d abord /photo pour activer l analyse par image !")
        return
 
    await update.message.reply_text("Image recue, analyse en cours...")
 
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_bytes = await file.download_as_bytearray()
        image_b64 = base64.b64encode(file_bytes).decode("utf-8")
 
        fmt = session.get("format") or "cash"
        if fmt == "cash":
            format_context = "Cash game 100BB+."
        elif fmt == "spin":
            format_context = "Spin Go stacks courts push/fold."
        elif fmt.startswith("mtt"):
            parts = fmt.split("_")
            format_context = "MTT stack " + (parts[1] if len(parts) > 1 else "?") + " phase " + (parts[2] if len(parts) > 2 else "?") + "."
        else:
            format_context = "Cash game standard."
 
        prompt = (
            "Tu es un expert poker GTO. Analyse cette capture d ecran.\n\n"
            "FORMAT : " + format_context + "\n\n"
            "Identifie : cartes du joueur, board, positions, stacks, pot, action.\n\n"
            "Reponds UNIQUEMENT avec ce format :\n"
            "Lu sur l image : [resume]\n"
            "DECISION : [FOLD/CALL/RAISE/BET/CHECK]\n"
            "Sizing : [montant BB ou N/A]\n"
            "Pot odds : [%] | Equity min : [%] | SPR : [valeur]\n"
            "GTO : [frequences ex raise 70% call 30%]\n"
            "Exploit : [1 phrase]\n"
            "Facteur cle : [1 phrase]\n"
            "Attention : [1 phrase]"
        )
 
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        result = response.content[0].text
        decision_match = re.search(r'DECISION\s*:\s*(\w+)', result)
        decision = decision_match.group(1) if decision_match else "?"
        hand_info = {"cards": "photo", "board": "photo", "street": "photo", "mypos": "?", "villainpos": "?"}
        add_to_history(user_id, hand_info, decision)
 
        de, freq, action, action_finale = get_randomizer(result, decision)
        increment_image(user_id)
        text_ok2, text_left2, image_ok2, image_left2 = get_limits(user_id)
 
        bilan = get_bilan(user_id)
        bilan["total"] += 1
        hand_id = bilan["total"]
 
        focus = session.get("focus", False)
        if focus:
            profil, strong, medium, bluff = get_range_estimate("inconnu")
            final = (
                "*" + decision + "* | " + "voir analyse" + " | "
                "Value " + str(strong) + "% Bluff " + str(bluff) + "% | "
                "De " + str(de) + "/" + str(freq) + "% -> *" + action_finale + "*"
            )
        else:
            bluff_idx, bluff_label = get_bluff_index("?", "?", "inconnu")
            final = (
                result + "\n\n"
                "---\n"
                "*Range adversaire*\n"
                "Estimation basee sur l image\n\n"
                "---\n"
                "*Indice de Bluff : " + str(bluff_idx) + "/10*\n"
                + bluff_label + "\n\n"
                "---\n"
                "*Randomizer GTO*\n"
                "De : " + str(de) + "/100\n"
                "Frequence : " + action + " " + str(freq) + "%\n"
                "*Action finale : " + action_finale + "*"
            )
            if user_id != ADMIN_ID:
                final += "\n\nAnalyses boutons : " + str(text_left2) + "/" + str(DAILY_LIMIT_TEXT)
                final += "\nAnalyses photo : " + str(image_left2) + "/" + str(DAILY_LIMIT_IMAGE)
 
        await update.message.reply_text(final, reply_markup=result_keyboard(hand_id), parse_mode='Markdown')
        session["step"] = None
 
    except Exception as e:
        await update.message.reply_text("Erreur lecture image. Verifie la nettete et reessaie.\nOu utilise /m pour l analyse manuelle.")
 
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    text = update.message.text.strip()
    step = session.get("step")
 
    if step == "waiting_photo":
        await update.message.reply_text("Envoie une photo ! Ou /reset pour annuler.")
    elif step == "cards":
        session["hand"]["cards"] = text
        session["step"] = "street"
        await update.message.reply_text(
            "Cartes : *" + text + "*\n\nEtape 4/6\nStreet :",
            reply_markup=street_keyboard(),
            parse_mode='Markdown'
        )
    elif step == "board":
        session["hand"]["board"] = text
        session["step"] = "action"
        await update.message.reply_text(
            "Board : *" + text + "*\n\nEtape 5/6\nTape l action adverse :\n"
            "ex: cbet5/10 - check - donk6/15",
            parse_mode='Markdown'
        )
    elif step == "action":
        session["hand"]["action"] = text
        session["step"] = "stack"
        await update.message.reply_text(
            "Action : *" + text + "*\n\nEtape 6/6\nStacks effectifs :",
            reply_markup=stack_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "/m analyser une main\n"
            "/photo capture d ecran\n"
            "/bilan tes statistiques\n"
            "/historique dernieres mains\n"
            "/focus mode minimaliste\n"
            "/reset remettre a zero"
        )
 
async def run_analysis(query, user_id, session):
    hand = session["hand"]
    fmt = session.get("format") or "cash"
    focus = session.get("focus", False)
 
    if fmt == "cash":
        format_context = "Cash game 100BB+. Analyse GTO pure + exploitative."
    elif fmt == "spin":
        format_context = "Spin Go stacks courts. PUSH/FOLD uniquement."
    elif fmt.startswith("mtt"):
        parts = fmt.split("_")
        stack = parts[1] if len(parts) > 1 else "?"
        phase = parts[2] if len(parts) > 2 else "?"
        icm = "tres haute" if phase in ["bulle", "ft"] else "moyenne"
        format_context = "MTT stack " + stack + " phase " + phase + " ICM " + icm + "."
    else:
        format_context = "Cash game standard."
 
    read_raw = hand.get("read", "inconnu")
    stats_str = hand.get("stats_str", "")
    full_read = (read_raw + " " + stats_str).strip()
    read_clean, vpip, af, three_bet = parse_stats(full_read)
 
    main_str = (
        "Position : " + hand.get("mypos", "?") + " vs " + hand.get("villainpos", "?") + "\n"
        "Cartes : " + hand.get("cards", "?") + "\n"
        "Street : " + hand.get("street", "?") + "\n"
        "Board : " + hand.get("board", "preflop") + "\n"
        "Action : " + hand.get("action", "?") + "\n"
        "Stack : " + hand.get("stack", "?") + "\n"
        "Read : " + full_read
    )
 
    prompt = ("Tu es un expert poker GTO et coach pro. Analyse cette situation.\n\n"
              "FORMAT : " + format_context + "\n\n"
              "MAIN :\n" + main_str + "\n\n"
              "Reponds UNIQUEMENT avec ce format :\n"
              "DECISION : [FOLD/CALL/RAISE/BET/CHECK]\n"
              "Sizing : [montant BB ou N/A]\n"
              "Pot odds : [%] | Equity min : [%] | SPR : [valeur]\n"
              "GTO : [frequences ex raise 70% call 30%]\n"
              "Exploit : [1 phrase selon le read]\n"
              "Facteur cle : [1 phrase]\n"
              "Attention : [1 phrase piege frequent]")
 
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        result = response.content[0].text
 
        decision_match = re.search(r'DECISION\s*:\s*(\w+)', result)
        decision = decision_match.group(1) if decision_match else "?"
        add_to_history(user_id, hand, decision)
 
        profil, strong, medium, bluff = get_range_estimate(read_clean, vpip, af, three_bet)
        board = hand.get("board", "")
        cards = hand.get("cards", "")
        bluff_idx, bluff_label = get_bluff_index(board, cards, read_clean)
        de, freq, action, action_finale = get_randomizer(result, decision)
 
        increment_text(user_id)
        text_ok, text_left, image_ok, image_left = get_limits(user_id)
 
        bilan = get_bilan(user_id)
        bilan["total"] += 1
        hand_id = bilan["total"]
 
        if focus:
            final = (
                "*" + decision + "* | Sizing : voir analyse | "
                "Value " + str(strong) + "% Bluff " + str(bluff) + "% | "
                "De " + str(de) + "/" + str(freq) + "% -> *" + action_finale + "*"
            )
        else:
            final = (
                result + "\n\n"
                "---\n"
                "*Range adversaire (" + profil + ")*\n"
                "Mains fortes (value) : " + str(strong) + "%\n"
                "Mains moyennes : " + str(medium) + "%\n"
                "Bluffs : " + str(bluff) + "%\n\n"
                "---\n"
                "*Indice de Bluff : " + str(bluff_idx) + "/10*\n"
                + bluff_label + "\n\n"
                "---\n"
                "*Randomizer GTO*\n"
                "De : " + str(de) + "/100\n"
                "Frequence : " + action + " " + str(freq) + "%\n"
                "*Action finale : " + action_finale + "*"
            )
            if user_id != ADMIN_ID:
                final += "\n\nAnalyses restantes : " + str(text_left) + "/" + str(DAILY_LIMIT_TEXT)
                final += " | Photos : " + str(image_left) + "/" + str(DAILY_LIMIT_IMAGE)
 
        await query.edit_message_text(final, reply_markup=result_keyboard(hand_id), parse_mode='Markdown')
        session["step"] = None
        session["hand"] = {}
 
    except Exception as e:
        await query.edit_message_text("Erreur d analyse. Tape /m pour reessayer.")
 
def main():
    load_data()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("m", m_cmd))
    app.add_handler(CommandHandler("photo", photo_cmd))
    app.add_handler(CommandHandler("focus", focus_cmd))
    app.add_handler(CommandHandler("bilan", bilan_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("historique", historique_cmd))
    app.add_handler(CommandHandler("format", format_cmd))
    app.add_handler(CommandHandler("aide", aide))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("Bot demarre !")
    app.run_polling()
 
if __name__ == "__main__":
    main()
