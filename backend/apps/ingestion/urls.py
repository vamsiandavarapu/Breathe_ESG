from django.urls import path
from . import views
urlpatterns = [
    path('ingest/upload/', views.UploadView.as_view(), name='upload'),
    path('ingest/jobs/', views.JobListView.as_view(), name='jobs-list'),
]
