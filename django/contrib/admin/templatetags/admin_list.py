import datetime

from django.conf import settings
from django.contrib.admin.util import lookup_field, display_for_field, label_for_field
from django.contrib.admin.views.main import (ALL_VAR, EMPTY_CHANGELIST_VALUE,
    ORDER_VAR, ORDER_TYPE_VAR, PAGE_VAR, SEARCH_VAR)
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils import formats
from django.utils.datastructures import SortedDict
from django.utils.html import escape, conditional_escape
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.translation import ugettext as _
from django.utils.encoding import smart_unicode, force_unicode
from django.template import Library


register = Library()

DOT = '.'

@register.simple_tag
def paginator_number(cl,i):
    """
    Generates an individual page index link in a paginated list.
    """
    if i == DOT:
        return u'... '
    elif i == cl.page_num:
        return mark_safe(u'<span class="this-page">%d</span> ' % (i+1))
    else:
        return mark_safe(u'<a href="%s"%s>%d</a> ' % (escape(cl.get_query_string({PAGE_VAR: i})), (i == cl.paginator.num_pages-1 and ' class="end"' or ''), i+1))

@register.inclusion_tag('admin/pagination.html')
def pagination(cl):
    """
    Generates the series of links to the pages in a paginated list.
    """
    paginator, page_num = cl.paginator, cl.page_num

    pagination_required = (not cl.show_all or not cl.can_show_all) and cl.multi_page
    if not pagination_required:
        page_range = []
    else:
        ON_EACH_SIDE = 3
        ON_ENDS = 2

        # If there are 10 or fewer pages, display links to every page.
        # Otherwise, do some fancy
        if paginator.num_pages <= 10:
            page_range = range(paginator.num_pages)
        else:
            # Insert "smart" pagination links, so that there are always ON_ENDS
            # links at either end of the list of pages, and there are always
            # ON_EACH_SIDE links at either end of the "current page" link.
            page_range = []
            if page_num > (ON_EACH_SIDE + ON_ENDS):
                page_range.extend(range(0, ON_EACH_SIDE - 1))
                page_range.append(DOT)
                page_range.extend(range(page_num - ON_EACH_SIDE, page_num + 1))
            else:
                page_range.extend(range(0, page_num + 1))
            if page_num < (paginator.num_pages - ON_EACH_SIDE - ON_ENDS - 1):
                page_range.extend(range(page_num + 1, page_num + ON_EACH_SIDE + 1))
                page_range.append(DOT)
                page_range.extend(range(paginator.num_pages - ON_ENDS, paginator.num_pages))
            else:
                page_range.extend(range(page_num + 1, paginator.num_pages))

    need_show_all_link = cl.can_show_all and not cl.show_all and cl.multi_page
    return {
        'cl': cl,
        'pagination_required': pagination_required,
        'show_all_url': need_show_all_link and cl.get_query_string({ALL_VAR: ''}),
        'page_range': page_range,
        'ALL_VAR': ALL_VAR,
        '1': 1,
    }

def result_headers(cl):
    """
    Generates the list column headers.
    """
    # We need to know the 'ordering field' that corresponds to each
    # item in list_display, and we need other info, so do a pre-pass
    # on list_display
    list_display_info = SortedDict()
    for i, field_name in enumerate(cl.list_display):
        admin_order_field = None
        text, attr = label_for_field(field_name, cl.model,
            model_admin = cl.model_admin,
            return_attr = True
        )
        if attr:
            admin_order_field = getattr(attr, "admin_order_field", None)
        if admin_order_field is None:
            ordering_field_name = field_name
        else:
            ordering_field_name = admin_order_field
        list_display_info[ordering_field_name] = dict(text=text,
                                                      attr=attr,
                                                      index=i,
                                                      admin_order_field=admin_order_field,
                                                      field_name=field_name)

    del admin_order_field, text, attr

    ordering_fields = cl.get_ordering_fields()

    for ordering_field_name, info in list_display_info.items():
        if info['attr']:
            # Potentially not sortable

            # if the field is the action checkbox: no sorting and special class
            if info['field_name'] == 'action_checkbox':
                yield {
                    "text": info['text'],
                    "class_attrib": mark_safe(' class="action-checkbox-column"')
                }
                continue

            if not info['admin_order_field']:
                # Not sortable
                yield {"text": info['text']}
                continue

        # OK, it is sortable if we got this far
        th_classes = []
        order_type = ''
        new_order_type = 'asc'
        sort_pos = 0
        # Is it currently being sorted on?
        if ordering_field_name in ordering_fields:
            order_type = ordering_fields.get(ordering_field_name).lower()
            sort_pos = ordering_fields.keys().index(ordering_field_name) + 1
            th_classes.append('sorted %sending' % order_type)
            new_order_type = {'asc': 'desc', 'desc': 'asc'}[order_type]

        # build new ordering param
        o_list = []
        make_qs_param = lambda t, n: ('-' if t == 'desc' else '') + str(n)

        for f, ot in ordering_fields.items():
            try:
                colnum = list_display_info[f]['index']
            except KeyError:
                continue

            if f == ordering_field_name:
                # We want clicking on this header to bring the ordering to the
                # front
                o_list.insert(0, make_qs_param(new_order_type, colnum))
            else:
                o_list.append(make_qs_param(ot, colnum))

        if ordering_field_name not in ordering_fields:
            colnum = list_display_info[ordering_field_name]['index']
            o_list.insert(0, make_qs_param(new_order_type, colnum))

        o_list = '.'.join(o_list)

        yield {
            "text": info['text'],
            "sortable": True,
            "ascending": order_type == "asc",
            "sort_pos": sort_pos,
            "url": cl.get_query_string({ORDER_VAR: o_list}),
            "class_attrib": mark_safe(th_classes and ' class="%s"' % ' '.join(th_classes) or '')
        }

