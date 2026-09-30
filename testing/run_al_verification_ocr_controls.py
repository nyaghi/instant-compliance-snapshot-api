"""Offline synthetic OCR controls. No browser, live challenge or registry access.

Load the exact master helper without starting/importing the full server so this
test can run in the local OCR runtime. These are not live acceptance evidence.
"""
import ast
import base64
import io
import json
from pathlib import Path
import random
import re
import sys
import threading
import time
from PIL import Image, ImageDraw, ImageFont

_AL_VERIFICATION_OCR = None
_AL_VERIFICATION_OCR_LOCK = threading.Lock()
root = Path(__file__).resolve().parents[1]
tree = ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'al_read_verification_image')
exec(compile(ast.Module(body=[helper], type_ignores=[]), 'master-al-ocr-helper', 'exec'))


def run():
    rng = random.Random(292)
    font = ImageFont.truetype('C:/Windows/Fonts/arialbi.ttf', 24)
    results = []
    for index in range(30):
        value = ''.join(rng.choice('0123456789ABCDEF' if index < 20 else 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(6))
        label = Image.new('RGB', (125, 35), 'white')
        ImageDraw.Draw(label).text((2, 0), value, font=font, fill='black')
        picture = Image.new('RGB', (125, 80), 'white')
        picture.paste(label.resize((125, 15 if index % 2 else 20)), (0, 30))
        buffer = io.BytesIO(); picture.save(buffer, format='PNG')
        started = time.monotonic(); answer = ''; error = ''
        try:
            answer = al_read_verification_image('data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(), started+15)
        except Exception as exc:
            error = type(exc).__name__
        results.append({'synthetic': True, 'expected': value, 'actual': answer, 'match': answer == value,
                        'error': error, 'seconds': round(time.monotonic()-started, 3)})
    result = {'purpose': 'Synthetic feasibility controls only; not live Alabama validation',
              'total': len(results), 'matches': sum(r['match'] for r in results),
              'incorrect_reads': sum(bool(r['actual']) and not r['match'] for r in results),
              'average_seconds': round(sum(r['seconds'] for r in results)/len(results), 3), 'cases': results}
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}))
    return 0 if result['matches'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(run())
