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
import boto3
from botocore.exceptions import ClientError
import random

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

TriggerLinks = [
    'instagram.com/reel', 
    'instagram.com/p', 
    'youtube.com/watch?v=', 
    'youtu.be/', 
    'youtube.com/shorts/', 
    'vt.tiktok.com/', 
    'tiktok.com/t', 
    'twitter.com/', 
    'x.com/', 
    'soundcloud.com/',
    'bilibili.com/', # All services from here onwards are untested, but should still work in most circumstances
    'bilibili.tv/',
    'dailymotion.com/',
    'pinterest.com',
    'reddit.com/',
    'streamable.com/',
    'tumblr.com/',
    'twitch.tv/'
    ]

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
                    tryToSendMessage = await channel.send(f'Starting download...')
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
    
    if message.guild is not None and message.guild.id == 612289903769944064: # RoFT Fan Chat
        return
    
    if client.user.mentioned_in(message):
        isPinged = True
    
    global TriggerLinks
    for keyword in TriggerLinks:
        if keyword in message.content:
            if isPinged:
                await CreatePreview(message, None)
            elif 'soundcloud.com/' in keyword:
                await message.add_reaction("🎵")
            else:
                await message.add_reaction("🎬")
                await message.add_reaction("🎵")

    # if ('twitter.com/' in message.content):
    #     try:
    #         await secrets.CreateBirdsitePreview(message, isPinged)
    #     except:
    #         pass

