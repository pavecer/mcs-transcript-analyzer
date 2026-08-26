import json
import unittest
from unittest.mock import patch

from scripts.publish_linkedin_post import LINKEDIN_POSTS_ENDPOINT, publish_post, update_post


class FakeResponse:
    status = 201
    headers = {"x-restli-id": "urn:li:share:123"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeUpdateResponse(FakeResponse):
    status = 204


class PublishLinkedInPostTests(unittest.TestCase):
    @patch("scripts.publish_linkedin_post.urllib.request.urlopen")
    def test_publishes_public_main_feed_post(self, urlopen):
        urlopen.return_value = FakeResponse()

        post_urn = publish_post(
            "Release details",
            "urn:li:person:abc",
            "secret-token",
            "202608",
        )

        self.assertEqual(post_urn, "urn:li:share:123")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, LINKEDIN_POSTS_ENDPOINT)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer secret-token")
        self.assertEqual(request.headers["Linkedin-version"], "202608")
        self.assertEqual(payload["author"], "urn:li:person:abc")
        self.assertEqual(payload["commentary"], "Release details")
        self.assertEqual(payload["lifecycleState"], "PUBLISHED")
        self.assertEqual(payload["distribution"]["feedDistribution"], "MAIN_FEED")

    @patch("scripts.publish_linkedin_post.urllib.request.urlopen")
    def test_updates_existing_post_commentary(self, urlopen):
        urlopen.return_value = FakeUpdateResponse()

        post_urn = update_post(
            "Short release announcement",
            "urn:li:share:123",
            "secret-token",
            "202608",
        )

        self.assertEqual(post_urn, "urn:li:share:123")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(
            request.full_url,
            f"{LINKEDIN_POSTS_ENDPOINT}/urn%3Ali%3Ashare%3A123",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["X-restli-method"], "PARTIAL_UPDATE")
        self.assertEqual(payload, {"patch": {"$set": {"commentary": "Short release announcement"}}})


if __name__ == "__main__":
    unittest.main()