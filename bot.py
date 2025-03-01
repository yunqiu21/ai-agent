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

#
# Global Data Structures
#

# Change the offers dictionary to be user-specific
# Structure: offers[user_id][offer_id] = { offer_data }
offers = {}
# offers = {
#     "1049221845360066620": {
#     "1": {        
#         "name": "CompanyA",
#         "job_description": "As a Data professional at Meta, you will shape the future of people-facing and business-facing products we build across our entire family of applications (Facebook, Instagram, Messenger, WhatsApp, Oculus). By applying your technical skills, analytical mindset, and product intuition to one of the richest data sets in the world, you will have the opportunity to work on complex and meaningful problems that have a direct impact on the lives of people around the world. You will have the chance to work with cutting-edge technology and tools to develop innovative solutions to some of the most pressing challenges facing our platform.",
#         "package": "100k USD",
#         "extra": []    
#     },
#     },
#     "761050704008708146":{
#     "1": {        
#         "name": "CompanyB",
#         "job_description": "Lead the development and optimization of features within TikTok Ads Manager, focusing on improving the ads creation workflow and user journey for the Creative performance ads vertical. Recommend and prioritize innovative features to enhance the usability and performance of the platform, ensuring the ad creation experience is seamless and intuitive for these verticals. Collaborate with cross-functional teams to identify challenges, define product strategies, and set objectives that align with the needs of Creative performance advertisers. Leverage customer feedback, user research, and data analytics to identify opportunities for growth and continuous improvement in the ad creation process. Stay up-to-date with ad tech trends and emerging technologies, applying this knowledge to keep TikTok at the forefront of advertising solutions. Track and analyze key product metrics to inform product decisions and drive iterative improvements to the ads platform.",
#         "package": "200k USD",
#         "extra": []    
#     },
#     "2": {        
#         "name": "CompanyC",
#         "job_description": "As an Account Executive, you will work with your respective set of advertisers to shape their business growth and strengthen long-term relationships. You will drive scalable product adoption and business growth. In this role, you will anticipate how decisions are made at a C-Level, you will explore and uncover the business needs of customers, and understand how our range of product offerings can grow their business. You will set the goal and strategy for how their advertising can reach users.",
#         "package": "300k USD",
#         "extra": []    
#     },
#     },
# }

# Stores the entire "debate history" so that we can feed it to Mistral
# Example structure: [("username", "message text"), ("Bot", "message text"), ...]
# Key: user_id, Value: list of (speaker, message) tuples
user_debate_histories = {}

# Track which users are currently in the middle of a create_offer_form
active_form_sessions = {}

# Setup logging
logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)
logging.basicConfig()

# Load environment variables
load_dotenv()

class CustomHelpCommand(commands.HelpCommand):
    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="Bot Commands", description="Here are the available commands:", color=discord.Color.blue())

        # List prefix commands with descriptions
        for cog, commands in mapping.items():
            filtered_commands = await self.filter_commands(commands, sort=True)
            command_list = [f"`!{command.name}` - {command.help or 'No description available'}" for command in filtered_commands]

            if command_list:
                embed.add_field(name=cog.qualified_name if cog else "General", value="\n".join(command_list), inline=False)

        # Manually list slash commands with descriptions
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

# Mistral agent
agent = GPTAgent()

# Fetch Discord token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


