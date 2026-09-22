from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('', views.index, name='index'),
    path('company/<str:ticker>/', views.company_detail, name='company_detail'),
]
