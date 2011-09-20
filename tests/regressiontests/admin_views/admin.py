# -*- coding: utf-8 -*-
import datetime
import tempfile
import os

from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.forms.models import BaseModelFormSet
from django.core.mail import EmailMessage

from models import *


def callable_year(dt_value):
    return dt_value.year
callable_year.admin_order_field = 'date'


class ArticleInline(admin.TabularInline):
    model = Article


class ChapterInline(admin.TabularInline):
    model = Chapter


class ChapterXtra1Admin(admin.ModelAdmin):
    list_filter = ('chap',
                   'chap__title',
                   'chap__book',
                   'chap__book__name',
                   'chap__book__promo',
                   'chap__book__promo__name',)


class ArticleAdmin(admin.ModelAdmin):
    list_display = ('content', 'date', callable_year, 'model_year', 'modeladmin_year')
    list_filter = ('date', 'section')

    def changelist_view(self, request):
        "Test that extra_context works"
        return super(ArticleAdmin, self).changelist_view(
            request, extra_context={
                'extra_var': 'Hello!'
            }
        )

    def modeladmin_year(self, obj):
        return obj.date.year
    modeladmin_year.admin_order_field = 'date'
    modeladmin_year.short_description = None

    def delete_model(self, request, obj):
        EmailMessage(
            'Greetings from a deleted object',
            'I hereby inform you that some user deleted me',
            'from@example.com',
            ['to@example.com']
        ).send()
        return super(ArticleAdmin, self).delete_model(request, obj)

    def save_model(self, request, obj, form, change=True):
        EmailMessage(
            'Greetings from a created object',
            'I hereby inform you that some user created me',
            'from@example.com',
            ['to@example.com']
        ).send()
        return super(ArticleAdmin, self).save_model(request, obj, form, change)


class RowLevelChangePermissionModelAdmin(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        """ Only allow changing objects with even id number """
        return request.user.is_staff and (obj is not None) and (obj.id % 2 == 0)


class CustomArticleAdmin(admin.ModelAdmin):
    """
    Tests various hooks for using custom templates and contexts.
    """
    change_list_template = 'custom_admin/change_list.html'
    change_form_template = 'custom_admin/change_form.html'
    add_form_template = 'custom_admin/add_form.html'
    object_history_template = 'custom_admin/object_history.html'
    delete_confirmation_template = 'custom_admin/delete_confirmation.html'
    delete_selected_confirmation_template = 'custom_admin/delete_selected_confirmation.html'

    def changelist_view(self, request):
        "Test that extra_context works"
        return super(CustomArticleAdmin, self).changelist_view(
            request, extra_context={
                'extra_var': 'Hello!'
            }
        )


class ThingAdmin(admin.ModelAdmin):
    list_filter = ('color__warm', 'color__value')


class InquisitionAdmin(admin.ModelAdmin):
    list_display = ('leader', 'country', 'expected')


class SketchAdmin(admin.ModelAdmin):
    raw_id_fields = ('inquisition',)


class FabricAdmin(admin.ModelAdmin):
    list_display = ('surface',)
    list_filter = ('surface',)


class BasePersonModelFormSet(BaseModelFormSet):
    def clean(self):
        for person_dict in self.cleaned_data:
            person = person_dict.get('id')
            alive = person_dict.get('alive')
            if person and alive and person.name == "Grace Hopper":
                raise forms.ValidationError("Grace is not a Zombie")


class PersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'gender', 'alive')
    list_editable = ('gender', 'alive')
    list_filter = ('gender',)
    search_fields = ('^name',)
    save_as = True

    def get_changelist_formset(self, request, **kwargs):
        return super(PersonAdmin, self).get_changelist_formset(request,
            formset=BasePersonModelFormSet, **kwargs)

    def queryset(self, request):
        # Order by a field that isn't in list display, to be able to test
        # whether ordering is preserved.
        return super(PersonAdmin, self).queryset(request).order_by('age')


class FooAccount(Account):
    """A service-specific account of type Foo."""
    servicename = u'foo'


class BarAccount(Account):
    """A service-specific account of type Bar."""
    servicename = u'bar'


class FooAccountAdmin(admin.StackedInline):
    model = FooAccount
    extra = 1


class BarAccountAdmin(admin.StackedInline):
    model = BarAccount
    extra = 1


class PersonaAdmin(admin.ModelAdmin):
    inlines = (
        FooAccountAdmin,
        BarAccountAdmin
    )


class SubscriberAdmin(admin.ModelAdmin):
    actions = ['mail_admin']

    def mail_admin(self, request, selected):
        EmailMessage(
            'Greetings from a ModelAdmin action',
            'This is the test email from a admin action',
            'from@example.com',
            ['to@example.com']
        ).send()


