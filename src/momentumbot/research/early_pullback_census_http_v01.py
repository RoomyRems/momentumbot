"""Fixed-host HTTPS exchange; no environment credentials, retries or redirects.

This callable is not a capture launcher or authorization. A future separately
registered launcher must enforce durable consumption before supplying it.
"""
import http.client
import time
from urllib.parse import urlencode, urlsplit

from momentumbot.research import early_pullback_census_v01 as m


class DirectHTTPS:
    def __init__(self, *, connection_factory=http.client.HTTPSConnection, clock=time.monotonic):
        self.connection_factory, self.clock = connection_factory, clock

    def __call__(self, request, credential):
        m.validate_request(request)
        m.require(type(credential) is str and 8 <= len(credential) <= 1024
                  and credential.isascii() and all(32 < ord(c) < 127 for c in credential), "invalid credential")
        params = dict(request["params"], apiKey=credential)
        path = urlsplit(request["url"]).path + "?" + urlencode(params)
        connection = self.connection_factory("api.massive.com", timeout=30)
        started = self.clock()
        body = bytearray()
        status, encoding, complete = None, "identity", False
        try:
            connection.request("GET", path, headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "MomentumBot " + m.ID})
            response = connection.getresponse()
            status = response.status
            encoding = response.getheader("Content-Encoding", "identity").lower()
            length = response.getheader("Content-Length")
            if length is not None:
                m.require(length.isascii() and length.isdecimal(), "invalid content length")
                length = int(length)
            while len(body) <= m.MAX_BODY:
                if self.clock() - started >= 30:
                    break
                chunk = response.read1(min(65_536, m.MAX_BODY + 1 - len(body)))
                if not chunk:
                    complete = length is None or len(body) == length
                    break
                body.extend(chunk)
                if len(body) > m.MAX_BODY:
                    break
            return {"status": status, "body": bytes(body), "complete": complete, "encoding": encoding}
        except (http.client.IncompleteRead, TimeoutError, OSError):
            if status is None:
                raise
            return {"status": status, "body": bytes(body), "complete": False, "encoding": encoding}
        finally:
            connection.close()
