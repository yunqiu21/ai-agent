# CS 153 - Infrastructure at Scale AI Agent Starter Code

Note that for Discord the terms Bot and App are interchangable. We will use App in this manual.

## Discord App Framework Code

This is the base framework for students to complete the CS 153 final project. Please follow the instructions to fork this repository into your own repository and make all of your additions there.

## Discord App Setup Instructions

Your group will be making your very own AI agent and import it into our CS153 server as a Discord App. This starter code provides the framework for a Discord App implemented in Python. Follow the instructions below.

### Join the Discord Server

First, every member of the team should join the Discord server using the invite link on Ed.

### Get your Role within the Server

Role Options:

`Student`: For enrolled students in the course.

`Online-Student`: For students taking this course online.

`Auditor`: For those auditing the course.

`Collaborator`: For external collaborators or guests.

How to Join Your Role:

1. Send a Direct Message (DM) to the Admin Bot.
2. Use the following command format: `.join <Role Name>`
3. Replace `<Role Name>` with one of the options above (e.g., `.join Student`).

How to Leave Your Role:

1. Send a Direct Message (DM) to the Admin Bot.
2. Use the following command format: `.leave <Role Name>`
3. Replace `<Role Name>` with one of the options above (e.g., `.leave Student`).

### Creating/Joining Your Group Channel

How to create or join your group channel:

1. Send a Direct Message (DM) to the Admin Bot.
2. Pick a **unique** group name (**IMPORTANT**)
3. Use the following command format:`.channel <Group Name>`
4. Replace `<Group Name>` with the name of your project group (e.g., `.channel Group 1`).

**What Happens When You Use the Command:**

If the Channel Already Exists:

- Check if you already have the role for this group. If you don’t have the role, it will assign you the role corresponding to `<Group Name>` granting you access to the channel.

If the Channel Does Not Exist:

- Create a new text channel named `<Group-Name>` in the Project Channels category.
- Create a role named `<group name>` (the system will intentionally lower the case) and assign it to you.

- Set permissions so that:
  - Only members with the `<group name>` role can access the channel.
  - The app and server admins have full access. All other server members are denied access.
  - Once completed, you'll be able to access your group's private channel in the Project Channels category.

## [One student per group] Setting up your bot

##### Note: only ONE student per group should follow the rest of these steps.

### Download files

1. Fork and clone this GitHub repository.
2. Share the repo with your teammates.
3. Create a file called `.env` the same directory/folder as `bot.py`. The `.env` file should look like this, replacing the “your key here” with your key. In the below sections, we explain how to obtain Discord keys and Mistral API keys.

```
DISCORD_TOKEN=“your key here”
MISTRAL_API_KEY=“your key here”
```

#### Making the bot

1. Go to https://discord.com/developers and click “New Application” in the top right corner.
2. Pick a cool name for your new bot!

##### It is very important that you name your app exactly following this scheme; some parts of the bot’s code rely on this format.

1. Next, you’ll want to click on the tab labeled “Bot” under “Settings.”
2. Click “Copy” to copy the bot’s token. If you don’t see “Copy”, hit “Reset Token” and copy the token that appears (make sure you’re the first team member to go through these steps!)
3. Open `.env` and paste the token between the quotes on the line labeled `DISCORD_TOKEN`.
4. Scroll down to a region called “Privileged Gateway Intents”
5. Tick the options for “Presence Intent”, “Server Members Intent”, and “Message Content Intent”, and save your changes.
6. Click on the tab labeled “OAuth2” under “Settings”
7. Click the tab labeled “URL Generator” under “OAuth2”.
8. Check the box labeled “bot”. Once you do that, another area with a bunch of options should appear lower down on the page.
9. Check the following permissions, then copy the link that’s generated. <em>Note that these permissions are just a starting point for your bot. We think they’ll cover most cases, but you may run into cases where you want to be able to do more. If you do, you’re welcome to send updated links to the teaching team to re-invite your bot with new permissions.</em>
   <img width="700" alt="Screenshot 2024-04-22 at 4 31 31 PM" src="https://github.com/stanfordio/cs152bots/assets/96695971/520c040e-f494-4b7e-bb45-01dd59772462">

10. Copy paste this link into the #app-invite-link channel on the CS 153 Discord server. Someone in the teaching team will invite your bot.
11. After your bot appears in #welcome, find your bot's "application ID" on the Discord Developer panel.
    ![CleanShot 2025-01-21 at 23 42 53@2x](https://github.com/user-attachments/assets/2cf6b8fd-5756-494c-a6c3-8c61e821d568)
13. Send a DM to the admin bot: use the `.add-bot <application ID>` command to add the bot to your channel.

#### Setting up the Mistral API key

1. Go to [Mistral AI Console](console.mistral.ai) and sign up for an account. During sign-up, you will be prompted to set up a workspace. Choose a name for your workspace and select "I'm a solo creator." If you already have an account, log in directly.
2. After logging in, navigate to the "Workspace" section on the left-hand menu. Click on "Billing" and select “Experiment for free”.
3. A pop-up window will appear. Click "Accept" to subscribe to the experiment plan and follow the instructions to verify your phone number.
4. Once you have successfully subscribed to the experiment plan, go to the "API keys" page under the “API” section in the menu on the left.
5. Click on "Create new key" to generate a new API key.
6. After the key is generated, it will appear under “Your API keys” with the text: `“Your key is: <your-api-key>”`. Copy the API key and save it securely, as it will not be displayed again for security reasons.
7. Open your `.env` file and paste the API key between the quotes on the line labeled `MISTRAL_API_KEY`.

#### Setting up the starter code

First things first, the starter code is written in Python. You’ll want to make sure that you have Python 3 installed on your machine; if you don’t, follow [these instructions to install PyCharm](https://web.stanford.edu/class/cs106a/handouts/installingpycharm.html), the Stanford-recommended Python editor. Alternatively, you can use a text editor of your choice.

Once you’ve done that, open a terminal in the same folder as your `bot.py` file. (If you haven’t used your terminal before, check out [this guide](https://www.macworld.com/article/2042378/master-the-command-line-navigating-files-and-folders.html)!)

You’ll need to install some libraries if you don’t have them already, namely:

    # python3 -m pip install mistralai
    # python3 -m pip install discord.py
    # python3 -m pip install python-dotenv
    # python3 -m pip install audioop-lts

## Guide To The Starter Code

The starter code includes two files, `bot.py` and `agent.py`. Let's take a look at what this project already does.

To do this, run `python3 bot.py` and leave it running in your terminal. Next, go into your team’s channel `Group-Name` and try typing any message. You should see the bot respond in the same channel. The default behavior of the bot is, that any time it sees a message (from a user), it sends that message to Mistral's API and sends back the response.

Let's take a deeper look into how this is done. In the `bot.py` file, scroll to the `on_message` function. This function is called every time a message is sent in your channel. Observe how `agent.run()` is called on the message content, and how the result of that message call is sent back to the user.

This agent is defined in the `agent.py` file. The `run()` function creates a simple LLM call with a system message defined at the top, and the user's message passed in. The response from the LLM is then returned.

Check out this finalized [weather agent bot](https://github.com/CS-153/weather-agent-template/blob/main/agent.py) to see a more detailed example.

## Troubleshooting

### `Exception: .env not found`!

If you’re seeing this error, it probably means that your terminal is not open in the right folder. Make sure that it is open inside the folder that contains `bot.py` and `.env`
