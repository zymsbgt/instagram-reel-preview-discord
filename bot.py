# This file is for a complete rewrite of the bot. Production ready.

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
import glob
import time
#import pycurl

discordFileSizeLimit = 8000000
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

successfulJobs = 0
failedJobs = 0
consecutiveFailedJobs = 0

async def timeTakenToCompleteJob(func):
    async def wrapper(*args, **kwargs):
        t1 = time.time()
        await func(*args, **kwargs)
        t2 = time.time()-t1
        print(f'The job took {t2} seconds to complete')
    return wrapper

async def timeTakenToCompressVideo(func):
    async def wrapper(*args, **kwargs):
        t1 = time.time()
        await func(*args, **kwargs)
        t2 = time.time()-t1
        print(f'The video took {t2} seconds to compress')
    return wrapper

@client.event
async def on_ready():
    servers = client.guilds
    print("Servers I'm currently in:")
    for server in servers:
        print(server.name)
    print('server successfully started as {0.user}'.format(client))

@client.event
async def on_reaction_add(reaction, user):
    username = str(reaction.message.author).split('#')[0]
    user_message = str(reaction.message.content)
    channel = str(reaction.message.channel)
    guild = str(reaction.message.guild.name)

    if user == client.user:
        return

    for reaction in reaction.message.reactions:
        if reaction.me:
            # await user.send("You reacted with the same emoji as the bot! This feature is coming soon") # this is for DMing the person who reacted
            # await reaction.message.channel.send(f"{user} reacted with the same emoji as the bot! This feature is coming soon")
            print(f'{user} reacted on message with content {user_message} in #{channel} in guild {guild}. Starting new job.')
            try:
                tryToSendMessage = await reaction.message.channel.send(f'Attempting to start job...')
            except Exception as ex:
                await user.send("It appears that I may not have permission to send the video in the channel. Here's more info on what went wrong:")
                template = "||{0}||"
                errorToSend = template.format(ex)
                await user.send(errorToSend)
            else:
                await tryToSendMessage.delete()
                await CreatePreview(reaction.message, username, user_message)

@client.event
async def on_message(message):
    username = str(message.author).split('#')[0]
    user_message = str(message.content)
    channel = str(message.channel.name)
    guild = str(message.guild.name)
    isPinged = False
    
    if message.author == client.user:
        return
    
    if client.user.mentioned_in(message):
        print(f'Pinged in message: {username} on #{channel} in "{guild}": {user_message}')
        isPinged = True
    
    if ('instagram.com/p' in message.content) or ('instagram.com/reel' in message.content):
        print(f'Instagram content detected in message: {username} on #{channel} in "{guild}": {user_message}')
        if (isPinged == False):
            print("Putting a download reaction emoji")
            await message.add_reaction("⏬")
        else:
            await CreatePreview(message, username, user_message)

