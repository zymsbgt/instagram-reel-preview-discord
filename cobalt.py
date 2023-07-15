# This file is the second rewrite for this bot, designed to be used with the Cobalt API. This script is on production as of May 27 2023

import discord
import requests
import os
import platform
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse
import re
import secrets
import io
import time
import asyncio
import asyncio.subprocess as asp

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

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
            try:
                tryToSendMessage = await reaction.message.channel.send(f'Attempting to start download...')
            except Exception as ex:
                await user.send("It appears that I may not have permission to send the video in the channel. Here's more info on what went wrong:")
                template = "||{0}||"
                errorToSend = template.format(ex)
                await user.send(errorToSend)
            else:
                await CreatePreview(reaction.message, tryToSendMessage)

@client.event
async def on_message(message):
    isPinged = False
    
    if message.author == client.user:
        return
    
    if (message.guild.id == 612289903769944064): # RoFT Fan Chat
        return
    
    if client.user.mentioned_in(message):
        isPinged = True
    
    TriggerLinks = ['instagram.com/reel', 'instagram.com/p', 'youtube.com/watch?v=', 'youtu.be/', 'youtube.com/shorts/']
    if any(keyword in message.content for keyword in TriggerLinks):
        if (isPinged == False):
            await message.add_reaction("⏬")
        else:
            await CreatePreview(message)

    if ('twitter.com/' in message.content):
        try:
            await secrets.CreateBirdsitePreview(message, isPinged)
        except:
            pass

async def CreatePreview(message, messageToEdit = None):
    try:
        DebugMode = False
        start_time = time.time()
        if (message.guild.id == 443253214859755522):
            DebugMode = True
        
        TriggerLinks = ['instagram.com/reel', 'instagram.com/p', 'youtube.com/watch?v=', 'youtu.be/', 'youtube.com/shorts/']
        urls = []

        # Splitting the message content by whitespace to extract potential links
        words = message.content.split()
        print(words)

        for word in words:
            print(word)
            if any(keyword in word for keyword in TriggerLinks):
                urls.append(word)

        if not urls:
            await message.channel.send("**Content Downloader Worker:** I could not find any links in your message")
            return
    
        print(f"{message.author.name} in #{message.channel.name} in guild {message.guild.name}: {message.content}")

        for url in urls:
            if messageToEdit == None:
                editMessage = await message.channel.send(f"URL found: {url}")
            else:
                editMessage = messageToEdit
                await editMessage.edit(content=f"URL found: {url}")
            parsed_url = urlparse(url)
            url_without_query = urlunparse(parsed_url._replace(query=''))
            await editMessage.edit(content=f"Formatted URL: {url_without_query}. Waiting for Cobalt to reply...")

            response = await SendRequestToCobalt(url, editMessage, message)

            if (response == None):
                await editMessage.delete()
                return
            else:
                response_data = response.json()
                response_code = response.status_code
                response_status = response_data.get("status")

                video_url = response_data.get("url")

                print("Successfully got video url:" + video_url)
                await editMessage.edit(content=f"Successfully got video url:<{video_url}>\nDownloading video now...")
                if (response_status == "stream"):
                    InfoMessage = await UploadVideoStream(message, editMessage, DebugMode, video_url)
                else:
                    InfoMessage = await UploadVideo(message, editMessage, DebugMode, video_url)
                end_time = time.time()
                execution_time = end_time - start_time
                execution_time_rounded = round(execution_time, 1)
                print(f"Job complete! ({execution_time_rounded}s)")
                if (InfoMessage != None):
                    await InfoMessage.edit(content=f"**Debug:** Video request from **{message.author.name}** ({execution_time_rounded}s)")
            await editMessage.delete()
    except Exception as e:
        await message.channel.send(f"Error occured: {e}")

async def ProcessVideoCompression(editMessage, message, filepath):
    if os.path.exists(filepath + '-compressed.mp4'):
        if (filepath != 'video-compressed.mp4'):
            await editMessage.edit(content=f'Found compressed video in cache! Uploading it...')
    elif os.path.exists(filepath + '-compressing.mp4'):
        await message.channel.send(f'This video has already been requested and is now processing. Please try again later')
        await editMessage.delete()
        return True
    else:                                   
        await compressVideo(message, filepath)
        await editMessage.edit(content=f'Uploading compressed video...')
    return False

async def compressVideo(message, filepath):
    timeElapsed2 = time.time()
    if platform.system() == "Windows":
        output = await asyncio.create_subprocess_exec("discord-video.bat", filepath,stdout=asp.PIPE, stderr=asp.STDOUT,)
        await output.stdout.read()
    elif platform.system() == "Linux":
        output = await asyncio.create_subprocess_exec("bash", "discord-video.sh", filepath,stdout=asp.PIPE, stderr=asp.STDOUT,)
        await output.stdout.read()
    else:
        print("Compression failed as the script is running on unknown OS. What are you using!?")
    if (os.path.exists(filepath + '-compressed.mp4') == False):
        print("Compression process was complete, but output file is absent! It is likely that compression did not succeed.")
        await message.channel.send("**Warning**: Compression process was complete, but output file is absent! It is likely that compression did not succeed.")
    timeElapsed2 = time.time()-timeElapsed2
    print(f'Compression finished! Time elapsed: {timeElapsed2} seconds')

