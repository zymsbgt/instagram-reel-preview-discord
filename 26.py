# This file is the fourth rewrite of this bot from the ground up to make ZymBot able to make better use of both Cobalt and yt-dlp.
# Design decisions baked into this rewrite:
#   - Strict per-service backend routing (Cobalt OR yt-dlp, no cross-fallback) via the `services` registry.
#   - Per-user anti-spam lock (`processingUsers`) released in a finally block so a crash can never lock someone out.
#   - Empty (0-byte) downloads from a Cobalt server automatically retry on the NEXT Cobalt server.
#   - Unified 8 MB origin-channel limit. Oversized handling differs by Cobalt response type:
#       * tunnel   -> ephemeral URL, useless to hand out, so upload to the higher-limit alt channel; if that fails, give up.
#       * redirect -> durable source URL, so just post it.
#   - S3 and ffmpeg compression are intentionally left out.

import discord
from discord import app_commands
import requests
import os
import platform
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse
import re
import io
import time
import aiohttp
import yt_dlp

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Service registry: name -> (backend, [url substrings that identify it])
# backend is "Cobalt" or "YtDlp". Routing is strict: a service only ever uses its assigned backend.
services = {
    "Instagram":  ("Cobalt", ["instagram.com/reel", "instagram.com/p/"]),
    "YouTube":    ("Cobalt", ["youtube.com/watch?v=", "youtu.be/", "youtube.com/shorts/"]),
    "TikTok":     ("Cobalt", ["tiktok.com/"]),
    "Twitter":    ("Cobalt", ["twitter.com/", "x.com/"]),
    "SoundCloud": ("Cobalt", ["soundcloud.com/"]),
    "Bilibili":   ("Cobalt", ["bilibili.com/", "bilibili.tv/"]),
    "Dailymotion":("Cobalt", ["dailymotion.com/"]),
    "Pinterest":  ("Cobalt", ["pinterest.com"]),
    "Reddit":     ("Cobalt", ["reddit.com/"]),
    "Streamable": ("Cobalt", ["streamable.com/"]),
    "Tumblr":     ("Cobalt", ["tumblr.com/"]),
    "Twitch":     ("Cobalt", ["twitch.tv/"]),
    "Bluesky":    ("Cobalt", ["bsky.app/"]),
    "Xiaohongshu":("Cobalt", ["xiaohongshu.com/"]),
    "Newgrounds": ("Cobalt", ["newgrounds.com/"]),
    "Facebook":   ("Cobalt", ["facebook.com/"]),
    "Medal":      ("YtDlp",  ["medal.tv/"]),
    "Odysee":     ("YtDlp",  ["odysee.com/"]),
    "Bandcamp":   ("YtDlp",  ["bandcamp.com/"])
}

# Services that only carry audio, so they offer the 🎵 reaction only (no 🎬).
AUDIO_ONLY_SERVICES = {"SoundCloud", "Bandcamp"}
# derive a flat list of substrings used to detect links
TriggerLinks = []
for svc, (_, substrings) in services.items():
    TriggerLinks.extend(substrings)
# remove duplicates while preserving order
TriggerLinks = list(dict.fromkeys(TriggerLinks))

# Discord origin-channel upload limit (non-boosted server = 8 MB).
ORIGIN_LIMIT_MB = 8

# Guild IDs with special behaviour (kept hardcoded, matching cobalt_v10.py)
DEBUG_GUILD_ID = 443253214859755522       # bot developer's server; verbose debug output
ROFT_GUILD_ID = 612289903769944064        # RoFT Fan Chat; only reacts 🎵 to SoundCloud
MONADO_GUILD_ID = 883295230441451552      # Monado server; no reactions at all

# Per-user anti-spam lock. A user id in here has a download in progress.
processingUsers = []


