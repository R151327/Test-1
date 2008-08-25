from django.conf import settings
from django.contrib.comments import signals
from django.contrib.comments.models import Comment
from regressiontests.comment_tests.models import Article
from regressiontests.comment_tests.tests import CommentTestCase

class CommentViewTests(CommentTestCase):

    def testPostCommentHTTPMethods(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        response = self.client.get("/post/", data)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "POST")

    def testPostCommentMissingCtype(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        del data["content_type"]
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 400)

    def testPostCommentBadCtype(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        data["content_type"] = "Nobody expects the Spanish Inquisition!"
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 400)

    def testPostCommentMissingObjectPK(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        del data["object_pk"]
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 400)

    def testPostCommentBadObjectPK(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        data["object_pk"] = "14"
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 400)

    def testCommentPreview(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        data["submit"] = "preview"
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "comments/preview.html")

    def testHashTampering(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        data["security_hash"] = "Nobody expects the Spanish Inquisition!"
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 400)

    def testDebugCommentErrors(self):
        """The debug error template should be shown only if DEBUG is True"""
        olddebug = settings.DEBUG

        settings.DEBUG = True
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        data["security_hash"] = "Nobody expects the Spanish Inquisition!"
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "comments/400-debug.html")

        settings.DEBUG = False
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 400)
        self.assertTemplateNotUsed(response, "comments/400-debug.html")

        settings.DEBUG = olddebug

    def testCreateValidComment(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        self.response = self.client.post("/post/", data, REMOTE_ADDR="1.2.3.4")
        self.assertEqual(self.response.status_code, 302)
        self.assertEqual(Comment.objects.count(), 1)
        c = Comment.objects.all()[0]
        self.assertEqual(c.ip_address, "1.2.3.4")
        self.assertEqual(c.comment, "This is my comment")

    def testPreventDuplicateComments(self):
        """Prevent posting the exact same comment twice"""
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        self.client.post("/post/", data)
        self.client.post("/post/", data)
        self.assertEqual(Comment.objects.count(), 1)

        # This should not trigger the duplicate prevention
        self.client.post("/post/", dict(data, comment="My second comment."))
        self.assertEqual(Comment.objects.count(), 2)

    def testCommentSignals(self):
        """Test signals emitted by the comment posting view"""

        # callback
        def receive(sender, **kwargs):
            self.assertEqual(sender.comment, "This is my comment")
            # TODO: Get the two commented tests below to work.
#            self.assertEqual(form_data["comment"], "This is my comment")
#            self.assertEqual(request.method, "POST")
            received_signals.append(kwargs.get('signal'))

        # Connect signals and keep track of handled ones
        received_signals = []
        excepted_signals = [signals.comment_will_be_posted, signals.comment_was_posted]
        for signal in excepted_signals:
            signal.connect(receive)

        # Post a comment and check the signals
        self.testCreateValidComment()
        self.assertEqual(received_signals, excepted_signals)

    def testWillBePostedSignal(self):
        """
        Test that the comment_will_be_posted signal can prevent the comment from
        actually getting saved
        """
        def receive(sender, **kwargs): return False
        signals.comment_will_be_posted.connect(receive)
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        response = self.client.post("/post/", data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Comment.objects.count(), 0)

    def testWillBePostedSignalModifyComment(self):
        """
        Test that the comment_will_be_posted signal can modify a comment before
        it gets posted
        """
        def receive(sender, **kwargs):
            sender.is_public = False # a bad but effective spam filter :)...

        signals.comment_will_be_posted.connect(receive)
        self.testCreateValidComment()
        c = Comment.objects.all()[0]
        self.failIf(c.is_public)

    def testCommentNext(self):
        """Test the different "next" actions the comment view can take"""
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        response = self.client.post("/post/", data)
        self.assertEqual(response["Location"], "http://testserver/posted/?c=1")

        data["next"] = "/somewhere/else/"
        data["comment"] = "This is another comment"
        response = self.client.post("/post/", data)
        self.assertEqual(response["Location"], "http://testserver/somewhere/else/?c=2")

    def testCommentDoneView(self):
        a = Article.objects.get(pk=1)
        data = self.getValidData(a)
        response = self.client.post("/post/", data)
        response = self.client.get("/posted/", {'c':1})
        self.assertTemplateUsed(response, "comments/posted.html")
        self.assertEqual(response.context[0]["comment"], Comment.objects.get(pk=1))

