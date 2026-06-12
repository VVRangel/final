from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import random
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "super-secure-game-vault-2026")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///game.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ---------------- MODELS ---------------- #

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    word = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.Integer, nullable=False)
    attempts = db.Column(db.Integer, nullable=False)
    money = db.Column(db.Integer, default=0, nullable=False)


class PlayerProfile(db.Model):
    name = db.Column(db.String(50), primary_key=True)
    password_hash = db.Column(db.String(256), nullable=False)
    tokens = db.Column(db.Integer, default=0, nullable=False)

    # STACKABLE PERK COUNTERS
    perk_wallet = db.Column(db.Integer, default=0, nullable=False)
    perk_shield = db.Column(db.Integer, default=0, nullable=False)
    perk_discount = db.Column(db.Integer, default=0, nullable=False)
    perk_charm = db.Column(db.Integer, default=0, nullable=False)
    perk_extender = db.Column(db.Integer, default=0, nullable=False)
    perk_contract = db.Column(db.Integer, default=0, nullable=False)


# ---------------- GAME CONFIGURATION ---------------- #

WORDS = [
    "cat", "dog", "sun", "tree", "car", "python", "rocket",
    "forest", "planet", "algorithm", "quantum", "horizon",
    "matrix", "cyber", "arcade", "victory", "blitz", "crypt",
    "pixel", "wizard", "nebula", "glitch", "cobalt"
]

BASE_SHOP = {
    "vowel": 500, "hint": 650, "consolation": 800, "insurance": 900,
    "spy": 1100, "reveal": 1200, "double": 1600, "doubledown": 1800, "solve": 8500
}

META_SHOP_ITEMS = {
    "wallet": {"name": "Wallet Boost", "base_cost": 4, "desc": "Permanently begin all future games with +200 extra cash reserves per item stack."},
    "shield": {"name": "Shield Pack", "base_cost": 6, "desc": "Start matches with safety shields pre-loaded to eat 'LOSE' wheel sectors."},
    "discount": {"name": "VIP Pass", "base_cost": 9, "desc": "Save 10% on live in-game show item prices per stack. Maximum 5 stacks."},
    "charm": {"name": "Lucky Charm", "base_cost": 5, "desc": "Adds a guaranteed flat +100 cash to all successful wheel currency landings."},
    "extender": {"name": "Turn Extender", "base_cost": 7, "desc": "Grants you -2 free turns at the start of a match. Great for high scoreboard rankings!"},
    "contract": {"name": "Token Contract", "base_cost": 10, "desc": "Get a +15% multiplier on final Star Token rewards when solving puzzles."}
}


# ---------------- HELPERS ---------------- #

def mask(word, guessed):
    return " ".join([c.upper() if c in guessed else "_" for c in word])


def spin_wheel():
    return random.choice([0, 50, 100, 200, "LOSE", "LOSE", "BANKRUPT", "HINT"])


def get_live_shop_prices():
    prices = BASE_SHOP.copy()
    discount_stacks = min(5, session.get("perk_discount_stacks", 0))
    discount_factor = 1.0 - (discount_stacks * 0.10)
    for item in prices:
        prices[item] = int(prices[item] * discount_factor)
    return prices


def get_player_perk_count(profile, perk_type):
    """Helper method to return the current integer stack count of a perk."""
    perk_map = {
        "wallet": profile.perk_wallet,
        "shield": profile.perk_shield,
        "discount": profile.perk_discount,
        "charm": profile.perk_charm,
        "extender": profile.perk_extender,
        "contract": profile.perk_contract
    }
    return perk_map.get(perk_type, 0)


# ---------------- ROUTES ---------------- #

