#!/bin/bash

# 64 000 000 bits / video length = target bitrate

#MAX_VIDEO_SIZE="187500000"
MAX_VIDEO_SIZE="162500000"
#MAX_AUDIO_SIZE="12500000"

# Check argument

if [[ "$1" == "" ]]; then
	echo "Error: No video file selected"
	echo "Usage: $0 <video-file>"
	exit
fi

# Check if file is video, get duration if it is

DURATION=$(ffprobe -hide_banner "$1" -show_entries format=duration -v quiet -of csv="p=0")

if [[ "$DURATION" == "" ]]; then
	echo Error, ffprobe returned no duration. "$1" is possibly not a video file
	exit
fi

echo "$1" is a video file and is "$DURATION" seconds long

# Calculate bitrate

ADJUSTED_DURATION=$(printf "%.0f\n" "$DURATION")
VIDEO_BITRATE=$((MAX_VIDEO_SIZE / ADJUSTED_DURATION))
#AUDIO_BITRATE=$(echo $((MAX_AUDIO_SIZE / ADJUSTED_DURATION)))

ffmpeg -hide_banner -y -i "$1" -c:v libvpx-vp9 -row-mt 1 -b:v "$VIDEO_BITRATE" -pix_fmt yuv420p -vf scale=720:1080 -pass 1 -an -f null /dev/null && ffmpeg -hide_banner -y -i "$1" -c:v libvpx-vp9 -cpu-used 7 -row-mt 1 -b:v "$VIDEO_BITRATE" -pix_fmt yuv420p -vf scale=720:1080 -pass 2 "$1-compressing.mp4"
mv "$1-compressing.mp4" "$1-compressed.mp4"
done