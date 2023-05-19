# This file is the second rewrite for this bot, designed to be used with the Cobalt API. This script is still a work in progress.

import discord
import requests
import os
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse
import re

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

cobalt_url = "https://co.wukko.me/api/json"

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
    
    if client.user.mentioned_in(message):
        isPinged = True
    
    if ('instagram.com/p' in message.content) or ('instagram.com/reel' in message.content):
        if (isPinged == False):
            await message.add_reaction("⏬")
        else:
            await CreatePreview(message)

async def CreatePreview(message, messageToEdit = None):
    if message.author == client.user:
        return

    IGPostLinks = ['instagram.com/p', 'instagram.com/reel']
    if any(keyword in message.content for keyword in IGPostLinks):
        urls = re.findall(r'(https?://(?:www\.)?instagram\.com/(?:p|reel)/\S+)', message.content)
        if not urls:
            return

        for url in urls:
            if messageToEdit == None:
                editMessage = await message.channel.send(f"URL found: {url}")
            else:
                editMessage = messageToEdit
                await editMessage.edit(content=f"URL found: {url}")
            parsed_url = urlparse(url)
            url_without_query = urlunparse(parsed_url._replace(query=''))
            await editMessage.edit(content=f"Formatted URL: {url_without_query}. Sending to Cobalt now...")

            headers = {
                "Accept": "application/json"
            }

            params = {
                'url': url
            }

            try:
                response = requests.post(cobalt_url, headers=headers, json=params)
                # response = requests.post(cobalt_url, headers=headers)
                response.raise_for_status()
                response_data = response.json()
                response_code = response.status_code
                response_status = response_data.get("status")

                if (response_status == "redirect"): # Instagram download requests will always be responded with a "redirect"
                    await editMessage.edit(content=f"Success! Posting link now...")
                    video_url = response_data.get("url")
                    await message.channel.send(video_url)
                    # Replace this section soon with downloading the video itself, and then uploading the media onto the discord channel
                else:
                    response_text = response_data.get("text")
                    await message.channel.send(f"**Error:** Failed to download video. The download server sent the following message:\n{response_code} {response_status} {response_text}")
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                await message.channel.send("**Error:** Something went wrong while making the request.")
            except ValueError as e:
                print(f"JSON decoding error: {e}")
                await message.channel.send("**Error:** Something went wrong while decoding the server response.")
            
            await editMessage.delete()

token = os.getenv('DISCORD_TOKEN')
client.run(token)