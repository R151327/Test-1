from django.conf.urls import url, include

from .views import empty_view


urlpatterns = [
    url(r'^$', empty_view, name="named-url1"),
    url(r'^extra/(?P<extra>\w+)/$', empty_view, name="named-url2"),
    url(r'^(?P<one>\d+)|(?P<two>\d+)/$', empty_view),
    url(r'^included/', include('urlpatterns_reverse.included_named_urls')),
]
