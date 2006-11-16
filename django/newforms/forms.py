"""
Form classes
"""

from fields import Field
from widgets import TextInput, Textarea
from util import ErrorDict, ErrorList, ValidationError

NON_FIELD_ERRORS = '__all__'

def pretty_name(name):
    "Converts 'first_name' to 'First name'"
    name = name[0].upper() + name[1:]
    return name.replace('_', ' ')

class DeclarativeFieldsMetaclass(type):
    "Metaclass that converts Field attributes to a dictionary called 'fields'."
    def __new__(cls, name, bases, attrs):
        attrs['fields'] = dict([(name, attrs.pop(name)) for name, obj in attrs.items() if isinstance(obj, Field)])
        return type.__new__(cls, name, bases, attrs)

class Form(object):
    "A collection of Fields, plus their associated data."
    __metaclass__ = DeclarativeFieldsMetaclass

    def __init__(self, data=None, auto_id=False): # TODO: prefix stuff
        self.data = data or {}
        self.auto_id = auto_id
        self.clean_data = None # Stores the data after clean() has been called.
        self.__errors = None # Stores the errors after clean() has been called.

    def __str__(self):
        return self.as_table()

    def __iter__(self):
        for name, field in self.fields.items():
            yield BoundField(self, field, name)

    def __getitem__(self, name):
        "Returns a BoundField with the given name."
        try:
            field = self.fields[name]
        except KeyError:
            raise KeyError('Key %r not found in Form' % name)
        return BoundField(self, field, name)

    def clean(self):
        if self.__errors is None:
            self.full_clean()
        return self.clean_data

    def errors(self):
        "Returns an ErrorDict for self.data"
        if self.__errors is None:
            self.full_clean()
        return self.__errors

    def is_valid(self):
        """
        Returns True if the form has no errors. Otherwise, False. This exists
        solely for convenience, so client code can use positive logic rather
        than confusing negative logic ("if not form.errors()").
        """
        return not bool(self.errors())

    def as_table(self):
        "Returns this form rendered as HTML <tr>s -- excluding the <table></table>."
        return u'\n'.join(['<tr><td>%s:</td><td>%s</td></tr>' % (pretty_name(name), BoundField(self, field, name)) for name, field in self.fields.items()])

    def as_ul(self):
        "Returns this form rendered as HTML <li>s -- excluding the <ul></ul>."
        return u'\n'.join(['<li>%s: %s</li>' % (pretty_name(name), BoundField(self, field, name)) for name, field in self.fields.items()])

    def as_table_with_errors(self):
        "Returns this form rendered as HTML <tr>s, with errors."
        output = []
        if self.errors().get(NON_FIELD_ERRORS):
            # Errors not corresponding to a particular field are displayed at the top.
            output.append('<tr><td colspan="2"><ul>%s</ul></td></tr>' % '\n'.join(['<li>%s</li>' % e for e in self.errors()[NON_FIELD_ERRORS]]))
        for name, field in self.fields.items():
            bf = BoundField(self, field, name)
            if bf.errors:
                output.append('<tr><td colspan="2"><ul>%s</ul></td></tr>' % '\n'.join(['<li>%s</li>' % e for e in bf.errors]))
            output.append('<tr><td>%s:</td><td>%s</td></tr>' % (pretty_name(name), bf))
        return u'\n'.join(output)

    def as_ul_with_errors(self):
        "Returns this form rendered as HTML <li>s, with errors."
        output = []
        if self.errors().get(NON_FIELD_ERRORS):
            # Errors not corresponding to a particular field are displayed at the top.
            output.append('<li><ul>%s</ul></li>' % '\n'.join(['<li>%s</li>' % e for e in self.errors()[NON_FIELD_ERRORS]]))
        for name, field in self.fields.items():
            bf = BoundField(self, field, name)
            line = '<li>'
            if bf.errors:
                line += '<ul>%s</ul>' % '\n'.join(['<li>%s</li>' % e for e in bf.errors])
            line += '%s: %s</li>' % (pretty_name(name), bf)
            output.append(line)
        return u'\n'.join(output)

    def full_clean(self):
        """
        Cleans all of self.data and populates self.__errors and self.clean_data.
        """
        self.clean_data = {}
        errors = ErrorDict()
        for name, field in self.fields.items():
            value = self.data.get(name, None)
            try:
                value = field.clean(value)
                self.clean_data[name] = value
                if hasattr(self, 'clean_%s' % name):
                    value = getattr(self, 'clean_%s' % name)()
                self.clean_data[name] = value
            except ValidationError, e:
                errors[name] = e.messages
        try:
            self.clean_data = self.clean()
        except ValidationError, e:
            errors[NON_FIELD_ERRORS] = e.messages
        if errors:
            self.clean_data = None
        self.__errors = errors

    def clean(self):
        """
        Hook for doing any extra form-wide cleaning after Field.clean() been
        called on every field.
        """
        return self.clean_data

class BoundField(object):
    "A Field plus data"
    def __init__(self, form, field, name):
        self._form = form
        self._field = field
        self._name = name

    def __str__(self):
        "Renders this field as an HTML widget."
        # Use the 'widget' attribute on the field to determine which type
        # of HTML widget to use.
        return self.as_widget(self._field.widget)

    def _errors(self):
        """
        Returns an ErrorList for this field. Returns an empty ErrorList
        if there are none.
        """
        try:
            return self._form.errors()[self._name]
        except KeyError:
            return ErrorList()
    errors = property(_errors)

    def as_widget(self, widget, attrs=None):
        attrs = attrs or {}
        auto_id = self.auto_id
        if not attrs.has_key('id') and not widget.attrs.has_key('id') and auto_id:
            attrs['id'] = auto_id
        return widget.render(self._name, self._form.data.get(self._name, None), attrs=attrs)

    def as_text(self, attrs=None):
        """
        Returns a string of HTML for representing this as an <input type="text">.
        """
        return self.as_widget(TextInput(), attrs)

    def as_textarea(self, attrs=None):
        "Returns a string of HTML for representing this as a <textarea>."
        return self.as_widget(Textarea(), attrs)

    def _auto_id(self):
        """
        Calculates and returns the ID attribute for this BoundField, if the
        associated Form has specified auto_id. Returns an empty string otherwise.
        """
        auto_id = self._form.auto_id
        if auto_id and '%s' in str(auto_id):
            return str(auto_id) % self._name
        elif auto_id:
            return self._name
        return ''
    auto_id = property(_auto_id)
