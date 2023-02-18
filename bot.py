# This file is for a complete rewrite of the bot. Not ready for production

import discord
from urllib.parse import urlparse
import yt_dlp
import ffmpeg
import os
import platform
from dotenv import load_dotenv # new discord bot token library
import asyncio
import asyncio.subprocess as asp
import re
#import pycurl

discordFileSizeLimit = 8000000
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

successfulJobs = 0
failedJobs = 0
consecutiveFailedJobs = 0

@client.event
async def on_ready():
    servers = client.guilds
    print("Servers I'm currently in:")
    for server in servers:
        print(server.name)
    print('server successfully started as {0.user}'.format(client))

@client.event
async def on_reaction_add(reaction, user):
    if user == client.user:
        return

    for reaction in reaction.message.reactions:
        if reaction.me:
            await user.send("You reacted with the same emoji as the bot! This feature is coming soon") # this is for DMing the person who reacted
            # await reaction.message.channel.send(f"{user} reacted with the same emoji as the bot! This feature is coming soon")

@client.event
async def on_message(message):
    username = str(message.author).split('#')[0]
    user_message = str(message.content)
    channel = str(message.channel.name)
    guild = str(message.guild.name)
    
    if message.author == client.user:
        return
    
    isPinged = False
    killSwitch = False # Change this value to activate/deactivate killswitch

    if client.user.mentioned_in(message):
        print(f'Pinged in message: {username} on #{channel} in "{guild}": {user_message}')
        isPinged = True
    
    if 'instagram.com' in message.content:
        global successfulJobs, failedJobs, consecutiveFailedJobs
        print(f'Instagram content detected in message: {username} on #{channel} in "{guild}": {user_message}')
        if (isPinged == False):
            print("Putting a download reaction emoji")
            await message.add_reaction("⏬")
        else:
            instagram_regex = r"(?P<url>https?://(www\.)?instagram\.com/(p|reel)/[a-zA-Z0-9-_]+)"
            matches = re.finditer(instagram_regex, user_message)
            for match in matches:
                instagram_link = match.group('url')
                editMessage = await message.channel.send(f'<Instagram post detected! Processing Instagram link: {instagram_link}>')
                
                if (killSwitch == True):
                    await failedToGetVideoKillSwitch(message, username, editMessage, True)
                    return
                
                if (consecutiveFailedJobs >= 2):
                    await failedToGetVideoKillSwitch(message, username, editMessage, False)
                    return
                
                parsed_url = urlparse(instagram_link)

                if parsed_url.path.startswith('/reel'):
                    isReel = True
                elif parsed_url.path.startswith('/p'):
                    isReel = False
                
                # Set the video title
                if (isReel == True):
                    ydl = yt_dlp.YoutubeDL({'outtmpl': '%(title)s-%(id)s.%(ext)s'})
                else:
                    ydl = yt_dlp.YoutubeDL({'outtmpl': '%(id)s.%(ext)s'})
                
                #post
                with ydl:
                        try:
                            result = ydl.extract_info(
                                instagram_link,
                                download=True
                            )
                        except Exception as ex:
                            await failedToGetVideo(message, username, ex, editMessage)
                
                #reel
                with ydl:
                        try:
                            result = ydl.extract_info(
                                instagram_link,
                                download=True
                            )
                            if 'entries' in result:
                                # Note: This should never happen, but just in case it does, this code is here to save it.
                                video = result['entries'][0]
                                await message.channel.send("More than one reel has been detected. Will only send the first one")
                            else:
                                video = result
                        except Exception as ex:
                            await failedToGetVideo(message, username, ex, editMessage)

                
                

async def failedToGetVideoKillSwitch(message, username, editMessage, ghostMode = True):
    await message.channel.send('I could not access the post posted by **' + username + '**. Here is some info about what went wrong:')
    if (ghostMode == True):
        await message.channel.send("||[0;31mERROR:[0m [Instagram] CoXvYm_gVBE: Requested content is not available, rate-limit reached or login required. Use --cookies, --cookies-from-browser, --username and --password, or --netrc (instagram) to provide account credentials||")
    else:
        await message.channel.send("Kill switch activated as the bot's current IP address is suspected to be blocked by Instagram. Please change the bot's IP address.")
    await incrementFailedJobCounter(editMessage)

async def failedToGetVideo(message, username, ex, editMessage):
    global consecutiveFailedJobs
    await message.channel.send('I could not access the post posted by **' + username + '**. Here is some info about what went wrong:')
    template = "||{0}||"
    errorToSend = template.format(ex)
    await message.channel.send(errorToSend)
    consecutiveFailedJobs = consecutiveFailedJobs + 1
    await incrementFailedJobCounter(editMessage)

async def compress_video(filepath):
    if platform.system() == "Windows":
        output = await asyncio.create_subprocess_exec("discord-video.bat", filepath,stdout=asp.PIPE, stderr=asp.STDOUT,)
        await output.stdout.read()
    elif platform.system() == "Linux":
        output = await asyncio.create_subprocess_exec("bash", "discord-video.sh", filepath,stdout=asp.PIPE, stderr=asp.STDOUT,)
        await output.stdout.read()
    else:
        print("Running on unknown OS. What are you using!?")

async def AttemptToSendVideo(message, video, editMessage):
    global successfulJobs, consecutiveFailedJobs
    await message.channel.send(file=discord.File(video))
    await editMessage.delete()
    successfulJobs = successfulJobs + 1
    consecutiveFailedJobs = 0
    print(f'Successful jobs: {successfulJobs}, Failed jobs: {failedJobs}')

async def incrementFailedJobCounter(editMessage):
    global failedJobs
    await editMessage.delete()
    failedJobs = failedJobs + 1
    print(f'Successful jobs: {successfulJobs}, Failed jobs: {failedJobs}')

token = os.getenv('DISCORD_TOKEN')
client.run(token)