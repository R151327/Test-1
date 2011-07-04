# -*- encoding: utf-8 -*-
from __future__ import with_statement
import codecs
import os
import posixpath
import shutil
import sys
import tempfile
from StringIO import StringIO

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.utils.encoding import smart_unicode
from django.utils.functional import empty
from django.utils._os import rmtree_errorhandler

from django.contrib.staticfiles import finders, storage

TEST_ROOT = os.path.dirname(__file__)


class StaticFilesTestCase(TestCase):
    """
    Test case with a couple utility assertions.
    """
    def setUp(self):
        # Clear the cached default_storage out, this is because when it first
        # gets accessed (by some other test), it evaluates settings.MEDIA_ROOT,
        # since we're planning on changing that we need to clear out the cache.
        default_storage._wrapped = empty

        # To make sure SVN doesn't hangs itself with the non-ASCII characters
        # during checkout, we actually create one file dynamically.
        _nonascii_filepath = os.path.join(
            TEST_ROOT, 'apps', 'test', 'static', 'test', u'fi\u015fier.txt')
        with codecs.open(_nonascii_filepath, 'w', 'utf-8') as f:
            f.write(u"fi\u015fier in the app dir")
        self.addCleanup(os.unlink, _nonascii_filepath)

    def assertFileContains(self, filepath, text):
        self.assertTrue(text in self._get_file(smart_unicode(filepath)),
                        u"'%s' not in '%s'" % (text, filepath))

    def assertFileNotFound(self, filepath):
        self.assertRaises(IOError, self._get_file, filepath)

StaticFilesTestCase = override_settings(
    DEBUG = True,
    MEDIA_URL = '/media/',
    STATIC_URL = '/static/',
    MEDIA_ROOT =  os.path.join(TEST_ROOT, 'project', 'site_media', 'media'),
    STATIC_ROOT = os.path.join(TEST_ROOT, 'project', 'site_media', 'static'),
    STATICFILES_DIRS = (os.path.join(TEST_ROOT, 'project', 'documents'),),
    STATICFILES_FINDERS = (
        'django.contrib.staticfiles.finders.FileSystemFinder',
        'django.contrib.staticfiles.finders.AppDirectoriesFinder',
        'django.contrib.staticfiles.finders.DefaultStorageFinder',
    ),
)(StaticFilesTestCase)


class BuildStaticTestCase(StaticFilesTestCase):
    """
    Tests shared by all file-resolving features (collectstatic,
    findstatic, and static serve view).

    This relies on the asserts defined in UtilityAssertsTestCase, but
    is separated because some test cases need those asserts without
    all these tests.
    """
    def setUp(self):
        super(BuildStaticTestCase, self).setUp()
        self.old_root = settings.STATIC_ROOT
        settings.STATIC_ROOT = tempfile.mkdtemp()
        self.run_collectstatic()
        # Use our own error handler that can handle .svn dirs on Windows
        self.addCleanup(shutil.rmtree, settings.STATIC_ROOT,
                        ignore_errors=True, onerror=rmtree_errorhandler)

    def tearDown(self):
        settings.STATIC_ROOT = self.old_root
        super(BuildStaticTestCase, self).tearDown()

    def run_collectstatic(self, **kwargs):
        call_command('collectstatic', interactive=False, verbosity='0',
                     ignore_patterns=['*.ignoreme'], **kwargs)

    def _get_file(self, filepath):
        assert filepath, 'filepath is empty.'
        filepath = os.path.join(settings.STATIC_ROOT, filepath)
        with codecs.open(filepath, "r", "utf-8") as f:
            return f.read()


class TestDefaults(object):
    """
    A few standard test cases.
    """
    def test_staticfiles_dirs(self):
        """
        Can find a file in a STATICFILES_DIRS directory.
        """
        self.assertFileContains('test.txt', 'Can we find')

    def test_staticfiles_dirs_subdir(self):
        """
        Can find a file in a subdirectory of a STATICFILES_DIRS
        directory.
        """
        self.assertFileContains('subdir/test.txt', 'Can we find')

    def test_staticfiles_dirs_priority(self):
        """
        File in STATICFILES_DIRS has priority over file in app.
        """
        self.assertFileContains('test/file.txt', 'STATICFILES_DIRS')

    def test_app_files(self):
        """
        Can find a file in an app static/ directory.
        """
        self.assertFileContains('test/file1.txt', 'file1 in the app dir')

    def test_nonascii_filenames(self):
        """
        Can find a file with non-ASCII character in an app static/ directory.
        """
        self.assertFileContains(u'test/fişier.txt', u'fişier in the app dir')

    def test_camelcase_filenames(self):
        """
        Can find a file with capital letters.
        """
        self.assertFileContains(u'test/camelCase.txt', u'camelCase')