def _boolean_icon(field_val):
    BOOLEAN_MAPPING = {True: 'yes', False: 'no', None: 'unknown'}
    return mark_safe(u'<img src="%simg/admin/icon-%s.gif" alt="%s" />' %
        (settings.ADMIN_MEDIA_PREFIX, BOOLEAN_MAPPING[field_val], field_val))

def items_for_result(cl, result, form):
    """
    Generates the actual list of data.
    """
    first = True
    pk = cl.lookup_opts.pk.attname
    for field_name in cl.list_display:
        row_class = ''
        try:
            f, attr, value = lookup_field(field_name, result, cl.model_admin)
        except (AttributeError, ObjectDoesNotExist):
            result_repr = EMPTY_CHANGELIST_VALUE
        else:
            if f is None:
                if field_name == u'action_checkbox':
                    row_class = ' class="action-checkbox"'
                allow_tags = getattr(attr, 'allow_tags', False)
                boolean = getattr(attr, 'boolean', False)
                if boolean:
                    allow_tags = True
                    result_repr = _boolean_icon(value)
                else:
                    result_repr = smart_unicode(value)
                # Strip HTML tags in the resulting text, except if the
                # function has an "allow_tags" attribute set to True.
                if not allow_tags:
                    result_repr = escape(result_repr)
                else:
                    result_repr = mark_safe(result_repr)
            else:
                if isinstance(f.rel, models.ManyToOneRel):
                    field_val = getattr(result, f.name)
                    if field_val is None:
                        result_repr = EMPTY_CHANGELIST_VALUE
                    else:
                        result_repr = escape(field_val)
                else:
                    result_repr = display_for_field(value, f)
                if isinstance(f, models.DateField)\
                or isinstance(f, models.TimeField)\
                or isinstance(f, models.ForeignKey):
                    row_class = ' class="nowrap"'
        if force_unicode(result_repr) == '':
            result_repr = mark_safe('&nbsp;')
        # If list_display_links not defined, add the link tag to the first field
        if (first and not cl.list_display_links) or field_name in cl.list_display_links:
            table_tag = {True:'th', False:'td'}[first]
            first = False
            url = cl.url_for_result(result)
            # Convert the pk to something that can be used in Javascript.
            # Problem cases are long ints (23L) and non-ASCII strings.
            if cl.to_field:
                attr = str(cl.to_field)
            else:
                attr = pk
            value = result.serializable_value(attr)
            result_id = repr(force_unicode(value))[1:]
            yield mark_safe(u'<%s%s><a href="%s"%s>%s</a></%s>' % \
                (table_tag, row_class, url, (cl.is_popup and ' onclick="opener.dismissRelatedLookupPopup(window, %s); return false;"' % result_id or ''), conditional_escape(result_repr), table_tag))
        else:
            # By default the fields come from ModelAdmin.list_editable, but if we pull
            # the fields out of the form instead of list_editable custom admins
            # can provide fields on a per request basis
            if (form and field_name in form.fields and not (
                    field_name == cl.model._meta.pk.name and
                        form[cl.model._meta.pk.name].is_hidden)):
                bf = form[field_name]
                result_repr = mark_safe(force_unicode(bf.errors) + force_unicode(bf))
            else:
                result_repr = conditional_escape(result_repr)
            yield mark_safe(u'<td%s>%s</td>' % (row_class, result_repr))
    if form and not form[cl.model._meta.pk.name].is_hidden:
        yield mark_safe(u'<td>%s</td>' % force_unicode(form[cl.model._meta.pk.name]))

