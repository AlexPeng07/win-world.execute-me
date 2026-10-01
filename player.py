#!/usr/bin/env python3
"""A terminal music video. Python standard library + Windows Media Foundation audio."""
from __future__ import annotations
import argparse, bisect, json, os, signal, subprocess
import sys, threading, time, unicodedata
from pathlib import Path

from win import winconsole

ROOT = Path(__file__).resolve().parent
DIM, NORMAL, BRIGHT, WHITE = 0, 1, 2, 3
STYLES = {0:'\x1b[0;38;5;137m',1:'\x1b[0;38;5;215m',2:'\x1b[1;38;5;221m',3:'\x1b[1;38;5;230m',4:'\x1b[1;38;5;203m',5:'\x1b[0;38;5;94m',6:'\x1b[0;38;5;58m'}

FONT = {
'A':['01110','11011','11111','11011','11011'], 'B':['11110','11011','11110','11011','11110'],
'C':['01111','11000','11000','11000','01111'], 'D':['11110','11011','11011','11011','11110'],
'E':['11111','11000','11110','11000','11111'], 'F':['11111','11000','11110','11000','11000'],
'G':['01111','11000','11011','11011','01111'], 'H':['11011','11011','11111','11011','11011'],
'I':['11111','00100','00100','00100','11111'], 'J':['00111','00011','00011','11011','01110'],
'K':['11011','11110','11100','11110','11011'], 'L':['11000','11000','11000','11000','11111'],
'M':['10001','11011','10101','10001','10001'], 'N':['11001','11101','11111','10111','10011'],
'O':['01110','11011','11011','11011','01110'], 'P':['11110','11011','11110','11000','11000'],
'Q':['01110','11011','11011','01110','00011'], 'R':['11110','11011','11110','11101','11011'],
'S':['01111','11000','01110','00011','11110'], 'T':['11111','00100','00100','00100','00100'],
'U':['11011','11011','11011','11011','01110'], 'V':['11011','11011','11011','01110','00100'],
'W':['10001','10001','10101','11011','10001'], 'X':['11011','01110','00100','01110','11011'],
'Y':['11011','11011','01110','00100','00100'], 'Z':['11111','00011','00110','01100','11111'],
'0':['01110','11011','11011','11011','01110'], '1':['00100','01100','00100','00100','01110'],
'2':['11110','00011','01110','11000','11111'], '3':['11110','00011','01110','00011','11110'],
'4':['11011','11011','11111','00011','00011'], '5':['11111','11000','11110','00011','11110'],
'6':['01111','11000','11110','11011','01110'], '7':['11111','00011','00110','01100','01100'],
'8':['01110','11011','01110','11011','01110'], '9':['01110','11011','01111','00011','11110'],
';':['00000','00100','00000','00100','01000'], '.':['00000','00000','00000','00000','00100'],
'(':['00010','00100','00100','00100','00010'], ')':['01000','00100','00100','00100','01000'],
'-':['00000','00000','11111','00000','00000'], ' ':['00000']*5,
}

# Glyphs whose East Asian Width is Ambiguous count as one cell here, which is what the
# author's macOS terminal did. A Windows console sizes a cell from the font, so a CJK
# fallback can double them and shift every line after it. win/calibrate.py measures which
# glyphs the running console really draws wide; those go here, by name, from config.json.
AMBIGUOUS_WIDE = set()

def cw(ch):
    if unicodedata.combining(ch): return 0
    eaw=unicodedata.east_asian_width(ch)
    if eaw=='A': return 2 if ch in AMBIGUOUS_WIDE else 1
    return 2 if eaw in ('W','F') else 1

def width(s): return sum(cw(c) for c in s)

def crop(s, n):
    out=''; used=0
    for ch in s:
        k=cw(ch)
        if used+k>n: break
        out+=ch; used+=k
    return out

def wrap(s, n):
    if width(s)<=n: return [s]
    parts=[]
    while s:
        line=crop(s,n)
        if len(line)<len(s) and ' ' in line and all(ord(c)<128 for c in s):
            line=line.rsplit(' ',1)[0]
        parts.append(line); s=s[len(line):].lstrip()
    return parts

