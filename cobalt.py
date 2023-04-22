# This file is the second rewrite for this bot, designed to be used with the Cobalt API. This script is still a work in progress.

import discord
import requests
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

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

    if "instagram.com" in message.content:
        url = message.content

        headers = {
            "Accept": "application/json"
        }

        params = {
            'url': url,
            'vCodec': 'h264',
            'vQuality': '720',
            'aFormat': 'mp3',
            'isAudioOnly': 'false',
            'isNoTTWatermark': 'false',
            'isTTFullAudio': 'false',
            'isAudioMuted': 'false',
            'dubLang': 'false'
        }

        response = requests.post(cobalt_url, headers=headers, json=params)

        if response.status_code == 200 and response.json().get("status") == "success":
            video_url = response.json().get("url")
            await message.channel.send(video_url)
        else:
            print(response.json().get("text"))

token = os.getenv('DISCORD_TOKEN')
client.run(token)