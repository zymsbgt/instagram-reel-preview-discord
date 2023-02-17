import discord
from urllib.parse import urlparse
import yt_dlp
import ffmpeg
import os
import platform
import subprocess
from dotenv import load_dotenv # new discord bot token library
import asyncio
import asyncio.subprocess as asp
#import pycurl

discordFileSizeLimit = 8000000
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

successfulJobs = 0
failedJobs = 0

@client.event
async def on_ready():
    servers = client.guilds
    print("Servers I'm currently in:")
    for server in servers:
        print(server.name)
    print('server successfully started as {0.user}'.format(client))

@client.event
async def on_message(message):
    username = str(message.author).split('#')[0]
    user_message = str(message.content)
    channel = str(message.channel.name)
    guild = str(message.guild.name)
    
    if message.author == client.user:
        return
    
    if client.user.mentioned_in(message):
        print(f'Pinged in message: {username} on #{channel} in "{guild}": {user_message}')
        await message.channel.send(':wave:')
    
    if 'instagram.com' in message.content:
        global successfulJobs, failedJobs
        print(f'Instagram content detected in message: {username} on #{channel} in "{guild}": {user_message}')
        await message.add_reaction("⏬")
        cleanedMessage = message.content.replace("<", "")
        cleanedMessage = cleanedMessage.replace(">", "")
        
        parsed_url = urlparse(cleanedMessage)
        if parsed_url.path.startswith('/reel'):
            ydl = yt_dlp.YoutubeDL({'outtmpl': '%(title)s-%(id)s.%(ext)s'})
            
            with ydl:
                print("Parsed URL: " + parsed_url.path)
                try:
                    result = ydl.extract_info(
                        'https://www.instagram.com' + parsed_url.path,
                        download=True
                    )
                    if 'entries' in result:
                        # Note: This should never happen, but just in case it does, this code is here to save it.
                        video = result['entries'][0]
                        await message.channel.send("More than one reel has been detected. Will only send the first one")
                    else:
                        video = result
                except Exception as ex:
                    await failedToGetVideo(message, username, ex)
                else:
                    print(f'Instagram reel: {video["title"]} has been downloaded!')
                    filepath = video["title"] + "-" + video["id"] +  "." + video["ext"]

                    print(f"The filesize of the video is {os.path.getsize(filepath)}bytes")

                    with open(filepath, "rb") as video:
                        try:
                            await AttemptToSendVideo(message, video)
                        except:
                            if os.path.getsize(filepath) >= discordFileSizeLimit:
                                if os.path.exists(filepath + '-compressed.mp4'):
                                    pass
                                elif os.path.exists(filepath + '-compressing.mp4'):
                                    await message.channel.send('This reel has already been requested and is now processing. Please try again later')
                                    print('Post is already being compressed')
                                    return
                                else:
                                    await message.channel.send('Instagram reel posted by **' + username + '** was too large to upload. Will attempt to compress. (filesize: ' + str(os.path.getsize(filepath)) + ' bytes)')
                                    await compress_video(filepath)
                                filepath = filepath + '-compressed.mp4'

                                with open(filepath, "rb") as video:
                                    try:
                                        await message.channel.send('Instagram reel posted by **' + username + '** (compressed filesize: ' + str(os.path.getsize(filepath)) + ' bytes)')
                                        await AttemptToSendVideo(message, video)
                                    except:
                                        await message.channel.send("Something went wrong while uploading the reel onto discord :sweat:")
                                        incrementFailedJobCounter()
                            else:
                                await message.channel.send("Something went wrong while uploading the reel onto discord :sweat:")
                                incrementFailedJobCounter()
        
        if parsed_url.path.startswith('/p'):
            ydl = yt_dlp.YoutubeDL({'outtmpl': '%(id)s.%(ext)s'})
            
            with ydl:
                print("Parsed URL: " + parsed_url.path)
                try:
                    result = ydl.extract_info(
                        'https://www.instagram.com' + parsed_url.path,
                        download=True
                    )
                except Exception as ex:
                    await failedToGetVideo(message, username, ex)
                else:
                    print(f'Instagram post has been downloaded!')
                    if 'entries' in result:
                        videoList = result['entries']
                        index = 1
                        for i in videoList:
                            video = i
                            filepath = video["id"] + "." + video["ext"]
                            print(f"The filesize of the video is {os.path.getsize(filepath)}bytes")
                            if os.path.getsize(filepath) >= discordFileSizeLimit:
                                if os.path.exists(filepath + '-compressed.mp4'):
                                    pass
                                elif os.path.exists(filepath + '-compressing.mp4'):
                                    await message.channel.send('This post has already been requested and is now processing. Please try again later')
                                    print('Post is already being compressed')
                                    return
                                else:
                                    await message.channel.send('Instagram post number **' + str(index) + '** was too large to upload. Will attempt to compress. (filesize: ' + str(os.path.getsize(filepath)) + ' bytes)')
                                    await compress_video(filepath)
                                filepath = filepath + '-compressed.mp4'

                            with open(filepath, "rb") as video:
                                await message.channel.send('Instagram post #' + str(index) + ' posted by **' + username + '** (filesize: ' + str(os.path.getsize(filepath)) + ' bytes)')
                                try:
                                    await AttemptToSendVideo(message, video)
                                except:
                                    await message.channel.send("Something went wrong while uploading post #" + str(index) +" onto discord :sweat:")
                                    incrementFailedJobCounter()
                            index += 1

                    else:
                        video = result
                        filepath = video["id"] +  "." + video["ext"]
                        print(f"The filesize of the video is {os.path.getsize(filepath)}bytes")

                    with open(filepath, "rb") as video:
                        try:
                            await AttemptToSendVideo(message, video)
                        except:
                            if os.path.getsize(filepath) >= discordFileSizeLimit:
                                if os.path.exists(filepath + '-compressed.mp4'):
                                    pass
                                elif os.path.exists(filepath + '-compressing.mp4'):
                                    await message.channel.send('This reel has already been requested and is now processing. Please try again later')
                                    print('Post is already being compressed')
                                    return
                                else:
                                    await message.channel.send('Instagram reel posted by **' + username + '** was too large to upload. Will attempt to compress. (filesize: ' + str(os.path.getsize(filepath)) + ' bytes)')                                    
                                    await compress_video(filepath)
                                filepath = filepath + '-compressed.mp4'

                                with open(filepath, "rb") as video:
                                    try:
                                        await message.channel.send('Instagram reel posted by **' + username + '** (compressed filesize: ' + str(os.path.getsize(filepath)) + ' bytes)')
                                        await AttemptToSendVideo(message, video)
                                    except:
                                        await message.channel.send(f"Something went wrong while uploading the reel onto discord :sweat:")
                                        incrementFailedJobCounter()
                            else:
                                await message.channel.send(f"Something went wrong while uploading the reel onto discord :sweat:")
                                incrementFailedJobCounter()
        else:
            print("Not a valid Instagram post or reel")