class ResultList(list):
    # Wrapper class used to return items in a list_editable
    # changelist, annotated with the form object for error
    # reporting purposes. Needed to maintain backwards
    # compatibility with existing admin templates.
    def __init__(self, form, *items):
        self.form = form
        super(ResultList, self).__init__(*items)

def results(cl):
    if cl.formset:
        for res, form in zip(cl.result_list, cl.formset.forms):
            yield ResultList(form, items_for_result(cl, res, form))
    else:
        for res in cl.result_list:
            yield ResultList(None, items_for_result(cl, res, None))

def result_hidden_fields(cl):
    if cl.formset:
        for res, form in zip(cl.result_list, cl.formset.forms):
            if form[cl.model._meta.pk.name].is_hidden:
                yield mark_safe(force_unicode(form[cl.model._meta.pk.name]))

@register.inclusion_tag("admin/change_list_results.html")
def result_list(cl):
    """
    Displays the headers and data list together
    """
    headers = list(result_headers(cl))
    for h in headers:
        # Sorting in templates depends on sort_pos attribute
        h.setdefault('sort_pos', 0)
    return {'cl': cl,
            'result_hidden_fields': list(result_hidden_fields(cl)),
            'result_headers': headers,
            'reset_sorting_url': cl.get_query_string(remove=[ORDER_VAR]),
            'results': list(results(cl))}

@register.inclusion_tag('admin/date_hierarchy.html')
def date_hierarchy(cl):
    """
    Displays the date hierarchy for date drill-down functionality.
    """
    if cl.date_hierarchy:
        field_name = cl.date_hierarchy
        year_field = '%s__year' % field_name
        month_field = '%s__month' % field_name
        day_field = '%s__day' % field_name
        field_generic = '%s__' % field_name
        year_lookup = cl.params.get(year_field)
        month_lookup = cl.params.get(month_field)
        day_lookup = cl.params.get(day_field)

        link = lambda d: cl.get_query_string(d, [field_generic])

        if not (year_lookup or month_lookup or day_lookup):
            # select appropriate start level
            date_range = cl.query_set.aggregate(first=models.Min(field_name),
                                                last=models.Max(field_name))
            if date_range['first'] and date_range['last']:
                if date_range['first'].year == date_range['last'].year:
                    year_lookup = date_range['first'].year
                    if date_range['first'].month == date_range['last'].month:
                        month_lookup = date_range['first'].month

        if year_lookup and month_lookup and day_lookup:
            day = datetime.date(int(year_lookup), int(month_lookup), int(day_lookup))
            return {
                'show': True,
                'back': {
                    'link': link({year_field: year_lookup, month_field: month_lookup}),
                    'title': capfirst(formats.date_format(day, 'YEAR_MONTH_FORMAT'))
                },
                'choices': [{'title': capfirst(formats.date_format(day, 'MONTH_DAY_FORMAT'))}]
            }
        elif year_lookup and month_lookup:
            days = cl.query_set.filter(**{year_field: year_lookup, month_field: month_lookup}).dates(field_name, 'day')
            return {
                'show': True,
                'back': {
                    'link': link({year_field: year_lookup}),
                    'title': str(year_lookup)
                },
                'choices': [{
                    'link': link({year_field: year_lookup, month_field: month_lookup, day_field: day.day}),
                    'title': capfirst(formats.date_format(day, 'MONTH_DAY_FORMAT'))
                } for day in days]
            }
        elif year_lookup:
            months = cl.query_set.filter(**{year_field: year_lookup}).dates(field_name, 'month')
            return {
                'show' : True,
                'back': {
                    'link' : link({}),
                    'title': _('All dates')
                },
                'choices': [{
                    'link': link({year_field: year_lookup, month_field: month.month}),
                    'title': capfirst(formats.date_format(month, 'YEAR_MONTH_FORMAT'))
                } for month in months]
            }
        else:
            years = cl.query_set.dates(field_name, 'year')
            return {
                'show': True,
                'choices': [{
                    'link': link({year_field: str(year.year)}),
                    'title': str(year.year),
                } for year in years]
            }

@register.inclusion_tag('admin/search_form.html')
def search_form(cl):
    """
    Displays a search form for searching the list.
    """
    return {
        'cl': cl,
        'show_result_count': cl.result_count != cl.full_result_count,
        'search_var': SEARCH_VAR
    }

@register.inclusion_tag('admin/filter.html')
def admin_list_filter(cl, spec):
    return {'title': spec.title, 'choices' : list(spec.choices(cl))}

@register.inclusion_tag('admin/actions.html', takes_context=True)
def admin_actions(context):
    """
    Track the number of times the action field has been rendered on the page,
    so we know which value to use.
    """
    context['action_index'] = context.get('action_index', -1) + 1
    return context
