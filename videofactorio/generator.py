"""Full-color ROM player with exact compression of repeated panel images."""
from pathlib import Path
import json
import math
from .blueprint import Builder, encode, VERSION

SIGNALS = json.loads(Path(__file__).with_name('signals.json').read_text())
T = dict(type='virtual', name='signal-T')
F = dict(type='virtual', name='signal-F')
ALL = dict(type='virtual', name='signal-everything')
RESET = dict(type='virtual', name='signal-R')


def radar(b, key, x, y, channel):
    b.add(key, 'radar', x, y, 3, 3,
          control_behavior=dict(mode=2, universe_channel=channel if isinstance(channel,dict) else SIGNALS[channel]))


def banks(width, height):
    # Every bus reaches the top and bottom edges: no routing corridors in the image.
    strip_width = max(1, 256 // height)
    return [(x, 0) for x in range(0, width, strip_width)]


def power_axis(size):
    intervals = math.ceil((size + 2) / 18)
    return [-1 + round(i * (size + 2) / intervals) for i in range(intervals + 1)]


def screen_holes(width, height, power='normal'):
    if power != 'normal':
        return set()
    return {(x+dx, y+dy) for x in power_axis(width)[1:-1]
            for y in power_axis(height)[1:-1] for dx in (-1,0) for dy in (-1,0)}


def plan_rom(frames,width,height,compression='runs'):
    if compression not in ('none','runs'):
        raise ValueError('Unknown compression mode')
    plans=[]
    for bx,by in banks(width,height):
        pw,ph=min(256//height,width-bx),height
        runs=[]
        for index,frame in enumerate(frames):
            blob=b''.join(frame[((by+y)*width+bx)*3:
                               ((by+y)*width+bx+pw)*3] for y in range(ph))
            if compression=='runs' and runs and runs[-1]['blob']==blob:
                runs[-1]['end']=index+1
            else:
                runs.append(dict(start=index,end=index+1,blob=blob))
        plans.append(dict(width=pw,height=ph,runs=runs))
    return plans


def screen(b, width, height, wireless, ox=0, oy=0, channel_offset=0,power='normal',radio_channels=None):
    b.constant('run',ox-6,oy,[(T,1)])
    b.by_id['run']['player_description']='ПУСК / ПАУЗА: включите или выключите комбинатор. Значение сигнала оставьте равным 1.'
    b.constant('reset',ox-6,oy+2,[(RESET,1)])
    b.by_id['reset']['control_behavior']['is_on']=False
    b.by_id['reset']['player_description']='СБРОС: включите для возврата к первому кадру, затем выключите для продолжения.'
    b.wire('run','reset',1,1)
    anchors = []
    pixels = []
    holes=screen_holes(width,height,power)
    if power=='normal':
        for ix,x in enumerate(power_axis(width)):
            for iy,y in enumerate(power_axis(height)):
                key='screen-sub-0-left' if ix==0 and iy==0 else f'screen-power-{ix}-{iy}'
                b.add(key,'substation',ox+x-1,oy+y-1,2,2)
    for bank,(bx,by) in enumerate(banks(width,height)):
        x0,y0 = ox+bx, oy+by
        pw,ph=min(256//height,width-bx),height
        chain = []
        for ly in range(ph):
            xs = list(range(pw))
            if ly % 2:
                xs.reverse()
            for lx in xs:
                if (bx+lx,by+ly) in holes:
                    continue
                index = ly*pw+lx
                key = f'pixel-{bx+lx}-{by+ly}'
                b.add(key,'small-lamp',x0+lx,y0+ly,always_on=True,
                    control_behavior=dict(use_colors=True,color_mode=2,rgb_signal=SIGNALS[index]))
                if chain:
                    b.wire(chain[-1],key,2,2)
                chain.append(key)
                pixels.append(dict(key=key,bank=bank,index=index,x=bx+lx,y=by+ly))
        anchors.append(chain[0] if wireless else chain[-1])
        if wireless:
            key=f'rx-{bank}'
            radar(b,key,x0,y0-6-3*(bank%2 if 256//height<3 else 0),
                  radio_channels[bank] if radio_channels else channel_offset+bank)
            b.wire(key,chain[0],2,2)
            if bank==0:
                b.wire('run',key,1,1)
    return anchors,pixels


def memory(b, frames, width, height, fps, wireless, ox=0, oy=0, channel_offset=0,plans=None,radio_channels=None):
    ticks_per_frame = 60//fps
    period = len(frames)*ticks_per_frame
    # Red feedback sees previous value + one; green output is the clean tick counter.
    b.add('clock','decider-combinator',ox-5,oy,1,2,control_behavior=dict(decider_conditions=dict(
        conditions=[dict(first_signal=T,comparator='<',constant=period),
                    dict(first_signal=RESET,comparator='=',constant=0,compare_type='and')],
        outputs=[dict(signal=T,copy_count_from_input=True)])))
    b.wire('clock','clock',3,1)
    b.add('frame-counter','arithmetic-combinator',ox-3,oy,1,2,
        control_behavior=dict(arithmetic_conditions=dict(first_signal=T,operation='/',
            second_constant=ticks_per_frame,output_signal=F)))
    b.wire('clock','frame-counter',4,2)
    b.add('clock-sub','substation',ox-7,oy+5,2,2)
    anchors=[]
    plans=plans if plans is not None else plan_rom(frames,width,height)
    for bank,plan in enumerate(plans):
        x0=ox+bank*8
        gates=[]
        for slot,run in enumerate(plan['runs']):
            frame_id=run['start']
            frame=run['blob']
            y0=oy+slot*3
            values=[]
            for ly in range(plan['height']):
                for lx in range(plan['width']):
                    offset=(ly*plan['width']+lx)*3
                    r,g,blue=frame[offset:offset+3]
                    values.append((SIGNALS[ly*plan['width']+lx],r*65536+g*256+blue))
            # A reserved frame tag makes frame integrity testable on the receiving bus.
            values.append((F,frame_id+1))
            data=f'data-{bank}-{frame_id}'
            gate=f'gate-{bank}-{frame_id}'
            b.constant(data,x0,y0,values)
            conditions=[dict(first_signal=F,comparator='=',constant=frame_id,
                            first_signal_networks=dict(red=True,green=False))]
            if run['end']>frame_id+1:
                conditions=[dict(first_signal=F,comparator='≥',constant=frame_id,
                                 first_signal_networks=dict(red=True,green=False)),
                            dict(first_signal=F,comparator='<',constant=run['end'],compare_type='and',
                                 first_signal_networks=dict(red=True,green=False))]
            b.add(gate,'decider-combinator',x0+2,y0,1,2,
                control_behavior=dict(decider_conditions=dict(
                    conditions=conditions,
                    outputs=[dict(signal=ALL,copy_count_from_input=True,
                        networks=dict(red=False,green=True))])))
            b.wire(data,gate,2,2)
            if gates:
                b.wire(gates[-1],gate,4,4)
                # Control is on the inputs, never on the output bus.
                b.wire(gates[-1],gate,1,1)
            gates.append(gate)
        # No red data output: red input is the shared frame address.
        if anchors:
            b.wire(anchors[-1],gates[0],1,1)
        else:
            b.route('frame-counter',gates[0],3,1)
        anchors.append(gates[0])
        for y in range(oy+7,oy+len(plan['runs'])*3+8,18):
            b.add(f'memory-sub-{bank}-{y}','substation',x0+5,y,2,2)
        if wireless:
            b.add(f'tx-sub-{bank}','substation',x0+5,oy-7,2,2)
            key=f'tx-{bank}'
            radar(b,key,x0,oy-5,radio_channels[bank] if radio_channels else channel_offset+bank)
            b.route(gates[0],key,4,2)
            if bank==0:
                b.route(key,'clock',1,1)
    return anchors


def generate(frames, width, height, fps=10, channel_offset=0,compression='runs',power='normal',radio_channels=None):
    if power not in ('normal','none'):
        raise ValueError('Питание экрана: normal или none')
    if fps not in (1,2,3,4,5,6,10,12,15,20,30):
        raise ValueError('FPS must divide 60 and leave at least two ticks per frame')
    if not 1 <= width <= 128 or not 1 <= height <= 128:
        raise ValueError('Dimensions must be 1..128')
    if not frames or any(len(frame)!=width*height*3 for frame in frames):
        raise ValueError('Invalid RGB frame data')
    if radio_channels is not None and (len(radio_channels)!=len(banks(width,height)) or
            len({(s['type'],s['name']) for s in radio_channels})!=len(radio_channels)):
        raise ValueError('Для каждой полосы нужен отдельный канал радара')
    if radio_channels is None and (channel_offset<0 or channel_offset+len(banks(width,height))>len(SIGNALS)):
        raise ValueError('Insufficient radio channel identifiers')
    plans=plan_rom(frames,width,height,compression)
    record_count=sum(len(p['runs']) for p in plans)
    if record_count>10000:
        raise ValueError(f'Слишком большая схема: {record_count:,} записей памяти; предел прототипа — 10 000. Уменьшите разрешение, FPS или длительность.')
    encoding=dict(mode=compression,layout_version=4,screen_power=power,
                  missing_pixels=len(screen_holes(width,height,power)),input_panel_frames=len(frames)*len(plans),
                  stored_panel_frames=record_count,
                  panel_runs=[len(p['runs']) for p in plans])
    encoding['uncompressed_player_combinators']=2*encoding['input_panel_frames']+4
    encoding['player_combinators']=2*encoding['stored_panel_frames']+4
    result={}
    for kind in ('screen','memory','combined'):
        title={'screen':'Экран','memory':'Память','combined':'Экран + память'}[kind]
        supply='' if kind=='memory' else (' — своё питание' if power=='none' else ' — подстанции')
        b=Builder(f'{title} {width}×{height}, {fps} кадров/с'+supply+' · by RomOSTiny')
        anchors=[]
        pixels=[]
        if kind!='memory':
            anchors,pixels=screen(b,width,height,kind=='screen',channel_offset=channel_offset,power=power,radio_channels=radio_channels)
        if kind!='screen':
            oy=height+12 if kind=='combined' else 0
            outputs=memory(b,frames,width,height,fps,kind=='memory',oy=oy,channel_offset=channel_offset,plans=plans,radio_channels=radio_channels)
            if kind=='combined':
                for source,target in zip(outputs,anchors):
                    b.route(source,target,4,2)
                b.route('run','clock',1,1)
                for y in range(7,oy+8,16):
                    key=f'bridge-sub-{y}'
                    # Bridge is outside the lamp area and ROM columns.
                    b.add(key,'substation',-12,y,2,2)
        b.power()
        result[kind]=dict(blueprint=b.json(),stats=b.stats(),pixels=pixels,encoding=encoding,
            ids={k:dict(number=e['entity_number'],name=e['name'],**e['position']) for k,e in b.by_id.items()})
    return result


def export(result, out, metadata):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    book=[]
    for index,(kind,data) in enumerate(result.items()):
        (out/f'{kind}.txt').write_text(encode(data['blueprint']),encoding='utf-8')
        (out/f'{kind}.json').write_text(json.dumps(data['blueprint'],ensure_ascii=False),encoding='utf-8')
        (out/f'{kind}-ids.json').write_text(json.dumps(dict(ids=data['ids'],pixels=data['pixels'])),encoding='utf-8')
        book.append(dict(index=index,**data['blueprint']))
    (out/'book.txt').write_text(encode(dict(blueprint_book=dict(item='blueprint-book',
        label='Видео · by RomOSTiny',active_index=0,version=VERSION,blueprints=book))),encoding='utf-8')
    report=dict(**metadata,encoding=result['memory']['encoding'],variants={k:v['stats'] for k,v in result.items()})
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report