class TestFindStatic(BuildStaticTestCase, TestDefaults):
    """
    Test ``findstatic`` management command.
    """
    def _get_file(self, filepath):
        _stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            call_command('findstatic', filepath, all=False, verbosity='0')
            sys.stdout.seek(0)
            lines = [l.strip() for l in sys.stdout.readlines()]
            contents = codecs.open(
                smart_unicode(lines[1].strip()), "r", "utf-8").read()
        finally:
            sys.stdout = _stdout
        return contents

    def test_all_files(self):
        """
        Test that findstatic returns all candidate files if run without --first.
        """
        _stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            call_command('findstatic', 'test/file.txt', verbosity='0')
            sys.stdout.seek(0)
            lines = [l.strip() for l in sys.stdout.readlines()]
        finally:
            sys.stdout = _stdout
        self.assertEqual(len(lines), 3) # three because there is also the "Found <file> here" line
        self.assertTrue('project' in lines[1])
        self.assertTrue('apps' in lines[2])


class TestBuildStatic(BuildStaticTestCase, TestDefaults):
    """
    Test ``collectstatic`` management command.
    """
    def test_ignore(self):
        """
        Test that -i patterns are ignored.
        """
        self.assertFileNotFound('test/test.ignoreme')

    def test_common_ignore_patterns(self):
        """
        Common ignore patterns (*~, .*, CVS) are ignored.
        """
        self.assertFileNotFound('test/.hidden')
        self.assertFileNotFound('test/backup~')
        self.assertFileNotFound('test/CVS')


class TestBuildStaticClear(BuildStaticTestCase):
    """
    Test the ``--clear`` option of the ``collectstatic`` managemenet command.
    """
    def run_collectstatic(self, **kwargs):
        clear_filepath = os.path.join(settings.STATIC_ROOT, 'cleared.txt')
        with open(clear_filepath, 'w') as f:
            f.write('should be cleared')
        super(TestBuildStaticClear, self).run_collectstatic(clear=True)

    def test_cleared_not_found(self):
        self.assertFileNotFound('cleared.txt')


class TestBuildStaticExcludeNoDefaultIgnore(BuildStaticTestCase, TestDefaults):
    """
    Test ``--exclude-dirs`` and ``--no-default-ignore`` options of the
    ``collectstatic`` management command.
    """
    def run_collectstatic(self):
        super(TestBuildStaticExcludeNoDefaultIgnore, self).run_collectstatic(
            use_default_ignore_patterns=False)

    def test_no_common_ignore_patterns(self):
        """
        With --no-default-ignore, common ignore patterns (*~, .*, CVS)
        are not ignored.

        """
        self.assertFileContains('test/.hidden', 'should be ignored')
        self.assertFileContains('test/backup~', 'should be ignored')
        self.assertFileContains('test/CVS', 'should be ignored')


class TestNoFilesCreated(object):

    def test_no_files_created(self):
        """
        Make sure no files were create in the destination directory.
        """
        self.assertEqual(os.listdir(settings.STATIC_ROOT), [])


class TestBuildStaticDryRun(BuildStaticTestCase, TestNoFilesCreated):
    """
    Test ``--dry-run`` option for ``collectstatic`` management command.
    """
    def run_collectstatic(self):
        super(TestBuildStaticDryRun, self).run_collectstatic(dry_run=True)


class TestBuildStaticNonLocalStorage(BuildStaticTestCase, TestNoFilesCreated):
    """
    Tests for #15035
    """
    pass

TestBuildStaticNonLocalStorage = override_settings(
    STATICFILES_STORAGE='regressiontests.staticfiles_tests.storage.DummyStorage',
)(TestBuildStaticNonLocalStorage)


if sys.platform != 'win32':
    class TestBuildStaticLinks(BuildStaticTestCase, TestDefaults):
        """
        Test ``--link`` option for ``collectstatic`` management command.

        Note that by inheriting ``TestDefaults`` we repeat all
        the standard file resolving tests here, to make sure using
        ``--link`` does not change the file-selection semantics.
        """
        def run_collectstatic(self):
            super(TestBuildStaticLinks, self).run_collectstatic(link=True)

        def test_links_created(self):
            """
            With ``--link``, symbolic links are created.
            """
            self.assertTrue(os.path.islink(os.path.join(settings.STATIC_ROOT, 'test.txt')))


class TestServeStatic(StaticFilesTestCase):
    """
    Test static asset serving view.
    """
    urls = 'regressiontests.staticfiles_tests.urls.default'

    def _response(self, filepath):
        return self.client.get(
            posixpath.join(settings.STATIC_URL, filepath))

    def assertFileContains(self, filepath, text):
        self.assertContains(self._response(filepath), text)

    def assertFileNotFound(self, filepath):
        self.assertEqual(self._response(filepath).status_code, 404)


