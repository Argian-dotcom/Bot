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
            expiry TEXT DEFAULT NULL,
            is_lifetime INTEGER DEFAULT 0
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
    raise ValueError("DISCORD_TOKEN environment variable is not set. Please set it in Render Environment Variables.")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- HELPER FUNCTIONS ----------
def get_current_time():
    """Get current UTC time with timezone"""
    return datetime.now(timezone.utc)

def generate_key_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def add_key(key_code, script_url, max_uses, expiry_days, is_lifetime=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    expiry = None
    
    # For lifetime keys, set max_uses to 99999 (essentially unlimited)
    if is_lifetime:
        max_uses = 99999
    
    if not is_lifetime and expiry_days > 0:
        # Calculate expiry using UTC timezone
        expiry_time = get_current_time() + timedelta(days=expiry_days)
        expiry = expiry_time.isoformat()
    
    try:
        c.execute("INSERT INTO keys (key_code, script_url, max_uses, expiry, is_lifetime) VALUES (?, ?, ?, ?, ?)",
                  (key_code, script_url, max_uses, expiry, 1 if is_lifetime else 0))
        conn.commit()
        print(f"✅ Key created: {key_code} | Lifetime: {is_lifetime} | Max Uses: {max_uses}")
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def is_key_valid(key_code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT max_uses, used_count, expiry, is_lifetime FROM keys WHERE key_code = ?", (key_code,))
    row = c.fetchone()
    conn.close()
    if not row:
        print(f"❌ Key not found: {key_code}")
        return False
    max_uses, used_count, expiry, is_lifetime = row
    
    print(f"🔍 Key Check: {key_code} | Used: {used_count}/{max_uses} | Lifetime: {is_lifetime} | Expiry: {expiry}")
    
    # Check if already fully redeemed
    if used_count >= max_uses:
        print(f"❌ Key fully redeemed: {key_code}")
        return False
    
    # If lifetime key, no expiry check needed
    if is_lifetime:
        print(f"✅ Lifetime key valid: {key_code}")
        return True
    
    if expiry:
        try:
            exp_dt = datetime.fromisoformat(expiry)
            current_time = get_current_time()
            print(f"⏰ Expiry check: Current={current_time} | Expiry={exp_dt}")
            if current_time > exp_dt:
                print(f"❌ Key expired: {key_code}")
                return False
        except Exception as e:
            print(f"❌ Error parsing expiry time: {e}")
            return False
    
    print(f"✅ Key is valid: {key_code}")
    return True

def redeem_key(key_code, discord_id):
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
            current_time = get_current_time()
            if current_time > exp_dt:
                conn.close()
                return None, None, "This key has expired."
        except Exception as e:
            conn.close()
            return None, None, f"Error checking expiry: {str(e)}"
    
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
    """Get all keys with their details"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key_code, script_url, max_uses, used_count, redeemed_by, is_lifetime, expiry FROM keys ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def add_github_url(name, github_url):
    """Add a GitHub URL preset"""
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
    """Get all GitHub URL presets"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, github_url FROM github_urls ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_github_url_by_name(name):
    """Get GitHub URL by name"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT github_url FROM github_urls WHERE name = ?", (name,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------- MODAL ----------
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
        
        try:
            script_url, used_key, msg = redeem_key(key_code, user_id)
            
            if script_url is None:
                embed = discord.Embed(
                    title="❌ Redemption Failed",
                    description=msg,
                    color=discord.Color.red()
                )
                embed.set_footer(text="Please check your key and try again.")
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Success - show loader
            loader = f'getgenv().Key = "{used_key}"\nloadstring(game:HttpGet("{script_url}"))()'
            
            embed = discord.Embed(
                title="✅ Key Redeemed Successfully!",
                description=msg,
                color=discord.Color.green()
            )
            embed.add_field(
                name="🔑 Your Loader",
                value=f"```lua\n{loader}\n```",
                inline=False
            )
            embed.set_footer(text="Copy the loader and paste it in your executor.")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
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
            embed = discord.Embed(
                title="📭 No Loaders Yet",
                description="You haven't redeemed any keys yet.\n\nClick the **🔑 Redeem Key** button to get started!",
                color=discord.Color.orange()
            )
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
                
                # Format date nicely
                try:
                    redeemed_date = datetime.fromisoformat(redeemed_at).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    redeemed_date = redeemed_at
                
                desc += f"**Redeemed:** {redeemed_date}\n```lua\n{loader}\n```\n\n"
        
        embed = discord.Embed(
            title="📜 Your Loaders",
            description=desc if desc else "No loaders available.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Copy the loader and paste it in your executor.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 My Stats", style=discord.ButtonStyle.secondary, custom_id="view_stats")
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        total = get_user_stats(user_id)
        
        embed = discord.Embed(
            title="📊 Your Statistics",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="🎉 Total Keys Redeemed",
            value=str(total),
            inline=False
        )
        embed.set_footer(text="Keep collecting those keys!")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

# ---------- SLASH COMMANDS ----------
@bot.tree.command(name="panel", description="Send the key redemption panel to a channel")
@app_commands.describe(channel="The channel to send the panel (optional)")
async def panel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    
    target = channel or interaction.channel
    embed = discord.Embed(
        title="🔑 Key Redemption Panel",
        description="Use the buttons below to manage your keys!",
        color=discord.Color.gold()
    )
    embed.add_field(name="🔑 Redeem Key", value="Enter your key code to get the loader", inline=False)
    embed.add_field(name="📜 View Loaders", value="See all your redeemed loaders (without key details)", inline=False)
    embed.add_field(name="📊 My Stats", value="Check your redemption statistics (only redemption count)", inline=False)
    
    view = PanelView()
    message = await target.send(embed=embed, view=view)
    await interaction.response.send_message(f"✅ Panel sent to {target.mention}", ephemeral=True)

@bot.tree.command(name="apply", description="Add a GitHub URL preset (admin only)")
@app_commands.describe(
    name="Name for this preset (e.g., MainScript, AntiBat)",
    github_url="Raw GitHub URL (e.g., https://raw.githubusercontent.com/.../script.lua)"
)
async def apply(interaction: discord.Interaction, name: str, github_url: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    
    success = add_github_url(name, github_url)
    
    if success:
        embed = discord.Embed(
            title="✅ GitHub URL Saved",
            description=f"Preset '{name}' has been saved!",
            color=discord.Color.green()
        )
        embed.add_field(name="📁 Preset Name", value=f"`{name}`", inline=False)
        embed.add_field(name="🔗 GitHub URL", value=github_url, inline=False)
        embed.add_field(name="💡 Usage", value=f"Use `/genkey` with `github_preset: {name}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Preset '{name}' already exists.", ephemeral=True)

@bot.tree.command(name="genkey", description="Generate a new key (admin only)")
@app_commands.describe(
    key_code="Optional custom key; auto-generate if blank",
    max_uses="Max redemptions (default 1, ignored if lifetime=True)",
    is_lifetime="Make this a lifetime key (never expires, unlimited uses)? (default False)",
    github_preset="Use a saved GitHub preset (e.g., MainScript, AntiBat)",
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
    
    # Determine GitHub URL
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
    success = add_key(key_code, github_url, max_uses, expiry_days, is_lifetime)
    
    if success:
        # Determine expiry text
        if is_lifetime:
            expiry_text = "LIFETIME ♾️"
            expiry_display = "Never Expires"
            max_uses_display = "Unlimited ♾️"
        elif expiry_days > 0:
            expiry_text = f"{expiry_days} days"
            expiry_time = get_current_time() + timedelta(days=expiry_days)
            expiry_display = expiry_time.strftime("%Y-%m-%d %H:%M:%S UTC")
            max_uses_display = str(max_uses)
        else:
            expiry_text = "No expiry"
            expiry_display = "Never"
            max_uses_display = str(max_uses)
        
        embed = discord.Embed(title="✅ Key Generated", color=discord.Color.green())
        embed.add_field(name="🔑 Key Code", value=f"`{key_code}`", inline=False)
        embed.add_field(name="📈 Max Uses", value=max_uses_display, inline=True)
        embed.add_field(name="⏰ Expiry Type", value=expiry_text, inline=True)
        embed.add_field(name="🕐 Expires At", value=expiry_display, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Key `{key_code}` already exists.", ephemeral=True)

@bot.tree.command(name="viewall", description="View all keys and their details (admin only)")
async def viewall(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    keys = get_all_keys()
    
    if not keys:
        embed = discord.Embed(
            title="📭 No Keys",
            description="No keys have been generated yet.",
            color=discord.Color.orange()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    # Create embeds for each key (max 25 fields per embed)
    embeds = []
    current_embed = discord.Embed(title="🔑 All Keys", color=discord.Color.blue())
    field_count = 0
    
    for key_code, script_url, max_uses, used_count, redeemed_by, is_lifetime, expiry in keys:
        # Determine status
        if used_count >= max_uses:
            status = "❌ FULLY REDEEMED"
        elif is_lifetime:
            status = "✅ LIFETIME (Active)"
        elif expiry:
            try:
                exp_dt = datetime.fromisoformat(expiry)
                if get_current_time() > exp_dt:
                    status = "⏰ EXPIRED"
                else:
                    status = "✅ ACTIVE"
            except:
                status = "❓ UNKNOWN"
        else:
            status = "✅ ACTIVE"
        
        # Redeemed by user
        redeemed_text = f"<@{redeemed_by}>" if redeemed_by else "Nobody yet"
        
        # Format expiry
        if is_lifetime:
            expiry_text = "Never"
        elif expiry:
            try:
                exp_dt = datetime.fromisoformat(expiry).strftime("%Y-%m-%d %H:%M")
                expiry_text = exp_dt
            except:
                expiry_text = "N/A"
        else:
            expiry_text = "No expiry"
        
        field_value = f"**Status:** {status}\n**Uses:** {used_count}/{max_uses}\n**Redeemed By:** {redeemed_text}\n**Expires:** {expiry_text}"
        
        current_embed.add_field(name=f"🔑 {key_code}", value=field_value, inline=False)
        field_count += 1
        
        # Start new embed if too many fields
        if field_count >= 25:
            embeds.append(current_embed)
            current_embed = discord.Embed(title="🔑 All Keys (Continued)", color=discord.Color.blue())
            field_count = 0
    
    if field_count > 0:
        embeds.append(current_embed)
    
    # Send all embeds
    for embed in embeds:
        await interaction.followup.send(embed=embed, ephemeral=True)

# ---------- VALIDATION WEB SERVER ----------
async def validate(request):
    try:
        data = await request.json()
        key = data.get('key')
    except Exception as e:
        print(f"❌ JSON parse error: {e}")
        return web.json_response({"valid": False, "message": "Invalid JSON"}, status=200)
    
    if not key:
        print("❌ No key provided in request")
        return web.json_response({"valid": False, "message": "No key provided"}, status=200)
    
    print(f"🔍 Validating key: {key}")
    valid = is_key_valid(key)
    
    if valid:
        print(f"✅ Key validation passed: {key}")
        return web.json_response({"valid": True, "message": "Key is valid"}, status=200)
    else:
        print(f"❌ Key validation failed: {key}")
        return web.json_response({"valid": False, "message": "Key is invalid or expired"}, status=200)

async def health_check(request):
    """Health check endpoint for UptimeRobot - returns 200 OK"""
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
    print(f"✅ Health check available at / and /health")
    
    await asyncio.Event().wait()

# ---------- BOT EVENTS ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Bot is ready!")
    print(f"✅ Current UTC Time: {get_current_time().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"✅ Database path: {DB_PATH}")
    
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
