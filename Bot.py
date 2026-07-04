import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
import random
import string
from datetime import datetime, timedelta
from aiohttp import web
import asyncio

# ---------- DATABASE ----------
# Use /tmp for Render (persistent across deployments)
DB_PATH = os.getenv("DATABASE_PATH", "/tmp/keys.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE NOT NULL,
            script_url TEXT NOT NULL,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            redeemed_by TEXT DEFAULT NULL,
            redeemed_at TEXT DEFAULT NULL,
            expiry TEXT DEFAULT NULL
        )
    ''')
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
    conn.commit()
    conn.close()

init_db()

# ---------- BOT SETUP ----------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set. Please set it in Render Environment Variables.")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- HELPER FUNCTIONS ----------
def generate_key_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def add_key(key_code, script_url, max_uses, expiry_days):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    expiry = None
    if expiry_days > 0:
        expiry = (datetime.utcnow() + timedelta(days=expiry_days)).isoformat()
    try:
        c.execute("INSERT INTO keys (key_code, script_url, max_uses, expiry) VALUES (?, ?, ?, ?)",
                  (key_code, script_url, max_uses, expiry))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def is_key_valid(key_code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT max_uses, used_count, expiry FROM keys WHERE key_code = ?", (key_code,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    max_uses, used_count, expiry = row
    if used_count >= max_uses:
        return False
    if expiry:
        exp_dt = datetime.fromisoformat(expiry)
        if datetime.utcnow() > exp_dt:
            return False
    return True

def redeem_key(key_code, discord_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, script_url, max_uses, used_count, redeemed_by, expiry FROM keys WHERE key_code = ?", (key_code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None, None, "Invalid key code."
    key_id, script_url, max_uses, used_count, redeemed_by, expiry = row
    if expiry:
        exp_dt = datetime.fromisoformat(expiry)
        if datetime.utcnow() > exp_dt:
            conn.close()
            return None, None, "This key has expired."
    if used_count >= max_uses:
        conn.close()
        return None, None, "This key has been fully redeemed."
    new_used = used_count + 1
    if redeemed_by is None:
        redeemed_by = discord_id
    c.execute("UPDATE keys SET used_count = ?, redeemed_by = ?, redeemed_at = ? WHERE id = ?",
              (new_used, redeemed_by, datetime.utcnow().isoformat(), key_id))
    c.execute("INSERT INTO users (discord_id, total_redeemed) VALUES (?, 1) "
              "ON CONFLICT(discord_id) DO UPDATE SET total_redeemed = total_redeemed + 1", (discord_id,))
    c.execute("INSERT INTO redemptions (discord_id, key_code, redeemed_at) VALUES (?, ?, ?)",
              (discord_id, key_code, datetime.utcnow().isoformat()))
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

# ---------- MODAL ----------
class RedeemModal(discord.ui.Modal, title="Redeem Key"):
    key_input = discord.ui.TextInput(label="Enter your key code", placeholder="e.g. ABC123", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        key_code = self.key_input.value.strip()
        user_id = str(interaction.user.id)
        script_url, used_key, msg = redeem_key(key_code, user_id)
        if script_url is None:
            embed = discord.Embed(title="❌ Failed", description=msg, color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        loader = f'getgenv().Key = "{used_key}"\nloadstring(game:HttpGet("{script_url}"))()'
        embed = discord.Embed(title="✅ Key Redeemed!", description=msg, color=discord.Color.green())
        embed.add_field(name="Your Loader", value=f"```lua\n{loader}\n```", inline=False)
        embed.set_footer(text="I-copy ang loader at i-paste sa executor.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- PANEL VIEW ----------
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Redeem Key", style=discord.ButtonStyle.primary, custom_id="redeem")
    async def redeem_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedeemModal(interaction))

    @discord.ui.button(label="View Script", style=discord.ButtonStyle.success, custom_id="view_script")
    async def view_script_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        redemptions = get_user_redemptions(user_id)
        if not redemptions:
            embed = discord.Embed(title="No Scripts", description="Wala ka pang na-redeem na keys.", color=discord.Color.orange())
        else:
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
                    desc += f"**Key:** {key_code}\n```lua\n{loader}\n```\n\n"
            embed = discord.Embed(title="📜 Your Loaders", description=desc, color=discord.Color.blue())
            embed.set_footer(text="I-copy ang loader at i-paste sa executor.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="View Stats", style=discord.ButtonStyle.secondary, custom_id="view_stats")
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        total = get_user_stats(user_id)
        embed = discord.Embed(title="Your Stats", color=discord.Color.purple())
        embed.add_field(name="Keys Redeemed", value=total, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- SLASH COMMANDS ----------
@bot.tree.command(name="panel", description="Send the key redemption panel to a channel")
@app_commands.describe(channel="The channel to send the panel (optional)")
async def panel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    target = channel or interaction.channel
    embed = discord.Embed(title="🔑 Key Redemption Panel", description="Use the buttons below.", color=discord.Color.gold())
    view = PanelView()
    await target.send(embed=embed, view=view)
    await interaction.response.send_message(f"Panel sent to {target.mention}", ephemeral=True)

@bot.tree.command(name="genkey", description="Generate a new key (admin only)")
@app_commands.describe(
    key_code="Optional custom key; auto-generate if blank",
    github_url="Raw GitHub URL of the Lua script (e.g., https://raw.githubusercontent.com/.../script.lua)",
    max_uses="Max redemptions (default 1)",
    expiry_days="Days until expiry (0 = no expiry, default 0)"
)
async def genkey(
    interaction: discord.Interaction,
    github_url: str,
    key_code: str = None,
    max_uses: int = 1,
    expiry_days: int = 0
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    if not key_code:
        key_code = generate_key_code()
    success = add_key(key_code, github_url, max_uses, expiry_days)
    if success:
        expiry_text = f"{expiry_days} days" if expiry_days > 0 else "No expiry"
        embed = discord.Embed(title="✅ Key Generated", color=discord.Color.green())
        embed.add_field(name="Key Code", value=key_code, inline=False)
        embed.add_field(name="GitHub URL", value=github_url, inline=False)
        embed.add_field(name="Max Uses", value=str(max_uses), inline=True)
        embed.add_field(name="Expiry", value=expiry_text, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(f"Key `{key_code}` already exists.", ephemeral=True)

# ---------- VALIDATION WEB SERVER ----------
async def validate(request):
    try:
        data = await request.json()
        key = data.get('key')
    except:
        return web.json_response({"valid": False, "message": "Invalid JSON"}, status=400)
    if not key:
        return web.json_response({"valid": False, "message": "No key provided"}, status=400)
    valid = is_key_valid(key)
    if valid:
        return web.json_response({"valid": True})
    else:
        return web.json_response({"valid": False}, status=403)

async def start_web():
    app = web.Application()
    app.router.add_post('/validate', validate)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Use PORT from Render environment, fallback to 5000 for local testing
    port = int(os.getenv("PORT", 5000))
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Validation server running on port {port}")
    
    # Keep the server alive
    await asyncio.Event().wait()

# ---------- BOT EVENTS ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    
    # Start the web server in background
    bot.loop.create_task(start_web())

# ---------- RUN ----------
if __name__ == "__main__":
    bot.run(TOKEN)
