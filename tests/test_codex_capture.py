import datetime
import fcntl
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from codex_capture import CodexCollector, read_turns


def event(kind, payload):
    return {'type': kind, 'timestamp': '2026-09-14T10:00:00Z', 'payload': payload}


def rollout():
    usage = {'input_tokens': 100, 'cached_input_tokens': 60, 'output_tokens': 20,
             'reasoning_output_tokens': 10}
    return [event('session_meta', {'id': 'session', 'cwd': '/repo'}),
        event('event_msg', {'type': 'task_started', 'turn_id': 'turn'}),
        event('turn_context', {'turn_id': 'turn', 'model': 'test-model'}),
        event('event_msg', {'type': 'user_message', 'message': 'private prompt'}),
        event('token_usage_record', {'turn_id': 'turn', 'thread_id': 'session', 'response_id': 'r1', 'usage': usage}),
        event('token_usage_record', {'turn_id': 'turn', 'thread_id': 'session', 'response_id': 'r1', 'usage': usage}),
        event('event_msg', {'type': 'token_count', 'info': {'last_token_usage': usage}}),
        event('response_item', {'type': 'custom_tool_call', 'call_id': 'c1', 'name': 'tool'}),
        event('event_msg', {'type': 'task_complete', 'turn_id': 'turn', 'duration_ms': 1500})]


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'rollout.jsonl'

    def write(self, events):
        self.path.write_text('\n'.join(json.dumps(e) for e in events) + '\n')

    @patch('codex_capture.record_prompts', return_value=False)
    def test_normalization_deduplication_and_privacy(self, _):
        self.write(rollout())
        row, = read_turns(self.path)
        self.assertEqual((row['input_tokens'], row['cache_read_tokens'], row['output_tokens'], row['total_tokens']), (40, 60, 20, 120))
        self.assertEqual(row['prompt'], '')
        self.assertEqual(row['n_tool_calls'], 1)
        self.assertEqual(row['elapsed_sec'], 1.5)
        self.assertIsNone(row['credit'])

    def test_epoch_completion_is_normalized(self):
        events = rollout()
        events[-1]["payload"]["completed_at"] = 1788489814
        self.write(events)
        ts = read_turns(self.path)[0]["ts"]
        self.assertEqual(datetime.datetime.fromisoformat(ts),
                         datetime.datetime(2026, 9, 4, 2, 43, 34, tzinfo=datetime.timezone.utc))

    def test_ts_uses_local_offset_like_other_ledger_rows(self):
        self.write(rollout())
        ts = read_turns(self.path)[0]["ts"]
        local = datetime.datetime(2026, 9, 14, 10, 0, tzinfo=datetime.timezone.utc).astimezone()
        self.assertEqual(ts, local.isoformat(timespec="seconds"))

    def test_incomplete_and_legacy_turns_are_skipped(self):
        self.write(rollout()[:-1])
        self.assertEqual(read_turns(self.path), [])
        self.write([e for e in rollout() if e['type'] != 'token_usage_record'])
        self.assertEqual(read_turns(self.path), [])

    def test_inherited_usage_is_not_counted_in_fork(self):
        events = rollout()
        events[0]['payload']['id'] = 'child-session'
        self.write(events)
        self.assertEqual(read_turns(self.path), [])

    def test_sync_is_idempotent_and_keeps_other_ledger(self):
        home = Path(self.tmp.name)
        source = home / 'sessions/2026/09/14'
        source.mkdir(parents=True)
        self.path = source / 'rollout.jsonl'
        self.write(rollout())
        directory = home / 'data'
        directory.mkdir()
        (directory / 'ledger.jsonl').write_text('original\n')
        collector = CodexCollector(home, directory, '2026-09')
        self.assertEqual(collector.sync(), 1)
        self.assertEqual(collector.sync(), 1)
        self.assertEqual(CodexCollector(home, directory, '2026-09').sync(), 1)
        self.assertEqual((directory / 'ledger.jsonl').read_text(), 'original\n')


    def test_sync_does_not_hold_main_ledger_lock_while_parsing(self):
        # capture.py (the Stop hook) takes .ledger.lock; parsing rollouts must never block it.
        home = Path(self.tmp.name)
        source = home / 'sessions/2026/09/14'
        source.mkdir(parents=True)
        self.path = source / 'rollout.jsonl'
        self.write(rollout())
        directory = home / 'data'
        directory.mkdir()
        seen = []

        def probe(path):
            with open(directory / '.ledger.lock', 'a') as fh:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fh, fcntl.LOCK_UN)
                    seen.append('free')
                except BlockingIOError:
                    seen.append('held')
            return read_turns(path)

        with patch('codex_capture.read_turns', side_effect=probe):
            self.assertEqual(CodexCollector(home, directory, '2026-09').sync(), 1)
        self.assertEqual(seen, ['free'])
        self.assertFalse((directory / '.ledger.lock').read_text())


if __name__ == '__main__':
    unittest.main()
