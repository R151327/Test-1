from django.conf.urls import patterns, url, include

import urlconf_inner


urlpatterns = patterns('',
    url(r'^test/me/$', urlconf_inner.inner_view, name='outer'),
    url(r'^inner_urlconf/', include(urlconf_inner.__name__))
)