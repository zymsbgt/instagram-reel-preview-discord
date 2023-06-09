# This file is the second rewrite for this bot, designed to be used with the Cobalt API. This script is on production as of May 27

import discord
import requests
import os
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse
import re
import secrets
import io

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

cobalt_url = "https://co.wuk.sh/api/json"

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
    
    if client.user.mentioned_in(message):
        isPinged = True
    
    if (('instagram.com/reel' in message.content) or ('instagram.com/p' in message.content)):
        if (isPinged == False):
            await message.add_reaction("⏬")
        else:
            await CreateInstaReelPreview(message)
    
    if ('twitter.com/' in message.content):
        await secrets.CreateBirdsitePreview(message, isPinged)

async def CreateInstaReelPreview(message, messageToEdit = None):
    IGLinks = ['instagram.com/reel', 'instagram.com/p']
    if any(keyword in message.content for keyword in 'instagram.com/reel'):
        urls = re.findall(r'(https?://(?:www\.)?instagram\.com/(?:p|reel)/\S+)', message.content)
        if not urls:
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

            headers = {
                "Accept": "application/json"
            }

            params = {
                'url': url
            }

            try:
                response = requests.post(cobalt_url, headers=headers, json=params)
                response.raise_for_status()
                response_data = response.json()
                response_code = response.status_code
                response_status = response_data.get("status")

                if (response_code == requests.codes.ok): # Instagram download requests will always be responded with a "redirect"
                    await editMessage.edit(content=f"Success! Downloading video now...")
                    video_url = response_data.get("url")
                    video_response = requests.get(video_url)
                    video_bytes = video_response.content
                    video_bytes_io = io.BytesIO(video_bytes)

                    # Check the file size
                    video_bytes_io.seek(0, io.SEEK_END)  # Move the file pointer to the end of the buffer
                    file_size_bytes = video_bytes_io.tell()  # Get the current position, which represents the file size in bytes
                    file_size_mb = file_size_bytes / (1024 * 1024)  # Convert bytes to megabytes

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
                    print("Job complete!")
                else:
                    response_text = response_data.get("text")
                    await message.channel.send(f"**Error:** Failed to download video. The download server sent the following message:\n{response_code} {response_status} {response_text}")
                    print(f"Job failed: {response_code} {response_status} {response_text}")
            except requests.exceptions.RequestException as e:
                await message.channel.send(f"**Request error:** {e}")
                print(f"Request error: {e}")
            except ValueError as e:
                await message.channel.send(f"JSON decoding error: {e}")
                print(f"JSON decoding error: {e}")
            
            await editMessage.delete()

token = os.getenv('DISCORD_TOKEN')
client.run(token)