#@timeTakenToCompleteJob
async def CreatePreview(message, username, user_message):
    instagram_regex = r"(?P<url>https?://(www\.)?instagram\.com/(p|reel)/[a-zA-Z0-9-_]+)"
    matches = re.finditer(instagram_regex, user_message)
    for match in matches:
        instagram_link = match.group('url')
        try:
            editMessage = await message.channel.send(f'New job: Processing Instagram link: <{instagram_link}>')
        except Exception as ex:
            # No permissions to send in channel
            # Maybe DM the user the video instead?
            return
        
        killSwitch = False # Change this value to activate/deactivate killswitch
        if (killSwitch == True):
            await failedToGetVideoKillSwitch(message, username, editMessage, True)
            return
        if (consecutiveFailedJobs >= 2):
            await failedToGetVideoKillSwitch(message, username, editMessage, False)
            return
        
        parsed_url = urlparse(instagram_link)

        if parsed_url.path.startswith('/reel/'):
            reelOrPost = "reel"
        elif parsed_url.path.startswith('/p/'):
            reelOrPost = "post"
        await editMessage.edit(content=f'New job: Processing Instagram {reelOrPost}: <{instagram_link}>')
        id = parsed_url.path.split("/")[2]
        print("id: " + id)

        # Search if there is an existing video in the catalogue
        search_pattern = "*{}*.mp4".format(id)
        await editMessage.edit(content=f'Searching local cache for {reelOrPost}...')
        matching_files = glob.glob(search_pattern)

        videoIsFromCache = False
        if len(matching_files) == 0:
            await editMessage.edit(content=f'Video not found in local cache. Fetching {reelOrPost} from Instagram...')
            if (reelOrPost == "reel"):
                ydl = yt_dlp.YoutubeDL({'outtmpl': f'%(id)s-%(title)s-{reelOrPost}.%(ext)s'})
            else:
                ydl = yt_dlp.YoutubeDL({'outtmpl': f'%(id)s-%(title)s-{reelOrPost}.%(ext)s'})
            with ydl:
                try: 
                    result = ydl.extract_info(
                            instagram_link,
                            download=True
                        )
                    await editMessage.edit(content=f'{reelOrPost} fetched from Instagram! Now uploading post...')
                    if (('entries' in result) and (reelOrPost == "reel")):
                        # Note: This should never happen, but just in case it does, this code is here to save it.
                        video = result['entries'][0]
                        await editMessage.edit(content=f"More than one {reelOrPost} has been detected. Will only send the first one")
                    else:
                        video = result
                    print(f'Instagram {reelOrPost}: {video["title"]} has been downloaded!')
                except Exception as ex:
                    await failedToGetVideo(message, username, ex, editMessage)
                    return
        else:
            videoIsFromCache = True
            filepath = matching_files[0]
            print(f'Found matching video file: {matching_files[0]}')
            # if os.path.exists(filepath + '-compressed.mp4'):
            #     filepath = filepath + '-compressed.mp4'
            # elif os.path.exists(filepath + '-compressing.mp4'):
            #     await message.channel.send(f'This {reelOrPost} has already been requested and is now processing. Please try again later')
            #     print(f'{reelOrPost} is already being compressed')
            #     await editMessage.delete()
            #     return
            await editMessage.edit(content=f'Found matching {reelOrPost}! Uploading from cache...')
            result = matching_files[0]
        
        if 'entries' in result: # If there are multiple videos in a post
            videoList = result['entries']
            index = 1
            for i in videoList:
                video = i
                if videoIsFromCache == False:
                    filepath = video["id"] + "-" + video["title"] + "-" + reelOrPost + "." + video["ext"]
                print(f"The filesize of the video is {os.path.getsize(filepath)}bytes")

                with open(filepath, "rb") as video:
                    try:
                        await AttemptToSendVideo(message, video, editMessage)
                    except:
                        if os.path.getsize(filepath) >= discordFileSizeLimit:
                            if (await ProcessVideoCompression(editMessage, reelOrPost, message, username, filepath) == True): # If true, video is already processing
                                return
                            filepath = filepath + '-compressed.mp4'

                        with open(filepath, "rb") as video:
                            await message.channel.send(f'Instagram {reelOrPost} #{str(index)} posted by **{username}** (filesize: {str(os.path.getsize(filepath))} bytes)')
                            try:
                                await editMessage.edit(content=f'Uploading compressed video (Attempt #2)...')
                                await AttemptToSendVideo(message, video, editMessage)
                            except Exception as ex:
                                await message.channel.send(f"Something went wrong while uploading the {reelOrPost} onto discord, here's what happened:")
                                template = "||{0}||"
                                errorToSend = template.format(ex)
                                await message.channel.send(errorToSend)
                                await incrementFailedJobCounter(editMessage)
                        index += 1
        else: # If there is only one video to download (can be a post or a reel)
            video = result
            if videoIsFromCache == False:
                filepath = video["id"] + "-" + video["title"] + "-" + reelOrPost + "." + video["ext"]
            print(f"The filesize of the video is {os.path.getsize(filepath)}bytes")

            with open(filepath, "rb") as video:
                try:
                    await AttemptToSendVideo(message, video, editMessage)
                except:
                    if os.path.getsize(filepath) >= discordFileSizeLimit:
                        if (await ProcessVideoCompression(editMessage, reelOrPost, message, username, filepath) == True): # If true, video is already processing
                            return
                        filepath = filepath + '-compressed.mp4'

                        with open(filepath, "rb") as video:
                            try:
                                await message.channel.send(f'Instagram reel posted by **{username}** (compressed filesize: {str(os.path.getsize(filepath))} bytes)')
                                await AttemptToSendVideo(message, video, editMessage)
                            except Exception as ex:
                                await message.channel.send(f"Something went wrong while uploading the {reelOrPost} onto discord, here's what happened:")
                                template = "||{0}||"
                                errorToSend = template.format(ex)
                                await message.channel.send(errorToSend)
                                await incrementFailedJobCounter(editMessage)
                    else:
                        await message.channel.send(f"Something went wrong while uploading the {reelOrPost} onto discord :sweat:")
                        await incrementFailedJobCounter(editMessage)



async def ProcessVideoCompression(editMessage, reelOrPost, message, username, filepath): # If this function returns true, return from the on_message event
    if os.path.exists(filepath + '-compressed.mp4'):
        await editMessage.edit(content=f'Found compressed video in cache! Uploading it... (Attempt #2)')
    elif os.path.exists(filepath + '-compressing.mp4'):
        await message.channel.send(f'This {reelOrPost} has already been requested and is now processing. Please try again later')
        print(f'{reelOrPost} is already being compressed')
        await editMessage.delete()
        return True
    else:                                   
        await editMessage.edit(content=f'Instagram {reelOrPost} posted by **{username}** was too large to upload. Will attempt to compress. (filesize: {str(os.path.getsize(filepath))} bytes)')
        await compressVideo()
        await editMessage.edit(content=f'Uploading compressed video (Attempt #2)...')
    return False

@timeTakenToCompressVideo
async def compressVideo(filepath):
    if platform.system() == "Windows":
        output = await asyncio.create_subprocess_exec("discord-video.bat", filepath,stdout=asp.PIPE, stderr=asp.STDOUT,)
        await output.stdout.read()
    elif platform.system() == "Linux":
        output = await asyncio.create_subprocess_exec("bash", "discord-video.sh", filepath,stdout=asp.PIPE, stderr=asp.STDOUT,)
        await output.stdout.read()
    else:
        print("Running on unknown OS. What are you using!?")


async def failedToGetVideoKillSwitch(message, username, editMessage, ghostMode = True):
    await message.channel.send('I could not access the post posted by **' + username + '**. Here is some info about what went wrong:')
    # await message.channel.send('All proxies have either been blocked by Instagram or are unavailable')
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