# -*- coding: utf-8 -*-
# Tests for the media handling on widgets and forms

media_tests = r"""
>>> from django.forms import TextInput, Media, TextInput, CharField, Form, MultiWidget
>>> from django.conf import settings
>>> ORIGINAL_MEDIA_URL = settings.MEDIA_URL
>>> settings.MEDIA_URL = 'http://media.example.com/media/'

# Check construction of media objects
>>> m = Media(css={'all': ('path/to/css1','/path/to/css2')}, js=('/path/to/js1','http://media.other.com/path/to/js2','https://secure.other.com/path/to/js3'))
>>> print m
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>

>>> class Foo:
...     css = {
...        'all': ('path/to/css1','/path/to/css2')
...     }
...     js = ('/path/to/js1','http://media.other.com/path/to/js2','https://secure.other.com/path/to/js3')
>>> m3 = Media(Foo)
>>> print m3
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>

>>> m3 = Media(Foo)
>>> print m3
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>

# A widget can exist without a media definition
>>> class MyWidget(TextInput):
...     pass

>>> w = MyWidget()
>>> print w.media
<BLANKLINE>

###############################################################
# DSL Class-based media definitions
###############################################################

# A widget can define media if it needs to.
# Any absolute path will be preserved; relative paths are combined
# with the value of settings.MEDIA_URL
>>> class MyWidget1(TextInput):
...     class Media:
...         css = {
...            'all': ('path/to/css1','/path/to/css2')
...         }
...         js = ('/path/to/js1','http://media.other.com/path/to/js2','https://secure.other.com/path/to/js3')

>>> w1 = MyWidget1()
>>> print w1.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>

# Media objects can be interrogated by media type
>>> print w1.media['css']
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />

>>> print w1.media['js']
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>

# Media objects can be combined. Any given media resource will appear only
# once. Duplicated media definitions are ignored.
>>> class MyWidget2(TextInput):
...     class Media:
...         css = {
...            'all': ('/path/to/css2','/path/to/css3')
...         }
...         js = ('/path/to/js1','/path/to/js4')

>>> class MyWidget3(TextInput):
...     class Media:
...         css = {
...            'all': ('/path/to/css3','path/to/css1')
...         }
...         js = ('/path/to/js1','/path/to/js4')

>>> w2 = MyWidget2()
>>> w3 = MyWidget3()
>>> print w1.media + w2.media + w3.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>

# Check that media addition hasn't affected the original objects
>>> print w1.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>

###############################################################
# Property-based media definitions
###############################################################

# Widget media can be defined as a property
>>> class MyWidget4(TextInput):
...     def _media(self):
...         return Media(css={'all': ('/some/path',)}, js = ('/some/js',))
...     media = property(_media)

>>> w4 = MyWidget4()
>>> print w4.media
<link href="/some/path" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/some/js"></script>

# Media properties can reference the media of their parents
>>> class MyWidget5(MyWidget4):
...     def _media(self):
...         return super(MyWidget5, self).media + Media(css={'all': ('/other/path',)}, js = ('/other/js',))
...     media = property(_media)

>>> w5 = MyWidget5()
>>> print w5.media
<link href="/some/path" type="text/css" media="all" rel="stylesheet" />
<link href="/other/path" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/some/js"></script>
<script type="text/javascript" src="/other/js"></script>

# Media properties can reference the media of their parents,
# even if the parent media was defined using a class
>>> class MyWidget6(MyWidget1):
...     def _media(self):
...         return super(MyWidget6, self).media + Media(css={'all': ('/other/path',)}, js = ('/other/js',))
...     media = property(_media)

>>> w6 = MyWidget6()
>>> print w6.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/other/path" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/other/js"></script>

###############################################################
# Inheritance of media
###############################################################

# If a widget extends another but provides no media definition, it inherits the parent widget's media
>>> class MyWidget7(MyWidget1):
...     pass

>>> w7 = MyWidget7()
>>> print w7.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>

# If a widget extends another but defines media, it extends the parent widget's media by default
>>> class MyWidget8(MyWidget1):
...     class Media:
...         css = {
...            'all': ('/path/to/css3','path/to/css1')
...         }
...         js = ('/path/to/js1','/path/to/js4')

>>> w8 = MyWidget8()
>>> print w8.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>

# If a widget extends another but defines media, it extends the parents widget's media,
# even if the parent defined media using a property.
>>> class MyWidget9(MyWidget4):
...     class Media:
...         css = {
...             'all': ('/other/path',)
...         }
...         js = ('/other/js',)

>>> w9 = MyWidget9()
>>> print w9.media
<link href="/some/path" type="text/css" media="all" rel="stylesheet" />
<link href="/other/path" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/some/js"></script>
<script type="text/javascript" src="/other/js"></script>

# A widget can disable media inheritance by specifying 'extend=False'
>>> class MyWidget10(MyWidget1):
...     class Media:
...         extend = False
...         css = {
...            'all': ('/path/to/css3','path/to/css1')
...         }
...         js = ('/path/to/js1','/path/to/js4')

>>> w10 = MyWidget10()
>>> print w10.media
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="/path/to/js4"></script>

# A widget can explicitly enable full media inheritance by specifying 'extend=True'
>>> class MyWidget11(MyWidget1):
...     class Media:
...         extend = True
...         css = {
...            'all': ('/path/to/css3','path/to/css1')
...         }
...         js = ('/path/to/js1','/path/to/js4')

>>> w11 = MyWidget11()
>>> print w11.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>

# A widget can enable inheritance of one media type by specifying extend as a tuple
>>> class MyWidget12(MyWidget1):
...     class Media:
...         extend = ('css',)
...         css = {
...            'all': ('/path/to/css3','path/to/css1')
...         }
...         js = ('/path/to/js1','/path/to/js4')

>>> w12 = MyWidget12()
>>> print w12.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="/path/to/js4"></script>

###############################################################
# Multi-media handling for CSS
###############################################################

# A widget can define CSS media for multiple output media types
>>> class MultimediaWidget(TextInput):
...     class Media:
...         css = {
...            'screen, print': ('/file1','/file2'),
...            'screen': ('/file3',),
...            'print': ('/file4',)
...         }
...         js = ('/path/to/js1','/path/to/js4')

>>> multimedia = MultimediaWidget()
>>> print multimedia.media
<link href="/file4" type="text/css" media="print" rel="stylesheet" />
<link href="/file3" type="text/css" media="screen" rel="stylesheet" />
<link href="/file1" type="text/css" media="screen, print" rel="stylesheet" />
<link href="/file2" type="text/css" media="screen, print" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="/path/to/js4"></script>

###############################################################
# Multiwidget media handling
###############################################################

# MultiWidgets have a default media definition that gets all the 
# media from the component widgets
>>> class MyMultiWidget(MultiWidget):
...     def __init__(self, attrs=None):
...         widgets = [MyWidget1, MyWidget2, MyWidget3]
...         super(MyMultiWidget, self).__init__(widgets, attrs)
            
>>> mymulti = MyMultiWidget()
>>> print mymulti.media   
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>

###############################################################
# Media processing for forms
###############################################################

# You can ask a form for the media required by its widgets.
>>> class MyForm(Form):
...     field1 = CharField(max_length=20, widget=MyWidget1())
...     field2 = CharField(max_length=20, widget=MyWidget2())
>>> f1 = MyForm()
>>> print f1.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>

# Form media can be combined to produce a single media definition.
>>> class AnotherForm(Form):
...     field3 = CharField(max_length=20, widget=MyWidget3())
>>> f2 = AnotherForm()
>>> print f1.media + f2.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>

# Forms can also define media, following the same rules as widgets.
>>> class FormWithMedia(Form):
...     field1 = CharField(max_length=20, widget=MyWidget1())
...     field2 = CharField(max_length=20, widget=MyWidget2())
...     class Media:
...         js = ('/some/form/javascript',)
...         css = {
...             'all': ('/some/form/css',)
...         }
>>> f3 = FormWithMedia()
>>> print f3.media
<link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<link href="/some/form/css" type="text/css" media="all" rel="stylesheet" />
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>
<script type="text/javascript" src="/some/form/javascript"></script>

# Media works in templates
>>> from django.template import Template, Context
>>> Template("{{ form.media.js }}{{ form.media.css }}").render(Context({'form': f3}))
u'<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>
<script type="text/javascript" src="/some/form/javascript"></script><link href="http://media.example.com/media/path/to/css1" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet" />
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet" />
<link href="/some/form/css" type="text/css" media="all" rel="stylesheet" />'

>>> settings.MEDIA_URL = ORIGINAL_MEDIA_URL
"""
