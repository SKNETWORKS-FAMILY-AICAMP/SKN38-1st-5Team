import json
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.errors import StreamlitSecretNotFoundError
from streamlit.testing.v1 import AppTest

from tests import app_env
import kakao_map


class KakaoKeyTest(unittest.TestCase):
    def read(self, reader, secrets, environment=None):
        with patch.object(kakao_map.st, "secrets", secrets), patch.dict("os.environ", environment or {}, clear=True):
            return reader()

    def test_keys_come_from_their_own_secret_names(self):
        secrets = {"kakao": {"javascript_api_key": " browser ", "rest_api_key": "server"}}
        self.assertEqual(self.read(kakao_map.javascript_key, secrets), "browser")
        self.assertEqual(self.read(kakao_map.rest_key, secrets), "server")

    def test_environment_is_used_when_secret_is_blank_or_missing(self):
        environment = {"KAKAO_JAVASCRIPT_API_KEY": "from-env"}
        self.assertEqual(self.read(kakao_map.javascript_key, {"kakao": {"javascript_api_key": " "}}, environment), "from-env")
        self.assertEqual(self.read(kakao_map.javascript_key, {}, environment), "from-env")

    def test_missing_key_is_empty_string(self):
        self.assertEqual(self.read(kakao_map.javascript_key, {}), "")
        self.assertEqual(self.read(kakao_map.rest_key, {"kakao": "invalid"}), "")

    def test_missing_secrets_file_is_empty_string(self):
        class MissingSecrets:
            def get(self, *_):
                raise StreamlitSecretNotFoundError("No secrets found.")

        self.assertEqual(self.read(kakao_map.javascript_key, MissingSecrets()), "")


class SdkLoaderTest(unittest.TestCase):
    def test_loader_follows_dynamic_loading_contract(self):
        for fragment in ("https://dapi.kakao.com/v2/maps/sdk.js", "autoload=false", "kakao.maps.load(",
                         "encodeURIComponent(appkey)", "setTimeout(fail, 8000)", "clusterer"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, kakao_map.SDK_LOADER_JS)
        self.assertNotIn("//dapi.kakao.com/v2/maps/sdk.js?appkey=' + appkey", kakao_map.SDK_LOADER_JS)

    def test_failed_load_can_be_retried(self):
        self.assertIn("window.chachachaKakaoSdk = null", kakao_map.SDK_LOADER_JS)


class OwnershipMapPayloadTest(unittest.TestCase):
    def hero(self, key):
        with patch("scene_city3d.javascript_key", return_value=key):
            app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
            app.switch_page("app_pages/ownership.py").run()
        self.assertFalse(app.exception)
        return next(item.proto for item in app.get("bidi_component")
                    if item.proto.component_name == "chachacha_h2_seoul")

    def test_without_key_the_svg_scene_is_used_and_no_sdk_is_requested(self):
        hero = self.hero("")
        self.assertEqual(json.loads(hero.json)["kakao_key"], "")
        self.assertIn('class="h2-city"', hero.html_content)

    def test_with_key_the_same_component_receives_boundaries_and_key(self):
        hero = self.hero("test-only")
        payload = json.loads(hero.json)
        self.assertEqual(payload["kakao_key"], "test-only")
        self.assertEqual(len([d for d in payload["districts"] if d["polygons"]]), 25)
        self.assertIn('class="h2-kakao"', hero.html_content)
        self.assertIn("window.chachachaKakao", hero.js_content)


if __name__ == "__main__":
    unittest.main()