async def CreatePreview(message, messageToEdit = None, reactedUser = None, AudioOnly = False):
    try:
        DebugMode = False
        start_time = time.time()
        if message.guild is not None and message.guild.id == 443253214859755522:
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

        if DebugMode == True:
            print(f"{message.author.name} in #{message.channel.name} in guild {message.guild.name}: {message.content}")

        for url in urls:
            # Remove FixTweet/FixUpX
            if "fxtwitter.com/" in url:
                url = url.replace('https://fx', 'https://')
            if "vxtwitter.com/" in url:
                url = url.replace('https://vx', 'https://')
            if "fixupx.com/" in url:
                url = url.replace('https://fixup', 'https://')

            # Set messageToEdit var
            if messageToEdit == None:
                editMessage = await message.channel.send(f"URL found: {url}")
            else:
                editMessage = messageToEdit
                await editMessage.edit(content=f"URL found: {url}")
            parsed_url = urlparse(url)
            url_without_query = urlunparse(parsed_url._replace(query=''))
            await editMessage.edit(content=f"Formatted URL: {url_without_query}. Waiting for Cobalt to reply...")

            response, ServerRequestCount, errorLogs = await SendRequestToCobalt(url, editMessage, message, AudioOnly)

            if (response == None):
                if (DebugMode == True):
                    await editMessage.edit(content=f"Requests to a randomly selected pool of {(ServerRequestCount)} Cobalt servers to download the content were unsuccessful. Here's what each one of them replied:")
                    if errorLogs == []:
                        await message.channel.send("Could not send error logs. (errorLogs variable is empty [more likely] or missing permissions [less likely]) Check server console for details.")
                    for i in errorLogs:
                        await message.channel.send(f"{i}")
                else:
                    await editMessage.edit(content=f"Requests to all {(ServerRequestCount + 1)} Cobalt servers were unsuccessful. Check the bot console for details.")
                return
            else:
                response_data = response.json()
                response_code = response.status_code
                response_status = response_data.get("status")

                video_url = response_data.get("url")

                if (AudioOnly):
                    print(f"Successfully got audio for url: {video_url}")
                    await editMessage.edit(content=f"Successfully got audio for url:<{video_url}>\nDownloading audio now...")
                else:
                    print(f"Successfully got video for url: {video_url}")
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
    
    if file_size_mb > 20000:
        await editMessage.edit(content=f"Uhhh... guys? I can't handle a video this big...")
        await message.channel.send(f"**Error**: Could not upload video. Filesize is too large to handle ({file_size_mb} MB)")
    elif file_size_mb > 25:
        await editMessage.edit(content=f"Download successful, but video is above filesize limit. Uploading video to S3 Storage...")
        # Upload video to MinIO S3 storage
        minio_url = await upload_to_s3(filename)
        if minio_url:
            await message.channel.send(f"{minio_url}")
        else:
            await editMessage.edit(content=f"Failed to upload video to S3, compressing video instead...")
            # Fallback code in case S3 storage is offline (video compression method)
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
        await editMessage.edit(content=f"Download success! Uploading video now...")
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
    cobalt_url = [
        "api.cobalt.tools",
        "cobalt-uk.programowanie.fun",
        "cobalt-us.programowanie.fun",
        "cobalt-br.programowanie.fun",
        "api.co.rooot.gay",
        "capi.oak.li",
        "api-cobalt.boykisser.systems",
        "cobalt.wither.ing",
        "cobalt-api.alexagirl.studio",
        "api.snaptik.so",
        "dl01.spotifyloader.com",
        "co.eepy.today",
        "cobalt-api.schizo.city"
        ]
    errorLogs = []
    userAgent = "ZymBot/23.162.136.83.rolling.release GodotEngine/4.2.1.stable.official " + platform.system()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": userAgent
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
    ServerCount = 0 # Do not modify this. It is for the bot to keep track of which server it's on
    # TODO: Pick main instance + 4 instances at random to download videos from
    servers_to_query = ["https://co.wuk.sh/api/json"] + random.sample(["https://" + server + "/api/json" for server in cobalt_url if server != "co.wuk.sh"], k=4)
    for CobaltServerToUse in servers_to_query:
        print(f"Server to query: {CobaltServerToUse}")
        timeout = 20
        try:
            response = requests.post(CobaltServerToUse, headers=headers, json=params, timeout=timeout)
            response_data = response.json()
            response_code = response.status_code

            if not response_data: # Check if the response_data is empty or not
                print(f"**{CobaltServerToUse}**: Empty response.")
                await editMessage.edit(content=f"**{CobaltServerToUse}**: Empty response. Trying another server...")
                errorLogs.append(f"**{CobaltServerToUse}**: Empty response.")
                ServerCount += 1
                continue

            if (200 <= response_code < 300):
                video_url = response_data.get("url")
                if (video_url == None):
                    print(f"**{CobaltServerToUse}**: Server returned a blank URL. Check if the link contains any videos. This bot does not support downloading images.")
                    await editMessage.edit(content=f"**{CobaltServerToUse}**: Server returned a blank URL. Check if the link contains any videos. This bot does not support downloading images.")
                    errorLogs.append(f"**{CobaltServerToUse}**: Server returned a blank URL. Check if the link contains any videos. This bot does not support downloading images.")
                    print(errorLogs)
                    ServerCount += 1
                    return None, ServerCount, errorLogs
                else:
                    return response, ServerCount, errorLogs
            elif (400 <= response_code < 599):
                response_status = response_data.get("status")
                response_text = response_data.get("text")
                print(f"**{CobaltServerToUse}**: {response_code} {response_status}:\n{response_text}")
                await editMessage.edit(content=f"**{CobaltServerToUse}**: {response_code} {response_status}:\n{response_text}.\nTrying another server...")
                errorLogs.append(f"**{CobaltServerToUse}**: {response_code} {response_status}:\n{response_text}")
            else:
                print(f"**{CobaltServerToUse}** returned an unknown response code")
                await editMessage.edit(content=f"**{CobaltServerToUse}** returned an unknown response code. Trying another server...")
                errorLogs.appen(f"**{CobaltServerToUse}** returned an unknown response code")
        except requests.exceptions.Timeout:
            print(f"**{CobaltServerToUse}**: Request timed out after {timeout} seconds")
            await editMessage.edit(content=f"**{CobaltServerToUse}**: Request timed out after {timeout} seconds. Trying another server...")
            errorLogs.append(f"**{CobaltServerToUse}**: Request timed out after {timeout} seconds")
        except requests.exceptions.HTTPError as http_err:
            print(f"**{CobaltServerToUse}**: HTTP error: {http_err}")
            await editMessage.edit(content=f"**{CobaltServerToUse}**: HTTP error: {http_err}. Trying another server...")
            errorLogs.append(f"**{CobaltServerToUse}**: HTTP error: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            print(f"**{CobaltServerToUse}**: Connection error: {conn_err}")
            await editMessage.edit(content=f"**{CobaltServerToUse}**: Connection error: {conn_err}. Trying another server...")
            errorLogs.append(f"**{CobaltServerToUse}**: Connection error: {conn_err}")
        except requests.exceptions.RequestException as req_err:
            print(f"**{CobaltServerToUse}**: Request error: {req_err}")
            print(f"Response content: {response.content.decode('utf-8')}")
            await editMessage.edit(content=f"**{CobaltServerToUse}**: Request blocked by Cloudflare. Trying another server...")
            errorLogs.append(f"**{CobaltServerToUse}**: Request blocked by Cloudflare.")
        except json.JSONDecodeError as json_err:
            print(f"**{CobaltServerToUse}**: JSON decoding error: {json_err}")
            await editMessage.edit(content=f"**{CobaltServerToUse}**: JSON decoding error: {json_err}. Trying another server...")
            errorLogs.append(f"**{CobaltServerToUse}**: JSON decoding error: {json_err}")
        except Exception as e:
            print(f"**{CobaltServerToUse}**: An unexpected error occurred: {e}")
            await editMessage.edit(content=f"**{CobaltServerToUse}**: An unexpected error occurred: {e}. Trying another server...")
            errorLogs.append(f"**{CobaltServerToUse}**: An unexpected error occurred: {e}")
        finally:
            print(f"{CobaltServerToUse} could not obtain video. Trying another server...")
            ServerCount += 1
    return None, ServerCount, errorLogs

async def upload_to_s3(filename):
    # Set up MinIO client
    s3_client = boto3.client(
        's3',
        endpoint_url=os.getenv('S3_ENDPOINT_URL'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
        aws_secret_access_key=os.getenv('S3_SECRET_KEY')
    )

    # Set MinIO bucket name
    bucket_name = os.getenv('S3_BUCKET_NAME')

    print("Current directory:", os.getcwd())
    try:
        # Upload file to MinIO bucket
        s3_client.upload_file(filename, bucket_name, filename)

        # Return the URL of the uploaded file
        return s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': filename},
            ExpiresIn=259200  # URL expiration time in seconds
        )
    except ClientError as e:
        print(f"Error uploading to MinIO: {e}")
        await editMessage.edit(content=f"Error uploading to MinIO: {e}")
        return None

token = os.getenv('DISCORD_TOKEN')
client.run(token)