class TestServeDisabled(TestServeStatic):
    """
    Test serving static files disabled when DEBUG is False.
    """
    def setUp(self):
        super(TestServeDisabled, self).setUp()
        settings.DEBUG = False

    def test_disabled_serving(self):
        self.assertRaisesRegexp(ImproperlyConfigured, 'The staticfiles view '
            'can only be used in debug mode ', self._response, 'test.txt')


class TestServeStaticWithDefaultURL(TestServeStatic, TestDefaults):
    """
    Test static asset serving view with manually configured URLconf.
    """
    pass

class TestServeStaticWithURLHelper(TestServeStatic, TestDefaults):
    """
    Test static asset serving view with staticfiles_urlpatterns helper.
    """
    urls = 'regressiontests.staticfiles_tests.urls.helper'


class TestServeAdminMedia(TestServeStatic):
    """
    Test serving media from django.contrib.admin.
    """
    def _response(self, filepath):
        return self.client.get(
            posixpath.join(settings.STATIC_URL, 'admin/', filepath))

    def test_serve_admin_media(self):
        self.assertFileContains('css/base.css', 'body')


class FinderTestCase(object):
    """
    Base finder test mixin.

    On Windows, sometimes the case of the path we ask the finders for and the
    path(s) they find can differ. Compare them using os.path.normcase() to
    avoid false negatives.
    """
    def test_find_first(self):
        src, dst = self.find_first
        found = self.finder.find(src)
        self.assertEqual(os.path.normcase(found), os.path.normcase(dst))

    def test_find_all(self):
        src, dst = self.find_all
        found = self.finder.find(src, all=True)
        found = [os.path.normcase(f) for f in found]
        dst = [os.path.normcase(d) for d in dst]
        self.assertEqual(found, dst)


class TestFileSystemFinder(StaticFilesTestCase, FinderTestCase):
    """
    Test FileSystemFinder.
    """
    def setUp(self):
        super(TestFileSystemFinder, self).setUp()
        self.finder = finders.FileSystemFinder()
        test_file_path = os.path.join(TEST_ROOT, 'project', 'documents', 'test', 'file.txt')
        self.find_first = (os.path.join('test', 'file.txt'), test_file_path)
        self.find_all = (os.path.join('test', 'file.txt'), [test_file_path])


class TestAppDirectoriesFinder(StaticFilesTestCase, FinderTestCase):
    """
    Test AppDirectoriesFinder.
    """
    def setUp(self):
        super(TestAppDirectoriesFinder, self).setUp()
        self.finder = finders.AppDirectoriesFinder()
        test_file_path = os.path.join(TEST_ROOT, 'apps', 'test', 'static', 'test', 'file1.txt')
        self.find_first = (os.path.join('test', 'file1.txt'), test_file_path)
        self.find_all = (os.path.join('test', 'file1.txt'), [test_file_path])


class TestDefaultStorageFinder(StaticFilesTestCase, FinderTestCase):
    """
    Test DefaultStorageFinder.
    """
    def setUp(self):
        super(TestDefaultStorageFinder, self).setUp()
        self.finder = finders.DefaultStorageFinder(
            storage=storage.StaticFilesStorage(location=settings.MEDIA_ROOT))
        test_file_path = os.path.join(settings.MEDIA_ROOT, 'media-file.txt')
        self.find_first = ('media-file.txt', test_file_path)
        self.find_all = ('media-file.txt', [test_file_path])


class TestMiscFinder(TestCase):
    """
    A few misc finder tests.
    """
    def test_get_finder(self):
        self.assertTrue(isinstance(finders.get_finder(
            'django.contrib.staticfiles.finders.FileSystemFinder'),
            finders.FileSystemFinder))

    def test_get_finder_bad_classname(self):
        self.assertRaises(ImproperlyConfigured,
            finders.get_finder, 'django.contrib.staticfiles.finders.FooBarFinder')

    def test_get_finder_bad_module(self):
        self.assertRaises(ImproperlyConfigured,
            finders.get_finder, 'foo.bar.FooBarFinder')


class TestStaticfilesDirsType(TestCase):
    """
    We can't determine if STATICFILES_DIRS is set correctly just by looking at
    the type, but we can determine if it's definitely wrong.
    """
    def test_non_tuple_raises_exception(self):
        self.assertRaises(ImproperlyConfigured, finders.FileSystemFinder)

TestStaticfilesDirsType = override_settings(
    STATICFILES_DIRS = 'a string',
)(TestStaticfilesDirsType)
