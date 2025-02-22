import os
import discord
import logging

from discord.ext import commands
from dotenv import load_dotenv
from agent import MistralAgent

#
# Global Data Structures
#

# In-memory dictionary to store offers:
#   offers[offer_id] = {
#       "name": "Company XYZ",
#       "job_description": "...",
#       "package": "...",
#       "extra": [ ...list of appended updates... ]
#   }
offers = {}

# Stores the entire "debate history" so that we can feed it to Mistral
# Example structure: [("username", "message text"), ("Bot", "message text"), ...]
debate_history = []

# Setup logging
logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)
logging.basicConfig()

# Load environment variables
load_dotenv()

# Create the bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Mistral agent
agent = MistralAgent()

# Fetch Discord token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


#
# Helper Functions
#

def build_debate_context() -> str:
    """
    Constructs a single string that includes:
      1) All current offers (with name, job_description, package, and any extra info).
      2) The entire debate history of user/bot messages so far.
    """

    # 1) Summarize all job offers
    offers_summary_lines = ["Currently considered job offers:\n"]
    if not offers:
        offers_summary_lines.append("  (No offers yet.)\n")
    else:
        for oid, data in offers.items():
            extra_text = "\n       ".join(data["extra"]) if data["extra"] else "(No extra updates)"
            offers_summary_lines.append(
                f" • Offer ID: {oid}\n"
                f"   Company Name: {data['name']}\n"
                f"   Job Description: {data['job_description']}\n"
                f"   Package: {data['package']}\n"
                f"   Extra Info:\n       {extra_text}\n"
            )

    offers_summary = "\n".join(offers_summary_lines)

    # 2) Debate history
    debate_lines = ["Conversation history (user comments, prior arguments):"]
    if not debate_history:
        debate_lines.append("  (No conversation so far.)")
    else:
        for speaker, text in debate_history:
            debate_lines.append(f"{speaker}: {text}")
    debate_text = "\n".join(debate_lines)

    # Combine them
    context_str = f"{offers_summary}\n\n{debate_text}"
    return context_str


async def generate_company_argument(offer_id: int) -> str:
    """
    Uses the MistralAgent to produce a custom argument from a specific company's perspective,
    given the entire debate context so far.
    """
    # Step 1: Build the complete context as a system prompt
    context = build_debate_context()
    system_prompt = (
        "You are simulating a debate between multiple companies that want to hire a candidate.\n"
        "Include all relevant details in your responses, but stay in-character as the 'debate organizer.'\n"
        "You have the following context:\n\n"
        f"{context}\n"
    )

    # Step 2: Identify the target company
    company_data = offers.get(offer_id)
    if not company_data:
        # Should ideally never happen if we call this function with a valid ID
        return f"No company found with ID {offer_id}."

    # Step 3: Construct user_prompt telling Mistral to produce an argument from the company's perspective
    user_prompt = (
        f"Now, produce a persuasive argument from the perspective of company '{company_data['name']}' (offer ID: {offer_id}). "
        f"Focus on why the candidate should choose this offer over others. At most 200 characters"
    )

    # Step 4: Call MistralAgent
    response_text = await agent.generate_custom_response(system_prompt, user_prompt)
    return response_text


#
# Bot Events
#

@bot.event
async def on_ready():
    logger.info(f"{bot.user} has connected to Discord!")


@bot.event
async def on_message(message: discord.Message):
    # Do not respond to our own messages or other bots
    if message.author.bot:
        return

    # If it's a prefix command, let the command framework handle it
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # Otherwise, treat it as a normal user message that goes into debate_history
    debate_history.append((message.author.display_name, message.content))

    # Also get a normal AI response from Mistral (optional, if you want the bot to reply to all user messages)
    logger.info(f"Processing normal message from {message.author}: {message.content}")
    ai_response = await agent.run(message)

    # Add the AI response to debate_history if you want the next round to see the AI’s prior statements
    debate_history.append(("Bot", ai_response))

    # Reply in Discord
    await message.reply(ai_response)


#
# Bot Commands

@bot.command(name="ping", help="Pings the bot.")
async def ping(ctx, *, arg=None):
    if arg is None:
        await ctx.send("Pong!")
    else:
        await ctx.send(f"Pong! Your argument was {arg}")


@bot.command(name="create", help="Create a new job offer.")
async def create_offer(ctx: commands.Context, offer_id: int, name: str, job_description: str, *, package: str):
    if offer_id in offers:
        await ctx.send(f"Offer with ID `{offer_id}` already exists! Use !update to add more info.")
        return

    offers[offer_id] = {
        "name": name,
        "job_description": job_description,
        "package": package,
        "extra": []
    }
    await ctx.send(
        f"**Created** offer `{offer_id}`:\n"
        f"- Company Name: {name}\n"
        f"- Job Description: {job_description}\n"
        f"- Package: {package}"
    )


@bot.command(name="update", help="Update an existing offer with more info.")
async def update_offer(ctx: commands.Context, offer_id: int, *, more_info: str):
    if offer_id not in offers:
        await ctx.send(f"No offer found with ID `{offer_id}`.")
        return

    offers[offer_id]["extra"].append(more_info)
    await ctx.send(f"**Updated** offer `{offer_id}` with new info:\n{more_info}")


@bot.command(name="remove", help="Remove an existing offer.")
async def remove_offer(ctx: commands.Context, offer_id: int):
    if offer_id not in offers:
        await ctx.send(f"No offer found with ID `{offer_id}`.")
        return

    removed_offer = offers.pop(offer_id)
    await ctx.send(
        f"**Removed** offer `{offer_id}` from consideration:\n"
        f"- Company: {removed_offer['name']}"
    )


@bot.command(name="y", help="Continue the debate for one round (all companies speak).")
async def continue_debate(ctx: commands.Context, offer_id: int = None):
    """
    !y
    Allows each company in the offers dictionary to speak in turn,
    generating an AI-based argument from each company's perspective.
    !y <offer_id> - Ask a specific company to speak
    """
    if not offers:
        await ctx.send("No offers available to debate!")
        return

    if offer_id is None:
        # For each offer in memory, generate a new argument
        for offer_id, data in offers.items():
            argument = await generate_company_argument(offer_id)
            # Optionally, store it in debate_history so future calls see it
            debate_history.append((f"Company {data['name']}", argument))

            # Send the argument to the channel
            await ctx.send(f"**{data['name']} (Offer ID {offer_id})**:\n{argument}")
        return
    
    # Company-specific logic
    if offer_id not in offers:
        await ctx.send(f"No offer found with ID {offer_id}.")
        return
    
    company_data = offers[offer_id]
    argument = await generate_company_argument(offer_id)

    # Store this argument in debate_history
    debate_history.append((f"Company {company_data['name']}", argument))

    # Send the new argument to the channel
    await ctx.send(f"**{company_data['name']} (Offer ID {offer_id})**:\n{argument}")



if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
