"""Command-line converter. Run: python -m videofactorio input.mp4 --help."""
from pathlib import Path
import argparse
import json
import os
import time
from .generator import generate,export,screen_holes
from .media import read_frames,preview
from .paths import APP_ROOT


def convert(source,out,width=16,height=16,fps=10,seconds=3,start=0,channel_offset=0,compression='runs',power='both',progress=None,radio_channels=None):
    root=APP_ROOT
    (root/'tmp').mkdir(exist_ok=True)
    os.environ['TMP']=os.environ['TEMP']=str(root/'tmp')
    started=time.perf_counter()
    if progress:
        progress('Читаю и уменьшаю видео…')
    correction={}
    frames=read_frames(source,width,height,fps,seconds,start,info=correction)
    decoded=time.perf_counter()
    if power not in ('both','normal','none'):
        raise ValueError('Питание: both, normal или none')
    if progress:
        progress(f'Собираю память и экран: {len(frames)} кадров…')
    result=generate(frames,width,height,fps,channel_offset,compression,'none' if power=='none' else 'normal',radio_channels)
    if power=='both':
        full=generate(frames,width,height,fps,channel_offset,compression,'none',radio_channels)
        for kind in ('screen','combined'):
            result[kind+'-no-poles']=full[kind]
    generated=time.perf_counter()
    if progress:
        progress('Записываю чертежи и книгу…')
    report=export(result,out,dict(source=str(Path(source).resolve()),width=width,height=height,
        fps=fps,frames=len(frames),seconds=len(frames)/fps,start_seconds=start,
        requested_end_seconds=start+seconds,end_seconds=start+len(frames)/fps,
        channel_offset=channel_offset,radio_channels=radio_channels,color_correction=correction,
        factorio='2.1.24',codec='RGB24, vertical strips up to 256 signals, exact repeated-strip runs',screen_power=power,
        status='prototype; see live verification report for tested modes'))
    if progress:
        progress('Создаю предпросмотры…')
    preview(frames,width,height,fps,Path(out)/'preview.mp4')
    if power!='none':
        holes=screen_holes(width,height)
        masked=[]
        for frame in frames:
            pixels=bytearray(frame)
            for x,y in holes:
                offset=(y*width+x)*3
                pixels[offset:offset+3]=b'\x00\x00\x00'
            masked.append(bytes(pixels))
        preview(masked,width,height,fps,Path(out)/'preview-with-poles.mp4')
    # Raw frames are retained for exact live comparison; small test files stay on E:.
    (Path(out)/'frames.rgb').write_bytes(b''.join(frames))
    report['timing_seconds']=dict(decode=decoded-started,generate=generated-decoded,
        export_and_preview=time.perf_counter()-generated,total=time.perf_counter()-started)
    report['book_bytes']=(Path(out)/'book.txt').stat().st_size
    (Path(out)/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description='Видео → три чертежа Factorio')
    parser.add_argument('source',type=Path)
    parser.add_argument('--out',type=Path,default=APP_ROOT/'output'/'converted')
    parser.add_argument('--width',type=int,default=16)
    parser.add_argument('--height',type=int,default=16)
    parser.add_argument('--fps',type=int,default=10)
    parser.add_argument('--seconds',type=float,default=3)
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--channel-offset',type=int,default=0)
    parser.add_argument('--compression',choices=['none','runs'],default='runs')
    parser.add_argument('--power',choices=['both','normal','none'],default='both',
        help='Питание экрана: оба варианта, обычные подстанции или собственное питание')
    args=parser.parse_args()
    try:
        report=convert(**vars(args))
    except (ValueError,RuntimeError) as exc:
        parser.exit(1,str(exc)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
