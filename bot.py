import os
import discord
import logging


from discord.ext import commands
from dotenv import load_dotenv
from agent import GPTAgent

from discord.ui import Button, View, Modal, TextInput
from discord import ButtonStyle, TextStyle

import requests
from bs4 import BeautifulSoup
import validators

# Global Data Structures
offers = {}
user_debate_histories = {}

# Setup logging
logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)
logging.basicConfig()

# Load environment variables
load_dotenv()

class CustomHelpCommand(commands.HelpCommand):
    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="Bot Commands", description="Here are the available commands:", color=discord.Color.blue())

        for cog, commands in mapping.items():
            filtered_commands = await self.filter_commands(commands, sort=True)
            command_list = [f"`!{command.name}` - {command.help or 'No description available'}" for command in filtered_commands]

            if command_list:
                embed.add_field(name=cog.qualified_name if cog else "General", value="\n".join(command_list), inline=False)

        slash_commands = [
            ("/create", "Create a new job offer"),
            ("/update", "Update an existing offer")
        ]
        slash_list = "\n".join([f"`{cmd}` - {desc}" for cmd, desc in slash_commands])

        if slash_list:
            embed.add_field(name="Slash Commands", value=slash_list, inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

# Create the bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=CustomHelpCommand())

# Agent
agent = GPTAgent()

# Fetch Discord token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


class CreateOfferModal(discord.ui.Modal, title="Create New Offer"):
    company_name = discord.ui.TextInput(
        label="Company Name",
        placeholder="Enter company name",
        style=discord.TextStyle.short,
        required=True
    )
    job_title = discord.ui.TextInput(
        label="Job Title",
        placeholder="Enter job title",
        style=discord.TextStyle.short,
        required=True
    )
    location = discord.ui.TextInput(
        label="Location",
        placeholder="Enter job location (e.g., New York, Remote)",
        style=discord.TextStyle.short,
        required=True
    )
    job_description = discord.ui.TextInput(
        label="Job Description or URL",
        placeholder="Enter job description or paste a URL",
        style=discord.TextStyle.paragraph,
        required=True
    )
    package = discord.ui.TextInput(
        label="Package",
        placeholder="e.g., 100k USD + benefits",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = interaction.user.id
            if user_id not in offers:
                offers[user_id] = {}

            offer_id = str(len(offers[user_id]) + 1)
            while offer_id in offers[user_id]:
                offer_id = str(int(offer_id) + 1)

            job_desc = self.job_description.value
            if validators.url(job_desc):
                logger.info(f"URL detected, fetching content...")
                job_desc = fetch_website_info(job_desc)
                if job_desc.startswith("Error"):
                    await interaction.response.send_message(f"Failed to fetch URL content: {job_desc}", ephemeral=True)
                    return

            offers[user_id][offer_id] = {
                "name": self.company_name.value,
                "title": self.job_title.value,
                "location": self.location.value,
                "job_description": job_desc,
                "package": self.package.value,
            }

            await interaction.response.send_message(
                f"**Success!** Created offer `{offer_id}`:\n"
                f"- Company Name: {self.company_name.value}\n"
                f"- Job Title: {self.job_title.value}\n"
                f"- Location: {self.location.value}\n"
                f"- Job Description: {job_desc[:200]}...\n"
                f"- Package: {self.package.value}"
            )

            argument = await generate_company_argument(offer_id, user_id)
            if user_id not in user_debate_histories:
                user_debate_histories[user_id] = []
            user_debate_histories[user_id].append((f"Company {self.company_name.value}", argument))
            await interaction.followup.send(f"**Initial Response from {self.company_name.value}**:\n{argument}")

        except Exception as e:
            logger.error(f"Error in CreateOfferModal: {e}")
            await interaction.response.send_message("An error occurred while creating the offer.", ephemeral=True)

class UpdateOfferModal(discord.ui.Modal, title="Update Offer"):
    def __init__(self, offer_id: str, user_id: int):
        super().__init__()
        self.offer_id = offer_id
        self.user_id = user_id

        self.company_name = discord.ui.TextInput(
            label="Company Name",
            placeholder="Enter company name, leave blank to keep current",
            style=discord.TextStyle.short,
            required=False,
        )
        self.job_title = discord.ui.TextInput(
            label="Job Title",
            placeholder="Enter job title, leave blank to keep current",
            style=discord.TextStyle.short,
            required=False,
        )
        self.location = discord.ui.TextInput(
            label="Location",
            placeholder="e.g., New York, leave blank to keep current",
            style=discord.TextStyle.short,
            required=False,
        )
        self.job_description = discord.ui.TextInput(
            label="Job Description or URL",
            placeholder="Enter job description or paste a URL, leave blank to keep current",
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.package = discord.ui.TextInput(
            label="Package",
            placeholder="e.g., 100k USD + benefits, leave blank to keep current",
            style=discord.TextStyle.short,
            required=False,
        )

        self.add_item(self.company_name)
        self.add_item(self.job_title)
        self.add_item(self.location)
        self.add_item(self.job_description)
        self.add_item(self.package)

    async def on_submit(self, interaction: discord.Interaction):
        updated_fields = {}

        if self.company_name.value:
            updated_fields["name"] = self.company_name.value
        if self.job_title.value:
            updated_fields["title"] = self.job_title.value
        if self.location.value:
            updated_fields["location"] = self.location.value
        if self.job_description.value:
            job_desc = self.job_description.value
            if validators.url(job_desc):
                logger.info(f"URL detected, fetching content...")
                job_desc = fetch_website_info(job_desc)
                if job_desc.startswith("Error"):
                    await interaction.response.send_message(f"Failed to fetch URL content: {job_desc}", ephemeral=True)
                    return
            updated_fields["job_description"] = job_desc
        if self.package.value:
            updated_fields["package"] = self.package.value

        if not updated_fields:
            await interaction.response.send_message("No changes were made.", ephemeral=True)
            return

        offers[self.user_id][self.offer_id].update(updated_fields)

        update_msg = "\n".join([f"- **{key.capitalize()}**: {value[:200]}" for key, value in updated_fields.items()])
        await interaction.response.send_message(f"**Updated Offer `{self.offer_id}`**:\n{update_msg}")

@bot.tree.command(name="create", description="Create a new job offer")
async def create(interaction: discord.Interaction):
    modal = CreateOfferModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="update", description="Update an existing offer")
async def update(interaction: discord.Interaction, offer_id: str):
    user_id = interaction.user.id
    if user_id not in offers or offer_id not in offers[user_id]:
        await interaction.response.send_message(f"No offer found with ID `{offer_id}`.", ephemeral=True)
        return

    modal = UpdateOfferModal(offer_id, user_id)
    await interaction.response.send_modal(modal)

def fetch_website_info(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = [p.get_text() for p in soup.find_all('p')]
        extracted_text = "\n".join(paragraphs)
        return extracted_text if extracted_text else "No meaningful content found."

    except requests.exceptions.RequestException as e:
        return f"Error fetching website: {e}"
    
@bot.event
async def on_ready():
    logger.info(f"{bot.user} has connected to Discord!")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    logger.info(f"Processing normal message from {message.author}: {message.content}")

    if message.author.id not in user_debate_histories:
        user_debate_histories[message.author.id] = []

    user_debate_histories[message.author.id].append((message.author.display_name, message.content))

    if message.author.id in offers and offers[message.author.id]:
        await message.reply("**Companies respond to your message:**")
        for oid in offers[message.author.id]:
            argument = await generate_company_argument(oid, message.author.id)
            user_debate_histories[message.author.id].append((f"Company {offers[message.author.id][oid]['name']}", argument))
            await message.reply(f"**{offers[message.author.id][oid]['name']} (Offer ID {oid})**:\n{argument}")
    else:
        await message.reply("No offers available to debate! Use `/create` to add some offers first.")

@bot.command(name="go", help="Continue the debate for one round (all companies speak)")
async def continue_debate(ctx: commands.Context, offer_id: int = None):
    """
    !go
    Allows each company in the user's offers to speak in turn,
    generating an AI-based argument from each company's perspective.
    !go <offer_id> - Ask a specific company to speak
    """
    user_id = ctx.author.id
    if user_id not in offers or not offers[user_id]:
        await ctx.send("No offers available to debate!")
        return

    if user_id not in user_debate_histories:
        user_debate_histories[user_id] = []

    if offer_id is None:
        for oid in offers[user_id]:
            argument = await generate_company_argument(oid, user_id)
            user_debate_histories[user_id].append((f"Company {offers[user_id][oid]['name']}", argument))
            await ctx.send(f"**{offers[user_id][oid]['name']} (Offer ID {oid})**:\n{argument}")
        return

    if str(offer_id) not in offers[user_id]:
        await ctx.send(f"No offer found with ID {offer_id}.")
        return

    company_data = offers[user_id][str(offer_id)]
    argument = await generate_company_argument(offer_id, user_id)

    user_debate_histories[user_id].append((f"Company {company_data['name']}", argument))
    await ctx.send(f"**{company_data['name']} (Offer ID {offer_id})**:\n{argument}")

def build_debate_context(user_id: int) -> str:
    """
    Constructs a structured context string that includes:
      1) A summary of all current job offers for the user.
      2) The debate history, including arguments from companies and user responses.
    """

    offers_summary_lines = ["### Current Job Offers Under Consideration ###\n"]
    if user_id not in offers or not offers[user_id]:
        offers_summary_lines.append("No job offers available.\n")
    else:
        for oid, data in offers[user_id].items():
            offers_summary_lines.append(
                f"**Offer ID:** {oid}\n"
                f"**Company:** {data['name']}\n"
                f"**Job Title:** {data['title']}\n"
                f"**Location:** {data['location']}\n"
                f"**Job Description:** {data['job_description']}\n"
                f"**Compensation Package:** {data['package']}\n"
            )
    offers_summary = f"\n{'-'*40}".join(offers_summary_lines)

    debate_lines = ["### Debate History ###\n"]
    user_history = user_debate_histories.get(user_id, [])[-20:]
    if not user_history:
        debate_lines.append("No debate has occurred yet.")
    else:
        for speaker, text in user_history:
            debate_lines.append(f"[{speaker}]: {text}")

    debate_text = "\n".join(debate_lines)
    context_str = f"{offers_summary}\n\n{'='*40}\n\n{debate_text}"

    return context_str


async def generate_company_argument(offer_id: int, user_id: int, user_msg=None) -> str:
    """
    Uses the agent to produce a custom argument from a specific company's perspective,
    given the entire debate context so far.
    """
    context = build_debate_context(user_id)
    system_prompt = (
        "You are facilitating a competitive hiring debate between multiple companies trying to recruit a candidate.\n"
        "Each company must respond to prior arguments made by competitors while emphasizing its unique advantages.\n"
        "The candidate has shared their preferences and concerns, which should be prioritized when crafting responses.\n"
        "If the candidate has just asked a question, companies must address it directly before presenting their own arguments.\n"
        "Stay in-character as the 'debate organizer,' ensuring companies remain persuasive and relevant.\n\n"
        "Context so far:\n"
        f"{context}\n"
    )

    company_data = offers[user_id].get(offer_id)
    if not company_data:
        return f"No company found with ID {offer_id}."

    user_prompt = (
        f"Generate a persuasive counter-argument on behalf of '{company_data['name']}' (offer ID: {offer_id}).\n"
        "1. If the candidate has asked a question, **begin by answering it concisely and convincingly**.\n"
        "2. Respond to competing companies' arguments, pointing out weaknesses or gaps in their offers.\n"
        "3. Emphasize how your offer uniquely meets the candidate's stated preferences and priorities.\n"
        "4. Address any concerns raised by the candidate, reinforcing why your company is the best choice.\n"
        "5. Keep your response engaging and to the point, within 600 characters.\n"
    )

    if user_msg:
        user_prompt += f"\nThe candidate's most recent question or concern: \"{user_msg}\"\n"

    response_text = await agent.generate_custom_response(system_prompt, user_prompt)
    return response_text


@bot.command(name="remove", help="Remove an existing offer")
async def remove_offer(ctx: commands.Context, offer_id: int):
    if str(offer_id) not in offers[ctx.author.id]:
        await ctx.send(f"No offer found with ID `{offer_id}`.")
        return

    removed_offer = offers[ctx.author.id].pop(str(offer_id))
    await ctx.send(
        f"**Removed** offer `{offer_id}` from consideration:\n"
        f"- Company: {removed_offer['name']}"
    )

@bot.command(name="list", help="List all currently available offers")
async def list_all_offers(ctx: commands.Context):
    """
    !list
    Displays all offers for the current user.
    """
    user_id = ctx.author.id
    if user_id not in offers or not offers[user_id]:
        await ctx.send("No offers are currently available.")
        return

    lines = ["**Currently Available Offers:**\n"]
    for oid, data in offers[user_id].items():
        lines.append(
            f"**Offer ID:** {oid}\n"
            f"**Company Name:** {data['name']}\n"
            f"**Title:** {data['title']}\n"
            f"**Location:** {data['location']}\n"
            f"**Job Description:**\n{data['job_description'][:200]}...\n"
            f"**Package:** {data['package']}\n"
            "--------------------------------------\n"
        )

    message_text = "\n".join(lines)
    await ctx.send(message_text)


@bot.command(name="advise", help="Summarizes the conversation and suggests which offer to choose")
async def advise(ctx):
    user_id = ctx.author.id

    if user_id not in user_debate_histories or not user_debate_histories[user_id]:
        await ctx.send("You haven't discussed any offers yet. Start a discussion before asking for advice!")
        return

    context = build_debate_context(user_id)

    system_prompt = (
        "You are an expert career advisor helping a candidate choose between multiple job offers. "
        "Your goal is to provide a **personalized** recommendation based on the candidate's **stated priorities** "
        "and the arguments presented by competing companies.\n\n"
        "Carefully analyze:\n"
        "1. The candidate's preferences, concerns, and priorities mentioned in the debate.\n"
        "2. The strengths and weaknesses of each company's offer.\n"
        "3. How well each company has addressed the candidate's concerns.\n\n"
        "Your response should be clear, concise, and **directly reference what the candidate and companies have discussed**."
    )

    user_prompt = (
        "Summarize the discussion and recommend the **best** job offer for the candidate. "
        "Base your recommendation on **the candidate's concerns and priorities**, as well as the company arguments.\n\n"
        "Context so far:\n"
        f"{context}\n"
        "Your response should be **less than 600 characters** and **directly address what was discussed**."
    )

    advice = await agent.generate_custom_response(system_prompt, user_prompt)
    user_debate_histories[user_id].append((f"Bot's Advice", advice))
    await ctx.send(f"**Bot's Advice:**\n{advice}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
