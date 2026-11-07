"""Persistent, machine-local signing. No account or subscription is required."""
import hashlib
import json
import os
import plistlib
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

from lifecycle import write_json

LABEL = 'T3 Adds Local Code Signing'
MACHO = {bytes.fromhex(value) for value in (
    'feedface', 'cefaedfe', 'feedfacf', 'cffaedfe', 'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}


def command(*args):
    # Do not expose command arguments: import uses a generated temporary password.
    result = subprocess.run(list(map(str, args)), capture_output=True)
    if result.returncode:
        raise ValueError('Local signing command failed: ' + str(args[0]) + ' ' + str(args[1]) + '. '
                         + result.stderr.decode(errors='replace').strip())
    return result.stdout


def signing_directory(state):
    directory = Path(state) / 'signing'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    return directory


def load(state):
    path = Path(state) / 'signing/identity.json'
    if not path.exists():
        raise ValueError('Persistent signing is not configured. Run install.py setup-signing first. '
                         'Ad-hoc signing is not used because it can invalidate macOS privacy permissions.')
    config = json.loads(path.read_text())
    if config.get('schemaVersion') != 1 or not re.fullmatch(r'[0-9A-F]{40}', config.get('sha1', '')):
        raise ValueError('Invalid local signing configuration; preserve it and inspect before continuing.')
    identities = command('/usr/bin/security', 'find-identity', '-v', '-p', 'codesigning', config['keychain']).decode()
    if not re.search(r'\b' + config['sha1'] + r'\b', identities):
        raise ValueError('The recorded signing identity is unavailable or untrusted. Unlock its Keychain '
                         'and check the certificate. Do not replace the identity: that changes privacy identity.')
    return config


def setup(state):
    directory = signing_directory(state)
    config_path = directory / 'identity.json'
    pending_path = directory / 'setup.json'
    if config_path.exists():
        return load(state)
    if pending_path.exists():
        config = json.loads(pending_path.read_text())
    else:
        keychain = command('/usr/bin/security', 'default-keychain', '-d', 'user').decode().strip().strip('"')
        # Reuse after interrupted setup; never silently create another private key.
        with tempfile.TemporaryDirectory(prefix='key-', dir=directory) as temporary:
            temp = Path(temporary)
            password = temp / 'password'
            password.write_text(secrets.token_hex(32) + '\n')
            password.chmod(0o600)
            export_password = temp / 'export-password'
            export_password.write_text(password.read_text())
            export_password.chmod(0o600)
            cert = directory / 'certificate.pem'
            command('/usr/bin/openssl', 'req', '-new', '-x509', '-newkey', 'rsa:3072',
                    '-keyout', temp / 'private.pem', '-out', cert, '-days', '3650',
                    '-passout', 'file:' + str(password), '-subj', '/CN=' + LABEL,
                    '-addext', 'basicConstraints=critical,CA:FALSE',
                    '-addext', 'keyUsage=critical,digitalSignature',
                    '-addext', 'extendedKeyUsage=critical,codeSigning')
            der = command('/usr/bin/openssl', 'x509', '-in', cert, '-outform', 'DER')
            config = dict(schemaVersion=1, sha1=hashlib.sha1(der).hexdigest().upper(), keychain=keychain)
            command('/usr/bin/openssl', 'pkcs12', '-export', '-descert', '-inkey', temp / 'private.pem',
                    '-in', cert, '-out', temp / 'identity.p12', '-name', LABEL,
                    '-passin', 'file:' + str(password), '-passout', 'file:' + str(export_password))
            # Journal before importing so an interrupted operation cannot rotate identity.
            write_json(pending_path, dict(config, importCompleted=False))
            pending_path.chmod(0o600)
            command('/usr/bin/security', 'import', temp / 'identity.p12', '-k', keychain,
                    '-P', password.read_text().strip(), '-T', '/usr/bin/codesign')
            config['importCompleted'] = True
            write_json(pending_path, config)
    if not config.get('importCompleted'):
        raise ValueError('Signing setup was interrupted during Keychain import. Inspect the Keychain '
                         'and setup.json before retrying; no replacement identity was generated.')
    # User-domain, code-signing-only trust; never add a TLS root or alter system trust.
    command('/usr/bin/security', 'add-trusted-cert', '-r', 'trustRoot', '-p', 'codeSign',
            '-k', config['keychain'], directory / 'certificate.pem')
    write_json(config_path, {key: config[key] for key in ('schemaVersion', 'sha1', 'keychain')})
    config_path.chmod(0o600)
    config = load(state)
    pending_path.unlink()
    return config


def targets(app):
    """Sign nested Mach-O code inside out, avoiding symlink aliases and duplicate executables."""
    app = Path(app)
    bundles = {app}
    for path in app.rglob('*'):
        if (not path.is_symlink() and path.is_dir() and path.suffix in ('.app', '.framework', '.xpc')
                and not any((app / parent).is_symlink() for parent in path.relative_to(app).parents if str(parent) != '.')):
            bundles.add(path)
    executables = set()
    for bundle in bundles:
        for info in (bundle / 'Contents/Info.plist', bundle / 'Resources/Info.plist'):
            if info.exists():
                data = plistlib.loads(info.read_bytes())
                executable = data.get('CFBundleExecutable')
                if executable:
                    for path in (bundle / 'Contents/MacOS' / executable, bundle / executable):
                        if path.exists():
                            executables.add(path.resolve())
                break
    result = set(bundles)
    for path in app.rglob('*'):
        if path.is_symlink() or not path.is_file() or path.resolve() in executables:
            continue
        with path.open('rb') as stream:
            if stream.read(4) in MACHO:
                result.add(path)
    return sorted(result, key=lambda p: (-len(p.parts), str(p)))


def requirement(identifier, sha1):
    if not re.fullmatch(r'[0-9A-F]{40}', sha1):
        raise ValueError('Invalid certificate fingerprint.')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', identifier):
        raise ValueError('Unsupported code identifier; refusing to construct a signing requirement.')
    return f'designated => identifier "{identifier}" and certificate leaf = H"{sha1}"'


def metadata(path):
    result = subprocess.run(['/usr/bin/codesign', '-dv', '--verbose=4', str(path)], capture_output=True, check=True)
    text = result.stderr.decode()
    identifier = next(line.split('=', 1)[1] for line in text.splitlines() if line.startswith('Identifier='))
    return identifier, 'runtime' in text


def sign(app, state):
    config = load(state)
    with tempfile.TemporaryDirectory(prefix='entitlements-', dir=signing_directory(state)) as temporary:
        for path in targets(app):
            identifier, runtime = metadata(path)
            args = ['/usr/bin/codesign', '--force', '--sign', config['sha1'], '--keychain',
                    config['keychain'], '--timestamp=none', '--identifier', identifier,
                    '-r', '=' + requirement(identifier, config['sha1'])]
            if runtime:
                args += ['--options', 'runtime']
            raw = command('/usr/bin/codesign', '-d', '--entitlements', ':-', path)
            if raw:
                entitlements = plistlib.loads(raw)
                for key in list(entitlements):
                    if key.startswith('com.apple.developer.') or key in ('com.apple.application-identifier', 'keychain-access-groups'):
                        del entitlements[key]
                file = Path(temporary) / 'entitlements.plist'
                file.write_bytes(plistlib.dumps(entitlements))
                args += ['--entitlements', str(file)]
            command(*args, path)
    verify(app, config)
    return dict(kind='persistent-local-certificate', sha1=config['sha1'])


def verify(app, config):
    for path in targets(app):
        identifier, _ = metadata(path)
        # Check both the signer and the embedded designated requirement, not just bundle integrity.
        command('/usr/bin/codesign', '--verify', '--strict', '-R',
                '=' + requirement(identifier, config['sha1']).split(' => ', 1)[1], path)
        result = subprocess.run(['/usr/bin/codesign', '-d', '-r-', str(path)], capture_output=True, check=True)
        embedded = (result.stdout + result.stderr).decode()
        if config['sha1'].lower() not in embedded.lower() or 'cdhash' in embedded:
            raise ValueError('The designated requirement is not pinned to the persistent certificate.')
    command('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
