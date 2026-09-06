"""Retain Gunicorn access diagnostics without private cash URLs or query text."""

from gunicorn.glogging import Logger

from fin_ops_platform.app.route_access_policy import is_cash_request


class CashAccessLogger(Logger):
    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        path = environ.get("PATH_INFO", "").removeprefix("/fin-ops-api")
        if is_cash_request(path):
            atoms["r"] = f'{environ["REQUEST_METHOD"]} /api/cash {environ["SERVER_PROTOCOL"]}'
            atoms["U"] = "/api/cash"
            atoms["q"] = ""
        return atoms
