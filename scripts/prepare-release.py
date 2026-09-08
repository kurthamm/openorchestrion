"""Verify release identity and assemble redistributable, checksummed artifacts."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Release requires a final x.y.z version')
    dist = root / 'dist'
    wheel = dist / f'openorchestrion-{version}-py3-none-any.whl'
    sdist = dist / f'openorchestrion-{version}.tar.gz'
    assert wheel.is_file() and sdist.is_file()
    with zipfile.ZipFile(wheel) as archive:
        assert f'__version__ = "{version}"' in archive.read('openorchestrion/__init__.py').decode()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    bundle = dist / f'openorchestrion-{version}-source.zip'
    subprocess.run(['git', 'archive', '--format=zip', f'--prefix=openorchestrion-{version}/',
                    '-o', str(bundle), 'HEAD'], cwd=root, check=True)
    shutil.copy2(root / 'src/openorchestrion/deployment/install-appliance.sh', dist / 'install-appliance.sh')
    files = [wheel, sdist, bundle, dist / 'install-appliance.sh']
    manifest = {'version': version, 'commit': sha, 'python': '3.11–3.13',
                'artifacts': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    identity = dist / 'release.json'
    identity.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    files.append(identity)
    (dist / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in files))
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
