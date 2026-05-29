"""
Tenant model — multi-tenancy foundation.
Every piece of data in the system belongs to a Tenant.
A Tenant = one client company (e.g., "Tata Steel India Division").
"""
from django.db import models
from django.contrib.auth.models import User


class Tenant(models.Model):
    """
    A client company onboarded to Breathe ESG.
    All emission data is scoped to a tenant — one analyst cannot see another company's data.
    """
    name = models.CharField(max_length=255, help_text="Full legal name, e.g. 'Tata Steel Ltd - India Operations'")
    slug = models.SlugField(unique=True, help_text="URL-safe identifier, e.g. 'tata-steel-india'")
    industry = models.CharField(max_length=100, blank=True, help_text="e.g. 'Steel Manufacturing'")
    country = models.CharField(max_length=100, default='India')
    reporting_year = models.IntegerField(default=2024, help_text="The fiscal/calendar year being reported")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    """
    Links a Django User to a Tenant with a role.
    One user can belong to multiple tenants (a consultant managing multiple clients).
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),       # Can manage everything
        ('analyst', 'Analyst'),   # Can review and approve records
        ('viewer', 'Viewer'),     # Read-only
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='analyst')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'tenant')

    def __str__(self):
        return f"{self.user.username} → {self.tenant.name} ({self.role})"


def verify_tenant_access(user, tenant_id, allowed_roles=None):
    """
    Validates if the user belongs to the specified tenant and has one of the allowed roles.
    Returns:
        (True, TenantMembership) if allowed.
        (False, error_message) if denied.
    """
    if not user or not user.is_authenticated:
        return False, "Authentication required"
    if not tenant_id:
        return False, "tenant_id is required"
    
    try:
        membership = TenantMembership.objects.get(user=user, tenant_id=tenant_id)
        if allowed_roles and membership.role not in allowed_roles:
            return False, f"Permission denied: role '{membership.role}' is not authorized for this action."
        return True, membership
    except TenantMembership.DoesNotExist:
        return False, "Permission denied: you do not have access to this tenant's data."