@client.event
async def on_reaction_add(reaction, user):
    if user == client.user:
        return

    for reaction in reaction.message.reactions:
        if reaction.me:
            # await user.send("You reacted with the same emoji as the bot!") # this is for DMing the person who reacted
            await reaction.message.channel.send("You reacted with the same emoji as the bot!")



async def failedToGetVideo(message, username, ex):
    await message.channel.send('I could not access the post posted by **' + username + '**. Here is some info about what went wrong:')
    template = "||{0}||"
    errorToSend = template.format(ex)
    await message.channel.send(errorToSend)
    await incrementFailedJobCounter()

async def compress_video(filepath):
    if platform.system() == "Windows":
        output = await asyncio.create_subprocess_exec("discord-video.bat", filepath,stdout=asp.PIPE, stderr=asp.STDOUT,)
        await output.stdout.read()
    elif platform.system() == "Linux":
        output = await asyncio.create_subprocess_exec("bash", "discord-video.sh", filepath,stdout=asp.PIPE, stderr=asp.STDOUT,)
        await output.stdout.read()
    else:
        print("Running on unknown OS. What are you using!?")

async def AttemptToSendVideo(message, video):
    global successfulJobs
    await message.channel.send(file=discord.File(video))
    successfulJobs = successfulJobs + 1
    print(f'Successful jobs: {successfulJobs}, Failed jobs: {failedJobs}')

def incrementFailedJobCounter():
    global failedJobs
    failedJobs = failedJobs + 1
    print(f'Successful jobs: {successfulJobs}, Failed jobs: {failedJobs}')

token = os.getenv('DISCORD_TOKEN')
client.run(token)