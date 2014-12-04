from django.test import SimpleTestCase
from django.utils.safestring import mark_safe

from ..utils import render, setup


class FirstTests(SimpleTestCase):

    @setup({'first01': '{{ a|first }} {{ b|first }}'})
    def test_first01(self):
        output = render('first01', {"a": ["a&b", "x"], "b": [mark_safe("a&b"), "x"]})
        self.assertEqual(output, "a&amp;b a&b")

    @setup({'first02': '{% autoescape off %}{{ a|first }} {{ b|first }}{% endautoescape %}'})
    def test_first02(self):
        output = render('first02', {"a": ["a&b", "x"], "b": [mark_safe("a&b"), "x"]})
        self.assertEqual(output, "a&b a&b")
