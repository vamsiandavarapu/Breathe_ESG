"""
Run this after migrate to load sample data into the database.
python manage.py shell < seed_data.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from apps.tenants.models import Tenant
from apps.emissions.models import IngestionJob, RawRecord, EmissionRecord, AuditLog
import csv, sys

# Users
analyst, _ = User.objects.get_or_create(username='analyst', defaults={'email': 'analyst@breatheesg.com', 'first_name': 'Priya', 'last_name': 'Sharma'})
analyst.set_password('demo1234'); analyst.save()

admin_user, _ = User.objects.get_or_create(username='admin', defaults={'email': 'admin@breatheesg.com', 'first_name': 'Rahul', 'last_name': 'Mehta', 'is_staff': True})
admin_user.set_password('admin1234'); admin_user.save()

# Tokens
for u in [analyst, admin_user]:
    Token.objects.get_or_create(user=u)

# Tenants
t1, _ = Tenant.objects.get_or_create(user=analyst, slug='tata-steel-india', defaults={'name': 'Tata Steel Ltd - India Operations', 'industry': 'Steel Manufacturing', 'country': 'India', 'reporting_year': 2024, 'role': 'analyst'})
t2, _ = Tenant.objects.get_or_create(user=analyst, slug='infosys-ltd', defaults={'name': 'Infosys Ltd - Corporate', 'industry': 'Information Technology', 'country': 'India', 'reporting_year': 2024, 'role': 'viewer'})

t1_admin, _ = Tenant.objects.get_or_create(user=admin_user, slug='tata-steel-india', defaults={'name': 'Tata Steel Ltd - India Operations', 'industry': 'Steel Manufacturing', 'country': 'India', 'reporting_year': 2024, 'role': 'admin'})
t2_admin, _ = Tenant.objects.get_or_create(user=admin_user, slug='infosys-ltd', defaults={'name': 'Infosys Ltd - Corporate', 'industry': 'Information Technology', 'country': 'India', 'reporting_year': 2024, 'role': 'admin'})

print(f"Setup complete. Tenants: {Tenant.objects.count()}, Users: {User.objects.count()}")
print(f"Login: analyst / demo1234  |  admin / admin1234")
print(f"Tenant IDs: Tata Steel (Analyst)={t1.id}, Infosys (Analyst)={t2.id}")