def detect_service(url):
    """Return (service_name, backend) for the first service whose substring matches the url, else (None, None)."""
    low = url.lower()
    for svc, (backend, substrings) in services.items():
        for sub in substrings:
            if sub.lower() in low:
                return svc, backend
    return None, None


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

    added_emoji = payload.emoji.name  # unicode emoji or custom emoji name

    # Only act on a reaction that the bot itself placed on the message.
    for reaction in message.reactions:
        if str(reaction.emoji) != added_emoji or not reaction.me:
            continue
        # 👀 is reserved/no-op (the bot never adds it, so this branch is effectively dormant)
        if added_emoji not in ("🎬", "🎵"):
            return
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
        return


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if "@everyone" in message.content or "@here" in message.content:
        return

    isPinged = client.user.mentioned_in(message)
    content = message.content.lower()

    # Collect which services appear in the message (one hit per service is enough).
    matched = []  # list of (service_name, backend, matched_substring)
    for svc_name, (backend, substrings) in services.items():
        for sub in substrings:
            if sub.lower() in content:
                matched.append((svc_name, backend, sub))
                break

    if matched:
        # Pinged or in a DM: download the whole message right away, then we're done.
        if isPinged or message.guild is None:
            await CreatePreview(message)
            return

        guild_id = message.guild.id

        # 2 Servers: only react 🎵 to SoundCloud & Bandcamp links, nothing else.
        if guild_id == ROFT_GUILD_ID or guild_id == MONADO_GUILD_ID:
            if any(svc_name in AUDIO_ONLY_SERVICES for svc_name, _, _ in matched):
                await message.add_reaction("🎵")
            return

        # General case: build the set of reactions to offer.
        wants_video = False
        wants_audio = False
        for svc_name, backend, sub in matched:
            if svc_name in AUDIO_ONLY_SERVICES:
                wants_audio = True          # audio-only service (SoundCloud, Bandcamp)
            else:
                wants_video = True          # everything else offers video...
                wants_audio = True          # ...and audio
        if wants_video:
            await message.add_reaction("🎬")
        if wants_audio:
            await message.add_reaction("🎵")
        return

    # No links found: handle the "@bot" reply trigger.
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
            if any(sub.lower() in ref_content for sub in TriggerLinks):
                audio_only = cont in mention_forms_audio
                # If the replier is downloading someone else's message, record them as the requester.
                reacted_user = None if referenced.author == message.author else message.author
                await CreatePreview(referenced, None, reacted_user, audio_only)


async def CreatePreview(message, messageToEdit=None, reactedUser=None, AudioOnly=False):
    splashMessage = splash()

    # Who is requesting this download? (the reactor if reaction-triggered, otherwise the message author)
    requester_id = reactedUser.id if reactedUser is not None else message.author.id

    # Anti-spam lock: one active download per requester.
    if requester_id in processingUsers:
        await message.channel.send("You already have a download in progress. Please wait for it to finish before requesting another.")
        return
    processingUsers.append(requester_id)
    print(f"processingUsers: {processingUsers}")

    try:
        DebugMode = False
        start_time = time.time()
        if message.guild is not None and message.guild.id == DEBUG_GUILD_ID:
            DebugMode = True

        # Extract candidate links from the message.
        urls = []
        words = message.content.split()
        for word in words:
            if any(keyword in word for keyword in TriggerLinks):
                urls.append(word)

        if not urls:
            await message.channel.send("**Content Downloader Worker:** I could not find any links in your message")
            return

        if message.guild is None:
            print(f"{message.author.name} in Direct Messages: {message.content}")
        else:
            print(f"{message.author.name} in #{message.channel.name} in guild {message.guild.name}: {message.content}")

        for url in urls:
            service_name, backend = detect_service(url)

            # Strip FixTweet / vxtwitter style mirrors, but only for Twitter links.
            if service_name == "Twitter":
                if "fxtwitter.com/" in url:
                    url = url.replace('https://fx', 'https://')
                if "vxtwitter.com/" in url:
                    url = url.replace('https://vx', 'https://')
                if "fixupx.com/" in url:
                    url = url.replace('https://fixup', 'https://')
                if "girlcockx.com/" in url:
                    url = url.replace('https://girlcock', 'https://')

            # Status message we keep editing as the job progresses.
            if messageToEdit is None:
                editMessage = await message.channel.send(f"URL found: {url}")
            else:
                editMessage = messageToEdit
                await editMessage.edit(content=f"URL found: {url}")

            parsed_url = urlparse(url)
            url_without_query = urlunparse(parsed_url._replace(query=''))

            MediaType = "Audio" if AudioOnly else "Video"

            if backend == "YtDlp":
                await editMessage.edit(content=f"Formatted URL: {url_without_query}. Processing locally using yt-dlp...\n{splashMessage}")
                await HandleYtDlp(url, editMessage, message, AudioOnly)
            else:
                await editMessage.edit(content=f"Formatted URL: {url_without_query}. Waiting for Cobalt v10 to reply...\n{splashMessage}")
                await HandleCobalt(url, editMessage, message, AudioOnly, DebugMode, reactedUser, MediaType, start_time)

            await editMessage.delete()
    except Exception as e:
        await message.channel.send(f"The following error occured while generating the video:\n{e}")
    finally:
        # Always release the lock, even if the body threw, so the user is never permanently stuck.
        if requester_id in processingUsers:
            processingUsers.remove(requester_id)
        print(f"processingUsers: {processingUsers}")


