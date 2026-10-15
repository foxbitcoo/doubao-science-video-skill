#!/usr/bin/env python3
"""Render reviewed local clips + real narration. No network or credentials."""
import argparse
import json
import math
import re
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise ValueError(result.stderr[-1800:])
    return result.stdout


def probe(path):
    if shutil.which('ffprobe'):
        return json.loads(run(['ffprobe', '-v', 'error', '-show_format',
                               '-show_streams', '-of', 'json', str(path)]))
    # Some bundled FFmpeg runtimes omit ffprobe. Read only bounded metadata.
    result = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(path)],
                            capture_output=True, text=True)
    match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', result.stderr)
    if not match:
        raise ValueError('Could not read media duration: ' + str(path))
    streams = []
    for kind, codec in re.findall(r'Stream #[^\n]*?: (Video|Audio): ([^ ,\n]+)', result.stderr):
        streams.append({'codec_type': kind.lower(), 'codec_name': codec})
    duration = int(match[1])*3600 + int(match[2])*60 + float(match[3])
    return {'format': {'duration': str(duration)}, 'streams': streams,
            'metadata_method': 'ffmpeg_stderr_fallback'}


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Non-finite time')
    return value


def stamp(value, ass=False):
    ticks = round(value * (100 if ass else 1000))
    unit = 100 if ass else 1000
    seconds, fraction = divmod(ticks, unit)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return (f'{hours}:{minutes:02}:{seconds:02}.{fraction:02}' if ass else
            f'{hours:02}:{minutes:02}:{seconds:02},{fraction:03}')


def ass_text(value):
    # Prevent text from introducing ASS override tags or line-break commands.
    return value.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', ' ')


def render(manifest, output):
    if output.exists():
        raise ValueError('Output exists; choose a new filename')
    config = json.loads(manifest.read_text())
    segments = config['segments']
    if not segments:
        raise ValueError('No segments')
    font = config.get('font', 'sans-serif')
    if any(c in font for c in ',\r\n'):
        raise ValueError('Invalid font name')
    prepared, ids = [], set()
    for segment in segments:
        sid = segment['id']
        if not isinstance(sid, str) or sid in ids:
            raise ValueError('Segment IDs must be unique strings')
        ids.add(sid)
        video = (manifest.parent / segment['video']).resolve()
        audio = (manifest.parent / segment['audio']).resolve()
        vp, ap = probe(video), probe(audio)
        if not any(s['codec_type'] == 'video' for s in vp['streams']):
            raise ValueError('Missing video: ' + sid)
        if not any(s['codec_type'] == 'audio' for s in ap['streams']):
            raise ValueError('Missing narration: ' + sid)
        audio_duration = number(ap['format']['duration'])
        duration = audio_duration + 0.4
        start = number(segment.get('in', 0))
        end = number(segment.get('out', vp['format']['duration']))
        if not 0 <= start < end <= number(vp['format']['duration']) + 0.02:
            raise ValueError('Invalid source interval: ' + sid)
        cues = segment['cues']
        if not cues or ''.join(c['text'] for c in cues) != segment['narration']:
            raise ValueError('Subtitle text differs from narration: ' + sid)
        previous = 0
        for cue in cues:
            a, b = number(cue['start']), number(cue['end'])
            if not previous <= a < b <= duration:
                raise ValueError('Overlapping or out-of-range subtitle: ' + sid)
            if not cue['text'].strip():
                raise ValueError('Empty subtitle: ' + sid)
            previous = b
        prepared.append((segment, video, audio, duration, start, end))
    output.parent.mkdir(parents=True, exist_ok=True)
    srt_path = output.with_suffix('.srt')
    report_path = output.with_suffix('.report.json')
    if srt_path.exists() or report_path.exists():
        raise ValueError('Sidecar output exists; choose a new filename')
    srt, offset = [], 0
    with tempfile.TemporaryDirectory(prefix='science-render-', dir=output.parent) as temp:
        root = Path(temp)
        for index, (seg, video, audio, duration, start, end) in enumerate(prepared):
            events = [f'Dialogue: 1,0:00:00.00,{stamp(duration, True)},Label,,0,0,0,,AI生成画面与配音']
            for cue in seg['cues']:
                a, b = number(cue['start']), number(cue['end'])
                events.append(f'Dialogue: 0,{stamp(a, True)},{stamp(b, True)},Default,,0,0,0,,{ass_text(cue["text"])}')
                srt.append(f'{len(srt)+1}\n{stamp(offset+a)} --> {stamp(offset+b)}\n{cue["text"]}')
            ass = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n'
                   '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
                   f'Style: Default,{font},30,&H00FFFFFF,&H00000000,&H00202020,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,48,48,38,1\n'
                   f'Style: Label,{font},20,&H00FFFFFF,&H00000000,&H00202020,&H80000000,0,0,0,0,100,100,0,0,1,1,0,9,24,24,20,1\n'
                   '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n' + '\n'.join(events))
            (root / 'captions.ass').write_text(ass)
            speed = max(1, min(duration / (end-start), 1.5))
            vf = (f'trim=start={start}:end={end},setpts=(PTS-STARTPTS)*{speed},'
                  'scale=1280:720:force_original_aspect_ratio=decrease,'
                  'pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,'
                  f'tpad=stop_mode=clone:stop_duration={duration},ass=captions.ass')
            run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(video), '-i', str(audio),
                 '-map', '0:v:0', '-map', '1:a:0', '-vf', vf, '-af',
                 'loudnorm=I=-16:TP=-1.5:LRA=8,apad', '-t', str(duration),
                 '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
                 '-c:a', 'aac', '-ar', '48000', '-ac', '1', str(root / f'{index}.mp4')], cwd=root)
            offset += duration
        (root / 'concat.txt').write_text('\n'.join(f"file '{i}.mp4'" for i in range(len(prepared))))
        candidate = root / 'complete.mp4'
        run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'concat', '-safe', '0',
             '-i', 'concat.txt', '-c', 'copy', '-movflags', '+faststart', str(candidate)], cwd=root)
        run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(candidate), '-f', 'null', '-'])
        metadata = probe(candidate)
        # Exclusive publication: never replace an existing user file.
        with output.open('xb') as target, candidate.open('rb') as source:
            shutil.copyfileobj(source, target)
    srt_path.write_text('\n\n'.join(srt) + '\n')
    report = {'status': 'rendered_and_decoded', 'human_review': 'pending',
              'subtitle_timing_method': config.get('subtitle_timing_method', 'unspecified'),
              'segment_count': len(prepared), 'media': metadata}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'output': str(output), 'duration': metadata['format']['duration'],
                      'human_review': 'pending'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        render(args.manifest.resolve(), args.output.resolve())
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')
