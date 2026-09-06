from __future__ import annotations

import os


bind = os.environ.get("FIN_OPS_HTTP_BIND", "127.0.0.1:18001")
pidfile = os.environ.get("FIN_OPS_HTTP_PIDFILE", "/run/fin-ops/gunicorn.pid")
worker_class = "gthread"
workers = int(os.environ.get("FIN_OPS_HTTP_WORKERS", "1"))
threads = int(os.environ.get("FIN_OPS_HTTP_THREADS", "10"))
worker_connections = threads
backlog = int(os.environ.get("FIN_OPS_HTTP_BACKLOG", "128"))
timeout = int(os.environ.get("FIN_OPS_HTTP_TIMEOUT_SECONDS", "120"))
graceful_timeout = int(os.environ.get("FIN_OPS_HTTP_GRACEFUL_TIMEOUT_SECONDS", "30"))
keepalive = int(os.environ.get("FIN_OPS_HTTP_KEEPALIVE_SECONDS", "5"))
max_requests = int(os.environ.get("FIN_OPS_HTTP_MAX_REQUESTS", "5000"))
max_requests_jitter = int(os.environ.get("FIN_OPS_HTTP_MAX_REQUESTS_JITTER", "500"))
accesslog = "-"
errorlog = "-"
capture_output = True
logger_class = "fin_ops_platform.app.cash_access_logger.CashAccessLogger"
access_log_format = (
    '{"event":"gunicorn_access","remote":"%(h)s","request":"%(r)s",'
    '"status":%(s)s,"bytes":%(b)s,"duration_us":%(D)s,"request_id":"%({x-request-id}o)s"}'
)
