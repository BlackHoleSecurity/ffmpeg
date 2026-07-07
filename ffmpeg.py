#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
import os
import time
import threading
import itertools
import argparse
import re

def loading_animation(stop_event, progress_holder, lock):
    for c in itertools.cycle(['⠋', '⠙', '⠹', '⠼', '⠴', '⠦', '⠧', '⠏']):
        if stop_event.is_set():
            break
        with lock:
            percent = progress_holder.get('percent', 0.0)
        if percent < 0:
            percent_str = " N/A%"
        else:
            percent_str = f"{percent:5.1f}%"
        sys.stdout.write(f'\r[¡] Converting... {percent_str} {c}')
        sys.stdout.flush()
        time.sleep(0.08)
    sys.stdout.write('\r' + ' ' * 60 + '\r')
    sys.stdout.flush()

def get_quality_settings(quality):
    if quality == "high":
        return {"crf": "17", "preset": "slow",
                "bitrate": "14000k", "maxrate": "17000k", "bufsize": "22000k",
                "unsharp": "5:5:0.6:3:3:0.35", "eq": "contrast=1.12:brightness=0.01"}
    elif quality == "low":
        return {"crf": "22", "preset": "medium",
                "bitrate": "8500k", "maxrate": "11000k", "bufsize": "14000k",
                "unsharp": "3:3:0.3:3:3:0.15", "eq": "contrast=1.05:brightness=0.0"}
    else:
        return {"crf": "18", "preset": "slow",
                "bitrate": "12500k", "maxrate": "15500k", "bufsize": "20000k",
                "unsharp": "3:3:0.5:3:3:0.25", "eq": "contrast=1.08:brightness=0.005"}

def get_video_duration_seconds(input_file):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return float(out.strip())
    except Exception:
        return None

def convert_to_ig(input_file, output_file="output_ig.mp4", quality="medium"):
    if not os.path.exists(input_file):
        print(f"[x] Input file not found: {input_file}")
        return False

    total_duration = get_video_duration_seconds(input_file)

    settings = get_quality_settings(quality)
    vf_filter = (f"fps=60,scale=1080:1920:force_original_aspect_ratio=decrease,"
                 f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
                 f"eq={settings['eq']},unsharp={settings['unsharp']}")

    has_audio = True
    try:
        probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'a',
                     '-show_entries', 'stream=codec_type',
                     '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        if result.stdout.strip() != 'audio':
            has_audio = False
    except Exception:
        pass

    command = [
        'ffmpeg', '-i', input_file,
        '-map', '0:v:0?',
    ]
    if has_audio:
        command += ['-map', '0:a:0?']
    else:
        command += ['-an']

    command += [
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
    ]

    if has_audio:
        command += ['-c:a', 'aac', '-b:a', '256k']

    command += ['-progress', 'pipe:1', '-nostats']
    command += ['-movflags', '+faststart', '-vsync', 'cfr', '-y', output_file]

    print(f"\n[+] Input  : {input_file}")
    print(f"[>] Output : {output_file}")
    print(f"[*] Quality: {quality.upper()}")
    if total_duration:
        print(f"[*] Duration: {total_duration:.1f} sec\n")
    else:
        print("[*] Duration: unknown\n")

    progress_holder = {'percent': 0.0}
    lock = threading.Lock()
    stop_loading = threading.Event()

    anim_thread = threading.Thread(target=loading_animation,
                                   args=(stop_loading, progress_holder, lock))
    anim_thread.start()

    proc = None
    reader_thread = None
    stderr_output = ""

    try:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True)

        def progress_reader(stream, total_sec):
            for line in iter(stream.readline, ''):
                if stop_loading.is_set():
                    break
                if line.startswith('out_time_ms='):
                    try:
                        time_ms = int(line.split('=')[1].strip())
                        time_sec = time_ms / 1_000_000.0
                        if total_sec and total_sec > 0:
                            pct = min(100.0, (time_sec / total_sec) * 100.0)
                            with lock:
                                progress_holder['percent'] = pct
                        else:
                            with lock:
                                progress_holder['percent'] = -1.0
                    except (ValueError, IndexError):
                        pass
                elif line.startswith('progress=end'):
                    with lock:
                        progress_holder['percent'] = 100.0

        reader_thread = threading.Thread(target=progress_reader,
                                         args=(proc.stdout, total_duration))
        reader_thread.start()

        proc.wait()
        reader_thread.join(timeout=2)

        if proc.returncode != 0:
            stderr_output = proc.stderr.read()
            raise subprocess.CalledProcessError(proc.returncode, command, stderr=stderr_output)

        stop_loading.set()
        anim_thread.join()
        print("[#] Conversion completed successfully!")
        print(f"[*] Saved as: {output_file}")
        return True

    except KeyboardInterrupt:
        stop_loading.set()
        print("\n[!] Ctrl+C detected, stopping FFmpeg...")
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except:
                    pass
        if reader_thread and reader_thread.is_alive():
            reader_thread.join(timeout=1)
        anim_thread.join(timeout=1)
        print("[x] Conversion cancelled by user.")
        return False

    except subprocess.CalledProcessError as e:
        stop_loading.set()
        anim_thread.join()
        print("[x] Conversion failed!")
        if stderr_output:
            print("\n--- FFmpeg Error Log ---")
            print(stderr_output)
        return False

    except FileNotFoundError:
        stop_loading.set()
        anim_thread.join()
        print("[x] FFmpeg not found! Install FFmpeg and ensure it's in PATH.")
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
