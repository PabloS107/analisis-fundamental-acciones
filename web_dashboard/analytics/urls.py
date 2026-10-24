from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('', views.index, name='index'),
    path('company/<str:ticker>/', views.company_detail, name='company_detail'),
    path('api/search/', views.company_search, name='company_search'),
    path('api/pipeline/trigger/', views.trigger_pipeline, name='trigger_pipeline'),
    path('api/pipeline/status/<str:ticker>/', views.pipeline_status, name='pipeline_status'),
    path('api/sec-freshness/<str:ticker>/', views.sec_freshness_view, name='sec_freshness'),
]
