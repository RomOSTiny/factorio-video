"""Автоматические назначения радаров в пространстве редко используемых сигналов."""
from pathlib import Path
import hashlib,json,random,os
import msvcrt
from .generator import banks
from .paths import APP_ROOT

ROOT=APP_ROOT

def allocate(source,width,height,fps,start=0,seconds=None):
    digest=hashlib.sha256()
    with Path(source).open('rb') as file:
        while chunk:=file.read(1024*1024):
            digest.update(chunk)
    key=digest.hexdigest()+f':{width}x{height}:{fps}:lamp-brightness-v1'
    if start or seconds is not None:
        key+=f':start={start:.9g}:seconds={seconds:.9g}' if seconds is not None else f':start={start:.9g}'
    count=len(banks(width,height))
    folder=ROOT/'settings'
    folder.mkdir(exist_ok=True)
    path=folder/'radio-assignments.json'
    with (folder/'radio.lock').open('a+b') as lock:
        if lock.tell()==0:
            lock.write(b'0');lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
        try:
            assignments=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            if key in assignments:
                return assignments[key]
            used={(s['type'],s['name']) for group in assignments.values() for s in group}
            catalog=json.loads(Path(__file__).with_name('radio-signals.json').read_text(encoding='utf-8'))
            available=[s for s in catalog if (s['type'],s['name']) not in used]
            if len(available)<count:
                raise ValueError('Свободные каналы этой установки закончились. Обратитесь к автору программы: существующие назначения сохранены.')
            selected=random.Random(key).sample(available,count)
            assignments[key]=selected
            temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps(assignments,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temporary,path)
            return selected
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