def external_mail(modeladmin, request, selected):
    EmailMessage(
        'Greetings from a function action',
        'This is the test email from a function action',
        'from@example.com',
        ['to@example.com']
    ).send()
external_mail.short_description = 'External mail (Another awesome action)'


def redirect_to(modeladmin, request, selected):
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect('/some-where-else/')
redirect_to.short_description = 'Redirect to (Awesome action)'


class ExternalSubscriberAdmin(admin.ModelAdmin):
    actions = [redirect_to, external_mail]


class Podcast(Media):
    release_date = models.DateField()

    class Meta:
        ordering = ('release_date',) # overridden in PodcastAdmin


class PodcastAdmin(admin.ModelAdmin):
    list_display = ('name', 'release_date')
    list_editable = ('release_date',)
    date_hierarchy = 'release_date'
    ordering = ('name',)


class VodcastAdmin(admin.ModelAdmin):
    list_display = ('name', 'released')
    list_editable = ('released',)

    ordering = ('name',)


class ChildInline(admin.StackedInline):
    model = Child


class ParentAdmin(admin.ModelAdmin):
    model = Parent
    inlines = [ChildInline]

    list_editable = ('name',)

    def save_related(self, request, form, formsets, change):
        super(ParentAdmin, self).save_related(request, form, formsets, change)
        first_name, last_name = form.instance.name.split()
        for child in form.instance.child_set.all():
            if len(child.name.split()) < 2:
                child.name = child.name + ' ' + last_name
                child.save()


class EmptyModelAdmin(admin.ModelAdmin):
    def queryset(self, request):
        return super(EmptyModelAdmin, self).queryset(request).filter(pk__gt=1)


class OldSubscriberAdmin(admin.ModelAdmin):
    actions = None


temp_storage = FileSystemStorage(tempfile.mkdtemp())
UPLOAD_TO = os.path.join(temp_storage.location, 'test_upload')


class PictureInline(admin.TabularInline):
    model = Picture
    extra = 1


class GalleryAdmin(admin.ModelAdmin):
    inlines = [PictureInline]


class PictureAdmin(admin.ModelAdmin):
    pass


class LanguageAdmin(admin.ModelAdmin):
    list_display = ['iso', 'shortlist', 'english_name', 'name']
    list_editable = ['shortlist']


class RecommendationAdmin(admin.ModelAdmin):
    search_fields = ('=titletranslation__text', '=recommender__titletranslation__text',)


class WidgetInline(admin.StackedInline):
    model = Widget


class DooHickeyInline(admin.StackedInline):
    model = DooHickey


class GrommetInline(admin.StackedInline):
    model = Grommet


class WhatsitInline(admin.StackedInline):
    model = Whatsit


class FancyDoodadInline(admin.StackedInline):
    model = FancyDoodad


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'collector', 'order')
    list_editable = ('order',)


class CategoryInline(admin.StackedInline):
    model = Category


class CollectorAdmin(admin.ModelAdmin):
    inlines = [
        WidgetInline, DooHickeyInline, GrommetInline, WhatsitInline,
        FancyDoodadInline, CategoryInline
    ]


class LinkInline(admin.TabularInline):
    model = Link
    extra = 1

    readonly_fields = ("posted",)


class SubPostInline(admin.TabularInline):
    model = PrePopulatedSubPost

    prepopulated_fields = {
        'subslug' : ('subtitle',)
    }

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.published:
            return ('subslug',)
        return self.readonly_fields

    def get_prepopulated_fields(self, request, obj=None):
        if obj and obj.published:
            return {}
        return self.prepopulated_fields


class PrePopulatedPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug']
    prepopulated_fields = {
        'slug' : ('title',)
    }

    inlines = [SubPostInline]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.published:
            return ('slug',)
        return self.readonly_fields

    def get_prepopulated_fields(self, request, obj=None):
        if obj and obj.published:
            return {}
        return self.prepopulated_fields


class PostAdmin(admin.ModelAdmin):
    list_display = ['title', 'public']
    readonly_fields = ('posted', 'awesomeness_level', 'coolness', 'value', lambda obj: "foo")

    inlines = [
        LinkInline
    ]

    def coolness(self, instance):
        if instance.pk:
            return "%d amount of cool." % instance.pk
        else:
            return "Unkown coolness."

    def value(self, instance):
        return 1000
    value.short_description = 'Value in $US'


class CustomChangeList(ChangeList):
    def get_query_set(self, request):
        return self.root_query_set.filter(pk=9999) # Does not exist


class GadgetAdmin(admin.ModelAdmin):
    def get_changelist(self, request, **kwargs):
        return CustomChangeList


class PizzaAdmin(admin.ModelAdmin):
    readonly_fields = ('toppings',)


class WorkHourAdmin(admin.ModelAdmin):
    list_display = ('datum', 'employee')
    list_filter = ('employee',)


