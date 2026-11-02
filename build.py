"""Build the Windows application from this source tree."""
from pathlib import Path
import os
import PyInstaller.__main__

root=Path(__file__).resolve().parent
PyInstaller.__main__.run([
    '--noconfirm','--windowed','--onedir','--noupx','--name','RomOSTinyVideo',
    '--paths',str(root),'--distpath',str(root/'dist'),'--workpath',str(root/'build'),
    '--specpath',str(root/'build'),
    '--add-data',str(root/'videofactorio/signals.json')+os.pathsep+'videofactorio',
    '--add-data',str(root/'videofactorio/radio-signals.json')+os.pathsep+'videofactorio',
    str(root/'run.pyw')])
