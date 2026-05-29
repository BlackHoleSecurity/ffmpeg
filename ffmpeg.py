#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
import os
import time
import threading
import itertools
import argparse

def loading_animation(stop_event):
    for c in itertools.cycle(['⠋', '⠙', '⠹', '⠼', '⠴', '⠦', '⠧', '⠏']):
        if stop_event.is_set():
            break
        sys.stdout.write(f'\r[¡] Converting to Instagram format... {c}')
        sys.stdout.flush()
        time.sleep(0.08)
    sys.stdout.write('\r' + '_' * 55 + '\r')

def get_quality_settings(quality):
    if quality == "high":
        return {"crf": "17", "preset": "slower", "bitrate": "14000k", "maxrate": "17000k", "bufsize": "22000k",
                "unsharp": "5:5:0.6:3:3:0.35", "eq": "contrast=1.12:brightness=0.01"}
    elif quality == "low":
        return {"crf": "22", "preset": "medium", "bitrate": "8500k", "maxrate": "11000k", "bufsize": "14000k",
                "unsharp": "3:3:0.3:3:3:0.15", "eq": "contrast=1.05:brightness=0.0"}
    else: # medium
        return {"crf": "18", "preset": "slower", "bitrate": "12500k", "maxrate": "15500k", "bufsize": "20000k",
                "unsharp": "3:3:0.5:3:3:0.25", "eq": "contrast=1.08:brightness=0.005"}

def convert_to_ig(input_file, output_file="output_ig.mp4", quality="medium"):
    if not os.path.exists(input_file):
        print(f"[x] Input file not found: {input_file}")
        return False

    settings = get_quality_settings(quality)
    vf_filter = f"fps=60,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,eq={settings['eq']},unsharp={settings['unsharp']}"

    command = [
        'ffmpeg', '-i', input_file,
        '-vf', vf_filter,
        '-c:v', 'libx264',
        '-preset', settings['preset'],
        '-crf', settings['crf'],
        '-profile:v', 'main',
        '-level:v', '4.0',
        '-x264-params', "scenecut=0:open_gop=0:min-keyint=60:keyint=60:ref=5:psy-rd=0.85",
        '-b:v', settings['bitrate'],
        '-maxrate', settings['maxrate'],
        '-bufsize', settings['bufsize'],
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '256k',
        '-movflags', '+faststart',
        '-vsync', 'cfr',
        '-y', output_file
    ]

    print(f"\n[+] Input : {input_file}")
    print(f"[>] Output : {output_file}")
    print(f"[*] Quality : {quality.upper()}\n")

    stop_loading = threading.Event()
    loading_thread = threading.Thread(target=loading_animation, args=(stop_loading,))
    loading_thread.start()

    proc = None
    try:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()

        if proc.returncode!= 0:
            raise subprocess.CalledProcessError(proc.returncode, command)

        stop_loading.set()
        loading_thread.join()
        print("[#] Conversion completed successfully!")
        print(f"[*] Saved as: {output_file}")
        return True

    except KeyboardInterrupt:
        print("\n[!] Ctrl+C detected, stopping ffmpeg...")
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        stop_loading.set()
        loading_thread.join()
        print("[x] Conversion cancelled by user.")
        return False

    except subprocess.CalledProcessError:
        stop_loading.set()
        loading_thread.join()
        print("[x] Conversion failed!")
        return False

    except FileNotFoundError:
        stop_loading.set()
        loading_thread.join()
        print("[x] FFmpeg not found!")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram Video Converter (60fps)")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("output", nargs='?', default="output_ig.mp4",
                       help="Output video file (optional)")
    parser.add_argument("-q", "--quality", choices=["low", "medium", "high"],
                       default="medium", help="Quality level (default: medium)")

    args = parser.parse_args()

    convert_to_ig(args.input, args.output, args.quality)
