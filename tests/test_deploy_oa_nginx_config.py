from __future__ import annotations

from pathlib import Path
import unittest


NGINX_CONFIG_PATH = Path(__file__).resolve().parents[1] / "deploy" / "oa" / "nginx.fin-ops.conf.example"


class DeployOANginxConfigTests(unittest.TestCase):
    def test_fin_ops_spa_routes_fall_back_to_fin_ops_index(self) -> None:
        config = NGINX_CONFIG_PATH.read_text(encoding="utf-8")

        self.assertIn("location = /fin-ops", config)
        self.assertIn("return 301 /fin-ops/;", config)
        self.assertIn("location ^~ /fin-ops/ {", config)
        self.assertIn("alias /www/wwwroot/fin-ops/dist/;", config)
        self.assertIn("try_files $uri $uri/ /fin-ops/index.html;", config)

    def test_hashed_assets_do_not_fall_back_to_index_html(self) -> None:
        config = NGINX_CONFIG_PATH.read_text(encoding="utf-8")

        self.assertIn("location ^~ /fin-ops/assets/ {", config)
        self.assertIn("alias /www/wwwroot/fin-ops/dist/assets/;", config)
        self.assertIn("try_files $uri =404;", config)
        self.assertIn('add_header Cache-Control "public, immutable";', config)

    def test_index_html_is_not_cached_and_api_remains_proxied(self) -> None:
        config = NGINX_CONFIG_PATH.read_text(encoding="utf-8")

        self.assertIn("location = /fin-ops/index.html {", config)
        self.assertIn('add_header Cache-Control "no-store";', config)
        self.assertIn("location /fin-ops-api/ {", config)
        self.assertIn("proxy_pass http://fin_ops_api/;", config)

    def test_fin_ops_relative_api_routes_do_not_fall_back_to_index_html(self) -> None:
        config = NGINX_CONFIG_PATH.read_text(encoding="utf-8")

        relative_api_index = config.index("location ^~ /fin-ops/api/ {")
        spa_fallback_index = config.index("location ^~ /fin-ops/ {")
        self.assertLess(relative_api_index, spa_fallback_index)
        self.assertIn("rewrite ^/fin-ops/api/(.*)$ /api/$1 break;", config)
        self.assertIn("proxy_pass http://fin_ops_api;", config)

    def test_api_proxies_forward_conditional_request_etags(self) -> None:
        config = NGINX_CONFIG_PATH.read_text(encoding="utf-8")

        self.assertEqual(
            config.count("proxy_set_header If-None-Match $http_if_none_match;"),
            4,
        )


if __name__ == "__main__":
    unittest.main()
