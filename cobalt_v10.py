# This file is the third rewrite of this bot to make ZymBot's downloader mobule compatible with Cobalt v10. This script is not ready for production.
# There may be a toggleable option to fallback to local downloads using yt-dlp

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
import aiohttp
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
    'tiktok.com/',
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
    'twitch.tv/',
    'bsky.app/',
    'xiaohongshu.com/'
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
            if (emoji == "🎬" or emoji == "🎵" or emoji == "👀"):
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
            if isPinged or message.guild is None:
                await CreatePreview(message, None)
            elif 'soundcloud.com/' in keyword:
                await message.add_reaction("🎵")
            # elif 'x.com' in keyword or 'twitter.com' in keyword:
            #     await message.add_reaction("👀")
            #     # TODO: Perform checks to ensure that request is valid here:
            # elif 'bsky.app' in keyword or 'reddit.com' in keyword or 'xiaohongshu.com' in keyword:
            #     await message.add_reaction("👀")
            #     # TODO: Perform checks to ensure that request is valid here:
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
    # if True: # Uncomment this line if testing this try-except code block
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
            # Removes FixTweet/FixUpX
            if "fxtwitter.com/" in url:
                url = url.replace('https://fx', 'https://')
            if "vxtwitter.com/" in url:
                url = url.replace('https://vx', 'https://')
            if "fixupx.com/" in url:
                url = url.replace('https://fixup', 'https://')
            if "girlcockx.com/" in url:
                url = url.replace('https://girlcock', 'https://')

            # Set messageToEdit var
            if messageToEdit == None:
                editMessage = await message.channel.send(f"URL found: {url}")
            else:
                editMessage = messageToEdit
                await editMessage.edit(content=f"URL found: {url}")
            parsed_url = urlparse(url)
            url_without_query = urlunparse(parsed_url._replace(query=''))
            await editMessage.edit(content=f"Formatted URL: {url_without_query}. Waiting for Cobalt v10 to reply...")

            response, ServerRequestCount, errorLogs = await SendRequestToCobalt(url, editMessage, message, AudioOnly)

            if response == None:
                if DebugMode == True or message.guild is None:
                    await editMessage.edit(content=f"Requests to a randomly selected pool of {(ServerRequestCount)} Cobalt servers to download the content were unsuccessful. Here's what each one of them replied:")
                    if errorLogs == []:
                        await message.channel.send("Could not send error logs. (errorLogs variable is empty [more likely] or missing permissions [less likely]) Check server console for details.")
                    for i in errorLogs:
                        await message.channel.send(f"{i}")
                else:
                    await editMessage.edit(content=f"Requests to all {(ServerRequestCount)} Cobalt servers were unsuccessful. Check the bot console for details.")
                return
            else:
                response_data = await response.json()  # Make sure to await this
                response_code = response.status  # Access the status code correctly
                response_status = response_data.get("status")

                video_url = response_data.get("url")

                MediaType = "Media" # for printing out messages
                if (AudioOnly):
                    MediaType = "Audio"
                    print(f"Successfully got {MediaType.lower()} for url: {video_url}")
                    await editMessage.edit(content=f"Successfully got audio from url!\nDownloading audio now...")
                else:
                    MediaType = "Video"
                    print(f"Successfully got {MediaType.lower()} for url: {video_url}")
                    await editMessage.edit(content=f"Successfully got video for url!\nDownloading video now...")

                print(f"Successfully got video/audio from url! Response status: {response_status}")
                if (response_status == "tunnel"):
                    InfoMessage = await UploadVideoStream(message, editMessage, DebugMode, video_url, AudioOnly)
                elif (response_status == "picker"):
                    InfoMessage = "Cobalt has presented multiple videos to download from. The bot developer has never encountered this, thus I do not know what to do here"
                else: # response is redirect
                    InfoMessage = await UploadVideo(message, editMessage, DebugMode, video_url, AudioOnly)
                end_time = time.time()
                execution_time = end_time - start_time
                execution_time_rounded = round(execution_time, 1)
                print(f"Job complete! ({execution_time_rounded}s)")
                if (InfoMessage != None):
                    if ((reactedUser != None) and (message.author.name != reactedUser.name)):
                        await InfoMessage.edit(content=f"**Debug:** {MediaType} posted from **{message.author.name}** (Requested by **{reactedUser.name}**, {(ServerRequestCount + 1)} Cobalt requests, {execution_time_rounded}s)")
                        #TODO: Add alternate message for audio downloads
                    else:
                        await InfoMessage.edit(content=f"**Debug:** {MediaType} posted from **{message.author.name}** ({(ServerRequestCount + 1)} Cobalt requests, {execution_time_rounded}s)")
                        #TODO: Add alternate message for audio downloads
            await editMessage.delete()
    except Exception as e:
       await message.channel.send(f"The following error occured while generating the video:\n{e}")

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
    elif platform.system() == "Darwin":
        print("Compression failed as compression is not supported on macOS")
    else:
        print("Compression failed as the script is running on unknown OS. What are you using!?")
    if (os.path.exists(filepath + '-compressed.mp4') == False):
        print("Compression process was marked as complete, but output file is absent! It is likely that compression has failed.")
        await message.channel.send('**Warning**: Compression failed: No compression module (ffmpeg) detected on the bot')
    timeElapsed2 = time.time()-timeElapsed2
    print(f'Compression finished! Time elapsed: {timeElapsed2} seconds')

