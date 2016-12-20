from django.conf.urls import url
from . import views


urlpatterns = [
    url(
        r'^$',
        views.IndexView.as_view(),
        name='index'
    ),
    url(
        r'(?P<with_username>.*)/$',
        views.chat_view,
        name='chat'
    ),
]