# This file is the second rewrite for this bot, designed to be used with the Cobalt API. This script is on production as of May 27 2023

import discord
import requests
import os
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse
import re
import secrets
import io
import time

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
                await CreateInstaReelPreview(reaction.message, tryToSendMessage)

@client.event
async def on_message(message):
    isPinged = False
    
    if message.author == client.user:
        return
    
    if (message.guild.id == 612289903769944064): # RoFT Fan Chat
        return
    
    if client.user.mentioned_in(message):
        isPinged = True
    
    TriggerLinks = ['instagram.com/reel', 'instagram.com/p']
    if any(keyword in message.content for keyword in TriggerLinks):
        if (isPinged == False):
            await message.add_reaction("⏬")
        else:
            await CreateInstaReelPreview(message)
    
    if ('twitter.com/' in message.content):
        try:
            await secrets.CreateBirdsitePreview(message, isPinged)
        except:
            pass

async def CreateInstaReelPreview(message, messageToEdit = None):
    try:
        DebugMode = False
        start_time = time.time()
        print(message.guild.id)
        if (message.guild.id == 443253214859755522):
            DebugMode = True
        
        IGLinks = ['instagram.com/reel', 'instagram.com/p']
        urls = []

        # Splitting the message content by whitespace to extract potential links
        words = message.content.split()

        for word in words:
            if any(keyword in word for keyword in IGLinks):
                urls.append(word)

            if not urls:
                await message.channel.send("**Content Downloader Worker:** I could not find any links in your message")
                return

        # if any(keyword in message.content for keyword in IGLinks):
            ## This doesn't work for whatever reason anymore. Just returns an empty string even with IG links present
            # urls = re.findall(r"(https?://(?:www\.)?instagram\.com/(?:p|reel)/\S+)", message.content)
            # if not urls:
            #     await message.channel.send("**Content Downloader Worker:** I could not find any links in your message")
            #     if messageToEdit != None:
            #         await messageToEdit.delete()
            #     return

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

                    video_url = response_data.get("url")

                    print("Successfully got video url:" + video_url)
                    await editMessage.edit(content=f"Successfully got video url:<{video_url}>\nDownloading video now...")

                    video_response = requests.get(video_url)
                    video_bytes = video_response.content
                    video_bytes_io = io.BytesIO(video_bytes)

                    # Check the file size
                    video_bytes_io.seek(0, io.SEEK_END)  # Move the file pointer to the end of the buffer
                    file_size_bytes = video_bytes_io.tell()  # Get the current position, which represents the file size in bytes
                    file_size_mb = file_size_bytes / (1024 * 1024)  # Convert bytes to megabytes

                    if (DebugMode == True):
                        InfoMessage = await message.channel.send(f"**Debug:** Instagram request from **{message.author.name}**")
                    if file_size_mb <= 25:
                        # File size is below or equal to 25MB, send the video on Discord
                        video_bytes_io.seek(0)  # Reset the file pointer to the beginning of the buffer
                        await editMessage.edit(content=f"Download success! Uploading video now...")
                        
                        try:
                            await message.channel.send(file=discord.File(video_bytes_io, filename="video.mp4"))
                        except:
                            await editMessage.edit(content=f"Upload failed! Sending video link instead...")
                            await message.channel.send(video_url)
                    else:
                        await editMessage.edit(content=f"Download successful, but video is above filesize limit. Sending video link instead...")
                        await message.channel.send(video_url)
                    end_time = time.time()
                    execution_time = end_time - start_time
                    execution_time_rounded = round(execution_time, 1)
                    print(f"Job complete! ({execution_time_rounded}s)")
                    await InfoMessage.edit(content=f"**Debug:** Instagram request from **{message.author.name}** ({execution_time_rounded}s)")
                
                await editMessage.delete()
    except Exception as e:
        await message.channel.send(f"Error occured: {e}")

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

token = os.getenv('DISCORD_TOKEN')
client.run(token)