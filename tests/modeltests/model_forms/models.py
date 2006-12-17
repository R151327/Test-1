"""
34. Generating HTML forms from models

Django provides shortcuts for creating Form objects from a model class.

The function django.newforms.form_for_model() takes a model class and returns
a Form that is tied to the model. This Form works just like any other Form,
with one additional method: create(). The create() method creates an instance
of the model and returns that newly created instance. It saves the instance to
the database if create(save=True), which is default. If you pass
create(save=False), then you'll get the object without saving it.
"""

from django.db import models

class Category(models.Model):
    name = models.CharField(maxlength=20)
    url = models.CharField('The URL', maxlength=40)

    def __str__(self):
        return self.name

class Article(models.Model):
    headline = models.CharField(maxlength=50)
    pub_date = models.DateTimeField()
    categories = models.ManyToManyField(Category)

    def __str__(self):
        return self.headline

__test__ = {'API_TESTS': """
>>> from django.newforms import form_for_model, BaseForm

>>> Category.objects.all()
[]

>>> CategoryForm = form_for_model(Category)
>>> f = CategoryForm()
>>> print f
<tr><th><label for="id_name">Name:</label></th><td><input id="id_name" type="text" name="name" maxlength="20" /></td></tr>
<tr><th><label for="id_url">The URL:</label></th><td><input id="id_url" type="text" name="url" maxlength="40" /></td></tr>
>>> print f.as_ul()
<li><label for="id_name">Name:</label> <input id="id_name" type="text" name="name" maxlength="20" /></li>
<li><label for="id_url">The URL:</label> <input id="id_url" type="text" name="url" maxlength="40" /></li>
>>> print f['name']
<input id="id_name" type="text" name="name" maxlength="20" />

>>> f = CategoryForm(auto_id=False)
>>> print f.as_ul()
<li>Name: <input type="text" name="name" maxlength="20" /></li>
<li>The URL: <input type="text" name="url" maxlength="40" /></li>

>>> f = CategoryForm({'name': 'Entertainment', 'url': 'entertainment'})
>>> f.errors
{}
>>> f.clean_data
{'url': u'entertainment', 'name': u'Entertainment'}
>>> obj = f.create()
>>> obj
<Category: Entertainment>
>>> Category.objects.all()
[<Category: Entertainment>]

>>> f = CategoryForm({'name': "It's a test", 'url': 'test'})
>>> f.errors
{}
>>> f.clean_data
{'url': u'test', 'name': u"It's a test"}
>>> obj = f.create()
>>> obj
<Category: It's a test>
>>> Category.objects.all()
[<Category: Entertainment>, <Category: It's a test>]

>>> f = CategoryForm({'name': 'Third test', 'url': 'third'})
>>> f.errors
{}
>>> f.clean_data
{'url': u'third', 'name': u'Third test'}
>>> obj = f.create(save=False)
>>> obj
<Category: Third test>
>>> Category.objects.all()
[<Category: Entertainment>, <Category: It's a test>]
>>> obj.save()
>>> Category.objects.all()
[<Category: Entertainment>, <Category: It's a test>, <Category: Third test>]

>>> f = CategoryForm({'name': '', 'url': 'foo'})
>>> f.errors
{'name': [u'This field is required.']}
>>> f.clean_data
>>> f.create()
Traceback (most recent call last):
...
ValueError: The Category could not be created because the data didn't validate.

>>> f = CategoryForm({'name': '', 'url': 'foo'})
>>> f.create()
Traceback (most recent call last):
...
ValueError: The Category could not be created because the data didn't validate.

You can pass a custom Form class to form_for_model. Make sure it's a
subclass of BaseForm, not Form.
>>> class CustomForm(BaseForm):
...     def say_hello(self):
...         print 'hello'
>>> CategoryForm = form_for_model(Category, form=CustomForm)
>>> f = CategoryForm()
>>> f.say_hello()
hello
"""}