async def UploadVideoStream(message, editMessage, DebugMode, video_url, AudioOnly):
    video_response = requests.get(video_url, stream=True)
    MediaType = "Media"
    if AudioOnly == False:
        MediaType = "Video"
        filename = "video.mp4"
    else:
        MediaType = "Audio"
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
        InfoMessage = await message.channel.send(f"{MediaType} Video request from **{message.author.name}**")
    
    if file_size_mb > 20000:
        await editMessage.edit(content=f"Uhhh... guys? I can't handle a video this big...")
        await message.channel.send(f"**Error**: Could not upload video. Filesize is too large to handle ({file_size_mb} MB)")
    elif file_size_mb > 10:
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
        InfoMessage = await message.channel.send(f"**Debug:** Request from **{message.author.name}**")
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
    # TODO: First check the S3 Bucket if the resource already exist. If it does, get it from there. If not, proceed with below.
    cobalt_servers = {
        'COBALT_SERVER_0': (os.getenv('COBALT_SERVER_0'), os.getenv('COBALT_SERVER_0_API_KEY')),
        'COBALT_SERVER_1': (os.getenv('COBALT_SERVER_1'), os.getenv('COBALT_SERVER_1_API_KEY')),
        'COBALT_SERVER_2': (os.getenv('COBALT_SERVER_2'), os.getenv('COBALT_SERVER_2_API_KEY')),
        'COBALT_SERVER_3': (os.getenv('COBALT_SERVER_3'), os.getenv('COBALT_SERVER_3_API_KEY'))
    }
    userAgent = f"ZymBot/46.250.233.81.rolling.release GodotEngine/4.3.stable.official {platform.system()}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": userAgent
    }
    print(f"User Agent: {requests.get('https://httpbin.org/get', headers=headers).json()['headers']['User-Agent']}")

    errorLogs = []
    # Make sure to test these parameters properly if you make any changes! Cobalt likes to return an error.api.invalid_body for random changes to the params
    # Also, Do NOT add 'disableMetadata' parameter to the request, it will cause cobalt to respond with error.api.invalid_body
    params = {
        'url': url,
        'filenameStyle': 'classic'
    }
    if AudioOnly:
        params['downloadMode'] = 'audio'
    
    ServerCount = 0 # Do not modify this. It is for the bot to keep track of which server it's on
    # New code setup using aiohttp
    servers_to_query = [server for server, (url, key) in cobalt_servers.items() if url is not None]
    async with aiohttp.ClientSession() as session:
        for server_id in servers_to_query:
            cobalt_url, api_key = cobalt_servers[server_id]
            cobalt_url = f"https://{cobalt_url}"  # Ensure the URL is properly formatted
            
            print(f"Server to query: {cobalt_url}. Inserting API key into request.")
            headers["Authorization"] = f"Api-Key {api_key}"
            
            try:
                print(f"Requesting {cobalt_url} with headers: {headers} params: {params}")
                async with session.post(cobalt_url, headers=headers, json=params, timeout=20) as response:
                    response_code = response.status
                    try:
                        response_data = await response.json()
                    except aiohttp.ContentTypeError: # Log the response text for debugging
                        response_text = await response.text()
                        print(f"Unexpected content type. Response text: {response_text}")
                        raise

                    if not response_data:  # Check if the response_data is empty or not
                        print(f"**Cobalt server {ServerCount}**: Empty response.")
                        await editMessage.edit(content=f"**Cobalt server {ServerCount}**: Empty response. Trying another server...")
                        errorLogs.append(f"**Cobalt server {ServerCount}**: Empty response.")
                        ServerCount += 1
                        continue

                    if (200 <= response_code < 300):
                        video_url = response_data.get("url")
                        if video_url is None:
                            print(f"**Cobalt server {ServerCount}**: Server returned a blank URL. Check if the link contains any videos. This bot does not support downloading images.")
                            await editMessage.edit(content=f"**Cobalt server {ServerCount}**: Server returned a blank URL. Check if the link contains any videos. This bot does not support downloading images.")
                            errorLogs.append(f"**Cobalt server {ServerCount}**: Server returned a blank URL. Check if the link contains any videos. This bot does not support downloading images.")
                            print(errorLogs)
                            ServerCount += 1
                            return None, ServerCount, errorLogs
                        else:
                            return response, ServerCount, errorLogs
                    if (400 <= response_code < 500):
                        response_status = response_data.get("status")
                        error_info = response_data.get("error", {})
                        
                        # Log the status and error details
                        print(f"**Cobalt server {ServerCount}**: {response_code} {response_status}:\nError details: {error_info}")
                        
                        # Append detailed error information to the logs
                        errorLogs.append(f"**Cobalt server {ServerCount}**: {response_code} {response_status}: {error_info}")

            except Exception as e:
                print(f"**Cobalt server {ServerCount}**: An unexpected error occurred: {e}")
                await editMessage.edit(content=f"**Cobalt server {ServerCount}**: An unexpected error occurred: {e}. Trying another server...")
                errorLogs.append(f"**Cobalt server {ServerCount}**: An unexpected error occurred: {e}")
            finally:
                print(f"Cobalt server {ServerCount} could not obtain video. Trying another server...")
                ServerCount += 1
    return None, ServerCount, errorLogs

