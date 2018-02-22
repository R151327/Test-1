import warnings

from django.contrib.admin.options import ModelAdmin, TabularInline
from django.utils.deprecation import RemovedInDjango30Warning

from .models import Band, Song
from .test_checks import CheckTestCase


class HasAddPermissionObjTests(CheckTestCase):
    def test_model_admin_inherited_valid(self):
        class BandAdmin(ModelAdmin):
            pass

        self.assertIsValid(BandAdmin, Band)

    def test_model_admin_valid(self):
        class BandAdmin(ModelAdmin):
            def has_add_permission(self, request):
                return super().has_add_permission(request)

        self.assertIsValid(BandAdmin, Band)

    def test_inline_admin_inherited_valid(self):
        class SongInlineAdmin(TabularInline):
            model = Song

        class BandAdmin(ModelAdmin):
            inlines = [SongInlineAdmin]

        self.assertIsValid(BandAdmin, Band)

    def test_inline_admin_valid(self):
        class SongInlineAdmin(TabularInline):
            model = Song

            def has_add_permission(self, request, obj):
                return super().has_add_permission(request, obj)

        class BandAdmin(ModelAdmin):
            inlines = [SongInlineAdmin]

        self.assertIsValid(BandAdmin, Band)

    def test_inline_admin_warning(self):
        class SongInlineAdmin(TabularInline):
            model = Song

            def has_add_permission(self, request):
                return super().has_add_permission(request)

        class BandAdmin(ModelAdmin):
            inlines = [SongInlineAdmin]

        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter('always')
            self.assertIsValid(BandAdmin, Band)
        self.assertEqual(len(recorded), 1)
        self.assertIs(recorded[0].category, RemovedInDjango30Warning)
        self.assertEqual(str(recorded[0].message), (
            "Update SongInlineAdmin.has_add_permission() to accept a "
            "positional `obj` argument."
        ))