async def UploadVideoStream(message, editMessage, DebugMode, video_url):
    video_response = requests.get(video_url, stream=True)
    filename = "video.mp4"
    content_disposition = video_response.headers.get('Content-Disposition')
    if content_disposition is not None:
        filename = re.search('filename="(.+)"', content_disposition)[1]

    with open(filename, "wb") as file:
        for chunk in video_response.iter_content(chunk_size=1024):
            if chunk:
                file.write(chunk)
    
    file_size_bytes = os.path.getsize(filename)
    file_size_mb = file_size_bytes / (1024 * 1024)

    # Upload the video to Discord
    if (DebugMode == True):
        InfoMessage = await message.channel.send(f"**Debug:** Video request from **{message.author.name}**")
    if file_size_mb <= 25:
        await editMessage.edit(content=f"Download success! Uploading video now...")
        try:
            await message.channel.send(file=discord.File(filename))
        except:
            await editMessage.edit(content=f"Upload failed! Compressing video...")
            if (await ProcessVideoCompression(editMessage, message, filename) == True):
                return
            filename = filename + '-compressed.mp4'
            try:
                await message.channel.send(file=discord.File(filename))
            except:
                await message.channel.send("**Error**: Could not upload video")
    else:
        await editMessage.edit(content=f"Download successful, but video is above filesize limit. Compressing video...")
        if (await ProcessVideoCompression(editMessage, message, filename) == True):
            return
        filename = filename + '-compressed.mp4'
        try:
            await message.channel.send(file=discord.File(filename))
        except:
            await message.channel.send("**Error**: Could not upload video")

    # Comment this line if you would prefer to have a caching system that I inefficiently built. I didn't like how it turned out.
    os.remove(filename)

    if (DebugMode == True):
        return InfoMessage
    else:
        return None

async def UploadVideo(message, editMessage, DebugMode, video_url):
    video_response = requests.get(video_url)
    video_bytes = video_response.content
    video_bytes_io = io.BytesIO(video_bytes)

    # Check the file size
    video_bytes_io.seek(0, io.SEEK_END)  # Move the file pointer to the end of the buffer
    file_size_bytes = video_bytes_io.tell()  # Get the current position, which represents the file size in bytes
    file_size_mb = file_size_bytes / (1024 * 1024)  # Convert bytes to megabytes

    if (DebugMode == True):
        InfoMessage = await message.channel.send(f"**Debug:** Video request from **{message.author.name}**")
    if file_size_mb <= 25:
        # File size is below or equal to 25MB, send the video on Discord
        video_bytes_io.seek(0)  # Reset the file pointer to the beginning of the buffer
        await editMessage.edit(content=f"Download success! Uploading video now...")
        filename = "video.mp4"
        content_disposition = video_response.headers.get('Content-Disposition')
        if content_disposition is not None:
            filename = re.search('filename="(.+)"', content_disposition)[1]
        
        try:
            await message.channel.send(file=discord.File(video_bytes_io, filename=filename))
        except:
            await editMessage.edit(content=f"Upload failed! Sending video link instead...")
            await message.channel.send(video_url)
    else:
        await editMessage.edit(content=f"Download successful, but video is above filesize limit. Sending video link instead...")
        await message.channel.send(video_url)
    if (DebugMode == True):
        return InfoMessage
    else:
        return None

async def SendRequestToCobalt(url, editMessage, message):
    cobalt_url = [
        "nl-co.wuk.sh",
        "nl2-co.wuk.sh",
        "nl3-co.wuk.sh",
        #"co.wuk.sh",
        "cobalt.fluffy.tools",
        "toro.cobalt.synzr.ru",
        "co.de4.nodes.geyser.host",
        "cobalt.bobby99as.me"
        ]
    errorLogs = []
    headers = {"Accept": "application/json"}
    params = {'url': url}
    ServerCount = 0 # Do not change. This serves as a counter for the program.
    MaxServerCount = len(cobalt_url)

    while True:
        if ServerCount >= MaxServerCount:
            return None
        
        CobaltServerToUse = "https://" + cobalt_url[ServerCount] + "/api/json"
        # Add code here to timeout the request after 30s?
        response = requests.post(CobaltServerToUse, headers=headers, json=params)
        response_data = response.json()
        response_code = response.status_code

        if (200 <= response_code < 300):
            return response
        elif (400 <= response_code < 599):
            response_status = response_data.get("status")
            response_text = response_data.get("text")
            await message.channel.send(f"**{cobalt_url[ServerCount]}**: {response_code} {response_status}:\n{response_text}.")
            await editMessage.edit(content=f"Trying another server...")
        else:
            await editMessage.edit(content=f"**{cobalt_url[ServerCount]}** returned an unknown response code")
        ServerCount += 1

async def SendLargeMediaHandler(message, video_url, response_status):
    if (response_status == "stream"):
        await message.channel.send(f"**Error:** Cobalt server returned `stream` status, expected `success` or `redirect`")
    else:
        await message.channel.send(video_url)

token = os.getenv('DISCORD_TOKEN')
client.run(token)