async def HandleCobalt(url, editMessage, message, AudioOnly, DebugMode, reactedUser, MediaType, start_time):
    """Run the Cobalt request/download loop, retrying on the next server when a download comes back empty."""
    server_start = 0
    while True:
        response, ServerRequestCount, errorLogs = await SendRequestToCobalt(url, editMessage, message, AudioOnly, server_start)

        if response is None:
            # No (more) servers could fulfil the request.
            if DebugMode or message.guild is None:
                await editMessage.edit(content=f"Requests to {ServerRequestCount} Cobalt servers to download the content were unsuccessful. Here's what each one of them replied:")
                if not errorLogs:
                    await message.channel.send("Could not send error logs. (errorLogs variable is empty [more likely] or missing permissions [less likely]) Check server console for details.")
                for entry in errorLogs:
                    await message.channel.send(f"{entry}")
            else:
                await editMessage.edit(content=f"Requests to {ServerRequestCount} Cobalt servers were unsuccessful. Ask the developer to check the bot console for details.\n{splash()}")
            return

        response_data = await response.json()
        response_status = response_data.get("status")
        video_url = response_data.get("url")

        print(f"Successfully got {MediaType.lower()} for url: {video_url}")
        await editMessage.edit(content=f"Successfully got {MediaType.lower()} for url!\n**Downloading {MediaType.lower()} now**\n{splash()}")
        print(f"Successfully got video/audio from url! Response status: {response_status}")

        if response_status == "tunnel":
            InfoMessage, isEmpty = await UploadVideoStream(message, editMessage, DebugMode, video_url, AudioOnly)
        elif response_status == "picker":
            await message.channel.send("Cobalt has presented multiple videos to download from. The bot developer has never encountered this, thus I do not know what to do here")
            InfoMessage, isEmpty = None, False
        else:  # redirect
            InfoMessage, isEmpty = await UploadVideo(message, editMessage, DebugMode, video_url, AudioOnly)

        if isEmpty:
            # The server handed us a 0-byte file. Skip it and try the next one.
            server_start = ServerRequestCount + 1
            await editMessage.edit(content=f"Cobalt server {ServerRequestCount} returned an empty file. Trying another server...")
            continue

        # Done. Print debug/timing info if applicable.
        execution_time_rounded = round(time.time() - start_time, 1)
        print(f"Job complete! ({execution_time_rounded}s)")
        if InfoMessage is not None:
            if reactedUser is not None and message.author.name != reactedUser.name:
                await InfoMessage.edit(content=f"**Debug Info:** {MediaType} posted from **{message.author.name}** (Requested by **{reactedUser.name}**, {ServerRequestCount + 1} Cobalt requests, {execution_time_rounded}s)")
            else:
                await InfoMessage.edit(content=f"**Debug Info:** {MediaType} posted from **{message.author.name}** ({ServerRequestCount + 1} Cobalt requests, {execution_time_rounded}s)")
        return


