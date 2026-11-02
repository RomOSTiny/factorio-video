"""Decode and preview media using the user's FFmpeg installation."""
from pathlib import Path
import shutil
import subprocess
import json
import math
from .paths import APP_ROOT,BUNDLE_ROOT


def executable(name):
    for root in (APP_ROOT,BUNDLE_ROOT):
        bundled=root/(name+'.exe')
        if bundled.is_file():
            return str(bundled)
    found=shutil.which(name)
    if not found:
        raise RuntimeError(f'Не найден {name}. Установите FFmpeg и добавьте его в PATH.')
    return found


def run(args, **kwargs):
    import os
    return subprocess.run(args,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,**kwargs)


def brighten_dark_video(raw,width,height):
    """Lift dark midtones for lamps; preserve pure black and already bright artwork."""
    size=width*height*3
    count=len(raw)//size
    samples=[]
    frame_ids=sorted({i*(count-1)//7 for i in range(8)})
    for index in frame_ids:
        begin=index*size
        for pixel in range(0,width*height,max(1,width*height//512)):
            offset=begin+pixel*3
            peak=max(raw[offset:offset+3])
            if peak>4:samples.append(peak)
    median=sorted(samples)[len(samples)//2] if samples else 0
    gamma=1.0
    if 4<median<160:
        gamma=max(.55,min(1.0,math.log(160/255)/math.log(median/255)))
        lut=bytes(round(255*(value/255)**gamma) for value in range(256))
        raw=raw.translate(lut)
    return raw,dict(mode='automatic lamp brightness',gamma=gamma,source_peak_median=median)


def read_frames(source, width, height, fps, seconds, start=0,info=None):
    if not Path(source).is_file():
        raise ValueError('Видеофайл не найден')
    if not math.isfinite(seconds) or not math.isfinite(start) or seconds<=0 or seconds>60 or start<0:
        raise ValueError('Длительность должна быть от одного кадра до 60 секунд, начало — не меньше нуля.')
    if not 1<=width<=128 or not 1<=height<=128 or fps not in (1,2,3,4,5,6,10,12,15,20,30):
        raise ValueError('Неподдерживаемое разрешение или частота кадров')
    expected=math.ceil(seconds*fps-1e-9)
    if expected<1 or expected*width*height*3>256*1024*1024:
        raise ValueError('Выберите хотя бы один кадр; объём распакованного видео должен быть не больше 256 МиБ.')
    vf=(f'fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease:flags=area,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1')
    result=run([executable('ffmpeg'),'-v','error','-nostdin','-ss',str(start),'-i',str(source),
        '-t',str(seconds),'-an','-vf',vf,'-frames:v',str(expected),'-f','rawvideo','-pix_fmt','rgb24','pipe:1'],
        capture_output=True,timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    size=width*height*3
    if not result.stdout or len(result.stdout)%size:
        raise ValueError('В выбранном фрагменте нет кадров. Проверьте начало и длительность.')
    raw,correction=brighten_dark_video(result.stdout,width,height)
    if info is not None:info.update(correction)
    return [raw[i:i+size] for i in range(0,len(raw),size)]


def probe(source):
    """Read local metadata without decoding the video."""
    if not Path(source).is_file():
        raise ValueError('Видеофайл не найден')
    result=run([executable('ffprobe'),'-v','error','-select_streams','v:0',
        '-show_entries','format=duration:stream=width,height,avg_frame_rate,duration:stream_tags=rotate:stream_side_data=rotation',
        '-of','json',str(source)],capture_output=True,timeout=30)
    if result.returncode:
        raise ValueError('Не удалось прочитать видео. Проверьте формат и целостность файла.')
    data=json.loads(result.stdout)
    if not data.get('streams'):
        raise ValueError('В файле нет видеодорожки')
    stream=data['streams'][0]
    duration=data.get('format',{}).get('duration',stream.get('duration'))
    try:
        duration=float(duration)
        if not math.isfinite(duration) or duration<=0:
            duration=None
    except (ValueError,TypeError):
        duration=None
    rotation=stream.get('tags',{}).get('rotate',0)
    for side in stream.get('side_data_list',[]):
        if 'rotation' in side:
            rotation=side['rotation']
            break
    try:
        rotation=float(rotation)
        quarter_turn=math.isfinite(rotation) and round(rotation/90)%2
    except (ValueError,TypeError):
        quarter_turn=False
    width,height=stream['width'],stream['height']
    if quarter_turn:
        width,height=height,width
    return dict(width=width,height=height,seconds=duration)


def resize_nearest(frame,width,height,target_width,target_height):
    """Nearest-neighbour RGB resize, without large intermediate zoom images."""
    xs=[min(width-1,x*width//target_width)*3 for x in range(target_width)]
    rows={}
    result=[]
    for y in range(target_height):
        source_y=min(height-1,y*height//target_height)
        if source_y not in rows:
            start=source_y*width*3
            rows[source_y]=b''.join(frame[start+x:start+x+3] for x in xs)
        result.append(rows[source_y])
    return b''.join(result)


def preview(frames,width,height,fps,out):
    scale=max(1,min(768//width,768//height))
    result=run([executable('ffmpeg'),'-v','error','-nostdin','-y','-f','rawvideo','-pix_fmt','rgb24',
        '-s',f'{width}x{height}','-r',str(fps),'-i','pipe:0','-an','-vf',f'scale=iw*{scale}:ih*{scale}:flags=neighbor,pad=ceil(iw/2)*2:ceil(ih/2)*2',
        '-c:v','libx264','-pix_fmt','yuv420p',str(out)],input=b''.join(frames),capture_output=True,timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
