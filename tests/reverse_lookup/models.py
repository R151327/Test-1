"""
Reverse lookups

This demonstrates the reverse lookup features of the database API.
"""

from django.db import models
from django.utils.encoding import python_2_unicode_compatible


@python_2_unicode_compatible
class User(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class Poll(models.Model):
    question = models.CharField(max_length=200)
    creator = models.ForeignKey(User)

    def __str__(self):
        return self.question


@python_2_unicode_compatible
class Choice(models.Model):
    name = models.CharField(max_length=100)
    poll = models.ForeignKey(Poll, related_name="poll_choice")
    related_poll = models.ForeignKey(Poll, related_name="related_choice")

    def __str__(self):
        return self.name
