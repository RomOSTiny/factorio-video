"""Разрешения по форме видео и рекомендуемые варианты частоты кадров."""
PRESETS={
    'square':[(16,16),(32,32),(64,64),(96,96),(128,128)],
    'wide':[(16,9),(32,18),(64,36),(96,54),(128,72)],
    'portrait':[(9,16),(18,32),(36,64),(54,96),(72,128)],
}
NAMES={'square':'1:1','wide':'16:9','portrait':'9:16'}
SIZES=[(f'{w}×{h}',(w,h)) for group in PRESETS.values() for w,h in group]


def family(width,height):
    if abs(width/height-1)<=.05:
        return 'square'
    return 'wide' if width>height else 'portrait'


def fps_options(size):
    pixels=size[0]*size[1]
    if pixels<=1024:return (5,10,15,20,30)
    if pixels<=2500:return (5,10,15,20)
    if pixels<=6000:return (5,10,15)
    return (5,10)
