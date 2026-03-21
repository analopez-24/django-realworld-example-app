from django.conf.urls import url, include

urlpatterns = [
    url(r'^api/', include('conduit.apps.authentication.urls')),
    url(r'^api/', include('conduit.apps.articles.urls')),
    url(r'^api/', include('conduit.apps.profiles.urls')),
]