# Create Offer Modal with URL support
class CreateOfferModal(discord.ui.Modal, title="Create New Offer"):
    # offer_id = discord.ui.TextInput(
    #     label="Offer ID",
    #     placeholder="Enter a number (e.g., 1, 2, 3)",
    #     style=discord.TextStyle.short,
    #     required=True
    # )
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

            # Auto-generate offer_id
            offer_id = str(len(offers[user_id]) + 1)
            while offer_id in offers[user_id]:  # In case of deleted offers, find next available number
                offer_id = str(int(offer_id) + 1)

            # Check if job description is a URL
            job_desc = self.job_description.value
            if validators.url(job_desc):
                logger.info(f"URL detected, fetching content...")
                job_desc = fetch_website_info(job_desc)
                if job_desc.startswith("Error"):
                    await interaction.response.send_message(f"Failed to fetch URL content: {job_desc}", ephemeral=True)
                    return

            # Create the offer under the user's ID
            offers[user_id][offer_id] = {
                "name": self.company_name.value,
                "title": self.job_title.value,
                "location": self.location.value,
                "job_description": job_desc,
                "package": self.package.value,
                "extra": []
            }

            await interaction.response.send_message(
                f"**Success!** Created offer `{offer_id}`:\n"
                f"- Company Name: {self.company_name.value}\n"
                f"- Job Title: {self.job_title.value}\n"
                f"- Location: {self.location.value}\n"
                f"- Job Description: {job_desc[:200]}...\n"
                f"- Package: {self.package.value}"
            )

            # Generate initial AI response
            argument = await generate_company_argument(offer_id, user_id)
            if user_id not in user_debate_histories:
                user_debate_histories[user_id] = []
            user_debate_histories[user_id].append((f"Company {self.company_name.value}", argument))
            await interaction.followup.send(f"**Initial AI Response from {self.company_name.value}**:\n{argument}")

        except Exception as e:
            logger.error(f"Error in CreateOfferModal: {e}")
            await interaction.response.send_message("An error occurred while creating the offer.", ephemeral=True)

