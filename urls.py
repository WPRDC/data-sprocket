from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^ajax/get_package/$', views.get_package, name='get_package'),
    ]
