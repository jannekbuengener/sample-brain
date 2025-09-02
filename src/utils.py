import hashlib
from pathlib import Path

def file_hash(path: Path, blocksize: int = 65536) -> str:
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(blocksize), b''):
            h.update(chunk)
    return h.hexdigest()
