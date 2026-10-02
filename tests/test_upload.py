import hashlib
import httpx
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from google.genai import types, errors
from upload.client import GeminiError, RetryableGeminiError, OperationFailed, safe_call
from upload.config import Settings, load_settings
from upload.pipeline import sync_upload
from upload.state import save


class FakeStore:
    def __init__(self):
        self.store = "fileSearchStores/test"
        self.docs = {}
        self.operations = {}
        self.starts = 0
        self.deleted = []
        self.timeout_once = False
        self.fail_once = False
        self.fail_cleanup = False

    def ensure_store(self, name, owner):
        return name or self.store

    def documents(self, store):
        return list(self.docs.values())

    def start(self, store, path, metadata):
        self.starts += 1
        name = f"{store}/documents/doc-{self.starts}"
        self.docs[name] = {"name": name, "state": "STATE_PENDING", "metadata": metadata}
        operation = f"fileSearchStores/test/upload/operations/op-{self.starts}"
        self.operations[operation] = name
        return SimpleNamespace(name=operation)

    def wait(self, operation):
        if self.timeout_once:
            self.timeout_once = False
            raise TimeoutError("still indexing")
        name = self.operations[operation]
        if self.fail_once:
            self.fail_once = False
            self.docs[name]["state"] = "STATE_FAILED"
            raise OperationFailed("indexing failed")
        return self.wait_document(name)

    def wait_document(self, name):
        self.docs[name]["state"] = "STATE_ACTIVE"
        return self.docs[name]

    def delete(self, name):
        if self.fail_cleanup:
            self.fail_cleanup = False
            raise GeminiError("cleanup interrupted")
        self.deleted.append(name)
        self.docs.pop(name, None)


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.client = FakeStore()
        self.write_article("original")

    def write_article(self, body):
        path = self.output / "articles/1.md"
        path.parent.mkdir(exist_ok=True)
        text = "# Example\n\nArticle URL: https://support.optisigns.com/article/1\n\n" + body
        path.write_text(text, encoding="utf-8")
        record = {"path": "articles/1.md", "url": "https://support.optisigns.com/article/1",
                  "content_hash": hashlib.sha256(text.encode()).hexdigest()}
        save(self.output / "state.json", {"version": 1, "source": "https://support.optisigns.com",
                                         "locale": "en-us", "articles": {"1": record}})

    def state(self):
        return json.loads((self.output / "upload-state.json").read_text())

    def test_first_upload_and_unchanged_skip(self):
        self.assertEqual(sync_upload(self.client, self.output)["added"], 1)
        self.assertEqual(sync_upload(self.client, self.output)["skipped"], 1)
        self.assertEqual(self.client.starts, 1)
        self.assertEqual(len(self.client.docs), 1)
        self.assertEqual(self.state()["pending"], {})

    def test_changed_article_replaces_old_document(self):
        sync_upload(self.client, self.output)
        old = self.state()["articles"]["1"]["document_name"]
        self.write_article("edited")
        report = sync_upload(self.client, self.output)
        self.assertEqual(report["updated"], 1)
        self.assertEqual(self.client.deleted, [old])
        self.assertEqual(len(self.client.docs), 1)

    def test_failed_replacement_keeps_old_and_retries(self):
        sync_upload(self.client, self.output)
        old = self.state()["articles"]["1"]
        self.write_article("edited")
        self.client.fail_once = True
        with self.assertRaises(OperationFailed):
            sync_upload(self.client, self.output)
        self.assertEqual(self.state()["articles"]["1"], old)
        self.assertIn(old["document_name"], self.client.docs)
        self.assertEqual(sync_upload(self.client, self.output)["updated"], 1)
        self.assertEqual(len(self.client.docs), 1)

    def test_timeout_resumes_without_duplicate_upload(self):
        self.client.timeout_once = True
        with self.assertRaises(TimeoutError):
            sync_upload(self.client, self.output)
        self.assertNotIn("1", self.state()["articles"])
        self.assertIn("1", self.state()["pending"])
        self.assertEqual(sync_upload(self.client, self.output)["added"], 1)
        self.assertEqual(self.client.starts, 1)

    def test_content_changed_while_old_operation_pending(self):
        self.client.timeout_once = True
        with self.assertRaises(TimeoutError):
            sync_upload(self.client, self.output)
        self.write_article("newer")
        sync_upload(self.client, self.output)
        self.assertEqual(self.client.starts, 2)
        self.assertEqual(len(self.client.docs), 1)
        expected = json.loads((self.output / "state.json").read_text())["articles"]["1"]["content_hash"]
        self.assertEqual(self.state()["articles"]["1"]["uploaded_hash"], expected)

    def test_retry_recovers_remote_document_if_operation_was_not_saved(self):
        self.client.timeout_once = True
        with self.assertRaises(TimeoutError):
            sync_upload(self.client, self.output)
        state = self.state()
        state["pending"] = {}
        save(self.output / "upload-state.json", state)
        sync_upload(self.client, self.output)
        self.assertEqual(self.client.starts, 1)

    def test_cleanup_failure_is_retried_without_reupload(self):
        sync_upload(self.client, self.output)
        self.write_article("edited")
        self.client.fail_cleanup = True
        with self.assertRaises(GeminiError):
            sync_upload(self.client, self.output)
        self.assertEqual(self.client.starts, 2)
        sync_upload(self.client, self.output)
        self.assertEqual(self.client.starts, 2)
        self.assertEqual(len(self.client.docs), 1)

    def test_other_documents_are_never_deleted(self):
        self.client.docs['unrelated'] = {"name": 'unrelated', "state": "STATE_ACTIVE", "metadata": {"article_id": "1"}}
        sync_upload(self.client, self.output)
        self.write_article("edited")
        sync_upload(self.client, self.output)
        self.assertIn('unrelated', self.client.docs)

    def test_missing_remote_document_is_uploaded_again(self):
        sync_upload(self.client, self.output)
        self.client.docs.clear()
        self.assertEqual(sync_upload(self.client, self.output)["updated"], 1)
        self.assertEqual(self.client.starts, 2)

    def test_invalid_local_content_causes_no_remote_upload(self):
        (self.output / "articles/1.md").write_text("unexpected edit")
        with self.assertRaises(ValueError):
            sync_upload(self.client, self.output)
        self.assertEqual(self.client.starts, 0)

    def test_conflicting_store_is_rejected(self):
        sync_upload(self.client, self.output)
        with self.assertRaises(ValueError):
            sync_upload(self.client, self.output, "fileSearchStores/other")
        self.assertEqual(self.client.starts, 1)

    def test_missing_key_is_clear_and_key_not_in_repr_or_errors(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                load_settings(self.output)
        self.assertNotIn("test-secret", repr(Settings("test-secret")))
        def fail():
            raise RuntimeError("test-secret")
        with self.assertRaises(GeminiError) as caught:
            safe_call(fail)
        self.assertNotIn("test-secret", str(caught.exception))

    def test_upload_read_timeout_reports_article_without_exposing_request(self):
        def fail(*args, **kwargs):
            raise httpx.ReadTimeout("secret-key-in-request")
        def timed_out_start(*args):
            return safe_call(fail)
        with patch.object(self.client, 'start', side_effect=timed_out_start), patch('upload.pipeline.time.sleep'):
            with self.assertRaisesRegex(GeminiError, 'ReadTimeout'):
                sync_upload(self.client, self.output)
        report = json.loads((self.output / 'upload-last-run.json').read_text())
        self.assertEqual(report['failed_article_id'], '1')
        self.assertNotIn('secret-key-in-request', report['error'])
        self.assertEqual(self.state()['articles'], {})
        self.assertEqual(sync_upload(self.client, self.output)['added'], 1)

    def test_temporary_upload_failure_retries_current_article(self):
        original = self.client.start
        calls = []
        def flaky(*args):
            calls.append(1)
            if len(calls) == 1:
                raise RetryableGeminiError('Gemini HTTP 503')
            return original(*args)
        with patch.object(self.client, 'start', side_effect=flaky), patch('upload.pipeline.time.sleep'):
            report = sync_upload(self.client, self.output)
        self.assertEqual(report['added'], 1)
        self.assertEqual(report['retries'], 1)
        self.assertEqual(self.client.starts, 1)

    def test_lost_upload_response_reconciles_before_retry(self):
        original = self.client.start
        def lost_response(*args):
            operation = original(*args)
            self.client.wait(operation.name)
            raise RetryableGeminiError('response lost')
        with patch.object(self.client, 'start', side_effect=lost_response), patch('upload.pipeline.time.sleep'):
            report = sync_upload(self.client, self.output)
        self.assertEqual(report['added'], 1)
        self.assertEqual(report['retries'], 1)
        self.assertEqual(self.client.starts, 1)
        self.assertEqual(len(self.client.docs), 1)

    def test_read_retries_are_bounded_and_writes_are_not_blindly_retried(self):
        def fail():
            raise httpx.ReadTimeout('secret')
        with patch('upload.client.time.sleep'), patch('builtins.print'):
            from unittest.mock import Mock
            read = Mock(side_effect=fail)
            with self.assertRaises(RetryableGeminiError):
                safe_call(read, _retry_read=True)
            self.assertEqual(read.call_count, 3)
            write = Mock(side_effect=fail)
            with self.assertRaises(RetryableGeminiError):
                safe_call(write)
            self.assertEqual(write.call_count, 1)

    def test_active_unchanged_document_uses_fresh_catalog_without_extra_get(self):
        sync_upload(self.client, self.output)
        with patch.object(self.client, 'wait_document', side_effect=AssertionError('redundant GET')):
            self.assertEqual(sync_upload(self.client, self.output)['skipped'], 1)
        self.assertEqual(self.client.starts, 1)

    def test_api_503_is_retryable_but_auth_error_is_not(self):
        def unavailable():
            raise errors.ServerError(503, {'error': {'message': 'secret'}})
        with self.assertRaises(RetryableGeminiError) as caught:
            safe_call(unavailable)
        self.assertNotIn('secret', str(caught.exception))
        def unauthorized():
            raise errors.ClientError(401, {'error': {'message': 'secret'}})
        with self.assertRaises(GeminiError) as caught:
            safe_call(unauthorized, _retry_read=True)
        self.assertNotIsInstance(caught.exception, RetryableGeminiError)
        self.assertNotIn('secret', str(caught.exception))

    def test_retry_after_cleanup_failure_preserves_updated_count(self):
        sync_upload(self.client, self.output)
        self.write_article('edited')
        original = self.client.delete
        calls = []
        def flaky(name):
            calls.append(name)
            if len(calls) == 1:
                raise RetryableGeminiError('cleanup 503')
            return original(name)
        with patch.object(self.client, 'delete', side_effect=flaky), patch('upload.pipeline.time.sleep'):
            report = sync_upload(self.client, self.output)
        self.assertEqual(report['updated'], 1)
        self.assertEqual(report['skipped'], 0)
        self.assertEqual(report['files_embedded'], 1)
        self.assertEqual(self.client.starts, 2)
        self.assertEqual(len(self.client.docs), 1)

    def test_chunk_count_is_not_fabricated(self):
        report = sync_upload(self.client, self.output)
        self.assertIsNone(report["embedded_chunks"])
        self.assertEqual(report["files_embedded"], 1)
        self.assertEqual(report["estimated_chunks_embedded"], 1)
        repeated = sync_upload(self.client, self.output)
        self.assertEqual(repeated["estimated_chunks_embedded"], 0)
        self.assertIsNone(repeated["embedded_chunks"])
        config = types.UploadToFileSearchStoreConfig(chunking_config={
            "white_space_config": report["chunking"]}, mime_type="text/markdown")
        self.assertEqual(config.chunking_config.white_space_config.max_tokens_per_chunk, 512)


if __name__ == '__main__':
    unittest.main()
