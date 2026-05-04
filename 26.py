# This file is the fourth rewrite of this bot from the ground up to make ZymBot able to make better use of both Cobalt and yt-dlp.
# This script is currently not ready for production usage

import discord
from discord import app_commands
import requests
import os
import platform
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse
import re
import secrets
import io
import time
import aiohttp
import asyncio
import asyncio.subprocess as asp
import json
import boto3
from botocore.exceptions import ClientError
import random
import yt_dlp

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

services = {
    "Instagram": ("Cobalt", ["instagram.com/reel", "instagram.com/p/"]),
    "YouTube":   ("Cobalt", ["youtube.com/watch?v=", "youtu.be/", "youtube.com/shorts/"]),
    "TikTok":    ("Cobalt", ["tiktok.com/"]),
    "X":         ("Cobalt", ["twitter.com/", "x.com/"]),
    "SoundCloud":("Cobalt", ["soundcloud.com/"]),
    "Bilibili":  ("Cobalt", ["bilibili.com/", "bilibili.tv/"]),
    "Dailymotion":("Cobalt", ["dailymotion.com/"]),
    "Pinterest": ("Cobalt", ["pinterest.com"]),
    "Reddit":    ("Cobalt", ["reddit.com/"]),
    "Streamable":("Cobalt", ["streamable.com/"]),
    "Tumblr":    ("Cobalt", ["tumblr.com/"]),
    "Twitch":    ("Cobalt", ["twitch.tv/"]),
    "Bluesky":   ("Cobalt", ["bsky.app/"]),
    "Xiaohongshu":("Cobalt", ["xiaohongshu.com/"]),
    "Newgrounds":("Cobalt", ["newgrounds.com."]),
    "Facebook":  ("Cobalt", ["facebook.com/"]),
    "Medal":     ("YtDlp",  ["medal.tv/"]),
    "Odysee":    ("YtDlp",  ["odysee.com/"])
}
# derive a flat list of substrings used to detect links
TriggerLinks = []
for svc, (_, substrings) in services.items():
    TriggerLinks.extend(substrings)
# optional: remove duplicates
TriggerLinks = list(dict.fromkeys(TriggerLinks))


@client.event
async def on_ready():
    await tree.sync()
    servers = client.guilds
    print("Servers I'm currently in:")
    for server in servers:
        print(server.name)
    print('server successfully started as {0.user}'.format(client))

@client.event
async def on_raw_reaction_add(payload):
    if payload.user_id == client.user.id:
        return

    channel = await client.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    user = await client.fetch_user(payload.user_id)

    # normalize emoji string for comparison
    added_emoji = payload.emoji.name  # unicode emoji name or custom name
    # check if message already has a reaction with .me True for this emoji
    for reaction in message.reactions:
        try:
            if str(reaction.emoji) == added_emoji and reaction.me:
                # only respond to specific unicode emoji names (🎬 🎵 👀)
                if added_emoji in ("🎬", "🎵", "👀"):
                    try:
                        tryToSendMessage = await channel.send("Starting download...")
                    except Exception as ex:
                        await user.send("It appears that I do not have permission to send the video in the channel. Here's more info on what went wrong:")
                        await user.send(f"||{ex}||")
                        return
                    if added_emoji == "🎬":
                        await CreatePreview(message, tryToSendMessage, user)
                    elif added_emoji == "🎵":
                        await CreatePreview(message, tryToSendMessage, user, AudioOnly=True)
                break
        except Exception:
            continue

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if "@everyone" in message.content or "@here" in message.content:
        return

    isPinged = client.user.mentioned_in(message)
    foundAnyLinks = False

    content = message.content.lower()

    # find any service substrings in message
    for svc_name, (backend, substrings) in services.items():
        for sub in substrings:
            if sub.lower() in content:
                foundAnyLinks = True

                # If bot was pinged or DM, create preview
                if isPinged or message.guild is None:
                    await CreatePreview(message)
                    break  # stop checking substrings for this service

                # guild-specific special cases
                if message.guild:
                    if message.guild.id == 612289903769944064:
                        # only add soundcloud reaction in that guild
                        if "soundcloud.com/" in sub:
                            await message.add_reaction("🎵")
                        break
                    if message.guild.id == 883295230441451552:
                        break

                # if this substring is for soundcloud -> only audio react
                if "soundcloud.com/" in sub:
                    await message.add_reaction("🎵")
                    break

                # default: add both
                await message.add_reaction("🎬")
                await message.add_reaction("🎵")
                break
        if foundAnyLinks and (isPinged or message.guild is None):
            # preview already created; continue scanning only to set foundAnyLinks
            continue

    # exact mention triggers when no links found
    if not foundAnyLinks:
        mention_forms = {f"<@{client.user.id}>", f"<@!{client.user.id}>"}
        mention_forms_audio = {
            f"<@{client.user.id}> audioonly", f"<@!{client.user.id}> soundonly",
            f"<@{client.user.id}> audio", f"<@!{client.user.id}> sound",
            f"<@!{client.user.id}> music"
        }
        cont = message.content.strip().lower()
        if cont in mention_forms or cont in mention_forms_audio:
            if message.reference and isinstance(message.reference.resolved, type(message)):
                referenced = message.reference.resolved
                ref_content = (referenced.content or "").lower()
                for sub in TriggerLinks:
                    if sub.lower() in ref_content:
                        # decide audio flag
                        audio_only = cont in mention_forms_audio
                        # if author same/different handle user param accordingly
                        target_user = referenced.author if referenced.author == message.author else message.author
                        await CreatePreview(referenced, None, target_user if referenced.author != message.author else None, AudioOnly=audio_only)
                        break