from django.conf.urls.defaults import patterns, include, url
from django.conf.urls.i18n import i18n_patterns
from django.utils.translation import ugettext_lazy as _
from django.views.generic import TemplateView


view = TemplateView.as_view(template_name='dummy.html')

urlpatterns = patterns('',
    url(r'^not-prefixed/$', view, name='not-prefixed'),
    url(_(r'^translated/$'), view, name='no-prefix-translated'),
    url(_(r'^translated/(?P<slug>[\w-]+)/$'), view, name='no-prefix-translated-slug'),
)

urlpatterns += i18n_patterns('',
    url(r'^prefixed/$', view, name='prefixed'),
    url(_(r'^users/$'), view, name='users'),
    url(_(r'^account/'), include('regressiontests.i18n.patterns.urls.namespace', namespace='account')),
)
