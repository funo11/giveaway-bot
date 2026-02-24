import discord
import json
import os
import random
import asyncio
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DATA_FILE = "data.json"

# ---------------- LOAD / SAVE ----------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "giveaways": {},
            "last_winner": {},
            "weights": {},
            "boost": {}
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# ---------------- TIME PARSER ----------------

def parse_time(time_str):
    unit = time_str[-1]
    amount = int(time_str[:-1])

    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    else:
        raise ValueError("Invalid time format")

# ---------------- START GIVEAWAY ----------------

@tree.command(name="gstart", description="Start a giveaway")
async def gstart(interaction: discord.Interaction, duration: str, winners: int, prize: str):

    end_time = datetime.utcnow() + parse_time(duration)

    embed = discord.Embed(
        title="🎉 GIVEAWAY 🎉",
        description=f"Prize: **{prize}**\nReact with 🎉 to enter!\nEnds <t:{int(end_time.timestamp())}:R>",
        color=0x2b2d31
    )

    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("🎉")

    data["giveaways"][str(message.id)] = {
        "end": end_time.timestamp(),
        "winners": winners,
        "prize": prize,
        "channel": interaction.channel.id,
        "guild": interaction.guild.id
    }

    save_data(data)

    await interaction.response.send_message("Giveaway started!", ephemeral=True)

# ---------------- PICK WINNER ----------------

async def pick_winner(message_id, giveaway_data):

    channel = bot.get_channel(giveaway_data["channel"])
    message = await channel.fetch_message(int(message_id))

    users = []

    for reaction in message.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    users.append(user)

    if not users:
        await channel.send("No valid participants.")
        return

    guild_id = str(giveaway_data["guild"])
    last_winner = data["last_winner"].get(guild_id)

    weighted_pool = []

    for user in users:
        user_id = str(user.id)

        if user_id == last_winner:
            continue

        weight = 1

        if user_id in data["weights"]:
            weight += data["weights"][user_id]

        if user_id in data["boost"]:
            weight += data["boost"][user_id]

        weighted_pool.extend([user] * weight)

    if not weighted_pool:
        weighted_pool = users

    selected_winners = random.sample(
        weighted_pool,
        min(giveaway_data["winners"], len(weighted_pool))
    )

    data["last_winner"][guild_id] = str(selected_winners[0].id)
    save_data(data)

    mentions = ", ".join(user.mention for user in selected_winners)

    await channel.send(f"🎉 Congratulations {mentions}! You won **{giveaway_data['prize']}**")

# ---------------- LOOP CHECK ----------------

async def giveaway_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        current_time = datetime.utcnow().timestamp()

        for message_id in list(data["giveaways"].keys()):
            giveaway = data["giveaways"][message_id]

            if current_time >= giveaway["end"]:
                await pick_winner(message_id, giveaway)
                del data["giveaways"][message_id]
                save_data(data)

        await asyncio.sleep(10)

# ---------------- END GIVEAWAY ----------------

@tree.command(name="gend", description="End a giveaway early")
async def gend(interaction: discord.Interaction, message_id: str):

    if message_id in data["giveaways"]:
        giveaway = data["giveaways"][message_id]
        await pick_winner(message_id, giveaway)
        del data["giveaways"][message_id]
        save_data(data)

        await interaction.response.send_message("Giveaway ended.", ephemeral=True)
    else:
        await interaction.response.send_message("Giveaway not found.", ephemeral=True)

# ---------------- REROLL ----------------

@tree.command(name="greroll", description="Reroll a giveaway")
async def greroll(interaction: discord.Interaction, message_id: str):

    if message_id in data["giveaways"]:
        giveaway = data["giveaways"][message_id]
        await pick_winner(message_id, giveaway)
        await interaction.response.send_message("Giveaway rerolled.", ephemeral=True)
    else:
        await interaction.response.send_message("Giveaway not found.", ephemeral=True)

# ---------------- LIST GIVEAWAYS ----------------

@tree.command(name="glist", description="List active giveaways")
async def glist(interaction: discord.Interaction):

    if not data["giveaways"]:
        await interaction.response.send_message("No active giveaways.", ephemeral=True)
        return

    message_ids = "\n".join(data["giveaways"].keys())
    await interaction.response.send_message(f"Active Giveaways:\n{message_ids}", ephemeral=True)

# ---------------- WEIGHT ----------------

@tree.command(name="weight", description="Increase user's win chance")
async def weight(interaction: discord.Interaction, user: discord.Member, amount: int):

    data["weights"][str(user.id)] = amount
    save_data(data)

    await interaction.response.send_message("Weight updated.", ephemeral=True)

# ---------------- BOOST ----------------

@tree.command(name="boost", description="Manual win boost (max 3)")
async def boost(interaction: discord.Interaction, user: discord.Member, amount: int):

    if amount > 3:
        amount = 3

    data["boost"][str(user.id)] = amount
    save_data(data)

    await interaction.response.send_message("Boost updated.", ephemeral=True)

# ---------------- READY ----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync()
    bot.loop.create_task(giveaway_loop())

bot.run(TOKEN)
