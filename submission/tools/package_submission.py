"""Create a self-contained source ZIP from an explicit submission allowlist."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PACK = Path(__file__).resolve().parents[2]
PRIVATE_PARTS = {'.venv', '.git', '__pycache__', 'runs', 'build', 'dist', '.pytest_cache'}
TEXT_SUFFIXES = {'.py', '.json', '.jsonl', '.csv', '.md', '.toml', '.txt'}


def safe_member(path):
    return (not any(part in PRIVATE_PARTS or part.endswith('.egg-info') for part in path.parts)
        and not any(part.startswith('.env') and part != '.env.example' for part in path.parts)
        and not any(part.startswith('.llm_response_cache') for part in path.parts)
        and not path.name.endswith(('.pyc', '.sqlite', '.sqlite-wal', '.sqlite-shm')))


def members(pack):
    """Only supplied inputs and reviewable implementation/evidence are included."""
    pack = Path(pack).resolve()
    selected = {}
    for name in ('README.md', 'SUBMISSION.md', '.gitignore'):
        selected[name] = pack/name
    for name in ('config', 'data', 'pilot', 'replay', 'simulator'):
        for source in (pack/name).rglob('*'):
            if source.is_file() and safe_member(source.relative_to(pack)):
                selected[source.relative_to(pack).as_posix()] = source
    submission = pack/'submission'
    for source in submission.iterdir():
        if source.is_file() and (source.suffix in TEXT_SUFFIXES or source.name == '.env.example') and safe_member(source.relative_to(pack)):
            selected[source.relative_to(pack).as_posix()] = source
    for name in ('ott_agent', 'tools', 'tests', 'sample_replay', 'benchmarks'):
        for source in (submission/name).rglob('*'):
            if source.is_file() and source.suffix in TEXT_SUFFIXES and safe_member(source.relative_to(pack)):
                selected[source.relative_to(pack).as_posix()] = source
    pdf = pack/'assignment_one_user_one_agent.pdf'
    if not pdf.is_file():
        pdf = pack.parent/'assignment_one_user_one_agent.pdf'
    if pdf.is_file():
        selected['assignment_one_user_one_agent.pdf'] = pdf
    for source in selected.values():
        # Resolve links before reading; archive only this pack plus the named brief.
        resolved = source.resolve()
        if not resolved.is_relative_to(pack) and resolved != (pack.parent/'assignment_one_user_one_agent.pdf').resolve():
            raise ValueError('Archive input points outside authorized source directories')
    return selected


def package(pack, out):
    selected = members(pack)
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Archive already exists; choose another --out to preserve it')
    manifest = {'format': 1, 'root': 'one_user_one_agent_pack',
        'scope': 'Self-contained source repository and sample evidence. Excludes credentials, environments, caches and generated runs.',
        'entrypoint': 'submission/replay.py', 'provider_default': 'recorded', 'files': []}
    # Complete preflight before creating the deliverable.
    for relative, source in sorted(selected.items()):
        if not source.is_file():
            raise ValueError('Missing archive input: '+relative)
        if source.suffix in TEXT_SUFFIXES or source.name == '.env.example':
            with source.open(encoding='utf-8-sig') as stream:
                if any(re.search(r'sk-(?:proj-)?[A-Za-z0-9_-]{20,}', line) for line in stream):
                    raise ValueError('Possible credential in archive input: '+relative)
        manifest['files'].append({'path': relative, 'bytes': source.stat().st_size,
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    out.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(out, 'w', ZIP_DEFLATED, compresslevel=6) as archive:
        for relative, source in sorted(selected.items()):
            archive.write(source, manifest['root']+'/'+relative)
        archive.writestr(manifest['root']+'/SUBMISSION_MANIFEST.json', json.dumps(manifest, indent=2))
    with ZipFile(out) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive integrity check failed')
    return {'archive':str(out), 'files':len(selected), 'bytes':out.stat().st_size,
        'sha256':hashlib.sha256(out.read_bytes()).hexdigest(), 'manifest':manifest}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, default=PACK)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = package(args.pack, args.out)
    manifest = result.pop('manifest')
    manifest_path = args.out.with_suffix('.manifest.json')
    manifest_path.write_text(json.dumps({'archive':result, **manifest}, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