def splash():
    return ("This service is powered by [cobalt.tools](https://cobalt.tools). No ads, no bullshit; Best way to save what you love.\n"
            "Donate to help keep ZymBot's downloader running: https://cobalt.tools/donate")


async def upload_to_alt_channel(message, filename):
    """Upload an oversized file to the higher-limit alt channel and return its Discord CDN url, or None on failure."""
    alt_id = os.getenv('ALT_CHANNEL_ID')
    if not alt_id:
        print("ALT_CHANNEL_ID is not configured.")
        return None
    try:
        alt_id = int(alt_id)  # get_channel/fetch_channel need an int, not the raw env string
        alt_channel = client.get_channel(alt_id)
        if alt_channel is None:
            alt_channel = await client.fetch_channel(alt_id)
        label = "Direct Messages" if message.guild is None else message.guild.name
        with open(filename, 'rb') as f:
            backup_msg = await alt_channel.send(
                content=f"Media backup for {label}",
                file=discord.File(f, filename=os.path.basename(filename))
            )
        return backup_msg.attachments[0].url
    except Exception as ex:
        print(f"Alt-channel upload failed: {ex}")
        return None


async def UploadVideoStream(message, editMessage, DebugMode, video_url, AudioOnly):
    """Handle a Cobalt 'tunnel' response: stream to disk, then upload. Returns (InfoMessage, isEmpty)."""
    InfoMessage = None
    video_response = requests.get(video_url, stream=True)
    if AudioOnly:
        MediaType, filename = "Audio", "audio.mp3"
    else:
        MediaType, filename = "Video", "video.mp4"
    content_disposition = video_response.headers.get('Content-Disposition')
    if content_disposition is not None:
        match = re.search('filename="(.+)"', content_disposition)
        if match:
            filename = match[1]

    with open(filename, "wb") as file:
        for chunk in video_response.iter_content(chunk_size=1024):
            if chunk:
                file.write(chunk)

    file_size_bytes = os.path.getsize(filename)
    file_size_mb = file_size_bytes / (1024 * 1024)

    if DebugMode:
        InfoMessage = await message.channel.send(f"{MediaType} request from **{message.author.name}**")

    try:
        if file_size_bytes == 0:
            # Empty file: let the caller retry on a different server.
            return InfoMessage, True
        if file_size_mb <= ORIGIN_LIMIT_MB:
            await editMessage.edit(content="Download success! Uploading now...")
            try:
                await message.channel.send(file=discord.File(filename))
            except Exception:
                await message.channel.send("**Error**: Failed to upload uncompressed video to Discord")
        else:
            # Too big for the origin channel. The tunnel url is ephemeral, so try the higher-limit alt channel.
            await editMessage.edit(content="Download successful, but the file is above the filesize limit. Uploading to alternate channel...")
            attachment_url = await upload_to_alt_channel(message, filename)
            if attachment_url:
                await message.channel.send(f"✅ **Upload successful!**\nSince the file was over the limit, I have embedded it here: {attachment_url}")
            else:
                # tunnel url is useless to hand out, so we give up.
                await message.channel.send(f"**Error**: The file is too large to upload ({file_size_mb:.1f} MB) and the backup upload failed.")
        return InfoMessage, False
    finally:
        if os.path.exists(filename):
            os.remove(filename)


