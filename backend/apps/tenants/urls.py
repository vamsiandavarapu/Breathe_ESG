from django.urls import path
from . import views
urlpatterns = [
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('tenants/', views.TenantListView.as_view(), name='tenant-list'),
]
