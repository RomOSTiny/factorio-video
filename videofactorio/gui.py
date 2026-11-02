"""Простой настольный интерфейс: видео → разрешение → FPS → чертежи."""
from pathlib import Path
from datetime import datetime
import argparse
import math
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog,ttk
from .__main__ import convert
from .media import probe,read_frames,resize_nearest
from .radio import allocate
from .generator import banks
from .profiles import PRESETS,NAMES,SIZES,family,fps_options
from .paths import APP_ROOT

ROOT=APP_ROOT
BG='#101318'
CARD='#1a1f27'
LINE='#303844'
TEXT='#f5f3ee'
MUTED='#8f9aa9'
ACCENT='#ffb454'
DARK='#17120c'


class Button(tk.Canvas):
    def __init__(self,parent,text,command,width=120,height=44,accent=False,small=False):
        super().__init__(parent,width=width,height=height,bg=parent.cget('bg'),highlightthickness=0,
                         bd=0,takefocus=1,cursor='hand2')
        self.text=text
        self.command=command
        self.accent=accent
        self.small=small
        self.enabled=True
        self.selected=False
        self.hover=False
        self.bind('<Configure>',lambda _:self.draw())
        self.bind('<Enter>',lambda _:self.enter(True))
        self.bind('<Leave>',lambda _:self.enter(False))
        self.bind('<Button-1>',self.invoke)
        self.bind('<Return>',self.invoke)
        self.bind('<space>',self.invoke)
        self.bind('<FocusIn>',lambda _:self.draw())
        self.bind('<FocusOut>',lambda _:self.draw())

    def enter(self,on):
        self.hover=on
        self.draw()

    def set(self,text=None,enabled=None,selected=None):
        if text is not None:self.text=text
        if enabled is not None:self.enabled=enabled
        if selected is not None:self.selected=selected
        self.config(cursor='hand2' if self.enabled else 'arrow',takefocus=1 if self.enabled else 0)
        self.draw()

    def invoke(self,event=None):
        if self.enabled:
            self.focus_set()
            self.command()

    def draw(self):
        self.delete('all')
        w,h=self.winfo_width(),self.winfo_height()
        if w<3:return
        fill=ACCENT if self.accent and self.enabled else '#252c36' if self.hover and self.enabled else CARD
        outline=ACCENT if self.selected else LINE
        fg=DARK if self.accent and self.enabled else TEXT if self.enabled else '#59616c'
        if self.selected:fill='#352d23';fg=ACCENT
        if self.focus_get()==self and self.enabled:outline=ACCENT
        r=10
        self.create_polygon(1+r,1,w-r-1,1,w-1,1,w-1,1+r,w-1,h-r-1,w-1,h-1,w-r-1,h-1,
            r+1,h-1,1,h-1,1,h-r-1,1,r+1,1,1,smooth=True,fill=fill,outline=outline,width=1)
        self.create_text(w/2,h/2,text=self.text,fill=fg,font=('Segoe UI',10 if self.small else 11,'bold'))


def label(parent,text='',size=11,color=TEXT,bold=False,**kw):
    return tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,
                    font=('Segoe UI',size,'bold' if bold else 'normal'),**kw)


