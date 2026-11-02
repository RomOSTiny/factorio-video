"""Small dependency-free blueprint writer with geometry checks."""
import base64
import json
import math
import heapq
import zlib

VERSION = (2 << 48) | (1 << 32) | (24 << 16)


def encode(data):
    return '0' + base64.b64encode(zlib.compress(json.dumps(data, separators=(',', ':'),
        ensure_ascii=False).encode(), 9)).decode()


def decode(text):
    return json.loads(zlib.decompress(base64.b64decode(text.strip()[1:])))


class Builder:
    def __init__(self, label):
        self.label = label
        self.entities = []
        self.wires = set()
        self.occupied = set()
        self.by_id = {}

    def add(self, key, name, x, y, width=1, height=1, **settings):
        if key in self.by_id:
            raise ValueError(f'Duplicate entity {key}')
        tiles = {(x + dx, y + dy) for dx in range(width) for dy in range(height)}
        if self.occupied & tiles:
            raise ValueError(f'Entity overlap: {key} at {x},{y}')
        self.occupied.update(tiles)
        entity = dict(entity_number=len(self.entities)+1, name=name,
                      position=dict(x=x+width/2, y=y+height/2), **settings)
        self.entities.append(entity)
        self.by_id[key] = entity
        return key

    def wire(self, a, b, ca=1, cb=1, reach=9):
        ea, eb = self.by_id[a], self.by_id[b]
        distance = math.dist(tuple(ea['position'].values()), tuple(eb['position'].values()))
        if distance > reach + 1e-6:
            raise ValueError(f'Wire too long: {a} -> {b}: {distance}')
        endpoints = sorted([(ea['entity_number'], ca), (eb['entity_number'], cb)])
        self.wires.add((*endpoints[0], *endpoints[1]))

    def route(self, a, b, ca=1, cb=1):
        start=tuple(self.by_id[a]['position'].values())
        target=tuple(self.by_id[b]['position'].values())
        if math.dist(start,target)<=8:
            self.wire(a,b,ca,cb)
            return
        # Search may move away from the target to go around a solid lamp panel.
        queue=[]
        costs={}
        parents={}
        for dx in range(-7,8):
            for dy in range(-7,8):
                p=(round(start[0]-.5)+dx,round(start[1]-.5)+dy)
                dist=math.dist(start,(p[0]+.5,p[1]+.5))
                if p not in self.occupied and dist<=8:
                    costs[p]=dist
                    parents[p]=None
                    heapq.heappush(queue,(dist+1.1*math.dist((p[0]+.5,p[1]+.5),target),dist,p))
        goal=None
        steps=[(dx,dy) for dx in (-6,-4,-1,0,1,4,6) for dy in (-6,-4,-1,0,1,4,6)
               if 0<math.hypot(dx,dy)<=8]
        for _ in range(50000):
            if not queue:
                break
            _,cost,p=heapq.heappop(queue)
            if cost>costs[p]:
                continue
            if math.dist((p[0]+.5,p[1]+.5),target)<=8:
                goal=p
                break
            for dx,dy in steps:
                q=(p[0]+dx,p[1]+dy)
                new=cost+math.hypot(dx,dy)+.1
                if q in self.occupied or new>=costs.get(q,float('inf')):
                    continue
                costs[q]=new
                parents[q]=p
                heapq.heappush(queue,(new+1.1*math.dist((q[0]+.5,q[1]+.5),target),new,q))
        if goal is None:
            raise ValueError(f'Cannot route {a} -> {b}')
        path=[]
        while goal is not None:
            path.append(goal)
            goal=parents[goal]
        current,connector=a,ca
        for x,y in reversed(path):
            key=f'route-{len(self.entities)}'
            self.add(key,'medium-electric-pole',x,y)
            self.wire(current,key,connector,cb%2 or 2)
            current,connector=key,cb%2 or 2
        self.wire(current,b,connector,cb)

    def constant(self, key, x, y, values):
        filters = [dict(index=i+1, **signal, count=value, comparator='=',quality='normal')
                   for i,(signal,value) in enumerate(values) if value]
        sections = [dict(index=i//1000+1, filters=[dict(f,index=j+1)
                    for j,f in enumerate(filters[i:i+1000])]) for i in range(0,len(filters),1000)]
        return self.add(key, 'constant-combinator', x, y,
            control_behavior=dict(sections=dict(sections=sections)))

    def power(self):
        subs = [(k,e) for k,e in self.by_id.items() if e['name'] == 'substation']
        for i,(a,ea) in enumerate(subs):
            for b,eb in subs[i+1:]:
                if math.dist(tuple(ea['position'].values()), tuple(eb['position'].values())) <= 18:
                    self.wire(a,b,5,5,18)

    def json(self):
        return dict(blueprint=dict(item='blueprint', label=self.label, version=VERSION,
            entities=self.entities, wires=[list(w) for w in sorted(self.wires)]))

    def stats(self):
        counts = {}
        for e in self.entities:
            counts[e['name']] = counts.get(e['name'],0)+1
        xs=[p[0] for p in self.occupied]
        ys=[p[1] for p in self.occupied]
        return dict(entities=len(self.entities), wires=len(self.wires), counts=counts,
                    combinators=sum(n for name,n in counts.items() if 'combinator' in name),
                    width_tiles=max(xs)-min(xs)+1,height_tiles=max(ys)-min(ys)+1)
