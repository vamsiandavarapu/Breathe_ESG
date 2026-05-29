from django.urls import path
from . import views
urlpatterns = [
    path('emissions/', views.EmissionRecordListView.as_view(), name='emissions-list'),
    path('emissions/summary/', views.EmissionSummaryView.as_view(), name='emissions-summary'),
    path('emissions/<int:record_id>/update/', views.EmissionRecordDetailView.as_view(), name='emissions-update'),
]