class App:
    def __init__(self,window,source='',initial_size=None):
        self.window=window
        self.messages=queue.Queue()
        self.source=None
        self.metadata=None
        self.initial_size=initial_size
        self.size=None
        self.fps=None
        self.result=None
        self.busy=False
        self.preview_frames=[]
        self.preview_size=(64,36)
        self.preview_fps=10
        self.preview_version=0
        self.preview_index=0
        self.playing=False
        self.preview_epoch=0
        self.setting_slider=False
        self.photo=None
        self.preview_start=0
        self.range_manual=False
        self.setting_range=False
        self.range_job=None
        window.title('by RomOSTiny')
        window.config(bg=BG)
        window.geometry('1080x720')
        window.minsize(1010,700)
        self.icon=tk.PhotoImage(width=32,height=32)
        self.icon.put(BG,to=(0,0,32,32))
        for x,y in [(5,5),(13,5),(21,5),(5,13),(21,13),(13,21)]:
            self.icon.put(ACCENT,to=(x,y,x+6,y+6))
        window.iconphoto(True,self.icon)
        outer=tk.Frame(window,bg=BG,padx=32,pady=25)
        outer.pack(fill='both',expand=True)
        header=tk.Frame(outer,bg=BG)
        header.pack(fill='x',pady=(0,24))
        label(header,'by RomOSTiny',size=11,color=ACCENT).pack(side='right')
        body=tk.Frame(outer,bg=BG)
        body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=0,minsize=402)
        body.columnconfigure(1,weight=1,minsize=460)
        body.rowconfigure(0,weight=1)
        left=tk.Frame(body,bg=BG,width=402)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,28))
        self.upload=Button(left,'+  Загрузить видео',self.browse,width=402,height=64)
        self.upload.pack(fill='x')
        self.filename=label(left,'MP4, GIF и другие видео',size=10,color=MUTED,anchor='w')
        self.filename.pack(fill='x',pady=(8,0))
        self.fileinfo=label(left,'',size=10,color=MUTED,anchor='w')
        self.fileinfo.pack(fill='x',pady=(0,19))
        self.size_title=label(left,'Разрешение',size=12,bold=True,anchor='w')
        self.size_title.pack(fill='x')
        self.sizebar=tk.Frame(left,bg=BG)
        self.sizebar.pack(fill='x',pady=(10,20))
        self.size_buttons={}
        self.fps_box=tk.Frame(left,bg=BG)
        self.fps_title=label(self.fps_box,'Кадров в секунду',size=12,bold=True,anchor='w')
        self.fps_title.pack(fill='x')
        self.fps_bar=tk.Frame(self.fps_box,bg=BG)
        self.fps_bar.pack(fill='x',pady=(10,0))
        self.fps_buttons={}
        self.choose_hint=label(left,'Сначала загрузите видео.',size=11,color=MUTED,anchor='w')
        self.choose_hint.pack(fill='x',pady=(4,14))
        self.spacer=tk.Frame(left,bg=BG,height=24)
        self.spacer.pack(fill='x')
        self.action=Button(left,'Создать чертежи',self.primary,width=402,height=54,accent=True)
        self.action.pack(fill='x')
        self.action.set(enabled=False)
        style=ttk.Style(window)
        style.theme_use('clam')
        style.configure('Video.Horizontal.TProgressbar',troughcolor=BG,background=ACCENT,bordercolor=BG,
                        lightcolor=ACCENT,darkcolor=ACCENT)
        self.progress=ttk.Progressbar(left,mode='indeterminate',style='Video.Horizontal.TProgressbar',maximum=100)
        self.status=label(left,'',size=10,color=MUTED,anchor='w',justify='left',wraplength=394)
        self.status.pack(fill='x',pady=(10,0))
        self.folder=label(left,'',size=10,color=ACCENT,anchor='w',cursor='hand2')
        self.folder.pack(fill='x',pady=(7,0))
        self.folder.bind('<Button-1>',lambda _:self.open_folder())
        right=tk.Frame(body,bg=CARD,padx=18,pady=17,highlightthickness=1,highlightbackground=LINE)
        right.grid(row=0,column=1,sticky='nsew')
        preview_header=tk.Frame(right,bg=CARD)
        preview_header.pack(fill='x')
        label(preview_header,'Предпросмотр',size=12,bold=True).pack(side='left')
        self.play=Button(preview_header,'▶  Смотреть',self.toggle_preview,width=130,height=34,small=True)
        self.play.pack(side='right')
        self.play.set(enabled=False)
        self.canvas=tk.Canvas(right,bg='#0c0e12',bd=0,highlightthickness=0,width=430,height=284)
        self.canvas.pack(fill='both',expand=True,pady=(17,12))
        self.canvas.bind('<Configure>',lambda _:self.draw_frame())
        self.timeline=tk.Scale(right,from_=0,to=1,orient='horizontal',showvalue=False,
            bg=CARD,fg=TEXT,troughcolor=BG,activebackground=ACCENT,highlightthickness=0,bd=0,
            sliderrelief='flat',sliderlength=12,width=5,resolution=1,command=self.seek)
        self.timeline.pack(fill='x')
        self.timeline.config(state='disabled')
        self.clock=label(right,'0:00 / 0:00',size=10,color=MUTED,anchor='w')
        self.clock.pack(fill='x',pady=(6,0))
        interval=tk.Frame(right,bg=CARD)
        interval.pack(fill='x',pady=(12,0))
        self.range_start=tk.StringVar(value='0')
        self.range_end=tk.StringVar(value='60')
        self.range_fields=[]
        for column,(text,variable) in enumerate([('Начало, с',self.range_start),('Конец, с',self.range_end)]):
            cell=tk.Frame(interval,bg=CARD)
            cell.pack(side='left',fill='x',expand=True,padx=(0,16 if column==0 else 0))
            label(cell,text,size=10,color=MUTED).pack(side='left',padx=(0,8))
            field=tk.Entry(cell,textvariable=variable,width=9,bg=BG,fg=TEXT,insertbackground=ACCENT,
                selectbackground=ACCENT,selectforeground=DARK,relief='flat',font=('Segoe UI',11),
                highlightthickness=1,highlightbackground=LINE,highlightcolor=ACCENT,disabledbackground=CARD)
            field.pack(side='left',fill='x',expand=True,ipady=4)
            field.config(state='disabled')
            self.range_fields.append(field)
        self.range_limit=label(self.fps_box,'',size=10,color=MUTED,anchor='w')
        self.range_limit.pack(fill='x',pady=(10,0))
        self.range_start.trace_add('write',lambda *_:self.range_changed())
        self.range_end.trace_add('write',lambda *_:self.range_changed())
        footer=tk.Frame(outer,bg=BG)
        footer.pack(fill='x',pady=(18,0))
        label(footer,'Factorio 2.1.24   ·   без модов   ·   по кругу',size=10,color=MUTED).pack(side='left')
        self.toast=label(footer,'',size=10,color=ACCENT)
        self.toast.pack(side='right')
        window.protocol('WM_DELETE_WINDOW',self.close)
        window.after(100,self.poll)
        window.after(50,self.animate)
        if source:
            window.after(100,lambda:self.load_source(source))

    def browse(self):
        if self.busy:return
        source=filedialog.askopenfilename(parent=self.window,title='Загрузить видео',filetypes=[
            ('Видео и анимация','*.mp4 *.gif *.mkv *.webm *.mov *.avi'),('Все файлы','*.*')])
        if source:self.load_source(source)

    def load_source(self,source):
        self.source=str(Path(source).resolve())
        self.metadata=None
        self.result=None
        self.size=None
        self.fps=None
        self.playing=False
        self.preview_frames=[]
        self.preview_version+=1
        self.range_manual=False
        if self.range_job:
            self.window.after_cancel(self.range_job)
            self.range_job=None
        for field in self.range_fields:field.config(state='disabled')
        self.timeline.config(state='disabled')
        self.filename.config(text=Path(source).name[:52])
        self.fileinfo.config(text='Читаем видео…')
        self.fps_box.pack_forget()
        self.choose_hint.config(text='Выберите разрешение.')
        self.choose_hint.pack(fill='x',pady=(4,14),before=self.spacer)
        self.status.config(text='')
        self.folder.config(text='')
        self.action.set(text='Создать чертежи',enabled=False)
        self.play.set(text='▶  Смотреть',enabled=False)
        for button in self.size_buttons.values():button.set(selected=False,enabled=False)
        self.draw_frame()
        target=self.source
        def work():
            try:self.messages.put(('metadata',target,probe(source)))
            except Exception as exc:self.messages.put(('error_metadata',target,str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def choose_size(self,size):
        if self.busy or not self.metadata or size not in self.size_buttons:return
        self.size=size
        self.fps=10
        self.invalidate()
        for key,button in self.size_buttons.items():button.set(selected=key==size)
        self.choose_hint.pack_forget()
        self.fps_box.pack(fill='x',pady=(0,0),before=self.spacer)
        for widget in self.fps_bar.winfo_children():widget.destroy()
        self.fps_buttons={}
        for index,value in enumerate(fps_options(size)):
            button=Button(self.fps_bar,str(value),lambda f=value:self.choose_fps(f),width=64,height=42,small=True)
            button.grid(row=0,column=index,padx=(0,8))
            button.set(selected=value==self.fps)
            self.fps_buttons[value]=button
        self.action.set(enabled=True)
        self.update_fileinfo()
        self.apply_range()

    def choose_fps(self,fps):
        if self.busy:return
        self.fps=fps
        self.invalidate()
        for value,button in self.fps_buttons.items():button.set(selected=value==fps)
        self.update_fileinfo()
        self.apply_range()

    def show_sizes(self):
        group=family(self.metadata['width'],self.metadata['height'])
        self.size_title.config(text='Разрешение · '+NAMES[group])
        for widget in self.sizebar.winfo_children():widget.destroy()
        self.size_buttons={}
        for index,size in enumerate(PRESETS[group]):
            name=f'{size[0]}×{size[1]}'
            button=Button(self.sizebar,name,lambda s=size:self.choose_size(s),width=73,height=42,small=True)
            button.grid(row=0,column=index,padx=(0,6 if index<4 else 0),sticky='ew')
            self.sizebar.columnconfigure(index,weight=1)
            self.size_buttons[size]=button

    def maximum_seconds(self):
        seconds=60
        if self.size and self.fps:
            seconds=min(seconds,(10000//len(banks(*self.size)))/self.fps)
        return seconds

    def selection(self):
        try:
            start=float(self.range_start.get().replace(',','.'))
            end=float(self.range_end.get().replace(',','.'))
        except ValueError:
            raise ValueError('Укажите начало и конец в секундах.') from None
        if not math.isfinite(start) or not math.isfinite(end) or start<0 or end<=start:
            raise ValueError('Начало должно быть не меньше нуля, конец — позже начала.')
        duration=self.metadata.get('seconds')
        if duration:
            if end>duration+.001 or start>=duration:
                raise ValueError(f'Видео длится {duration:.3f} с. Выберите фрагмент внутри него.')
            end=min(end,duration)
        maximum=self.maximum_seconds()
        if end-start>maximum+.001:
            raise ValueError(f'Для этого режима максимум {maximum:g} с. Сократите фрагмент или уменьшите качество/FPS.')
        end=min(end,start+maximum)
        return start,end

    def range_changed(self):
        if self.setting_range or not self.metadata:return
        self.range_manual=True
        self.invalidate()
        self.playing=False
        self.preview_version+=1
        self.play.set(text='▶  Смотреть',enabled=False)
        self.action.set(enabled=False)
        self.update_limit()
        if self.range_job:self.window.after_cancel(self.range_job)
        self.range_job=self.window.after(450,self.apply_range)

    def apply_range(self):
        self.range_job=None
        if not self.metadata:return
        try:
            self.selection()
        except ValueError as exc:
            self.preview_version+=1
            self.preview_frames=[]
            self.playing=False
            self.play.set(text='▶  Смотреть',enabled=False)
            self.timeline.config(state='disabled')
            self.action.set(enabled=False)
            self.status.config(text=str(exc),fg=ACCENT)
            self.canvas.delete('all')
            self.canvas.create_text(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2,
                text='Укажите фрагмент видео',fill=MUTED,font=('Segoe UI',12))
            return
        self.status.config(text='',fg=MUTED)
        self.action.set(enabled=bool(self.size and self.fps))
        self.request_preview()

    def update_fileinfo(self):
        duration=self.metadata.get('seconds')
        self.fileinfo.config(text=f'{self.metadata["width"]}×{self.metadata["height"]}'+
            (f'  ·  {duration:.1f} с' if duration else ''))
        maximum=self.maximum_seconds()
        if not self.range_manual:
            self.setting_range=True
            self.range_start.set('0')
            end=min(duration or maximum,maximum)
            self.range_end.set(f'{end:.3f}'.rstrip('0').rstrip('.'))
            self.setting_range=False
        self.update_limit()

    def update_limit(self):
        if not self.metadata:return
        maximum=self.maximum_seconds()
        try:
            start=float(self.range_start.get().replace(',','.'))
            if not math.isfinite(start):start=0
        except ValueError:start=0
        duration=self.metadata.get('seconds')
        if duration is not None:
            maximum=min(maximum,max(0,duration-max(0,start)))
        value=f'{maximum:.3f}'.rstrip('0').rstrip('.').replace('.',',')
        self.range_limit.config(text=f'Максимальная длительность: {value} с')

    def invalidate(self):
        self.result=None
        self.action.set(text='Создать чертежи')
        self.status.config(text='')
        self.folder.config(text='')
        self.toast.config(text='')

    def request_preview(self):
        if not self.metadata:return
        self.playing=False
        self.play.set(text='▶  Смотреть',enabled=False)
        self.preview_frames=[]
        self.preview_version+=1
        version=self.preview_version
        source=self.source
        size=self.size or PRESETS[family(self.metadata['width'],self.metadata['height'])][2]
        fps=self.fps or 10
        start,end=self.selection()
        seconds=end-start
        self.preview_start=start
        self.draw_frame()
        def work():
            try:
                frames=read_frames(source,*size,fps,seconds,start)
                self.messages.put(('preview',version,size,fps,frames))
            except Exception as exc:self.messages.put(('error_preview',version,str(exc)))
        threading.Thread(target=work,daemon=True).start()

    @staticmethod
    def time_text(seconds):
        return f'{int(seconds)//60}:{int(seconds)%60:02d}'

    def draw_frame(self):
        self.canvas.delete('all')
        w,h=self.canvas.winfo_width(),self.canvas.winfo_height()
        if not self.preview_frames:
            self.canvas.create_text(w/2,h/2,text='Ваше видео будет здесь' if not self.metadata else 'Готовим предпросмотр…',
                                    fill=MUTED,font=('Segoe UI',12))
            return
        pw,ph=self.preview_size
        frame=self.preview_frames[self.preview_index]
        scale=min(max(1,w)/pw,max(1,h)/ph)
        tw,th=max(1,round(pw*scale)),max(1,round(ph*scale))
        rgb=resize_nearest(frame,pw,ph,tw,th)
        self.photo=tk.PhotoImage(data=f'P6\n{tw} {th}\n255\n'.encode()+rgb,format='PPM')
        self.canvas.create_image(w/2,h/2,image=self.photo)
        self.clock.config(text=f'{self.time_text(self.preview_start+self.preview_index/self.preview_fps)} / '
                               f'{self.time_text(self.preview_start+len(self.preview_frames)/self.preview_fps)}')
        self.setting_slider=True
        self.timeline.set(self.preview_index)
        self.setting_slider=False

    def toggle_preview(self):
        if not self.preview_frames:return
        self.playing=not self.playing
        self.preview_epoch=time.monotonic()-self.preview_index/self.preview_fps
        self.play.set(text='Ⅱ  Пауза' if self.playing else '▶  Смотреть')

    def seek(self,value):
        if self.setting_slider or not self.preview_frames:return
        index=min(len(self.preview_frames)-1,max(0,round(float(value))))
        # Scale callbacks can arrive after .set(); ignore updates of the current frame.
        if index==self.preview_index:return
        self.preview_index=index
        self.playing=False
        self.play.set(text='▶  Смотреть')
        self.draw_frame()

    def animate(self):
        if self.playing and self.preview_frames:
            index=int((time.monotonic()-self.preview_epoch)*self.preview_fps)%len(self.preview_frames)
            if index!=self.preview_index:
                self.preview_index=index
                self.draw_frame()
        self.window.after(25,self.animate)

    def primary(self):
        if self.result:
            CopyDialog(self)
        else:self.begin()

    def begin(self):
        if not self.source or not self.size or self.fps is None or self.busy:return
        try:
            start,end=self.selection()
        except ValueError:
            self.apply_range()
            return
        if self.range_job:
            self.window.after_cancel(self.range_job)
            self.range_job=None
        self.busy=True
        self.upload.set(enabled=False)
        for field in self.range_fields:field.config(state='disabled')
        for button in [*self.size_buttons.values(),*self.fps_buttons.values()]:button.set(enabled=False)
        self.action.set(text='Создаём…',enabled=False)
        self.status.config(text='Готовим видео…',fg=MUTED)
        self.progress.pack(fill='x',pady=(10,0),before=self.status)
        self.progress.start(12)
        out=ROOT/'output'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        source,size,fps=self.source,self.size,self.fps
        seconds=end-start
        def work():
            try:
                channels=allocate(source,*size,fps,start=start,seconds=seconds)
                report=convert(source,out,*size,fps,seconds,start=start,compression='runs',power='both',radio_channels=channels,
                               progress=lambda text:self.messages.put(('progress',text)))
                self.messages.put(('done',out,report))
            except Exception as exc:self.messages.put(('error_convert',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def finish(self):
        self.busy=False
        self.progress.stop()
        self.progress.pack_forget()
        self.upload.set(enabled=True)
        for field in self.range_fields:field.config(state='normal')
        for button in [*self.size_buttons.values(),*self.fps_buttons.values()]:button.set(enabled=True)
        self.action.set(enabled=True)

    def poll(self):
        try:
            while True:
                item=self.messages.get_nowait()
                kind=item[0]
                if kind=='metadata':
                    if item[1]!=self.source:continue
                    self.metadata=item[2]
                    self.update_fileinfo()
                    for field in self.range_fields:field.config(state='normal')
                    self.show_sizes()
                    if self.initial_size:
                        size=self.initial_size
                        self.initial_size=None
                        if size not in self.size_buttons:
                            size=min(self.size_buttons,key=lambda s:abs(max(s)-max(size)))
                        self.choose_size(size)
                    else:self.apply_range()
                elif kind=='error_metadata':
                    if item[1]!=self.source:continue
                    self.fileinfo.config(text='Не получилось открыть видео')
                    self.status.config(text=item[2],fg=ACCENT)
                elif kind=='preview':
                    _,version,size,fps,frames=item
                    if version!=self.preview_version:continue
                    self.preview_size=size
                    self.preview_fps=fps
                    self.preview_frames=frames
                    self.preview_index=0
                    self.timeline.config(to=len(frames)-1,state='normal')
                    self.play.set(enabled=True)
                    self.draw_frame()
                elif kind=='error_preview':
                    if item[1]!=self.preview_version:continue
                    self.canvas.delete('all')
                    self.canvas.create_text(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2,
                        text='Предпросмотр недоступен',fill=MUTED,font=('Segoe UI',12))
                elif kind=='progress':self.status.config(text=item[1])
                elif kind=='error_convert':
                    self.finish()
                    self.action.set(text='Попробовать ещё раз')
                    self.status.config(text=item[1],fg=ACCENT)
                elif kind=='done':
                    self.finish()
                    self.result=item[1]
                    self.report=item[2]
                    self.action.set(text='Скопировать чертежи')
                    self.status.config(text='Готово! Можно переносить на завод.',fg=ACCENT)
                    self.folder.config(text='Открыть папку результата ↗')
        except queue.Empty:pass
        self.window.after(80,self.poll)

    def copy(self,kind):
        text=(self.result/f'{kind}.txt').read_text(encoding='utf-8')
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.toast.config(text='Чертёж скопирован ✓')

    def open_folder(self):
        if self.result:os.startfile(self.result)

    def close(self):
        if self.busy:
            self.status.config(text='Дождитесь завершения — сохраняем чертежи.',fg=ACCENT)
        else:self.window.destroy()


class CopyDialog:
    def __init__(self,app):
        self.app=app
        self.window=tk.Toplevel(app.window)
        self.window.title('Скопировать чертёж')
        self.window.config(bg=BG)
        self.window.resizable(False,False)
        self.window.transient(app.window)
        self.window.geometry(f'540x410+{app.window.winfo_rootx()+250}+{app.window.winfo_rooty()+140}')
        self.window.grab_set()
        self.window.bind('<Escape>',lambda _:self.window.destroy())
        self.body=tk.Frame(self.window,bg=BG,padx=30,pady=25)
        self.body.pack(fill='both',expand=True)
        self.layout=None
        self.power=None
        self.stage1()

    def clear(self,step,title):
        for widget in self.body.winfo_children():widget.destroy()
        label(self.body,step,size=10,color=ACCENT,anchor='w').pack(fill='x')
        label(self.body,title,size=21,bold=True,anchor='w').pack(fill='x',pady=(9,24))

    def option(self,title,command):
        button=Button(self.body,title,command,width=478,height=66)
        button.pack(fill='x',pady=(0,12))
        return button

    def back(self,command):
        button=Button(self.body,'← Назад',command,width=104,height=36,small=True)
        button.pack(anchor='w',pady=(8,0))

    def stage1(self):
        self.clear('1 / 2','Как разместим?')
        self.option('Раздельно: экран и память',lambda:self.stage2('separate'))
        self.option('Всё вместе',lambda:self.stage2('combined'))

    def stage2(self,layout):
        self.layout=layout
        self.clear('2 / 2','Опоры у экрана?')
        self.option('С опорами ЛЭП',lambda:self.choose_power('normal'))
        self.option('Без опор · своё питание',lambda:self.choose_power('none'))
        self.back(self.stage1)

    def choose_power(self,power):
        self.power=power
        if self.layout=='combined':
            try:
                self.app.copy('combined' if power=='normal' else 'combined-no-poles')
                self.window.destroy()
            except (OSError,tk.TclError) as exc:self.error(str(exc))
        else:self.separate()

    def separate(self):
        self.clear('ГОТОВО','Экран и память')
        self.screen=self.option('Скопировать экран',lambda:self.copy_block('screen'))
        self.memory=self.option('Скопировать память',lambda:self.copy_block('memory'))
        self.note=label(self.body,'Вставляйте строки в импорт чертежей Factorio.',size=10,color=MUTED,anchor='w',wraplength=470)
        self.note.pack(fill='x',pady=(0,8))
        self.back(lambda:self.stage2('separate'))

    def copy_block(self,kind):
        try:
            self.app.copy('screen-no-poles' if kind=='screen' and self.power=='none' else kind)
            (self.screen if kind=='screen' else self.memory).set(text=('Экран' if kind=='screen' else 'Память')+' скопирован'+('а' if kind=='memory' else '')+' ✓')
        except (OSError,tk.TclError) as exc:self.error(str(exc))

    def error(self,text):
        self.app.toast.config(text='Не удалось скопировать')
        self.window.destroy()
        self.app.status.config(text=text,fg=ACCENT)


def main():
    parser=argparse.ArgumentParser(description='Видео в чертежи · by RomOSTiny')
    parser.add_argument('--source',default='')
    parser.add_argument('--size',choices=[name for name,_ in SIZES])
    args=parser.parse_args()
    (ROOT/'tmp').mkdir(exist_ok=True)
    os.environ['TEMP']=os.environ['TMP']=str(ROOT/'tmp')
    window=tk.Tk()
    App(window,args.source,dict(SIZES).get(args.size))
    window.mainloop()


if __name__=='__main__':main()
