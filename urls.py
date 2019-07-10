from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^ajax/get_package_list/$', views.get_package_list, name='get_package_list'),
    url(r'^ajax/get_package/$', views.get_package, name='get_package'),
    url(r'^ajax/get_resource/$', views.get_resource, name='get_resource'),
    ]
