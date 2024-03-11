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
import json

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

TriggerLinks = ['instagram.com/reel', 'instagram.com/p', 'youtube.com/watch?v=', 'youtu.be/', 'youtube.com/shorts/', 'vt.tiktok.com/', 'tiktok.com/t', 'twitter.com/', 'soundcloud.com/']

@client.event
async def on_ready():
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

    for reaction in message.reactions:
        if (str(reaction.emoji) == str(payload.emoji) and reaction.me):
            emoji = payload.emoji.name if payload.emoji.is_custom_emoji() else payload.emoji.name
            if (emoji == "🎬" or emoji == "🎵"):
                try:
                    tryToSendMessage = await channel.send(f'Attempting to start download...')
                except Exception as ex:
                    await user.send("It appears that I may not have permission to send the video in the channel. Here's more info on what went wrong:")
                    template = "||{0}||"
                    errorToSend = template.format(ex)
                    await user.send(errorToSend)
                else:
                    if emoji == "🎬":
                        await CreatePreview(message, tryToSendMessage, user)
                    elif emoji == "🎵":
                        await CreatePreview(message, tryToSendMessage, user, AudioOnly=True)

@client.event
async def on_message(message):
    isPinged = False
    
    if message.author == client.user:
        return
    
    if message.guild is not None:
        if message.guild.id == 612289903769944064: # RoFT Fan Chat
            return
    
    if client.user.mentioned_in(message):
        isPinged = True
    
    global TriggerLinks
    for keyword in TriggerLinks:
        if keyword in message.content:
            if isPinged:
                await CreatePreview(message)
            elif 'soundcloud.com/' in keyword:
                await message.add_reaction("🎵")
            else:
                await message.add_reaction("🎬")
                await message.add_reaction("🎵")

    if ('twitter.com/' in message.content):
        try:
            await secrets.CreateBirdsitePreview(message, isPinged)
        except:
            pass

async def CreatePreview(message, messageToEdit = None, reactedUser = None, AudioOnly = False):
    try:
        DebugMode = False
        start_time = time.time()
        if (message.guild.id == 443253214859755522):
            DebugMode = True
        
        global TriggerLinks
        urls = [] # Leave this blank

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

            response, ServerRequestCount = await SendRequestToCobalt(url, editMessage, message, AudioOnly)

            if (response == None):
                await editMessage.edit(content=f"Requests to all {(ServerRequestCount + 1)} Cobalt servers were unsuccessful. Here's what each one of them responded:")
                await message.channel.send("Failed to print error logs. Check server console.")
                return
            else:
                response_data = response.json()
                response_code = response.status_code
                response_status = response_data.get("status")

                video_url = response_data.get("url")

                if (AudioOnly):
                    print("Successfully got audio for url:" + video_url)
                    await editMessage.edit(content=f"Successfully got audio for url:<{video_url}>\nDownloading audio now...")
                else:
                    print("Successfully got video for url:" + video_url)
                    await editMessage.edit(content=f"Successfully got video for url:<{video_url}>\nDownloading video now...")

                if (response_status == "stream"):
                    InfoMessage = await UploadVideoStream(message, editMessage, DebugMode, video_url, AudioOnly)
                else:
                    InfoMessage = await UploadVideo(message, editMessage, DebugMode, video_url, AudioOnly)
                end_time = time.time()
                execution_time = end_time - start_time
                execution_time_rounded = round(execution_time, 1)
                print(f"Job complete! ({execution_time_rounded}s)")
                if (InfoMessage != None):
                    if ((reactedUser != None) and (message.author.name != reactedUser.name)):
                        await InfoMessage.edit(content=f"**Debug:** Video posted from **{message.author.name}** (Requested by **{reactedUser.name}**, {(ServerRequestCount + 1)} Cobalt requests, {execution_time_rounded}s)")
                    else:
                        await InfoMessage.edit(content=f"**Debug:** Video posted from **{message.author.name}** ({(ServerRequestCount + 1)} Cobalt requests, {execution_time_rounded}s)")
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
        print("Compression process was marked as complete, but output file is absent! It is likely that compression has failed.")
        await message.channel.send('**Warning**: Compression failed: No compression module (ffmpeg or handbrake) detected on the bot')
    timeElapsed2 = time.time()-timeElapsed2
    print(f'Compression finished! Time elapsed: {timeElapsed2} seconds')

async def UploadVideoStream(message, editMessage, DebugMode, video_url, AudioOnly):
    video_response = requests.get(video_url, stream=True)
    if AudioOnly == False:
        filename = "video.mp4"
    else:
        filename = "audio.mp3"
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
            if AudioOnly == False:
                filename = filename + '-compressed.mp4'
            else:
                filename = filename + '-compressed.mp3'
            try:
                await message.channel.send(file=discord.File(filename))
            except:
                await message.channel.send("**Error**: Could not upload video")
    elif file_size_mb <= 20000:
        await editMessage.edit(content=f"Download successful, but video is above filesize limit. Compressing video...")
        if (await ProcessVideoCompression(editMessage, message, filename) == True):
            return
        if AudioOnly == False:
            filename = filename + '-compressed.mp4'
        else:
            filename = filename + '-compressed.mp3'
        try:
            await message.channel.send(file=discord.File(filename))
        except:
            await message.channel.send("**Error**: Could not upload video")
    else:
        await editMessage.edit(content=f"Uhhh... guys? I can't handle a video this big...")
        await message.channel.send(f"**Error**: Could not upload video. Filesize is too large to handle ({file_size_mb} MB)")

    # Comment this line if you would prefer to have a caching system that I inefficiently built. I didn't like how it turned out.
    os.remove(filename)

    if (DebugMode == True):
        return InfoMessage
    else:
        return None

