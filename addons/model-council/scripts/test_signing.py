"""Signing identity, privacy, and nested-code safety checks; no Keychain changes."""
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
import signing
from lifecycle import write_json


class SigningTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = dict(schemaVersion=1, sha1='A' * 40, keychain=str(self.root / 'local.keychain-db'))

    def configure(self):
        write_json(self.root / 'signing/identity.json', self.config)

    def test_missing_identity_never_falls_back_to_ad_hoc(self):
        with self.assertRaisesRegex(ValueError, 'setup-signing'):
            signing.load(self.root)

    def test_missing_key_does_not_generate_replacement(self):
        self.configure()
        with patch.object(signing, 'command', return_value=b'0 valid identities found'):
            with self.assertRaisesRegex(ValueError, 'Do not replace'):
                signing.setup(self.root)
        self.assertEqual(json.loads((self.root / 'signing/identity.json').read_text()), self.config)

    def test_setup_is_idempotent(self):
        self.configure()
        with patch.object(signing, 'command', return_value=('1) ' + self.config['sha1']).encode()) as command:
            self.assertEqual(signing.setup(self.root), self.config)
        self.assertEqual(command.call_count, 1)
        self.assertIn('find-identity', command.call_args.args)

    def test_invalid_fingerprint_is_rejected(self):
        self.config['sha1'] = '-unsafe'
        self.configure()
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            signing.load(self.root)

    def test_interrupted_import_never_rotates_key(self):
        write_json(self.root / 'signing/setup.json', dict(self.config, importCompleted=False))
        with patch.object(signing, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'interrupted'):
                signing.setup(self.root)
        command.assert_not_called()

    def test_secret_arguments_are_not_in_errors(self):
        failure = subprocess.CompletedProcess([], 1, b'', b'import failed')
        with patch.object(signing.subprocess, 'run', return_value=failure):
            with self.assertRaises(ValueError) as error:
                signing.command('/usr/bin/security', 'import', '-P', 'private-generated-password')
        self.assertNotIn('private-generated-password', str(error.exception))

    def test_nested_code_is_signed_before_container_without_aliases(self):
        app = self.root / 'App.app'
        nested = app / 'Contents/Frameworks/Helper.app'
        executable = nested / 'Contents/MacOS/Helper'
        executable.parent.mkdir(parents=True)
        executable.write_bytes(bytes.fromhex('cffaedfe') + b'fixture')
        (nested / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'Helper'}))
        (app / 'alias.app').symlink_to(nested, target_is_directory=True)
        library = nested / 'Contents/Library.node'
        library.write_bytes(bytes.fromhex('cffaedfe') + b'fixture')
        self.assertEqual(signing.targets(app), [library, nested, app])

    def test_requirement_pins_key_and_bundle_not_build_hash(self):
        requirement = signing.requirement('com.example.app', self.config['sha1'])
        self.assertIn('certificate leaf = H"' + self.config['sha1'] + '"', requirement)
        self.assertNotIn('cdhash', requirement)
        with self.assertRaisesRegex(ValueError, 'identifier'):
            signing.requirement('unsafe" or true', self.config['sha1'])

    def test_sign_uses_inline_requirement_and_preserves_safe_entitlements(self):
        app = self.root / 'App.app'
        entitlement = {'com.apple.security.cs.allow-jit': True,
                       'com.apple.developer.team-identifier': 'fixture',
                       'keychain-access-groups': ['fixture']}
        observed = []
        def command(*args):
            if '--entitlements' in args and '-d' in args:
                return plistlib.dumps(entitlement)
            if '--sign' in args:
                self.assertTrue(args[args.index('-r') + 1].startswith('=designated =>'))
                file = args[args.index('--entitlements') + 1]
                observed.append(plistlib.loads(Path(file).read_bytes()))
                self.assertNotIn('--deep', args)
            return b''
        with patch.object(signing, 'load', return_value=self.config), patch.object(signing, 'targets', return_value=[app]), patch.object(signing, 'metadata', return_value=('com.example.app', True)), patch.object(signing, 'command', side_effect=command), patch.object(signing, 'verify'):
            signing.sign(app, self.root)
        self.assertEqual(observed, [{'com.apple.security.cs.allow-jit': True}])


if __name__ == '__main__':
    unittest.main()