class UpdateOfferModal(discord.ui.Modal, title="Update Offer"):
    def __init__(self, offer_id: str, user_id: int):
        super().__init__()
        self.offer_id = offer_id
        self.user_id = user_id
        offer_data = offers[user_id][offer_id]

        # Populate fields with existing values
        self.company_name = discord.ui.TextInput(
            label="Company Name",
            default=offer_data["name"],
            style=discord.TextStyle.short,
            required=True
        )
        self.job_title = discord.ui.TextInput(
            label="Job Title",
            default=offer_data["title"],
            style=discord.TextStyle.short,
            required=True
        )
        self.location = discord.ui.TextInput(
            label="Location",
            default=offer_data["location"],
            style=discord.TextStyle.short,
            required=True
        )
        self.job_description = discord.ui.TextInput(
            label="Job Description or URL",
            default=offer_data["job_description"][:4000],
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.package = discord.ui.TextInput(
            label="Package",
            default=offer_data["package"],
            style=discord.TextStyle.short,
            required=True
        )

        # Add all fields to the modal
        self.add_item(self.company_name)
        self.add_item(self.job_title)
        self.add_item(self.location)
        self.add_item(self.job_description)
        self.add_item(self.package)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Update the existing offer
            offers[self.user_id][self.offer_id] = {
                "name": self.company_name.value,
                "title": self.job_title.value,
                "location": self.location.value,
                "job_description": self.job_description.value,
                "package": self.package.value,
                "extra": offers[self.user_id][self.offer_id].get("extra", [])
            }

            await interaction.response.send_message(
                f"**Updated** offer `{self.offer_id}`:\n"
                f"- Company Name: {self.company_name.value}\n"
                f"- Job Title: {self.job_title.value}\n"
                f"- Location: {self.location.value}\n"
                f"- Job Description: {self.job_description.value[:200]}...\n"
                f"- Package: {self.package.value}"
            )
        except Exception as e:
            logger.error(f"Error in UpdateOfferModal: {e}")
            await interaction.response.send_message("An error occurred while updating the offer.", ephemeral=True)

# Slash Commands
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
#
# Helper Functions
#

def build_debate_context(user_id: int) -> str:
    """
    Constructs a structured context string that includes:
      1) A summary of all current job offers for the user.
      2) The debate history, including arguments from companies and user responses.
    """

    # 1) Summarize all job offers
    offers_summary_lines = ["### Current Job Offers Under Consideration ###\n"]
    if user_id not in offers or not offers[user_id]:
        offers_summary_lines.append("No job offers available.\n")
    else:
        for oid, data in offers[user_id].items():
            extra_text = "\n    ".join(data["extra"]) if data["extra"] else "None"
            offers_summary_lines.append(
                f"**Offer ID:** {oid}\n"
                f"**Company:** {data['name']}\n"
                f"**Job Title:** {data['title']}\n"
                f"**Location:** {data['location']}\n"
                f"**Job Description:** {data['job_description']}\n"
                f"**Compensation Package:** {data['package']}\n"
                f"**Additional Information:** {extra_text}\n"
            )

    offers_summary = f"\n{'-'*40}".join(offers_summary_lines)

    # 2) User-specific debate history
    debate_lines = ["### Debate History ###\n"]
    user_history = user_debate_histories.get(user_id, [])

    if not user_history:
        debate_lines.append("No debate has occurred yet.")
    else:
        for speaker, text in user_history:
            # # Label speakers clearly
            # speaker_label = (
            #     "[User]" if speaker == "user" else
            #     f"[Company: {speaker}]" if speaker in offers[user_id] else
            #     "[Debate Organizer]"
            # )
            debate_lines.append(f"[{speaker}]: {text}")

    debate_text = "\n".join(debate_lines)

    # Combine sections with a clear separator
    context_str = f"{offers_summary}\n\n{'='*40}\n\n{debate_text}"
    
    return context_str


async def generate_company_argument(offer_id: int, user_id: int, user_msg=None) -> str:
    """
    Uses the agent to produce a custom argument from a specific company's perspective,
    given the entire debate context so far.
    """
    # Step 1: Build the complete context as a system prompt
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

    # Step 2: Identify the target company
    company_data = offers[user_id].get(offer_id)
    if not company_data:
        return f"No company found with ID {offer_id}."

    # Step 4: Construct user_prompt telling the agent to respond strategically
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

    # Step 5: Call agent
    # logger.info(system_prompt + "\n" + user_prompt)
    response_text = await agent.generate_custom_response(system_prompt, user_prompt)
    return response_text

#
# Bot Events
#

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
    """
    This event is triggered on every incoming message. We skip sending the user's
    message to Mistral if they are in an active form session. Otherwise, if it's
    not a command (!...), we send it to Mistral.
    """
    if message.author.bot:
        return

    # If user typed a command (starts with "!"), process it and return
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # If this user is currently in a form session, skip Mistral:
    if message.author.id in active_form_sessions:
        # We do nothing, because presumably the create_offer_form logic
        # is waiting for their input with bot.wait_for(...)
        return

     # Otherwise, this is a normal user message; add it to debate history
    # and trigger a new round of debate
    logger.info(f"Processing normal message from {message.author}: {message.content}")
    # Initialize debate history for new users
    if message.author.id not in user_debate_histories:
        user_debate_histories[message.author.id] = []
    
    # Add user's message to their personal history
    user_debate_histories[message.author.id].append((message.author.display_name, message.content))

    # Trigger a new round of debate with all companies
    if message.author.id in offers and offers[message.author.id]:
        await message.reply("**Companies respond to your message:**")
        for oid in offers[message.author.id]:
            # Generate response using user-specific context
            argument = await generate_company_argument(oid, message.author.id)
            # Store company's response in user's personal history
            user_debate_histories[message.author.id].append((f"Company {offers[message.author.id][oid]['name']}", argument))
            await message.reply(f"**{offers[message.author.id][oid]['name']} (Offer ID {oid})**:\n{argument}")
    else:
        await message.reply("No offers available to debate! Use `/create` to add some offers first.")

#
# Bot Commands

@bot.command(name="ping", help="Pings the bot")
async def ping(ctx, *, arg=None):
    if arg is None:
        await ctx.send("Pong!")
    else:
        await ctx.send(f"Pong! Your argument was {arg}")


#
# Helper: A simple function to wait for one message from the same user/channel
#
async def ask_user_for_input(ctx: commands.Context, prompt: str, timeout=120) -> (bool, str):
    """
    Sends `prompt` to the channel, waits for user's next message.
    Returns (True, <message_content>) if user responded.
    Returns (False, None) if user timed out or typed 'cancel'.
    """
    await ctx.send(prompt)

    def check(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=timeout)
    except:
        await ctx.send("**Timed out.** Aborting the creation process.")
        return False, None

    if msg.content.lower() == "cancel":
        await ctx.send("**Cancelled.** Aborting the creation process.")
        return False, None

    return True, msg.content


#
# Multi-step Create Command
#
# @bot.command(name="create", help="Start an interactive form to create a new job offer.")
# async def create_offer_form(ctx: commands.Context):
#     """
#     !create_form
#     A multi-step flow to create an offer with a potentially long job description.
#     """
#     # 1) Mark user as in form session
#     if ctx.author.id in active_form_sessions:
#         await ctx.send("You are already creating an offer. Cancel or finish that first.")
#         return
#     active_form_sessions[ctx.author.id] = True

#     # 2) Ask for Offer ID
#     success, offer_id_str = await ask_user_for_input(
#         ctx,
#         "**Let's create a new job offer.**\nPlease enter an offer ID (integer) or type `cancel`:"
#     )
#     if not success:
#         active_form_sessions.pop(ctx.author.id, None)
#         return

#     try:
#         offer_id = int(offer_id_str)
#     except ValueError:
#         await ctx.send("Invalid integer for Offer ID. Aborting.")
#         active_form_sessions.pop(ctx.author.id, None)
#         return

#     if offer_id in offers:
#         await ctx.send(f"An offer with ID **{offer_id}** already exists. Aborting.")
#         active_form_sessions.pop(ctx.author.id, None)
#         return

#     # 3) Ask for Company Name
#     success, company_name = await ask_user_for_input(
#         ctx,
#         "Please enter the **Company Name** (or type `cancel`):"
#     )
#     if not success:
#         active_form_sessions.pop(ctx.author.id, None)
#         return

#     # 4) Ask for multi-line Job Description
#     await ctx.send(
#         "Please enter the **Job Description**.\n"
#         "Type as many lines as you want. When finished, type `DONE` on a separate line.\n"
#         "Or type `cancel` to abort."
#     )
#     try:
#         first_msg = await bot.wait_for(
#                 "message",
#                 check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
#                 timeout=300
#             )
#     except:
#         await ctx.send("**Timed out** while waiting for the job description. Aborting.")
#         active_form_sessions.pop(ctx.author.id, None)
#         return
#     logger.info(f"job description: {first_msg.content}")
#     if validators.url(first_msg.content):  # Check if it's a valid URL
#         logger.info(f"user inputs an url.")
#         job_description = fetch_website_info(first_msg.content)
#         logger.info(f"parsed url: {job_description[:30]}")
#     else:
#         job_description_lines = [first_msg.content]
#         while True:
#             try:
#                 msg = await bot.wait_for(
#                     "message",
#                     check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
#                     timeout=300
#                 )
#             except:
#                 await ctx.send("**Timed out** while waiting for the job description. Aborting.")
#                 active_form_sessions.pop(ctx.author.id, None)
#                 return

#             if msg.content.lower() == "cancel":
#                 await ctx.send("**Cancelled.** Aborting the creation process.")
#                 active_form_sessions.pop(ctx.author.id, None)
#                 return

#             if msg.content.lower() == "done":
#                 break

#             job_description_lines.append(msg.content)

#         job_description = "\n".join(job_description_lines)

#     # 5) Ask for Package
#     success, package_details = await ask_user_for_input(
#         ctx,
#         "Enter the **Package** (e.g. `100k USD + benefits`):"
#     )
#     if not success:
#         active_form_sessions.pop(ctx.author.id, None)
#         return

#     # 6) Summarize + Confirmation
#     summary = (
#         f"**Offer ID:** {offer_id}\n"
#         f"**Company Name:** {company_name}\n"
#         f"**Job Description:**\n{job_description}\n"
#         f"**Package:** {package_details}\n"
#     )
#     await ctx.send(f"**Here is what you've entered:**\n{summary}")

#     success, confirm = await ask_user_for_input(ctx, "Type `yes` to confirm or `no` to abort:")
#     if not success:
#         active_form_sessions.pop(ctx.author.id, None)
#         return

#     if confirm.lower() != "yes":
#         await ctx.send("**Aborted** creation process. No offer created.")
#         active_form_sessions.pop(ctx.author.id, None)
#         return

#     # 7) Actually save
#     offers[offer_id] = {
#         "name": company_name,
#         "job_description": job_description,
#         "package": package_details,
#         "extra": []
#     }

#     await ctx.send(
#         f"**Success!** Created offer `{offer_id}`:\n"
#         f"- Company Name: {company_name}\n"
#         f"- Job Description: (see above)\n"
#         f"- Package: {package_details}"
#     )

#     # 8) Mark session as finished
#     active_form_sessions.pop(ctx.author.id, None)


# @bot.command(name="update", help="Update an existing offer with more info.")
# async def update_offer(ctx: commands.Context, offer_id: int, *, more_info: str):
#     if offer_id not in offers:
#         await ctx.send(f"No offer found with ID `{offer_id}`.")
#         return

#     offers[offer_id]["extra"].append(more_info)
#     await ctx.send(f"**Updated** offer `{offer_id}` with new info:\n{more_info}")


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

    # Build a string listing each offer
    lines = ["**Currently Available Offers:**\n"]
    for oid, data in offers[user_id].items():
        lines.append(
            f"**Offer ID:** {oid}\n"
            f"**Company Name:** {data['name']}\n"
            f"**Job Description:**\n{data['job_description'][:50]}...\n"
            f"**Package:** {data['package']}\n"
            f"**Extra Info:** {', '.join(data['extra']) if data['extra'] else '(None)'}\n"
            "--------------------------------------\n"
        )

    message_text = "\n".join(lines)
    await ctx.send(message_text)


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

    # Initialize debate history for new users
    if user_id not in user_debate_histories:
        user_debate_histories[user_id] = []

    if offer_id is None:
        # Generate arguments from all companies
        for oid in offers[user_id]:
            argument = await generate_company_argument(oid, user_id)
            # Store response in user's personal history
            user_debate_histories[user_id].append((f"Company {offers[user_id][oid]['name']}", argument))
            await ctx.send(f"**{offers[user_id][oid]['name']} (Offer ID {oid})**:\n{argument}")
        return
    
    # Logic for a specific company
    if str(offer_id) not in offers[user_id]:
        await ctx.send(f"No offer found with ID {offer_id}.")
        return
    
    company_data = offers[user_id][str(offer_id)]
    argument = await generate_company_argument(offer_id, user_id)

    # Store the argument in user's personal history
    user_debate_histories[user_id].append((f"Company {company_data['name']}", argument))
    await ctx.send(f"**{company_data['name']} (Offer ID {offer_id})**:\n{argument}")

# helper
def fetch_website_info(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an error for HTTP issues

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract key content (e.g., paragraphs, headlines)
        # headlines = [h.get_text() for h in soup.find_all(['h1', 'h2'])]
        paragraphs = [p.get_text() for p in soup.find_all('p')]

        # Join extracted text
        extracted_text = "\n".join(paragraphs)

        return extracted_text if extracted_text else "No meaningful content found."

    except requests.exceptions.RequestException as e:
        return f"Error fetching website: {e}"

@bot.command(name="advise", help="Summarizes the conversation and suggests which offer to choose")
async def advise(ctx):
    user_id = ctx.author.id
    
    # Ensure the user has participated in a debate
    if user_id not in user_debate_histories or not user_debate_histories[user_id]:
        await ctx.send("You haven't discussed any offers yet. Start a discussion before asking for advice!")
        return

    # Build full debate context
    context = build_debate_context(user_id)

    # System prompt for decision-making
    system_prompt = (
        "You are an expert career advisor helping a candidate choose between multiple job offers. "
        "Your goal is to provide a **personalized** recommendation based on the candidate’s **stated priorities** "
        "and the arguments presented by competing companies.\n\n"
        "Carefully analyze:\n"
        "1. The candidate's preferences, concerns, and priorities mentioned in the debate.\n"
        "2. The strengths and weaknesses of each company's offer.\n"
        "3. How well each company has addressed the candidate's concerns.\n\n"
        "Your response should be clear, concise, and **directly reference what the candidate and companies have discussed**."
    )

    # User prompt to summarize and decide
    user_prompt = (
        "Summarize the discussion and recommend the **best** job offer for the candidate. "
        "Base your recommendation on **the candidate’s concerns and priorities**, as well as the company arguments.\n\n"
        "Context so far:\n"
        f"{context}\n"        
        "Your response should be **less than 600 characters** and **directly address what was discussed**."
    )

    # Generate advice using GPT-4o
    # logger.info(system_prompt + "\n" + user_prompt)
    advice = await agent.generate_custom_response(system_prompt, user_prompt)
    user_debate_histories[user_id].append((f"Bot's Advice", advice))
    await ctx.send(f"**Bot's Advice:**\n{advice}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
