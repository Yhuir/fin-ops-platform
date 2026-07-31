from __future__ import annotations

import atexit

from fin_ops_platform.app.application_factory import create_application
from fin_ops_platform.app.http_adapter import WsgiHttpAdapter


application = WsgiHttpAdapter(create_application())
atexit.register(application.close)
