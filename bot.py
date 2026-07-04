import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
import random
import string
from datetime import datetime, timedelta, timezone
from aiohttp import web
import asyncio
import json

# ---------- DATABASE ----------
# Use /tmp for Render (pansamantala); gumamit ng persistent volume sa production
DB_PATH = os.getenv("DATABASE_PATH", "/tmp/keys.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Main keys table – dinagdagan ng created_by at bound_roblox_id
    c.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE NOT NULL,
            script_url TEXT NOT NULL,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            redeemed_by TEXT DEFAULT NULL,
            redeemed_at TEXT DEFAULT NULL,
            expiry TEXT DEFAULT NULL,
            is_lifetime INTEGER DEFAULT 0,
            created_by TEXT DEFAULT NULL,
            bound_roblox_id TEXT DEFAULT NULL
        )
    ''')
    # Migration: idagdag ang mga bagong column kung wala pa
    c.execute("PRAGMA table_info(keys)")
    columns = [col[1] for col in c.fetchall()]
    if "created_by" not in columns:
        c.execute("ALTER TABLE keys ADD COLUMN created_by TEXT DEFAULT NULL")
    if "bound_roblox_id" not in columns:
        c.execute("ALTER TABLE keys ADD COLUMN bound_roblox_id TEXT DEFAULT NULL")

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            discord_id TEXT PRIMARY KEY,
            total_redeemed INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id TEXT NOT NULL,
            key_code TEXT NOT NULL,
            redeemed_at TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS github_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            github_url TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------- BOT SETUP ----------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set.")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- HELPER FUNCTIONS ----------
def get_current_time():
    return datetime.now(timezone.utc)

def generate_key_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def add_key(key_code, script_url, max_uses, expiry_days, is_lifetime, created_by):
    """Magdagdag ng key kasama ang creator (Discord ID)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    expiry = None
    if is_lifetime:
        max_uses = 99999
    if not is_lifetime and expiry_days > 0:
        expiry_time = get_current_time() + timedelta(days=expiry_days)
        expiry = expiry_time.isoformat()
    try:
        c.execute("INSERT INTO keys (key_code, script_url, max_uses, expiry, is_lifetime, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                  (key_code, script_url, max_uses, expiry, 1 if is_lifetime else 0, created_by))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def is_key_valid(key_code, roblox_id=None):
    """Suriin kung valid ang key, at kung may ibinigay na roblox_id, suriin din ang binding."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT max_uses, used_count, expiry, is_lifetime, bound_roblox_id FROM keys WHERE key_code = ?", (key_code,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False, "Key not found"
    max_uses, used_count, expiry, is_lifetime, bound_roblox = row

    if used_count >= max_uses:
        return False, "Key fully redeemed"

    if not is_lifetime and expiry:
        try:
            exp_dt = datetime.fromisoformat(expiry)
            if get_current_time() > exp_dt:
                return False, "Key expired"
        except:
            pass

    # Kung may ibinigay na roblox_id at may nakatali nang iba
    if roblox_id is not None and bound_roblox is not None:
        if str(bound_roblox) != str(roblox_id):
            return False, f"Key already bound to another Roblox account (ID: {bound_roblox})"

    return True, "Key is valid"

def bind_key_to_roblox(key_code, roblox_id):
    """I‑bind ang key sa Roblox ID (unang gamit)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, bound_roblox_id FROM keys WHERE key_code = ?", (key_code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "Key not found"
    key_id, bound = row
    if bound is not None:
        # May nakatali na – dapat pareho
        if str(bound) == str(roblox_id):
            conn.close()
            return True, "Key already bound to this Roblox account"
        else:
            conn.close()
            return False, f"Key already bound to another Roblox account (ID: {bound})"
    # Unang binding
    c.execute("UPDATE keys SET bound_roblox_id = ?, used_count = used_count + 1, redeemed_at = ? WHERE id = ?",
              (str(roblox_id), get_current_time().isoformat(), key_id))
    conn.commit()
    conn.close()
    return True, "Key successfully bound to your Roblox account"

def redeem_key(key_code, discord_id):
    """Discord redemption – para sa loader (hindi ito ang Roblox binding)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, script_url, max_uses, used_count, redeemed_by, expiry, is_lifetime FROM keys WHERE key_code = ?", (key_code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None, None, "Invalid key code."
    key_id, script_url, max_uses, used_count, redeemed_by, expiry, is_lifetime = row

    if expiry and not is_lifetime:
        try:
            exp_dt = datetime.fromisoformat(expiry)
            if get_current_time() > exp_dt:
                conn.close()
                return None, None, "This key has expired."
        except:
            pass

    if used_count >= max_uses:
        conn.close()
        return None, None, "This key has been fully redeemed."

    new_used = used_count + 1
    if redeemed_by is None:
        redeemed_by = discord_id
    current_time = get_current_time().isoformat()
    c.execute("UPDATE keys SET used_count = ?, redeemed_by = ?, redeemed_at = ? WHERE id = ?",
              (new_used, redeemed_by, current_time, key_id))
    c.execute("INSERT INTO users (discord_id, total_redeemed) VALUES (?, 1) "
              "ON CONFLICT(discord_id) DO UPDATE SET total_redeemed = total_redeemed + 1", (discord_id,))
    c.execute("INSERT INTO redemptions (discord_id, key_code, redeemed_at) VALUES (?, ?, ?)",
              (discord_id, key_code, current_time))
    conn.commit()
    conn.close()
    return script_url, key_code, "Key redeemed successfully!"

def get_user_redemptions(discord_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key_code, redeemed_at FROM redemptions WHERE discord_id = ? ORDER BY redeemed_at DESC", (discord_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_user_stats(discord_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT total_redeemed FROM users WHERE discord_id = ?", (discord_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_all_keys():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key_code, script_url, max_uses, used_count, redeemed_by, is_lifetime, expiry, created_by, bound_roblox_id FROM keys ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_keys_by_creator(discord_id):
    """Kunin ang lahat ng key na ginawa ng isang Discord user"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key_code, script_url, max_uses, used_count, bound_roblox_id, redeemed_by, redeemed_at, is_lifetime, expiry FROM keys WHERE created_by = ? ORDER BY id DESC", (discord_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_github_url(name, github_url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO github_urls (name, github_url) VALUES (?, ?)", (name, github_url))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_github_urls():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, github_url FROM github_urls ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_github_url_by_name(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT github_url FROM github_urls WHERE name = ?", (name,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------- MODAL FOR REDEEM (Discord) ----------
class RedeemModal(discord.ui.Modal, title="Redeem Key"):
    key_input = discord.ui.TextInput(
        label="Enter your key code",
        placeholder="e.g. ABC123XY",
        required=True,
        max_length=20
    )
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        key_code = self.key_input.value.strip().upper()
        user_id = str(interaction.user.id)
        script_url, used_key, msg = redeem_key(key_code, user_id)
        if script_url is None:
            embed = discord.Embed(title="❌ Redemption Failed", description=msg, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        loader = f'getgenv().Key = "{used_key}"\nloadstring(game:HttpGet("{script_url}"))()'
        embed = discord.Embed(title="✅ Key Redeemed Successfully!", description=msg, color=discord.Color.green())
        embed.add_field(name="🔑 Your Loader", value=f"```lua\n{loader}\n```", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

# ---------- PANEL VIEW ----------
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔑 Redeem Key", style=discord.ButtonStyle.primary, custom_id="redeem")
    async def redeem_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedeemModal())

    @discord.ui.button(label="📜 View Loaders", style=discord.ButtonStyle.success, custom_id="view_script")
    async def view_script_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        redemptions = get_user_redemptions(user_id)
        if not redemptions:
            embed = discord.Embed(title="📭 No Loaders Yet", description="You haven't redeemed any keys yet.", color=discord.Color.orange())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        desc = ""
        for key_code, redeemed_at in redemptions:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT script_url FROM keys WHERE key_code = ?", (key_code,))
            row = c.fetchone()
            conn.close()
            if row:
                script_url = row[0]
                loader = f'getgenv().Key = "{key_code}"\nloadstring(game:HttpGet("{script_url}"))()'
                try:
                    redeemed_date = datetime.fromisoformat(redeemed_at).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    redeemed_date = redeemed_at
                desc += f"**Redeemed:** {redeemed_date}\n```lua\n{loader}\n```\n\n"
        embed = discord.Embed(title="📜 Your Loaders", description=desc, color=discord.Color.blue())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 My Stats", style=discord.ButtonStyle.secondary, custom_id="view_stats")
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        total = get_user_stats(str(interaction.user.id))
        embed = discord.Embed(title="📊 Your Statistics", color=discord.Color.purple())
        embed.add_field(name="🎉 Total Keys Redeemed", value=str(total), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

# ---------- SLASH COMMANDS ----------
@bot.tree.command(name="panel", description="Send the key redemption panel to a channel")
@app_commands.describe(channel="The channel to send the panel (optional)")
async def panel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    target = channel or interaction.channel
    embed = discord.Embed(title="🔑 Key Redemption Panel", description="Use the buttons below.", color=discord.Color.gold())
    view = PanelView()
    await target.send(embed=embed, view=view)
    await interaction.response.send_message(f"✅ Panel sent to {target.mention}", ephemeral=True)

@bot.tree.command(name="apply", description="Add a GitHub URL preset (admin only)")
@app_commands.describe(name="Preset name", github_url="Raw GitHub URL")
async def apply(interaction: discord.Interaction, name: str, github_url: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    success = add_github_url(name, github_url)
    if success:
        embed = discord.Embed(title="✅ GitHub URL Saved", description=f"Preset '{name}' saved.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Preset '{name}' already exists.", ephemeral=True)

@bot.tree.command(name="genkey", description="Generate a new key (admin only)")
@app_commands.describe(
    key_code="Optional custom key; auto-generate if blank",
    max_uses="Max redemptions (default 1, ignored if lifetime=True)",
    is_lifetime="Make this a lifetime key (never expires, unlimited uses)? (default False)",
    github_preset="Use a saved GitHub preset (e.g., MainScript)",
    github_url="Raw GitHub URL (only if not using preset)",
    expiry_days="Days until expiry (0 = no expiry, default 0, ignored if lifetime=True)"
)
async def genkey(
    interaction: discord.Interaction,
    key_code: str = None,
    max_uses: int = 1,
    is_lifetime: bool = False,
    github_preset: str = None,
    github_url: str = None,
    expiry_days: int = 0
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if github_preset:
        github_url = get_github_url_by_name(github_preset)
        if not github_url:
            await interaction.response.send_message(f"❌ Preset '{github_preset}' not found.", ephemeral=True)
            return
    elif not github_url:
        await interaction.response.send_message("❌ Please provide either a GitHub preset or direct URL.", ephemeral=True)
        return
    if not key_code:
        key_code = generate_key_code()
    key_code = key_code.upper()
    # I‑save ang creator (Discord ID ng gumamit ng command)
    success = add_key(key_code, github_url, max_uses, expiry_days, is_lifetime, str(interaction.user.id))
    if success:
        expiry_text = "LIFETIME ♾️" if is_lifetime else f"{expiry_days} days" if expiry_days > 0 else "No expiry"
        embed = discord.Embed(title="✅ Key Generated", color=discord.Color.green())
        embed.add_field(name="🔑 Key Code", value=f"`{key_code}`", inline=False)
        embed.add_field(name="📈 Max Uses", value="Unlimited" if is_lifetime else str(max_uses), inline=True)
        embed.add_field(name="⏰ Expiry", value=expiry_text, inline=True)
        embed.add_field(name="👤 Created By", value=f"<@{interaction.user.id}>", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Key `{key_code}` already exists.", ephemeral=True)

@bot.tree.command(name="mykeys", description="View all keys you have generated")
async def mykeys(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    keys = get_keys_by_creator(user_id)
    if not keys:
        embed = discord.Embed(title="📭 No Keys", description="You haven't generated any keys yet.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    embed = discord.Embed(title="🔑 Your Generated Keys", color=discord.Color.blue())
    for key_code, script_url, max_uses, used_count, bound_roblox, redeemed_by, redeemed_at, is_lifetime, expiry in keys[:10]:
        status = "✅ Bound" if bound_roblox else "❌ Unused"
        roblox_info = f"Roblox ID: {bound_roblox}" if bound_roblox else "Not yet bound"
        redeemed_by_display = f"<@{redeemed_by}>" if redeemed_by else "Nobody"
        embed.add_field(
            name=f"`{key_code}`",
            value=f"Script: {script_url}\nStatus: {status}\n{roblox_info}\nRedeemed by: {redeemed_by_display}\nUses: {used_count}/{max_uses if not is_lifetime else '∞'}",
            inline=False
        )
    if len(keys) > 10:
        embed.set_footer(text="Showing first 10 keys.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="viewall", description="View all keys and details (admin only)")
async def viewall(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    keys = get_all_keys()
    if not keys:
        embed = discord.Embed(title="📭 No Keys", description="No keys generated yet.", color=discord.Color.orange())
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    embeds = []
    current_embed = discord.Embed(title="🔑 All Keys", color=discord.Color.blue())
    field_count = 0
    for key_code, script_url, max_uses, used_count, redeemed_by, is_lifetime, expiry, created_by, bound_roblox in keys:
        status = "❌ FULLY REDEEMED" if used_count >= max_uses else "✅ ACTIVE"
        if is_lifetime:
            status = "♾️ LIFETIME"
        elif expiry:
            try:
                if get_current_time() > datetime.fromisoformat(expiry):
                    status = "⏰ EXPIRED"
            except:
                pass
        redeemed_text = f"<@{redeemed_by}>" if redeemed_by else "Nobody"
        creator_text = f"<@{created_by}>" if created_by else "Unknown"
        roblox_text = bound_roblox if bound_roblox else "Not bound"
        expiry_text = "Never" if is_lifetime else (expiry[:10] if expiry else "No expiry")
        field_value = f"**Status:** {status}\n**Uses:** {used_count}/{max_uses if not is_lifetime else '∞'}\n**Created by:** {creator_text}\n**Redeemed by:** {redeemed_text}\n**Roblox ID:** {roblox_text}\n**Expires:** {expiry_text}"
        current_embed.add_field(name=f"🔑 {key_code}", value=field_value, inline=False)
        field_count += 1
        if field_count >= 25:
            embeds.append(current_embed)
            current_embed = discord.Embed(title="🔑 All Keys (Continued)", color=discord.Color.blue())
            field_count = 0
    if field_count > 0:
        embeds.append(current_embed)
    for embed in embeds:
        await interaction.followup.send(embed=embed, ephemeral=True)

# ---------- WEB SERVER (VALIDATION ENDPOINT) ----------
async def validate(request):
    try:
        data = await request.json()
        key = data.get('key')
        roblox_id = data.get('robloxUserId')  # Inaasahan mula sa Roblox script
    except Exception as e:
        return web.json_response({"valid": False, "message": "Invalid JSON"}, status=200)

    if not key or not roblox_id:
        return web.json_response({"valid": False, "message": "Missing key or robloxUserId"}, status=200)

    # 1. Suriin kung valid ang key at kung may binding conflict
    valid, msg = is_key_valid(key, roblox_id)
    if not valid:
        return web.json_response({"valid": False, "message": msg}, status=200)

    # 2. Kung walang nakatali pang Roblox ID, i‑bind ito
    # Kunin ang kasalukuyang binding
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bound_roblox_id FROM keys WHERE key_code = ?", (key,))
    row = c.fetchone()
    conn.close()
    if row is None:
        return web.json_response({"valid": False, "message": "Key not found"}, status=200)
    bound = row[0]
    if bound is None:
        # Unang gamit – i‑bind
        success, bind_msg = bind_key_to_roblox(key, roblox_id)
        if success:
            return web.json_response({"valid": True, "message": bind_msg}, status=200)
        else:
            return web.json_response({"valid": False, "message": bind_msg}, status=200)
    else:
        # May nakatali na – dapat pareho (na‑check na sa is_key_valid)
        return web.json_response({"valid": True, "message": "Key is valid for this Roblox account"}, status=200)

async def health_check(request):
    return web.json_response({"status": "ok", "bot": "online"}, status=200)

async def start_web():
    app = web.Application()
    app.router.add_post('/validate', validate)
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 5000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Validation server running on port {port}")
    await asyncio.Event().wait()

# ---------- BOT EVENTS ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Current UTC Time: {get_current_time().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    if not hasattr(bot, 'web_server_started'):
        bot.web_server_started = True
        bot.loop.create_task(start_web())

# ---------- RUN ----------
if __name__ == "__main__":
    bot.run(TOKEN)
