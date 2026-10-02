import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from ingestion.converter import article_markdown
from ingestion.pipeline import sync
from ingestion.scraper import ZendeskClient


def article(article_id=1, body="<p>Original content</p>"):
    return {"id": article_id, "title": "Sample article", "body": body,
            "html_url": f"https://support.optisigns.com/hc/en-us/articles/{article_id}",
            "updated_at": "2026-01-01T00:00:00Z"}


class FakeClient:
    source = "https://support.optisigns.com"
    locale = "en-us"

    def __init__(self, items):
        self.items = items

    def articles(self, include_query):
        yield from self.items


class ScraperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)

    def run_sync(self, items, minimum=1):
        return sync(FakeClient(items), self.output, limit=0, minimum=minimum, include_query="")

    def test_conversion_preserves_structure_links_code_and_source(self):
        body = '<nav>REMOVE MENU</nav><script>REMOVE SCRIPT</script><div class="ads">REMOVE AD</div>'
        body += '<h2 id="steps">Steps</h2><p>Read <a href="../guide#step">the guide</a>.</p>'
        body += '<ul><li>First</li><li>Second</li></ul>'
        body += '<pre><code class="language-python">if True:\n    print(&quot;hello&quot;)\n\n\n</code></pre>'
        result = article_markdown(article(body=body))
        self.assertIn('Article URL: https://support.optisigns.com/hc/en-us/articles/1', result)
        self.assertIn('## Steps', result)
        self.assertIn('<a id="steps"></a>', result)
        self.assertIn('[the guide](../guide#step)', result)
        self.assertIn('- First', result)
        self.assertIn('    print("hello")\n\n\n', result)
        self.assertNotIn('REMOVE', result)
        self.assertIn(chr(96) * 3 + 'python', result)

    def test_embedded_video_and_unicode_are_preserved(self):
        result = article_markdown(article(body='<p>Hướng dẫn màn hình</p><iframe title="YouTube" src="https://www.youtube.com/embed/abc"></iframe>'))
        self.assertIn('Hướng dẫn màn hình', result)
        self.assertIn('[YouTube](https://www.youtube.com/embed/abc)', result)

    def test_binary_image_payload_is_removed_but_caption_and_normal_links_survive(self):
        payload = "A" * 125000
        body = '<h2>Instructions</h2><p>Scan the QR code.</p>'
        body += f'<img src="data:image/png;base64,{payload}" alt="QR menu">'
        body += '<img src="../images/example.png" alt="Example">'
        body += '<a href="../guide">Read guide</a>'
        result = article_markdown(article(body=body))
        self.assertNotIn(payload, result)
        self.assertNotIn('data:image/', result)
        self.assertIn('QR menu (image available in original article)', result)
        self.assertIn('Scan the QR code.', result)
        self.assertIn('![Example](../images/example.png)', result)
        self.assertIn('[Read guide](../guide)', result)

    def test_image_only_article_keeps_reference_to_original(self):
        result = article_markdown(article(body='<img src="DATA:IMAGE/PNG;base64,AAAA">'))
        self.assertIn('Embedded image (image available in original article)', result)
        self.assertIn('Article URL:', result)

    def test_nested_backticks_do_not_break_code_fence(self):
        ticks = chr(96) * 3
        result = article_markdown(article(body='<pre>' + ticks + '\nsample\n' + ticks + '</pre>'))
        self.assertIn(chr(96) * 4 + '\n' + ticks, result)

    def test_second_run_skips_and_body_or_title_changes_update(self):
        item = article()
        self.assertEqual(self.run_sync([item])["added"], 1)
        path = self.output / "articles/1.md"
        stamp = path.stat().st_mtime_ns
        item['updated_at'] = '2026-02-01T00:00:00Z'
        self.assertEqual(self.run_sync([item])["skipped"], 1)
        self.assertEqual(path.stat().st_mtime_ns, stamp)
        item['body'] = '<p>Edited content</p>'
        self.assertEqual(self.run_sync([item])["updated"], 1)
        item['title'] = 'New title'
        self.assertEqual(self.run_sync([item])["updated"], 1)
        self.assertEqual(len(list(path.parent.glob('*.md'))), 1)

    def test_missing_or_damaged_local_file_is_repaired(self):
        self.run_sync([article()])
        path = self.output / 'articles/1.md'
        path.unlink()
        self.assertEqual(self.run_sync([article()])["updated"], 1)
        path.write_text('damaged', encoding='utf-8')
        self.assertEqual(self.run_sync([article()])["updated"], 1)
        self.assertIn('Original content', path.read_text(encoding='utf-8'))

    def test_empty_body_does_not_advance_state(self):
        self.run_sync([article()])
        before = (self.output / 'state.json').read_text(encoding='utf-8')
        with self.assertRaises(ValueError):
            self.run_sync([article(2), article(3, '<nav>only menu</nav>')])
        self.assertEqual(before, (self.output / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(json.loads((self.output / 'last-run.json').read_text())['status'], 'failed')

    def test_minimum_and_corrupt_state_fail_explicitly(self):
        with self.assertRaises(ValueError):
            self.run_sync([article()], minimum=30)
        self.assertFalse((self.output / 'state.json').exists())
        (self.output / 'state.json').write_text('broken')
        with self.assertRaises(json.JSONDecodeError):
            self.run_sync([article()])

    def test_failed_write_is_not_recorded_in_state(self):
        self.run_sync([article()])
        before = (self.output / 'state.json').read_text()
        from ingestion import pipeline
        original = pipeline.atomic_write
        def fail_markdown(path, text):
            if path.suffix == '.md':
                raise OSError('disk full')
            original(path, text)
        with patch('ingestion.pipeline.atomic_write', side_effect=fail_markdown), self.assertRaises(OSError):
            self.run_sync([article(2)])
        self.assertEqual(before, (self.output / 'state.json').read_text())

    def test_pagination_deduplicates_seed_and_ignores_drafts(self):
        client = ZendeskClient()
        draft = article(3)
        draft['draft'] = True
        responses = [
            {'results': [{'id': 1, 'title': 'YouTube'}]},
            {'article': article(1)},
            {'articles': [article(1), article(2), draft], 'next_page': '?page=2'},
            {'articles': [article(2), article(4)], 'next_page': None},
        ]
        with patch.object(client, 'get', side_effect=responses):
            self.assertEqual([a['id'] for a in client.articles()], [1, 2, 4])

    def test_repeated_pagination_is_rejected(self):
        client = ZendeskClient()
        data = {'articles': [], 'next_page': 'https://support.optisigns.com/page2'}
        with patch.object(client, 'get', return_value=data), self.assertRaises(ValueError):
            list(client.articles(''))

    def test_http_429_retries_but_404_does_not(self):
        url = 'https://support.optisigns.com/api/test'
        client = ZendeskClient()
        limited = HTTPError(url, 429, 'rate limited', {'Retry-After': '1'}, None)
        with patch('ingestion.scraper.urlopen', side_effect=limited) as opener, patch('ingestion.scraper.time.sleep') as sleep:
            with self.assertRaises(HTTPError):
                client.get(url)
            self.assertEqual(opener.call_count, 4)
            self.assertEqual(sleep.call_count, 3)
        missing = HTTPError(url, 404, 'missing', {}, None)
        with patch('ingestion.scraper.urlopen', side_effect=missing) as opener:
            with self.assertRaises(HTTPError):
                client.get(url)
            self.assertEqual(opener.call_count, 1)


if __name__ == '__main__':
    unittest.main()
