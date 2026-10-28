"""Export thesis PDF and converge its editable TOC against actual PDF pages."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / '.cache/graduation_tools'))
import template_thesis


def convert_abstract_preview():
    local = ROOT / '.cache/graduation_office/root/usr/lib'
    env = os.environ.copy()
    binary = shutil.which('libreoffice')
    if not binary:
        binary = str(local / 'libreoffice/program/soffice.bin')
        env['LD_LIBRARY_PATH'] = ':'.join([str(local/'libreoffice/program'), str(local/'x86_64-linux-gnu'), env.get('LD_LIBRARY_PATH','')])
        env['SAL_USE_VCLPLUGIN'] = 'svp'
    output = ROOT / '.cache/midterm_abstract_20261021/word'
    output.mkdir(parents=True, exist_ok=True)
    pdf = output/'paper.pdf'
    before = pdf.stat().st_mtime_ns if pdf.exists() else None
    subprocess.run([binary, '-env:UserInstallation=file:///tmp/qllm-b4-abstract-office', '--headless', '--convert-to', 'pdf', '--outdir', str(output), str(ROOT/'docs/midterm2026/paper.docx')], env=env, check=True, timeout=90)
    if not pdf.exists() or pdf.stat().st_mtime_ns == before:
        raise RuntimeError('Abstract PDF was not refreshed')


def convert():
    local = ROOT / '.cache/graduation_office/root/usr/lib'
    env = os.environ.copy()
    binary = shutil.which('libreoffice')
    if not binary:
        binary = str(local / 'libreoffice/program/soffice.bin')
        env['LD_LIBRARY_PATH'] = ':'.join([str(local/'libreoffice/program'), str(local/'x86_64-linux-gnu'), env.get('LD_LIBRARY_PATH','')])
        env['SAL_USE_VCLPLUGIN'] = 'svp'
    command = [binary, '-env:UserInstallation=file:///tmp/qllm-thesis-template-office-3', '--headless', '--convert-to', 'pdf', '--outdir', str(HERE), str(HERE/'thesis.docx')]
    for attempt in range(6):
        template_thesis.build_thesis()
        # Conversion must actually replace the PDF; never silently accept a
        # stale artifact left by a failed export.
        before = (HERE/'thesis.pdf').stat().st_mtime_ns if (HERE/'thesis.pdf').exists() else None
        run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
        if run.returncode == 81:
            run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
        (ROOT/'.cache/graduation_office/template_convert.log').write_text(run.stdout+run.stderr)
        if run.returncode or (HERE/'thesis.pdf').stat().st_mtime_ns == before:
            raise RuntimeError('PDF conversion failed; inspect .cache/graduation_office/template_convert.log')
        entries = template_thesis.toc_entries()
        cache = HERE/'toc_cache.json'
        previous = json.loads(cache.read_text()) if cache.exists() else []
        if previous == entries:
            print(f'TOC converged: {len(entries)} entries; PDF and DOCX agree.')
            return
        cache.write_text(json.dumps(entries, ensure_ascii=False, indent=2)+'\n')
    raise RuntimeError('TOC did not converge within six PDF exports')


if __name__ == '__main__':
    if '--abstract-preview' in sys.argv:
        convert_abstract_preview()
    else:
        convert()