async def UploadVideo(message, editMessage, DebugMode, video_url, AudioOnly):
    """Handle a Cobalt 'redirect' response: download in memory, then upload. Returns (InfoMessage, isEmpty)."""
    InfoMessage = None
    video_response = requests.get(video_url)
    video_bytes_io = io.BytesIO(video_response.content)

    video_bytes_io.seek(0, io.SEEK_END)
    file_size_bytes = video_bytes_io.tell()
    file_size_mb = file_size_bytes / (1024 * 1024)

    if DebugMode:
        InfoMessage = await message.channel.send(f"**Debug Info:** Request from **{message.author.name}**")

    if file_size_bytes == 0:
        # Empty file: let the caller retry on a different server.
        return InfoMessage, True

    if file_size_mb <= ORIGIN_LIMIT_MB:
        video_bytes_io.seek(0)
        await editMessage.edit(content="Download success! Uploading now...")
        filename = "audio.mp3" if AudioOnly else "video.mp4"
        content_disposition = video_response.headers.get('Content-Disposition')
        if content_disposition is not None:
            match = re.search('filename="(.+)"', content_disposition)
            if match:
                filename = match[1]
        try:
            await message.channel.send(file=discord.File(video_bytes_io, filename=filename))
        except Exception:
            await editMessage.edit(content="Upload failed! Sending video link instead...")
            await message.channel.send(video_url)
    else:
        # redirect url is the durable source url, so handing it to the user is genuinely useful.
        await editMessage.edit(content="Download successful, but the file is above the filesize limit. Sending the source link instead...")
        await message.channel.send(video_url)
    return InfoMessage, False


async def SendRequestToCobalt(url, editMessage, message, AudioOnly, start_index=0):
    """Query Cobalt servers starting at start_index. Returns (response_or_None, server_index, errorLogs).

    On success, server_index is the index of the server that succeeded (resume the next attempt at index+1).
    On exhaustion, server_index equals the number of servers queried.
    """
    # YouTube / Bsky / Bilibili use a server subset that excludes COBALT_SERVER_0.
    if "youtube.com/watch?v=" in url or "youtu.be/" in url or "youtube.com/shorts/" in url or "bsky.app/" in url or "bilibili.com/" in url or "bilibili.tv/" in url:
        cobalt_servers = {
            'COBALT_SERVER_1': (os.getenv('COBALT_SERVER_1'), os.getenv('COBALT_SERVER_1_API_KEY')),
            'COBALT_SERVER_2': (os.getenv('COBALT_SERVER_2'), os.getenv('COBALT_SERVER_2_API_KEY')),
            'COBALT_SERVER_3': (os.getenv('COBALT_SERVER_3'), os.getenv('COBALT_SERVER_3_API_KEY')),
            'COBALT_SERVER_4': (os.getenv('COBALT_SERVER_4'), os.getenv('COBALT_SERVER_4_API_KEY'))
        }
    else:
        cobalt_servers = {
            'COBALT_SERVER_0': (os.getenv('COBALT_SERVER_0'), os.getenv('COBALT_SERVER_0_API_KEY')),
            'COBALT_SERVER_1': (os.getenv('COBALT_SERVER_1'), os.getenv('COBALT_SERVER_1_API_KEY')),
            'COBALT_SERVER_2': (os.getenv('COBALT_SERVER_2'), os.getenv('COBALT_SERVER_2_API_KEY')),
            'COBALT_SERVER_3': (os.getenv('COBALT_SERVER_3'), os.getenv('COBALT_SERVER_3_API_KEY')),
            'COBALT_SERVER_4': (os.getenv('COBALT_SERVER_4'), os.getenv('COBALT_SERVER_4_API_KEY'))
        }
    userAgent = f"ZymBot/46.250.233.81.rolling.release GodotEngine/4.3.stable.official {platform.system()}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": userAgent
    }

    errorLogs = []
    # Do NOT add 'disableMetadata' here; Cobalt responds with error.api.invalid_body.
    params = {
        'url': url,
        'filenameStyle': 'classic'
    }
    if AudioOnly:
        params['downloadMode'] = 'audio'

    servers_to_query = [server for server, (surl, key) in cobalt_servers.items() if surl is not None]

    ServerCount = start_index
    async with aiohttp.ClientSession() as session:
        for server_id in servers_to_query[start_index:]:
            cobalt_url, api_key = cobalt_servers[server_id]
            print(f"Server to query: {cobalt_url}. Inserting API key into request.")
            headers["Authorization"] = f"Api-Key {api_key}"

            try:
                print(f"Requesting {cobalt_url} with params: {params}")
                async with session.post(cobalt_url, headers=headers, json=params, timeout=20) as response:
                    response_code = response.status
                    try:
                        response_data = await response.json()
                    except aiohttp.ContentTypeError:
                        response_text = await response.text()
                        print(f"Unexpected content type. Response text: {response_text}")
                        raise

                    if not response_data:
                        print(f"**Cobalt server {ServerCount}**: Empty response.")
                        await editMessage.edit(content=f"**Cobalt server {ServerCount}**: Empty response. Trying another server...")
                        errorLogs.append(f"**Cobalt server {ServerCount}**: Empty response.")
                        ServerCount += 1
                        continue

                    if 200 <= response_code < 300:
                        video_url = response_data.get("url")
                        if video_url is None:
                            print(f"**Cobalt server {ServerCount}**: Server returned a blank URL. This bot does not support downloading images.")
                            await editMessage.edit(content=f"**Cobalt server {ServerCount}**: Server returned a blank URL. Check if the link contains any videos. This bot does not support downloading images.")
                            errorLogs.append(f"**Cobalt server {ServerCount}**: Server returned a blank URL.")
                            ServerCount += 1
                            return None, ServerCount, errorLogs
                        return response, ServerCount, errorLogs

                    if 400 <= response_code < 500:
                        response_status = response_data.get("status")
                        error_info = response_data.get("error", {})
                        print(f"**Cobalt server {ServerCount}**: {response_code} {response_status}:\nError details: {error_info}")
                        errorLogs.append(f"**Cobalt server {ServerCount}**: {response_code} {response_status}: {error_info}")

            except Exception as e:
                print(f"**Cobalt server {ServerCount}**: An unexpected error occurred: {e}")
                await editMessage.edit(content=f"**Cobalt server {ServerCount}**: An unexpected error occurred: {e}. Trying another server...")
                errorLogs.append(f"**Cobalt server {ServerCount}**: An unexpected error occurred: {e}")
            finally:
                print(f"Cobalt server {ServerCount} could not obtain video. Trying another server...")
                ServerCount += 1
    return None, ServerCount, errorLogs