class Canvas:
    def __init__(self,w,h):
        self.w=w; self.h=h
        self.clip=None
        self.cells=[[(' ',DIM) for _ in range(w)] for _ in range(h)]
    def put(self,x,y,s,style=NORMAL):
        x=int(x); y=int(y)
        if not 0<=y<self.h: return
        if self.clip and not self.clip[0]<=y<=self.clip[1]:return
        for ch in str(s):
            k=cw(ch)
            if k==0: continue
            if x>=0 and x+k<=self.w:
                self.cells[y][x]=(ch,style)
                if k==2: self.cells[y][x+1]=('',style)
            x+=k
    def center(self,y,s,style=NORMAL): self.put((self.w-width(s))//2,y,s,style)
    def line(self,x0,y0,x1,y1,ch='.',style=DIM):
        steps=max(1,int(max(abs(x1-x0),abs(y1-y0))*1.5))
        for i in range(steps+1):
            u=i/steps; self.put(round(x0+(x1-x0)*u),round(y0+(y1-y0)*u),ch,style)
    def box(self,x,y,w,h,style=DIM):
        if w<2 or h<2:return
        self.put(x,y,'+'+'-'*(w-2)+'+',style)
        self.put(x,y+h-1,'+'+'-'*(w-2)+'+',style)
        for yy in range(y+1,y+h-1):
            self.put(x,yy,'|',style); self.put(x+w-1,yy,'|',style)
    def big(self,y,text,style=BRIGHT):
        text=text.upper(); total=len(text)*6-1
        if total>self.w-6:
            self.center(y+2,text,style); return
        left=(self.w-total)//2
        for i,ch in enumerate(text):
            for dy,row in enumerate(FONT.get(ch,FONT[' '])):
                for dx,p in enumerate(row):
                    if p=='1':self.put(left+i*6+dx,y+dy,'#',style)
    def ansi(self):
        out=['\x1b[H']; last=None
        for y,row in enumerate(self.cells):
            out.append(f'\x1b[{y+1};1H')
            for ch,style in row:
                if not ch: continue
                if style!=last:out.append(STYLES[style]);last=style
                out.append(ch)
        return ''.join(out)+'\x1b[0m'
    def plain(self): return '\n'.join(''.join(ch for ch,_ in r) for r in self.cells)

CHAPTERS=[(0,'01 / CREATION','创建'),(29.709,'02 / DEVOTION','献出自我'),
          (110.9,'03 / ISOLATION','离开'),(125.708,'04 / EXECUTION','失控'),
          (177.246,'05 / LOVE','困于爱')]

class Film:
    def __init__(self):
        # read_text() with no encoding would use this machine's console codec (cp936 on a
        # Chinese Windows) and fail on the UTF-8 Chinese in lyrics.json.
        self.lyrics=json.loads((ROOT/'lyrics.json').read_text(encoding='utf-8'))
        self.times=[x['time'] for x in self.lyrics]
        self.spectrum=json.loads((ROOT/'spectrum.json').read_text(encoding='utf-8'))
        self.config=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
    def cue(self,t):
        idx=bisect.bisect_right(self.times,t)-1
        e=self.lyrics[idx] if idx>=0 else None
        return e if e and t<e['end'] else None
    def energy(self,t):
        a=self.spectrum['frames']
        return a[min(len(a)-1,max(0,int(t*self.spectrum['fps'])))]
    def render(self,t,w,h,paused=False,offset=0,help_on=False,ready=False):
        c=Canvas(w,h)
        if w<64 or h<24:
            c.center(h//2-2,'WORLD.EXECUTE(ME);',BRIGHT)
            c.center(h//2,'请放大窗口，或缩小终端字号',WHITE)
            c.center(h//2+2,f'{w} x {h} / minimum 64 x 24',NORMAL)
            c.center(h//2+4,'SPACE pause  Q quit',DIM)
            return c
        if 15.8<=t<29.709 and not ready:
            from scenes import title_takeover
            source=self.render(15.799,w,h,paused,offset,False,False) if t<18.1 else None
            title_takeover(c,t,FONT,source)
            if help_on:self.help(c,offset)
            return c
        end=self.config['duration']; e=self.cue(t+offset)
        act=max(x for x in CHAPTERS if x[0]<=max(0,t))
        c.put(2,0,'WORLD.EXECUTE(ME);',BRIGHT)
        state='READY' if ready else ('PAUSED' if paused else 'RUNNING')
        clock=f'{int(t)//60:02}:{int(t)%60:02}.{int(t*10)%10} / 03:32  {state}'
        c.put(w-width(clock)-2,0,clock,DIM)
        c.put(2,1,'-'*(w-4),DIM)
        c.put(2,2,act[1],NORMAL)
        top=4; bottom=h-8; cy=(top+bottom)/2; cx=w/2
        sh=max(6,bottom-top+1)
        spec=self.energy(t)
        pulse=sum(spec[:10])/10
        c.clip=(top,bottom)
        from scenes import draw_scene, phosphor
        draw_scene(c,t,top,bottom,pulse,e)
        phosphor(c,t,top,bottom)
        c.clip=None
        # Spectrum is measured from the supplied song, sampled on the audio clock.
        sy=h-6; cols=min(80,w-8); start=(w-cols)//2
        for i in range(cols):
            amp=spec[int(i*48/cols)]; level=max(0,round(amp*3))
            c.put(start+i,sy,'._:=|'[min(4,round(amp*4))],DIM)
        if ready:
            c.center(h-5,'MILI  /  world.execute(me);',WHITE)
            c.center(h-3,'[ SPACE / ENTER TO START ]',BRIGHT)
        elif e:
            ens=wrap(e['en'],w-8); zhs=wrap(e['zh'],w-8)
            # Two reserved lines per language prevent changes in caption position.
            for i,line in enumerate(ens[:2]):c.center(h-5+i,line,WHITE)
            for i,line in enumerate(zhs[:2]):c.center(h-3+i,line,BRIGHT)
        elif t>208:
            c.center(h-5,'PROCESS ENDED. THE LOOP REMAINS.',WHITE)
        else:
            c.center(h-5,'[ instrumental ]',DIM)
            c.center(h-3,'[ 间奏 ]',DIM)
        hint='SPACE play/pause   <- -> 5s   R restart   Q quit   H help'
        c.center(h-1,crop(hint,w-4),DIM)
        if ready:self.slate(c,top,bottom)
        if help_on:self.help(c,offset)
        return c
    def slate(self,c,top,bottom):
        for y in range(top,bottom+1):c.put(0,y,' '*c.w,DIM)
        cy=int((top+bottom)/2)
        c.center(top+1,'A TERMINAL MUSIC VIDEO',DIM)
        c.big(max(top+2,cy-4),'EXECUTE(ME);',BRIGHT)
        c.center(cy+3,'M I L I',WHITE)
        c.center(min(bottom,cy+6),'[ SPACE / ENTER TO START ]',BRIGHT)
    def help(self,c,offset):
        lines=['CONTROLS / 操作','SPACE / ENTER   播放或暂停','LEFT / RIGHT    后退或前进 5 秒',
               'R               从头播放','1 2 3 4 5       跳转五个章节','[ / ]           字幕提前 / 延后 0.1 秒',
               ', / .           上一句 / 下一句',
               '+ / -           音量','Q / ESC         退出','H               关闭帮助',f'字幕偏移 {offset:+.1f}s']
        w=min(c.w-4,58);x=(c.w-w)//2;y=(c.h-len(lines)-3)//2
        for yy in range(y,y+len(lines)+3):c.put(x,yy,' '*w,NORMAL)
        c.box(x,y,w,len(lines)+3,BRIGHT)
        for i,s in enumerate(lines):c.put(x+3,y+2+i,s,WHITE if i==0 else NORMAL)

POWERSHELL=os.path.join(os.environ.get('SystemRoot',r'C:\Windows'),'System32','WindowsPowerShell','v1.0','powershell.exe')

class Audio:
    def __init__(self,path):
        self.state={'time':0.,'duration':0.,'playing':False}
        self.last=time.monotonic(); self.error=''; self.ready_seconds=None
        argv=[POWERSHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',
              str(ROOT/'win'/'audioclock.ps1'),'-AudioPath',str(path)]
        # The clock outlives a Ctrl+C here: a new process group keeps it alive long enough
        # for this side to send 'quit' and collect it in the cleanup path.
        self.proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                   text=True,bufsize=1,encoding='utf-8',errors='replace',
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        threading.Thread(target=self.read,daemon=True).start()
        # stderr has to be drained or 4 KB of child chatter wedges the clock, and the
        # parent then blames it as 音频时钟停止更新.
        self.stderr_lines=[]
        threading.Thread(target=self.drain_stderr,daemon=True).start()
        # Longer than the macOS helper needed: PowerShell itself has to start first.
        # run() records how long this actually took so the number stays visible.
        deadline=time.monotonic()+20
        try:
            while not self.state['duration']:
                if self.error:raise RuntimeError(
                        f'音频引擎报错：{self.error}（pid={self.proc.pid}）')
                if self.proc.poll() is not None:
                    # The pid has to be in the message: it is the only way a caller can
                    # prove which child died, and the reaping test depends on it.
                    raise RuntimeError((self.stderr_text() or '')+
                                       f'音频引擎退出（退出码 {self.proc.returncode}，pid={self.proc.pid}）')
                if time.monotonic()>deadline:raise RuntimeError('音频引擎没有响应')
                time.sleep(.01)
        except BaseException:
            # Whoever spawns a child has to reap it: run()'s finally only sees this object
            # if the constructor returned, so a raise here would orphan powershell.exe.
            self.close()
            raise
    def drain_stderr(self):
        for line in self.proc.stderr:
            line=line.strip()
            if line:self.stderr_lines.append(line)
    def stderr_text(self):
        return '\n'.join(self.stderr_lines[-6:])
    def read(self):
        started=time.monotonic()
        for line in self.proc.stdout:
            try:
                message=json.loads(line)
                if 'error' in message:self.error=message['error']
                else:
                    self.state=message;self.last=time.monotonic()
                    if self.ready_seconds is None:self.ready_seconds=time.monotonic()-started
            except ValueError:pass
    def command(self,s):
        self.proc.stdin.write(s+'\n');self.proc.stdin.flush()
    def close(self):
        if self.proc.poll() is None:
            try:self.command('quit');self.proc.wait(timeout=2)
            except (BrokenPipeError,subprocess.TimeoutExpired):
                self.proc.terminate()
                try:self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:self.proc.kill()
        for stream in (self.proc.stdin,self.proc.stdout,self.proc.stderr):
            if stream is not None and not stream.closed:
                try:stream.close()
                except OSError:pass

class _NoProcess:
    def poll(self): return None

class Silent:
    """--backend none: the same clock interface with no sound, for debugging video only.

    Takes the duration from config.json because nothing decodes the file in this mode.
    """
    def __init__(self,duration):
        self.state={'time':0.,'duration':duration,'playing':False}
        self.last=time.monotonic(); self.error=''; self.proc=_NoProcess()
        self.ready_seconds=0.0; self.at=0.; self.since=None; self.stop=False
        threading.Thread(target=self.tick,daemon=True).start()
    def tick(self):
        while not self.stop:
            if self.since is not None:
                moved=self.at+(time.monotonic()-self.since)
                if moved>=self.state['duration']:
                    # The real clock stops reporting playing at the end; so does this one,
                    # or run() would sit at the last frame forever.
                    moved=self.state['duration']; self.since=None; self.state['playing']=False
                self.state['time']=moved
            self.last=time.monotonic(); time.sleep(1/64)
    def command(self,s):
        fields=s.split(' ')
        if fields[0]=='play': self.at=self.state['time']; self.since=time.monotonic(); self.state['playing']=True
        elif fields[0]=='pause': self.at=self.state['time']; self.since=None; self.state['playing']=False
        elif fields[0]=='seek' and len(fields)>1:
            self.at=min(max(0.,float(fields[1])),self.state['duration']-.01)
            self.state['time']=self.at
            if self.since is not None:self.since=time.monotonic()
    def close(self): self.stop=True

def open_audio(path,backend,duration=0.):
    return Silent(duration) if backend=='none' else Audio(path)

def run(args,film):
    if not sys.stdin.isatty():raise RuntimeError('请在交互式终端里运行（双击 播放MV.cmd）。')
    host=winconsole.host_report()
    if host!='windows-terminal':
        # The painter depends on the alternate screen and a hidden cursor; other hosts
        # honour those less reliably, so say it before the picture takes over the window.
        print(f'提示：当前终端宿主是 {host}，建议改用 Windows Terminal（双击 播放MV.cmd）。',file=sys.stderr)
    # stdout stays the console stream, which is what lets Python write through
    # WriteConsoleW and keep the Chinese captions independent of the console codepage.
    # Reopening it through /dev/tty or CONOUT$ would lose that.
    audio_path=Path(args.audio).expanduser().resolve() if args.audio else Path(film.config['audio'])
    if not args.audio and not audio_path.is_absolute():audio_path=ROOT/audio_path
    if args.backend!='none' and not audio_path.is_file():
        raise RuntimeError(f'找不到音频：{audio_path}\n请使用 --audio 指定 MP3 文件，或加 --backend none 只看画面。')
    console=winconsole.Console()
    try:console.enter()
    except OSError as e:raise RuntimeError(f'控制台模式设置失败：{e}')
    timer=winconsole.HighResolutionTimer(); timer.acquire()
    keyq=winconsole.KeyQueue()
    size_source='not measured yet'
    offset=args.offset if args.offset is not None else film.config.get('subtitle_offset',0.)
    started=args.autoplay or args.paused; paused=not args.autoplay; help_on=False; volume=.75; ready=not started
    current=args.start; playing_seen=False; frames=0; max_render=0.; size_last=None; report=[]
    def quit_signal(*_):raise KeyboardInterrupt
    watch=[signal.SIGTERM,signal.SIGINT]
    for name in ('SIGBREAK',):
        found=getattr(signal,name,None)
        if found is not None:watch.append(found)
    old_signals={s:signal.signal(s,quit_signal) for s in watch}
    audio=None
    try:
        # Opening the clock inside the try on purpose: if it never comes up, this finally is
        # the only thing that puts the console modes and the timer resolution back.
        audio=open_audio(audio_path,args.backend,film.config['duration'])
        sys.stdout.write('\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J');sys.stdout.flush()
        audio.command(f'seek {args.start}')
        if args.autoplay:audio.command('play')
        keybuf=''; next_frame=time.monotonic()
        while True:
            begin=time.monotonic()
            state=audio.state.copy();current=state['time']
            if audio.error:raise RuntimeError('音频输出不可用，请检查系统的声音输出设备。')
            if audio.proc.poll() is not None:raise RuntimeError('音频引擎意外退出。')
            if begin-audio.last>2:raise RuntimeError('音频时钟停止更新。')
            if state['playing']:playing_seen=True
            if playing_seen and not state['playing'] and not paused and current<.05:
                current=state['duration'];paused=True
                audio.command(f'seek {state["duration"]-.02}')
            if current>=state['duration']-.05 and not state['playing'] and started:paused=True
            # Ask the console rather than the shell: COLUMNS/LINES go stale after going
            # fullscreen. stdout's buffer is tried first because fd 0 is the console input
            # buffer, whose window record is not reliably valid on Windows.
            w,h,size_source=winconsole.size()
            w=min(w,240);h=min(h,85)
            # Leave the last column unused. This avoids terminal autowrap artifacts.
            c=film.render(current,w-1,h,paused,offset,help_on,ready)
            if (w,h)!=size_last:sys.stdout.write('\x1b[2J');size_last=(w,h)
            sys.stdout.write(c.ansi());sys.stdout.flush()
            frames+=1;max_render=max(max_render,time.monotonic()-begin)
            if frames%30==0:report.append({'audio_time':current,'playing':state['playing'],'width':w,'height':h,'frames':frames,'size_source':size_source})
            if args.stop_after is not None and current>=args.stop_after:break
            next_frame+=1/args.fps
            delay=max(0,next_frame-time.monotonic())
            if delay==0:next_frame=time.monotonic()
            # Keys arrive on a worker thread: select() does not work on console handles,
            # and a blocking read would hold the frame clock. Arrows are already rewritten
            # into the escape sequences the dispatch below expects.
            typed=keyq.read(delay)
            if typed:
                keybuf+=typed
                if keybuf=='\x1b':
                    follow=keyq.read(.035)
                    if follow:keybuf+=follow
                while keybuf:
                    if keybuf.startswith(('\x1b[C','\x1b[D')):
                        right=keybuf[2]=='C';keybuf=keybuf[3:]
                        audio.command(f'seek {min(state["duration"]-.05,max(0,current+(5 if right else -5)))}')
                    else:
                        key=keybuf[0];keybuf=keybuf[1:]
                        if key in ('q','Q','\x1b','\x03'):return
                        if key in (' ','\r','\n'):
                            if not started:started=True;ready=False;paused=False;audio.command('play')
                            else:paused=not paused;audio.command('pause' if paused else 'play')
                        elif key in ('r','R'):
                            audio.command('seek 0');audio.command('play');started=True;ready=False;paused=False
                        elif key in '12345':
                            audio.command(f'seek {CHAPTERS[int(key)-1][0]}');audio.command('play');started=True;ready=False;paused=False
                        elif key=='[':offset=round(offset+.1,2)
                        elif key==']':offset=round(offset-.1,2)
                        elif key in ',.':
                            i=bisect.bisect_right(film.times,current+.03)-1
                            i=min(len(film.times)-1,max(0,i+(1 if key=='.' else -1)))
                            audio.command(f'seek {film.times[i]}');started=True;ready=False
                        elif key in 'hH':help_on=not help_on
                        elif key in '+=':volume=min(1,volume+.05);audio.command(f'volume {volume}')
                        elif key=='-':volume=max(0,volume-.05);audio.command(f'volume {volume}')
    finally:
        if audio is not None:audio.close()
        keyq.close()
        # Order matters on the way out: put the console modes back before the screen
        # sequences that reveal the cursor and leave the alternate screen.
        console.leave()
        timer.release()
        sys.stdout.write('\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l');sys.stdout.flush()
        for s,handler in old_signals.items():signal.signal(s,handler)
        if args.report:
            destination=Path(args.report); destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(json.dumps({'frames':frames,'last_time':current,
                'max_frame_render_seconds':max_render,'fps':args.fps,'backend':args.backend,
                'host':host,'audio_ready_seconds':getattr(audio,'ready_seconds',None),
                'size_source':size_source,'console_mode_changes':console.notes,
                'ambiguous_wide':sorted(AMBIGUOUS_WIDE),'samples':report},
                indent=2,ensure_ascii=False),encoding='utf-8')

def ambiguous_used():
    """Every East-Asian-Ambiguous glyph this painter can actually put on screen.

    Derived from the sources rather than a hand-typed list, so it cannot drift when the
    scenes change. win/calibrate.py measures what the running console really draws.
    """
    text=''.join((ROOT/name).read_text(encoding='utf-8') for name in ('player.py','scenes.py'))
    return {ch for ch in set(text)
            if unicodedata.east_asian_width(ch)=='A' and not unicodedata.combining(ch)}

def main():
    p=argparse.ArgumentParser(description='world.execute(me); / bilingual terminal MV')
    p.add_argument('--audio');p.add_argument('--start',type=float,default=0.)
    p.add_argument('--autoplay',action='store_true');p.add_argument('--fps',type=int,default=24)
    p.add_argument('--paused',action='store_true')
    p.add_argument('--offset',type=float);p.add_argument('--snapshot',type=float)
    p.add_argument('--width',type=int,default=120);p.add_argument('--height',type=int,default=40)
    p.add_argument('--plain',action='store_true');p.add_argument('--report');p.add_argument('--stop-after',type=float)
    p.add_argument('--backend',choices=('winrt','none'),default='winrt',
                   help='winrt plays through Media Foundation; none draws silently, to check the picture alone')
    p.add_argument('--ambiguous-width',choices=('auto','1','2'),default='auto',
                   help='how wide this console draws Ambiguous glyphs; auto takes config.json')
    a=p.parse_args();film=Film()
    # A piped stdout on a Chinese Windows is cp936, which cannot encode every glyph the
    # scenes draw; the console stream itself needs nothing because Python writes it with
    # WriteConsoleW.
    if not sys.stdout.isatty():sys.stdout.reconfigure(encoding='utf-8')
    AMBIGUOUS_WIDE.update(film.config.get('ambiguous_wide',[]))
    if a.ambiguous_width=='1':AMBIGUOUS_WIDE.clear()
    elif a.ambiguous_width=='2':AMBIGUOUS_WIDE.clear();AMBIGUOUS_WIDE.update(ambiguous_used())
    if not 5<=a.fps<=60:p.error('--fps must be between 5 and 60')
    if a.snapshot is not None:
        c=film.render(a.snapshot,a.width,a.height,True)
        print(c.plain() if a.plain else c.ansi());return
    try:run(a,film)
    except KeyboardInterrupt:pass
    except Exception as e:print(f'播放失败：{e}',file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