class FoodDeliveryAdmin(admin.ModelAdmin):
    list_display=('reference', 'driver', 'restaurant')
    list_editable = ('driver', 'restaurant')


class PaperAdmin(admin.ModelAdmin):
    """
    A ModelAdmin with a custom queryset() method that uses only(), to test
    verbose_name display in messages shown after adding Paper instances.
    """

    def queryset(self, request):
        return super(PaperAdmin, self).queryset(request).only('title')


class CoverLetterAdmin(admin.ModelAdmin):
    """
    A ModelAdmin with a custom queryset() method that uses only(), to test
    verbose_name display in messages shown after adding CoverLetter instances.
    Note that the CoverLetter model defines a __unicode__ method.
    """

    def queryset(self, request):
        return super(CoverLetterAdmin, self).queryset(request).defer('date_written')


class StoryForm(forms.ModelForm):
    class Meta:
        widgets = {'title': forms.HiddenInput}


class StoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'content')
    list_display_links = ('title',) # 'id' not in list_display_links
    list_editable = ('content', )
    form = StoryForm
    ordering = ["-pk"]


class OtherStoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'content')
    list_display_links = ('title', 'id') # 'id' in list_display_links
    list_editable = ('content', )
    ordering = ["-pk"]


class ComplexSortedPersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'age', 'is_employee', 'colored_name')
    ordering = ('name',)

    def colored_name(self, obj):
        return '<span style="color: #%s;">%s</span>' % ('ff00ff', obj.name)
    colored_name.allow_tags = True
    colored_name.admin_order_field = 'name'


class AlbumAdmin(admin.ModelAdmin):
    list_filter = ['title']


class WorkHourAdmin(admin.ModelAdmin):
    list_display = ('datum', 'employee')
    list_filter = ('employee',)


site = admin.AdminSite(name="admin")
site.register(Article, ArticleAdmin)
site.register(CustomArticle, CustomArticleAdmin)
site.register(Section, save_as=True, inlines=[ArticleInline])
site.register(ModelWithStringPrimaryKey)
site.register(Color)
site.register(Thing, ThingAdmin)
site.register(Actor)
site.register(Inquisition, InquisitionAdmin)
site.register(Sketch, SketchAdmin)
site.register(Person, PersonAdmin)
site.register(Persona, PersonaAdmin)
site.register(Subscriber, SubscriberAdmin)
site.register(ExternalSubscriber, ExternalSubscriberAdmin)
site.register(OldSubscriber, OldSubscriberAdmin)
site.register(Podcast, PodcastAdmin)
site.register(Vodcast, VodcastAdmin)
site.register(Parent, ParentAdmin)
site.register(EmptyModel, EmptyModelAdmin)
site.register(Fabric, FabricAdmin)
site.register(Gallery, GalleryAdmin)
site.register(Picture, PictureAdmin)
site.register(Language, LanguageAdmin)
site.register(Recommendation, RecommendationAdmin)
site.register(Recommender)
site.register(Collector, CollectorAdmin)
site.register(Category, CategoryAdmin)
site.register(Post, PostAdmin)
site.register(Gadget, GadgetAdmin)
site.register(Villain)
site.register(SuperVillain)
site.register(Plot)
site.register(PlotDetails)
site.register(CyclicOne)
site.register(CyclicTwo)
site.register(WorkHour, WorkHourAdmin)
site.register(Reservation)
site.register(FoodDelivery, FoodDeliveryAdmin)
site.register(RowLevelChangePermissionModel, RowLevelChangePermissionModelAdmin)
site.register(Paper, PaperAdmin)
site.register(CoverLetter, CoverLetterAdmin)
site.register(Story, StoryAdmin)
site.register(OtherStory, OtherStoryAdmin)

# We intentionally register Promo and ChapterXtra1 but not Chapter nor ChapterXtra2.
# That way we cover all four cases:
#     related ForeignKey object registered in admin
#     related ForeignKey object not registered in admin
#     related OneToOne object registered in admin
#     related OneToOne object not registered in admin
# when deleting Book so as exercise all four troublesome (w.r.t escaping
# and calling force_unicode to avoid problems on Python 2.3) paths through
# contrib.admin.util's get_deleted_objects function.
site.register(Book, inlines=[ChapterInline])
site.register(Promo)
site.register(ChapterXtra1, ChapterXtra1Admin)
site.register(Pizza, PizzaAdmin)
site.register(Topping)
site.register(Album, AlbumAdmin)
site.register(Question)
site.register(Answer)
site.register(PrePopulatedPost, PrePopulatedPostAdmin)
site.register(ComplexSortedPerson, ComplexSortedPersonAdmin)

# Register core models we need in our tests
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
site.register(User, UserAdmin)
site.register(Group, GroupAdmin)