async def HandleYtDlp(url, editMessage, message, AudioOnly):
    """yt-dlp backend (Medal, Odysee). No fallback: on failure, just report it."""
    filename = await DownloadWithYtDlp(url, editMessage, message, AudioOnly)
    if filename is None:
        return
    try:
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        if file_size_mb <= ORIGIN_LIMIT_MB:
            await message.channel.send(file=discord.File(filename))
        else:
            await editMessage.edit(content="Download successful, but the file is above the filesize limit. Uploading to alternate channel...")
            attachment_url = await upload_to_alt_channel(message, filename)
            if attachment_url:
                await message.channel.send(f"✅ **Upload successful!**\nSince the file was over the limit, I have embedded it here: {attachment_url}")
            else:
                await message.channel.send(f"**Error**: The file is too large to upload ({file_size_mb:.1f} MB) and the backup upload failed.")
    except Exception:
        await message.channel.send("Unable to upload video")
    finally:
        if os.path.exists(filename):
            os.remove(filename)


async def DownloadWithYtDlp(url, editMessage, message, AudioOnly):
    await editMessage.edit(content="Notice: Using yt-dlp to download. This is experimental and is likely to fail.")
    ydl_opts = {'outtmpl': '%(id)s-%(title)s.%(ext)s'}
    if AudioOnly:
        ydl_opts['format'] = 'bestaudio/best'
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(url, download=True)
            await editMessage.edit(content="Media fetched! Now uploading...")
            print("yt-dlp has successfully downloaded media!")
            return ydl.prepare_filename(result)
        except Exception:
            print("Failed to download media")
            await editMessage.edit(content="Failed to download media")
            return None


token = os.getenv('DISCORD_TOKEN')
client.run(token)
