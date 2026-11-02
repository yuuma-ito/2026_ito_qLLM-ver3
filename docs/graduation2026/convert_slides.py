"""Build and export the thesis-aligned graduation slides without other documents."""
import os
from pathlib import Path
import shutil
import subprocess

from graduation_slides import build_slides

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def convert():
    build_slides()
    local = ROOT / '.cache/graduation_office/root/usr/lib'
    env = os.environ.copy()
    binary = shutil.which('libreoffice')
    if not binary:
        binary = str(local / 'libreoffice/program/soffice.bin')
        env['LD_LIBRARY_PATH'] = ':'.join([str(local / 'libreoffice/program'),
            str(local / 'x86_64-linux-gnu'), env.get('LD_LIBRARY_PATH', '')])
        env['SAL_USE_VCLPLUGIN'] = 'svp'
    pdf = HERE / 'slides.pdf'
    before = pdf.stat().st_mtime_ns if pdf.exists() else None
    command = [binary, '-env:UserInstallation=file:///tmp/qllm-slides-sync-20261102',
               '--headless', '--convert-to', 'pdf', '--outdir', str(HERE), str(HERE / 'slides.pptx')]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
    if result.returncode == 81:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
    if result.returncode or not pdf.exists() or pdf.stat().st_mtime_ns == before:
        raise RuntimeError('Slides PDF was not refreshed: ' + result.stdout + result.stderr)
    print(result.stdout.strip())


if __name__ == '__main__':
    convert()
