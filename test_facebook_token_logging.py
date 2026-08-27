import io
import logging
import unittest
from datetime import datetime, timezone
from contextlib import redirect_stdout
from unittest.mock import patch

import comment_bot
import main
import review_bot


TOKEN = "SENTINEL_FACEBOOK_ACCESS_TOKEN"


class Response:
    def __init__(self, ok=True, text="", payload=None):
        self.ok = ok
        self.text = text
        self.status_code = 500 if not ok else 200
        self._payload = payload or {"data": []}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.text)


class FacebookLoggingTests(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        comment_bot.log.addHandler(self.handler)
        comment_bot.log.setLevel(logging.INFO)

    def tearDown(self):
        comment_bot.log.removeHandler(self.handler)

    def assert_token_absent(self):
        self.assertNotIn(TOKEN, self.stream.getvalue())

    def test_success_uses_authorization_header_and_never_logs_token(self):
        with patch.object(comment_bot.requests, "request", return_value=Response(payload={"data": [{"id": "post-1"}]})) as call:
            posts = comment_bot.get_recent_posts("page-1", TOKEN, datetime.now(timezone.utc))

        self.assertEqual(posts, [{"id": "post-1"}])
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertNotIn("access_token", kwargs.get("params", {}))
        self.assert_token_absent()

    def test_http_error_redacts_token_from_response_logging(self):
        response = Response(False, "Graph error https://graph.facebook.com/?access_token=" + TOKEN)
        with patch.object(comment_bot.requests, "request", return_value=response):
            self.assertEqual(comment_bot.get_comments("post-1", TOKEN), [])
        self.assert_token_absent()

    def test_dns_network_failure_redacts_token_from_exception_logging(self):
        with patch.object(comment_bot.requests, "request", side_effect=OSError("DNS failed for access_token=" + TOKEN)):
            with self.assertRaises(comment_bot.FacebookRequestError) as raised:
                comment_bot.get_recent_posts("page-1", TOKEN, datetime.now(timezone.utc))
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assert_token_absent()

    def test_timeout_redacts_token_from_exception_logging(self):
        with patch.object(comment_bot.requests, "request", side_effect=TimeoutError("timed out with " + TOKEN)):
            with self.assertRaises(comment_bot.FacebookRequestError) as raised:
                comment_bot.post_reply("comment-1", TOKEN, "synthetic reply")
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assert_token_absent()

    def test_unexpected_exception_and_reply_response_are_redacted(self):
        with patch.object(comment_bot.requests, "request", side_effect=RuntimeError("unexpected " + TOKEN)):
            with self.assertRaises(comment_bot.FacebookRequestError) as raised:
                comment_bot.post_reply("comment-1", TOKEN, "synthetic reply")
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assert_token_absent()

        response = Response(False, "failure contains " + TOKEN)
        with patch.object(comment_bot.requests, "request", return_value=response):
            ok, response_text = comment_bot.post_reply("comment-1", TOKEN, "synthetic reply")
        self.assertFalse(ok)
        self.assertNotIn(TOKEN, response_text)
        self.assert_token_absent()

    def test_review_bot_facebook_calls_keep_tokens_out_of_urls_and_errors(self):
        with patch.object(review_bot.requests, "get", return_value=Response(payload={"data": []})) as get_call:
            review_bot.fb_get("page-1/ratings", TOKEN, {"fields": "id"})
        self.assertNotIn("access_token", get_call.call_args.kwargs.get("params", {}))
        self.assertEqual(get_call.call_args.kwargs["headers"]["Authorization"], "Bearer " + TOKEN)

        response = Response(False, "error " + TOKEN)
        output = io.StringIO()
        with patch.object(review_bot.requests, "post", return_value=response), redirect_stdout(output):
            with self.assertRaises(Exception):
                review_bot.fb_post("comment-1/comments", TOKEN, {"message": "synthetic"})
        self.assertNotIn(TOKEN, output.getvalue())

    def test_runner_redactor_covers_forwarded_query_strings(self):
        self.assertNotIn(TOKEN, main._redact_facebook_secret("https://graph.facebook.com/?access_token=" + TOKEN))


if __name__ == "__main__":
    unittest.main()