@app.route("/")
def home():
    profile = None
    scaled_meta_shop = {}

    if "user_id" in session:
        profile = PlayerProfile.query.get(session["user_id"])
        if profile:
            # Dynamically calculate inflating token costs for the UI template display
            for key, data in META_SHOP_ITEMS.items():
                current_stacks = get_player_perk_count(profile, key)
                # Cost increases exponentially: Base * (1.5 ^ stacks)
                inflated_cost = int(data["base_cost"] * (1.5 ** current_stacks))

                scaled_meta_shop[key] = {
                    "name": data["name"],
                    "desc": data["desc"],
                    "cost": inflated_cost,
                    "stacks": current_stacks
                }
    else:
        # Fallback view format if not authenticated
        for key, data in META_SHOP_ITEMS.items():
            scaled_meta_shop[key] = {
                "name": data["name"],
                "desc": data["desc"],
                "cost": data["base_cost"],
                "stacks": 0
            }

    return render_template("home.html", current_profile=profile, meta_shop=scaled_meta_shop)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("⚠️ Username and password are required!", "warning")
            return redirect(url_for("register"))

        existing_user = PlayerProfile.query.get(username)
        if existing_user:
            flash("❌ Username already taken! Choose another.", "error")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password)
        new_player = PlayerProfile(name=username, password_hash=hashed_pw, tokens=10)
        db.session.add(new_player)
        db.session.commit()

        flash("🎉 Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        player = PlayerProfile.query.get(username)
        if player and check_password_hash(player.password_hash, password):
            session["user_id"] = player.name
            flash(f"👋 Welcome back, {player.name}!", "success")
            return redirect(url_for("home"))
        else:
            flash("❌ Invalid username or password.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("word", None)
    flash("🔒 Logged out successfully.", "info")
    return redirect(url_for("home"))


@app.route("/start", methods=["POST"])
def start():
    if "user_id" not in session:
        flash("⚠️ You must be logged in to play!", "warning")
        return redirect(url_for("login"))

    profile = PlayerProfile.query.get(session["user_id"])
    diff = int(request.form.get("difficulty", 50))

    if diff < 40:
        pool = [w for w in WORDS if len(w) <= 3]
    elif diff < 70:
        pool = [w for w in WORDS if 4 <= len(w) <= 6]
    else:
        pool = [w for w in WORDS if len(w) >= 7]

    if not pool: pool = WORDS

    session["player_name"] = profile.name
    session["word"] = random.choice(pool)
    session["guessed"] = []
    session["difficulty"] = diff

    session["money"] = 300 + (profile.perk_wallet * 200)
    session["shields_left"] = profile.perk_shield
    session["attempts"] = 0 - (profile.perk_extender * 2)
    session["perk_charm_bonus"] = profile.perk_charm * 100
    session["perk_discount_stacks"] = profile.perk_discount
    session["perk_contract_multiplier"] = 1.0 + (profile.perk_contract * 0.15)

    session.pop("next_spin_ready", None)

    return redirect(url_for("game"))


@app.route("/meta-buy/<perk_type>")
def meta_buy(perk_type):
    if "user_id" not in session:
        flash("⚠️ Please login to purchase meta items!", "warning")
        return redirect(url_for("login"))

    profile = PlayerProfile.query.get(session["user_id"])
    if perk_type not in META_SHOP_ITEMS:
        return redirect(url_for("home"))

    current_stacks = get_player_perk_count(profile, perk_type)
    base_cost = META_SHOP_ITEMS[perk_type]["base_cost"]
    inflated_cost = int(base_cost * (1.5 ** current_stacks))

    if profile.tokens < inflated_cost:
        flash(f"❌ Insufficient Star Tokens! This stack level requires {inflated_cost} tokens.", "error")
        return redirect(url_for("home"))

    if perk_type == "discount" and profile.perk_discount >= 5:
        flash("⚠️ VIP Discount Pass has reached its maximum capability stack limit (5)!", "warning")
        return redirect(url_for("home"))

    profile.tokens -= inflated_cost
    if perk_type == "wallet":
        profile.perk_wallet += 1
    elif perk_type == "shield":
        profile.perk_shield += 1
    elif perk_type == "discount":
        profile.perk_discount += 1
    elif perk_type == "charm":
        profile.perk_charm += 1
    elif perk_type == "extender":
        profile.perk_extender += 1
    elif perk_type == "contract":
        profile.perk_contract += 1

    db.session.commit()

    next_cost = int(base_cost * (1.5 ** (current_stacks + 1)))
    flash(f"🎉 Upgraded! Stack count is now {current_stacks + 1}. Next level inflation milestone: {next_cost} Star Tokens.", "success")
    return redirect(url_for("home"))


@app.route("/spin")
def spin():
    if "word" not in session: return redirect(url_for("home"))

    # --- 30-SECOND COOLDOWN SYSTEM ---
    now = datetime.now()
    next_allowed_str = session.get("next_spin_ready")

    if next_allowed_str:
        next_allowed_dt = datetime.fromisoformat(next_allowed_str)
        if now < next_allowed_dt:
            time_remaining = next_allowed_dt - now
            seconds_left = int(time_remaining.total_seconds())
            flash(f"⏳ The wheel mechanism is locked! Wait {seconds_left}s before spinning again.", "warning")
            return redirect(url_for("game"))

    session["next_spin_ready"] = (now + timedelta(seconds=30)).isoformat()
    # ----------------------------------

    session["attempts"] += 1
    result = spin_wheel()

    if result == "LOSE":
        if session.get("shields_left", 0) > 0:
            session["shields_left"] -= 1
            flash(f"🛡️ Shield Absorbed! ({session['shields_left']} remaining)", "info")
        else:
            session["money"] = max(0, session["money"] - 400)
            flash("❌ Brutal Turn! You hit LOSE and dropped 400 coins!", "error")

    elif result == "BANKRUPT":
        if session.get("shields_left", 0) > 0:
            session["shields_left"] -= 1
            flash("🛡️ Shield shattered! Bankrupt penalty deflected completely.", "info")
        else:
            session["money"] = 0
            flash("💥 Total Catastrophe! You hit BANKRUPT and lost your entire balance!", "error")

    elif result == "HINT":
        flash(f"💡 Wheel Hint: The word starts with '{session['word'][0].upper()}'", "info")
    else:
        bonus = session.get("perk_charm_bonus", 0)
        session["money"] += (result + bonus)
        flash(f"💰 +{result} coins" + (f" (+{bonus} Charm!)" if bonus > 0 else "") + " added!", "success")

    return redirect(url_for("game"))


@app.route("/guess", methods=["POST"])
def guess():
    if "word" not in session: return redirect(url_for("home"))

    letter = request.form.get("letter", "").lower().strip()
    if not letter or len(letter) != 1 or not letter.isalpha():
        flash("⚠️ Please enter a single valid letter.", "warning")
        return redirect(url_for("game"))

    session["attempts"] += 1

    if letter in session["guessed"]:
        flash(f"You already guessed '{letter.upper()}'.", "warning")
    else:
        session["guessed"].append(letter)
        session.modified = True
        if letter in session["word"]:
            flash(f"Nice hit! '{letter.upper()}' is in the word.", "success")
            session["money"] += 100
        else:
            flash(f"Ouch! '{letter.upper()}' isn't there.", "error")

    return redirect(url_for("game"))


@app.route("/buy/<item>", methods=["GET", "POST"])
def buy(item):
    if "word" not in session: return redirect(url_for("home"))

    prices = get_live_shop_prices()
    if item not in prices: return redirect(url_for("game"))

    price = prices[item]
    if session["money"] < price:
        flash(f"❌ Not enough funds! You need {price} coins.", "error")
        return redirect(url_for("game"))

    session["money"] -= price

    if item == "vowel":
        target_vowels = [c for c in "aeiou" if c in session["word"] and c not in session["guessed"]]
        if target_vowels:
            chosen_vowel = random.choice(target_vowels)
            session["guessed"].append(chosen_vowel)
            session.modified = True
            flash(f"🔮 Vowel Blast: All '{chosen_vowel.upper()}' instances revealed!", "success")
        else:
            flash("No unrevealed vowels remain! (Refunding coins)", "warning")
            session["money"] += price
    elif item == "hint":
        vowels = [c for c in session["word"] if c in "aeiou" and c not in session["guessed"]]
        flash(
            f"💡 Shop Hint: One hidden vowel is '{random.choice(vowels).upper()}'" if vowels else f"💡 Shop Hint: Word starts with '{session['word'][0].upper()}'",
            "info")
    elif item == "consolation":
        session["attempts"] -= 3
        flash("📉 Consolation Prize: Reduced total attempts by 3.", "success")
    elif item == "insurance":
        session["shields_left"] = session.get("shields_left", 0) + 1
        flash(f"🛡️ Shield Pack Injected! Total: {session['shields_left']}", "success")
    elif item == "spy":
        spy_letter = request.form.get("spy_letter", "").lower().strip()
        if not spy_letter or len(spy_letter) != 1 or not spy_letter.isalpha():
            session["money"] += price
        else:
            flash(f"🕵️ Spy Glass Report: YES! '{spy_letter.upper()}' is inside." if spy_letter in session[
                "word"] else f"🕵️ Spy Glass Report: NO! '{spy_letter.upper()}' is absent.",
                  "success" if spy_letter in session["word"] else "error")
    elif item == "reveal":
        hidden = [c for c in session["word"] if c not in session["guessed"]]
        if hidden:
            chosen_letter = random.choice(hidden)
            session["guessed"].append(chosen_letter)
            session.modified = True
            flash(f"🔤 Revealed: '{chosen_letter.upper()}' filled in!", "success")
    elif item == "double":
        session["money"] *= 2
        flash("🔥 Shop item activated: DOUBLED YOUR FUNDS!", "success")
    elif item == "doubledown":
        if random.choice([True, False]):
            session["money"] += (price * 2)
            flash("🎲 GAMBLE WON! You tripled your item investment value!", "success")
        else:
            flash("🎲 GAMBLE LOST! Cash assets vaporized.", "error")
    elif item == "solve":
        for char in session["word"]:
            if char not in session["guessed"]: session["guessed"].append(char)
        session.modified = True
        flash("🔮 Instant-Solve Bypass Core Overdrive Configured!", "success")

    return redirect(url_for("game"))


@app.route("/game")
def game():
    if "word" not in session: return redirect(url_for("home"))

    word = session["word"]
    masked = mask(word, session["guessed"])
    attempts = session["attempts"]

    hint = ""
    if session["difficulty"] < 40 and attempts >= 6:
        hint = f"Tip: The word ends with '{word[-1].upper()}'"
    elif session["difficulty"] < 70 and attempts >= 8:
        hint = f"Tip: Structural vowel check count is {sum(1 for c in word if c in 'aeiou')}"

    if "_" not in masked.replace(" ", ""):
        final_score = Score(name=session["player_name"], word=word, difficulty=session["difficulty"], attempts=attempts,
                            money=session["money"])
        db.session.add(final_score)

        profile = PlayerProfile.query.get(session["user_id"])
        base_tokens = max(1, int(session["money"] / 200))
        tokens_earned = int(base_tokens * session.get("perk_contract_multiplier", 1.0))

        if profile: profile.tokens += tokens_earned
        db.session.commit()

        game_results = {"word": word.upper(), "money": session["money"], "attempts": attempts,
                        "name": session["player_name"], "tokens_earned": tokens_earned}
        session.pop("word", None)
        return render_template("win.html", results=game_results)

    return render_template("game.html", masked=masked, money=session["money"], attempts=attempts, hint=hint,
                           guessed_letters=sorted([c.upper() for c in session["guessed"]]),
                           shields=session.get("shields_left", 0), prices=get_live_shop_prices())


@app.route("/leaderboard")
def leaderboard():
    scores = Score.query.order_by(Score.money.desc(), Score.attempts.asc()).limit(10).all()
    profiles = PlayerProfile.query.order_by(PlayerProfile.tokens.desc()).limit(10).all()
    return render_template("leaderboard.html", scores=scores, profiles=profiles)


# ---------------- UNIVERSAL ROBUST DATABASE HOTFIX ---------------- #
with app.app_context():
    try:
        PlayerProfile.query.limit(1).all()
    except Exception:
        print("⚠️ Outdated or broken schema detected. Rebuilding all tables clean...")
        db.drop_all()

    db.create_all()
    print("🏁 Success: Database layout fully synchronized and matching models!")

if __name__ == "__main__":
    app.run(debug=True)
else:
    pass