async def UploadVideo(message, editMessage, DebugMode, video_url, AudioOnly):
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
        video_bytes_io.seek(0)  # Reset the file pointer to the beginning of the buffer
        await editMessage.edit(content=f"Download success! Uploading video now...")
        if AudioOnly == False:
            filename = "video.mp4"
        else:
            filename = "audio.mp3"
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

async def SendRequestToCobalt(url, editMessage, message, AudioOnly):
    # If link is Instagram link, use a different order of Cobalt URLs
    isInstagramLink = False
    InstagramLinks = ['instagram.com/reel', 'instagram.com/p']
    if any(keyword in url for keyword in InstagramLinks):
        isInstagramLink = True

    cobalt_url = []
    if (isInstagramLink == True):
        cobalt_url = [
            "co.wuk.sh",
            "co-api.orchidmc.me",
            "api.co.rooot.gay",
            "capi.oak.li"
            ]
    else:
        cobalt_url = [
            "co.wuk.sh",
            "api.co.rooot.gay",
            "capi.oak.li"
            ]
    errorLogs = []
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "ZymBot"
    }

    print(f"User Agent: {requests.get('https://httpbin.org/get', headers=headers).json()['headers']['User-Agent']}")

    if AudioOnly == True:
        params = {
            'url': url,
            'isAudioOnly': 'true',
            'filenamePattern': 'pretty',
            'disableMetadata': 'true',
            'isNoTTWatermark': 'true',
            'twitterGif': 'true'
            }
    else:
        params = {
            'url': url,
            'filenamePattern': 'pretty',
            'disableMetadata': 'true',
            'isNoTTWatermark': 'true',
            'twitterGif': 'true'
            }
    ServerCount = 0 # Do not change. This serves as a counter for the program.
    MaxServerCount = len(cobalt_url)

    while True:
        if ServerCount >= MaxServerCount:
            return None, ServerCount
        
        CobaltServerToUse = "https://" + cobalt_url[ServerCount] + "/api/json"
        print(f"Server Count: {ServerCount}")
        timeout = 20
        try:
            response = requests.post(CobaltServerToUse, headers=headers, json=params, timeout=timeout)
            response_data = response.json()
            response_code = response.status_code

            # Check if the response_data is empty or not
            if not response_data:
                print(f"**{cobalt_url[ServerCount]}**: Empty response.")
                await editMessage.edit(content=f"**{cobalt_url[ServerCount]}**: Empty response. Trying another server...")
                ServerCount += 1
                continue

            if (200 <= response_code < 300):
                return response, ServerCount
            elif (400 <= response_code < 599):
                response_status = response_data.get("status")
                response_text = response_data.get("text")
                print(f"**{cobalt_url[ServerCount]}**: {response_code} {response_status}:\n{response_text}")
                await editMessage.edit(content=f"**{cobalt_url[ServerCount]}**: {response_code} {response_status}:\n{response_text}.\nTrying another server...")
            else:
                print(f"**{cobalt_url[ServerCount]}** returned an unknown response code")
                await editMessage.edit(content=f"**{cobalt_url[ServerCount]}** returned an unknown response code. Trying another server...")
        except requests.exceptions.Timeout:
            print(f"**{cobalt_url[ServerCount]}**: Request timed out after {timeout} seconds")
            await editMessage.edit(content=f"**{cobalt_url[ServerCount]}**: Request timed out after {timeout} seconds. Trying another server...")
        except requests.exceptions.HTTPError as http_err:
            print(f"**{cobalt_url[ServerCount]}**: HTTP error: {http_err}")
            await editMessage.edit(content=f"**{cobalt_url[ServerCount]}**: HTTP error: {http_err}. Trying another server...")
        except requests.exceptions.ConnectionError as conn_err:
            print(f"**{cobalt_url[ServerCount]}**: Connection error: {conn_err}")
            await editMessage.edit(content=f"**{cobalt_url[ServerCount]}**: Connection error: {conn_err}. Trying another server...")
        except requests.exceptions.RequestException as req_err:
            print(f"**{cobalt_url[ServerCount]}**: Request error: {req_err}")
            print(f"Response content: {response.content.decode('utf-8')}")
            await editMessage.edit(content=f"**{cobalt_url[ServerCount]}**: Request blocked by Cloudflare. Trying another server...")
        except json.JSONDecodeError as json_err:
            print(f"**{cobalt_url[ServerCount]}**: JSON decoding error: {json_err}")
            await editMessage.edit(content=f"**{cobalt_url[ServerCount]}**: JSON decoding error: {json_err}. Trying another server...")
        except Exception as e:
            print(f"**{cobalt_url[ServerCount]}**: An unexpected error occurred: {e}")
            await editMessage.edit(content=f"**{cobalt_url[ServerCount]}**: An unexpected error occurred: {e}. Trying another server...")
        finally:
            ServerCount += 1

token = os.getenv('DISCORD_TOKEN')
client.run(token)