async def check_s3_storage_for_file():
    # Set up S3 storage client
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
        # Check if the file already exists in the bucket
        s3_client.head_object(Bucket=bucket_name, Key=filename)
        print(f"File {filename} already exists in bucket {bucket_name}. Skipping upload.")
        
        # Return the URL of the existing file
        return "https://zymsb.floofyand.gay/" + filename
    except ClientError as e:
        # If the error is 404, the file does not exist, so we can proceed to upload
        if e.response['Error']['Code'] == '404':
            # TODO: Return function and tell the bot to proceed with the request
            pass

async def upload_to_s3(filename):
    # Set up S3 storage client
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
        # Check if the file already exists in the bucket
        s3_client.head_object(Bucket=bucket_name, Key=filename)
        print(f"File {filename} already exists in bucket {bucket_name}. Skipping upload.")
        
        # Return the URL of the existing file
        return "https://zymsb.floofyand.gay/" + filename
    except ClientError as e:
        # If the error is 404, the file does not exist, so we can proceed to upload
        if e.response['Error']['Code'] == '404':
            try:
                # Upload file to MinIO bucket
                s3_client.upload_file(filename, bucket_name, filename)

                # Return the URL of the uploaded file
                return "https://zymsb.floofyand.gay/" + filename
                # return s3_client.generate_presigned_url(
                #     'get_object',
                #     Params={'Bucket': bucket_name, 'Key': filename},
                #     ExpiresIn=259200  # URL expiration time in seconds
                # )
            except:
                print("File upload failed")
                return None

token = os.getenv('DISCORD_TOKEN')
client.run(token)