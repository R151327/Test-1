import os
import re
import shutil
from django.test import TestCase
from django.core import management

LOCALE='de'

class ExtractorTests(TestCase):

    PO_FILE='locale/%s/LC_MESSAGES/django.po' % LOCALE

    def setUp(self):
        self._cwd = os.getcwd()
        self.test_dir = os.path.abspath(os.path.dirname(__file__))

    def _rmrf(self, dname):
        if os.path.commonprefix([self.test_dir, os.path.abspath(dname)]) != self.test_dir:
            return
        shutil.rmtree(dname)

    def tearDown(self):
        os.chdir(self.test_dir)
        try:
            self._rmrf('locale/%s' % LOCALE)
        except OSError:
            pass
        os.chdir(self._cwd)

    def assertMsgId(self, msgid, s, use_quotes=True):
        if use_quotes:
            msgid = '"%s"' % msgid
        return self.assert_(re.search('^msgid %s' % msgid, s, re.MULTILINE))

    def assertNotMsgId(self, msgid, s, use_quotes=True):
        if use_quotes:
            msgid = '"%s"' % msgid
        return self.assert_(not re.search('^msgid %s' % msgid, s, re.MULTILINE))


class BasicExtractorTests(ExtractorTests):

    def test_comments_extractor(self):
        os.chdir(self.test_dir)
        management.call_command('makemessages', locale=LOCALE, verbosity=0)
        self.assert_(os.path.exists(self.PO_FILE))
        po_contents = open(self.PO_FILE, 'r').read()
        self.assert_('#. Translators: This comment should be extracted' in po_contents)
        self.assert_('This comment should not be extracted' not in po_contents)
        # Comments in templates
        self.assert_('#. Translators: Django template comment for translators' in po_contents)
        self.assert_('#. Translators: Django comment block for translators' in po_contents)

    def test_templatize(self):
        os.chdir(self.test_dir)
        management.call_command('makemessages', locale=LOCALE, verbosity=0)
        self.assert_(os.path.exists(self.PO_FILE))
        po_contents = open(self.PO_FILE, 'r').read()
        self.assertMsgId('I think that 100%% is more that 50%% of anything.', po_contents)
        self.assertMsgId('I think that 100%% is more that 50%% of %\(obj\)s.', po_contents)

    def test_extraction_error(self):
        os.chdir(self.test_dir)
        shutil.copyfile('./templates/template_with_error.txt', './templates/template_with_error.html')
        self.assertRaises(SyntaxError, management.call_command, 'makemessages', locale=LOCALE, verbosity=0)
        try:
            management.call_command('makemessages', locale=LOCALE, verbosity=0)
        except SyntaxError, e:
            self.assertEqual(str(e), 'Translation blocks must not include other block tags: blocktrans (file templates/template_with_error.html, line 3)')
        finally:
            os.remove('./templates/template_with_error.html')
            os.remove('./templates/template_with_error.html.py') # Waiting for #8536 to be fixed


class JavascriptExtractorTests(ExtractorTests):

    PO_FILE='locale/%s/LC_MESSAGES/djangojs.po' % LOCALE

    def test_javascript_literals(self):
        os.chdir(self.test_dir)
        management.call_command('makemessages', domain='djangojs', locale=LOCALE, verbosity=0)
        self.assert_(os.path.exists(self.PO_FILE))
        po_contents = open(self.PO_FILE, 'r').read()
        self.assertMsgId('This literal should be included.', po_contents)
        self.assertMsgId('This one as well.', po_contents)


class IgnoredExtractorTests(ExtractorTests):

    def test_ignore_option(self):
        os.chdir(self.test_dir)
        management.call_command('makemessages', locale=LOCALE, verbosity=0, ignore_patterns=['ignore_dir/*'])
        self.assert_(os.path.exists(self.PO_FILE))
        po_contents = open(self.PO_FILE, 'r').read()
        self.assertMsgId('This literal should be included.', po_contents)
        self.assertNotMsgId('This should be ignored.', po_contents)


class SymlinkExtractorTests(ExtractorTests):

    def setUp(self):
        self._cwd = os.getcwd()
        self.test_dir = os.path.abspath(os.path.dirname(__file__))
        self.symlinked_dir = os.path.join(self.test_dir, 'templates_symlinked')

    def tearDown(self):
        super(SymlinkExtractorTests, self).tearDown()
        os.chdir(self.test_dir)
        try:
            os.remove(self.symlinked_dir)
        except OSError:
            pass
        os.chdir(self._cwd)

    def test_symlink(self):
        if hasattr(os, 'symlink'):
            if os.path.exists(self.symlinked_dir):
                self.assert_(os.path.islink(self.symlinked_dir))
            else:
                os.symlink(os.path.join(self.test_dir, 'templates'), self.symlinked_dir)
            os.chdir(self.test_dir)
            management.call_command('makemessages', locale=LOCALE, verbosity=0, symlinks=True)
            self.assert_(os.path.exists(self.PO_FILE))
            po_contents = open(self.PO_FILE, 'r').read()
            self.assertMsgId('This literal should be included.', po_contents)
            self.assert_('templates_symlinked/test.html' in po_contents)


class CopyPluralFormsExtractorTests(ExtractorTests):

    def test_copy_plural_forms(self):
        os.chdir(self.test_dir)
        management.call_command('makemessages', locale=LOCALE, verbosity=0)
        self.assert_(os.path.exists(self.PO_FILE))
        po_contents = open(self.PO_FILE, 'r').read()
        self.assert_('Plural-Forms: nplurals=2; plural=(n != 1)' in po_contents)


class NoWrapExtractorTests(ExtractorTests):

    def test_no_wrap_enabled(self):
        os.chdir(self.test_dir)
        management.call_command('makemessages', locale=LOCALE, verbosity=0, no_wrap=True)
        self.assert_(os.path.exists(self.PO_FILE))
        po_contents = open(self.PO_FILE, 'r').read()
        self.assertMsgId('This literal should also be included wrapped or not wrapped depending on the use of the --no-wrap option.', po_contents)

    def test_no_wrap_disabled(self):
        os.chdir(self.test_dir)
        management.call_command('makemessages', locale=LOCALE, verbosity=0, no_wrap=False)
        self.assert_(os.path.exists(self.PO_FILE))
        po_contents = open(self.PO_FILE, 'r').read()
        self.assertMsgId('""\n"This literal should also be included wrapped or not wrapped depending on the "\n"use of the --no-wrap option."', po_contents, use_quotes=False)
