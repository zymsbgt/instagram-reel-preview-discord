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
async def on_message(message):
    if message.author == client.user:
        return

    IGPostLinks = ['instagram.com/p', 'instagram.com/reel']
    if any(keyword in message.content for keyword in IGPostLinks):
        urls = re.findall(r'(https?://(?:www\.)?instagram\.com/(?:p|reel)/\S+)', message.content)
        if not urls:
            return

        for url in urls:
            editMessage = await message.channel.send(f"URL found: {url}")
            parsed_url = urlparse(url)
            url_without_query = urlunparse(parsed_url._replace(query=''))
            await editMessage.edit(content=f"Formatted URL: {url_without_query}. Sending to Cobalt now...")

            headers = {
                "Accept": "application/json"
            }

            params = {
                'url': url,
                'vCodec': 'h264',
                'vQuality': '720',
                'aFormat': 'best',
                'isAudioOnly': 'false',
                'isNoTTWatermark': 'false',
                'isTTFullAudio': 'false',
                'isAudioMuted': 'false',
                'dubLang': 'false'
            }

            try:
                response = requests.post(cobalt_url, headers=headers, json=params)
                response.raise_for_status()
                response_data = response.json()

                if (response_data.get("status") == "success" or response_data.get("status") == "stream"):
                    video_url = response_data.get("url")
                    await message.channel.send(video_url)
                else:
                    print(response_data.get("status"))
                    response_text = response_data.get("text")
                    await message.channel.send(f"**Error:** Failed to download video. The download server sent the following message:\n{response_text}")
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                await message.channel.send("**Error:** Something went wrong while making the request.")
            except ValueError as e:
                print(f"JSON decoding error: {e}")
                await message.channel.send("**Error:** Something went wrong while decoding the server response.")
            
            await editMessage.delete()

token = os.getenv('DISCORD_TOKEN')
client.run(token)