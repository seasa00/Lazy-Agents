"""Real workspace boundaries; every filesystem fixture is disposable."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from app.dev.workspace import demonstration, make_workspace_runner, request, WorkspaceFixtureProvider
from app.domain.agents import AgentKind
from app.domain.projects import RunStatus
from app.permissions.policy import WorkspacePolicy
from app.tools.files import FileConflict
from app.tools.gateway import FileToolRequest, WorkspaceToolGateway


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='m31-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'work'
        self.root.mkdir()
        self.file = self.root / 'greeting.txt'
        self.file.write_text('hello\n')
        self.gateway = WorkspaceToolGateway(WorkspacePolicy(self.root), before_mutation=lambda r: None)

    def call(self, operation, **kw):
        return self.gateway.execute(FileToolRequest(operation, kw.pop('actor', AgentKind.DEVELOPER),
            kw.pop('attempt_id', 'attempt-1'), kw.pop('generation', 1), **kw))

    def edit(self):
        before = self.call('read', path='greeting.txt')
        return self.call('edit', path='greeting.txt', expected_hash=before.content_hash,
                         old_text='hello', new_text='hello world')

    def capture(self, **kw):
        return self.call('capture_submission', submission_id='attempt-1:submission',
                         paths=('greeting.txt',), **kw).submission

    def test_list_read_write_edit(self):
        self.assertEqual(self.call('list').entries, ('greeting.txt',))
        self.edit()
        self.assertEqual(self.file.read_text(), 'hello world\n')
        self.call('write', path='new.txt', expected_hash=None, content='new')
        self.assertEqual(self.call('read', path='new.txt').content, 'new')

    def test_nested_directory(self):
        (self.root / 'src').mkdir()
        self.call('write', path='src/new.txt', expected_hash=None, content='new')
        self.assertEqual(self.call('list', path='src').entries, ('src/new.txt',))

    def test_noncanonical_paths_denied_without_changes(self):
        outside = self.base / 'outside.txt'
        outside.write_text('safe')
        for path in ('../outside.txt', str(outside), 'a/../../outside.txt', './greeting.txt',
                     'a//file', 'a/../greeting.txt', 'C:\\outside.txt', 'a\x00b', ''):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.call('write', path=path, expected_hash=None, content='bad')
        self.assertEqual(outside.read_text(), 'safe')
        self.assertEqual(self.file.read_text(), 'hello\n')

    def test_symlink_file_and_directory_denied(self):
        outside = self.base / 'outside.txt'
        outside.write_text('safe')
        (self.root / 'link').symlink_to(outside)
        (self.root / 'dir').symlink_to(self.base, target_is_directory=True)
        (self.root / 'inside').symlink_to(self.file)
        for path in ('link', 'dir/outside.txt', 'inside'):
            for operation in ('read', 'write'):
                with self.subTest(path=path, op=operation), self.assertRaises(ValueError):
                    self.call(operation, path=path, expected_hash=None, content='bad')
        self.assertEqual(self.call('list').entries, ('greeting.txt',))
        self.assertEqual(outside.read_text(), 'safe')

    def test_dangling_symlink_denied(self):
        (self.root / 'dangling').symlink_to(self.base / 'missing')
        with self.assertRaises(ValueError):
            self.call('write', path='dangling', expected_hash=None, content='bad')
        self.assertFalse((self.base / 'missing').exists())

    def test_hardlink_denied(self):
        os.link(self.file, self.root / 'alias')
        with self.assertRaises(ValueError):
            self.call('read', path='alias')
        with self.assertRaises(ValueError):
            self.call('write', path='alias', expected_hash=None, content='bad')
        self.assertEqual(self.file.read_text(), 'hello\n')

    def test_protected_paths(self):
        for path in ('.env', '.env.local', '.git/config', '.codex/config', '.agents/rules',
                     '.aws/credentials', 'secret.key', 'nested/.ENV', '.runtime/submission'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.call('write', path=path, expected_hash=None, content='bad')
        (self.root / '.env').write_text('secret')
        with self.assertRaises(ValueError):
            self.call('read', path='.env')
        self.assertNotIn('.env', self.call('list').entries)

    def test_additional_protected_paths(self):
        self.gateway = WorkspaceToolGateway(WorkspacePolicy(self.root, protected=('config',)), before_mutation=lambda r: None)
        with self.assertRaises(ValueError):
            self.call('write', path='config/token', expected_hash=None, content='bad')

    def test_reviewer_and_manager_mutations_and_live_reads_denied(self):
        for role in (AgentKind.REVIEWER, AgentKind.MANAGER):
            for operation in ('write', 'edit', 'capture_submission', 'read', 'list'):
                with self.subTest(role=role, operation=operation), self.assertRaises(ValueError):
                    self.call(operation, actor=role, path='greeting.txt')
        self.assertEqual(self.file.read_text(), 'hello\n')

    def test_unsupported_operations(self):
        for operation in ('delete', 'shell', 'terminal', 'install'):
            with self.assertRaises(ValueError):
                self.call(operation, path='greeting.txt')

    def test_expected_hash_is_required(self):
        for expected in ('', 'bad', None):
            with self.assertRaises(ValueError):
                self.call('write', path='greeting.txt', content='bad', expected_hash=expected)
        self.assertEqual(self.file.read_text(), 'hello\n')

    def test_external_edit_conflict(self):
        previous = self.call('read', path='greeting.txt')
        self.file.write_text('external')
        with self.assertRaises(FileConflict):
            self.call('write', path='greeting.txt', content='bad', expected_hash=previous.content_hash)
        self.assertEqual(self.file.read_text(), 'external')
        self.assertEqual(self.gateway.records[-1].outcome, 'conflict')

    def test_creation_conflicts_if_file_appears(self):
        with self.assertRaises(FileConflict):
            self.call('write', path='greeting.txt', expected_hash=None, content='bad')

    def test_edit_requires_unique_match(self):
        before = self.call('read', path='greeting.txt')
        for old in ('', 'absent', 'l'):
            with self.assertRaises(ValueError):
                self.call('edit', path='greeting.txt', expected_hash=before.content_hash, old_text=old, new_text='bad')

    def test_snapshot_diff_hash_and_stability(self):
        edited = self.edit()
        snapshot = self.capture()
        digest = snapshot.digest
        self.assertEqual(snapshot.files[0].content_hash, edited.content_hash)
        self.assertIn('-hello\n+hello world\n', snapshot.files[0].diff)
        self.file.write_text('external')
        result = self.call('read', actor=AgentKind.REVIEWER, submission_id=snapshot.id, path='greeting.txt')
        self.assertEqual(result.content, 'hello world\n')
        self.assertEqual(snapshot.digest, digest)
        with self.assertRaises(FrozenInstanceError):
            snapshot.id = 'tamper'

    def test_submission_reads_survive_removed_workspace(self):
        self.edit()
        snapshot = self.capture()
        self.file.unlink()
        self.root.rmdir()
        self.assertEqual(self.call('read', actor=AgentKind.REVIEWER, submission_id=snapshot.id,
                                  path='greeting.txt').content, 'hello world\n')

    def test_snapshot_paths_and_scope_enforced(self):
        self.edit()
        snapshot = self.capture()
        self.assertEqual(self.call('list', actor=AgentKind.MANAGER, submission_id=snapshot.id).entries, ('greeting.txt',))
        for fields in ({'attempt_id': 'wrong'}, {'generation': 2}, {'path': 'missing'}, {'submission_id': 'missing'}):
            args = {'path': 'greeting.txt', 'submission_id': snapshot.id, **fields}
            with self.assertRaises(ValueError):
                self.call('read', actor=AgentKind.REVIEWER, **args)

    def test_sealed_attempt_cannot_change_or_recapture(self):
        result = self.edit()
        self.capture()
        with self.assertRaises(ValueError):
            self.call('write', path='greeting.txt', expected_hash=result.content_hash, content='bad')
        with self.assertRaises(ValueError):
            self.capture()

    def test_capture_detects_external_edit(self):
        self.edit()
        self.file.write_text('external')
        with self.assertRaises(FileConflict):
            self.capture()

    def test_manifest_requires_exact_changed_paths(self):
        self.edit()
        for paths in ((), ('fake',), ('greeting.txt', 'greeting.txt')):
            with self.assertRaises(ValueError):
                self.call('capture_submission', paths=paths, submission_id='attempt-1:submission')
        self.capture()

    def test_reverted_file_is_not_changed(self):
        result = self.edit()
        self.call('write', path='greeting.txt', expected_hash=result.content_hash, content='hello\n')
        with self.assertRaises(ValueError):
            self.capture()

    def test_unbound_mutation_denied(self):
        self.gateway = WorkspaceToolGateway(WorkspacePolicy(self.root))
        with self.assertRaises(ValueError):
            self.edit()

    def test_guard_rechecked_before_replace(self):
        count = 0
        def guard(req):
            nonlocal count
            count += 1
            if count == 3:
                raise ValueError('paused')
        self.gateway.before_mutation = guard
        with self.assertRaisesRegex(ValueError, 'paused'):
            self.edit()
        self.assertEqual(self.file.read_text(), 'hello\n')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['greeting.txt'])

    def test_size_bounds(self):
        self.gateway = WorkspaceToolGateway(WorkspacePolicy(self.root, max_file_bytes=8), before_mutation=lambda r: None)
        self.file.write_text('x' * 9)
        with self.assertRaises(ValueError):
            self.call('read', path='greeting.txt')
        with self.assertRaises(ValueError):
            self.call('write', path='new', expected_hash=None, content='x' * 9)
        self.assertFalse((self.root / 'new').exists())

    def test_result_and_listing_bounds(self):
        self.gateway = WorkspaceToolGateway(WorkspacePolicy(self.root, max_result_bytes=8, max_entries=1), before_mutation=lambda r: None)
        with self.assertRaises(ValueError):
            self.call('read', path='greeting.txt')
        (self.root / 'second').write_text('two')
        with self.assertRaises(ValueError):
            self.call('list')

    def test_submission_size_bound(self):
        self.gateway = WorkspaceToolGateway(WorkspacePolicy(self.root, max_result_bytes=150), before_mutation=lambda r: None)
        self.edit()
        with self.assertRaisesRegex(ValueError, 'size limit'):
            self.capture()

    def test_binary_and_special_files_denied(self):
        self.file.write_bytes(b'\xff')
        with self.assertRaises(ValueError):
            self.call('read', path='greeting.txt')
        os.mkfifo(self.root / 'fifo')
        with self.assertRaises(ValueError):
            self.call('read', path='fifo')

    def test_workspace_root_validation_and_replacement(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.root)
        for path in (alias, self.base / 'missing', Path('/')):
            with self.assertRaises(ValueError):
                WorkspacePolicy(path)
        self.root.rename(self.base / 'moved')
        self.root.mkdir()
        with self.assertRaises(ValueError):
            self.call('list')

    def test_operation_records_are_immutable_and_attributable(self):
        self.edit()
        with self.assertRaises(ValueError):
            self.call('delete', path='greeting.txt')
        records = self.gateway.records
        self.assertEqual([r.outcome for r in records], ['succeeded', 'succeeded', 'denied'])
        self.assertTrue(all(r.attempt_id == 'attempt-1' and r.actor == 'developer' for r in records))
        self.assertIsNotNone(records[1].before_hash)
        self.assertIsNotNone(records[1].after_hash)
        self.assertEqual(len({r.id for r in records}), 3)

    def test_full_real_workspace_demonstration(self):
        report = demonstration()
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(len(report['denied']), 4)
        self.assertNotEqual(report['captured_content'], report['live_content'])

    def test_runner_pause_cancel_and_stale_generation_deny_mutation(self):
        for control in ('pause', 'cancel', 'change_scope'):
            with self.subTest(control=control):
                runner = make_workspace_runner(self.root)
                req = request(runner, 'write', path='new', expected_hash=None, content='bad')
                getattr(runner.controls, control)()
                with self.assertRaises(ValueError):
                    runner.file_tool(req)
                self.assertFalse((self.root / 'new').exists())
                self.assertEqual(runner.workspace_gateway.records[-1].outcome, 'denied')

    def test_runner_review_context_is_captured_not_live(self):
        runner = make_workspace_runner(self.root)
        old = runner.file_tool(request(runner, 'read', path='greeting.txt'))
        runner.file_tool(request(runner, 'write', path='greeting.txt', expected_hash=old.content_hash, content='hello world\n'))
        runner.step()
        snapshot = runner.run.workflow.submissions[0]
        self.file.write_text('external')
        runner.step()
        evidence = runner.provider.requests[-1].context['workflow']['evidence']
        self.assertEqual(evidence[0], snapshot.files.serialize())
        self.assertIn('UNVERIFIED', evidence[1])
        self.assertNotIn('external', evidence[0])

    def test_pause_during_developer_call_does_not_capture(self):
        runner = make_workspace_runner(self.root)
        old = runner.file_tool(request(runner, 'read', path='greeting.txt'))
        runner.file_tool(request(runner, 'write', path='greeting.txt', expected_hash=old.content_hash, content='hello world\n'))
        runner.provider.hook = lambda q: runner.controls.pause() if q.context['workflow']['phase'] == 'develop' else None
        runner.step()
        self.assertEqual(runner.run.status, RunStatus.PAUSED)
        self.assertFalse(runner.run.workflow.submissions)
        runner.provider.hook = None
        runner.controls.resume()
        runner.run_until_stopped()
        self.assertEqual(runner.run.status, RunStatus.COMPLETED)

    def test_added_file_manifest(self):
        self.call('write', path='new', expected_hash=None, content='new\n')
        snapshot = self.call('capture_submission', paths=('new',), submission_id='attempt-1:submission').submission
        self.assertIsNone(snapshot.files[0].before_hash)
        self.assertEqual(snapshot.files[0].to_dict()['change_type'], 'added')
        self.assertIn('--- /dev/null', snapshot.files[0].diff)

    def test_diff_without_final_newline(self):
        self.file.write_text('hello')
        self.edit()
        self.assertIn('-hello\n\\ No newline at end of file\n+hello world\n', self.capture().files[0].diff)

    def test_write_preserves_file_mode(self):
        self.file.chmod(0o640)
        self.edit()
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o640)

    def test_small_result_limit_denies_before_write(self):
        self.gateway = WorkspaceToolGateway(WorkspacePolicy(self.root, max_result_bytes=8), before_mutation=lambda r: None)
        with self.assertRaises(ValueError):
            self.call('write', path='new', expected_hash=None, content='new')
        self.assertFalse((self.root / 'new').exists())

    def test_later_attempt_does_not_overwrite_first_snapshot(self):
        edited = self.edit()
        first = self.capture()
        self.call('write', attempt_id='attempt-2', path='greeting.txt', expected_hash=edited.content_hash, content='revision\n')
        second = self.call('capture_submission', attempt_id='attempt-2', paths=('greeting.txt',),
                           submission_id='attempt-2:submission').submission
        self.assertEqual(first.files[0].content, b'hello world\n')
        self.assertEqual(second.files[0].before, first.files[0].content)
        self.assertNotEqual(first.digest, second.digest)

    def test_wrong_capture_identity_does_not_seal_attempt(self):
        self.edit()
        with self.assertRaises(ValueError):
            self.call('capture_submission', paths=('greeting.txt',), submission_id='wrong')
        self.capture()

    def test_cancel_during_developer_call_does_not_capture(self):
        runner = make_workspace_runner(self.root)
        old = runner.file_tool(request(runner, 'read', path='greeting.txt'))
        runner.file_tool(request(runner, 'write', path='greeting.txt', expected_hash=old.content_hash, content='hello world\n'))
        runner.provider.hook = lambda q: runner.controls.cancel() if q.context['workflow']['phase'] == 'develop' else None
        runner.step()
        self.assertEqual(runner.run.status, RunStatus.CANCELED)
        self.assertFalse(runner.run.workflow.submissions)
        self.assertEqual(len(runner.run.workflow.call_records), 3)

    def test_runner_external_edit_before_capture_blocks(self):
        runner = make_workspace_runner(self.root)
        old = runner.file_tool(request(runner, 'read', path='greeting.txt'))
        runner.file_tool(request(runner, 'write', path='greeting.txt', expected_hash=old.content_hash, content='hello world\n'))
        self.file.write_text('external')
        runner.step()
        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
        self.assertFalse(runner.run.workflow.submissions)
        self.assertEqual(self.file.read_text(), 'external')


if __name__ == '__main__':
    unittest.main()
