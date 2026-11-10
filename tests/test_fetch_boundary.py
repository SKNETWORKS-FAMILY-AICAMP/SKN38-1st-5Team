import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts import fetch_boundary as fetch


class FetchBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.destination = Path(self.directory) / 'raw' / 'boundary.geojson'
        self.body = json.dumps({'type': 'FeatureCollection', 'features': [{}] * 25}).encode()
        self.enterContext(patch.object(fetch, 'EXPECTED_SHA256', hashlib.sha256(self.body).hexdigest()))
        self.request = self.enterContext(patch.object(fetch.requests, 'get'))
        self.response = MagicMock(status_code=200)
        self.response.iter_content.return_value = [self.body]
        self.request.return_value.__enter__.return_value = self.response

    def test_verified_download_is_reused_without_network(self):
        self.assertTrue(fetch.fetch_boundary(self.destination))
        self.assertEqual(self.destination.read_bytes(), self.body)
        self.request.assert_called_once_with(fetch.SOURCE, stream=True, timeout=(3, 20), allow_redirects=False)
        self.request.reset_mock()
        self.assertFalse(fetch.fetch_boundary(self.destination))
        self.request.assert_not_called()

    def test_bad_hash_keeps_existing_file(self):
        self.destination.parent.mkdir()
        self.destination.write_bytes(b'existing')
        self.response.iter_content.return_value = [b'wrong source']
        with self.assertRaises(ValueError):
            fetch.fetch_boundary(self.destination)
        self.assertEqual(self.destination.read_bytes(), b'existing')

    def test_oversized_or_redirected_download_is_not_published(self):
        self.response.iter_content.return_value = [b'x' * (fetch.MAX_BYTES + 1)]
        with self.assertRaises(ValueError):
            fetch.fetch_boundary(self.destination)
        self.assertFalse(self.destination.exists())
        self.response.status_code = 302
        with self.assertRaises(ValueError):
            fetch.fetch_boundary(self.destination)
        self.assertFalse(self.destination.exists())
