from django.urls import path
from . import views
urlpatterns = [
    path('review/<int:record_id>/', views.ReviewActionView.as_view(), name='review-action'),
    path('review/bulk/', views.BulkReviewView.as_view(), name='review-bulk'),
    path('review/<int:record_id>/audit-log/', views.AuditLogView.as_view(), name='audit-log'),
]
