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

# New submission credentials
saurav, _ = User.objects.get_or_create(username='saurav', defaults={'email': 'saurav@breatheesg.com', 'first_name': 'Saurav', 'last_name': 'ESG', 'is_staff': True})
saurav.set_password('demo1234'); saurav.save()

rahul_user, _ = User.objects.get_or_create(username='rahul', defaults={'email': 'rahul@breatheesg.com', 'first_name': 'Rahul', 'last_name': 'ESG'})
rahul_user.set_password('demo1234'); rahul_user.save()

shivang, _ = User.objects.get_or_create(username='shivang', defaults={'email': 'shivang@breatheesg.com', 'first_name': 'Shivang', 'last_name': 'ESG'})
shivang.set_password('demo1234'); shivang.save()

# Tokens
for u in [analyst, admin_user, saurav, rahul_user, shivang]:
    Token.objects.get_or_create(user=u)

# Tenants mapping for Tata Steel and Infosys
for user_obj in [analyst, rahul_user, shivang]:
    # Analyst access
    Tenant.objects.get_or_create(user=user_obj, slug='tata-steel-india', defaults={'name': 'Tata Steel Ltd - India Operations', 'industry': 'Steel Manufacturing', 'country': 'India', 'reporting_year': 2024, 'role': 'analyst'})
    Tenant.objects.get_or_create(user=user_obj, slug='infosys-ltd', defaults={'name': 'Infosys Ltd - Corporate', 'industry': 'Information Technology', 'country': 'India', 'reporting_year': 2024, 'role': 'viewer'})

for admin_obj in [admin_user, saurav]:
    # Admin access
    Tenant.objects.get_or_create(user=admin_obj, slug='tata-steel-india', defaults={'name': 'Tata Steel Ltd - India Operations', 'industry': 'Steel Manufacturing', 'country': 'India', 'reporting_year': 2024, 'role': 'admin'})
    Tenant.objects.get_or_create(user=admin_obj, slug='infosys-ltd', defaults={'name': 'Infosys Ltd - Corporate', 'industry': 'Information Technology', 'country': 'India', 'reporting_year': 2024, 'role': 'admin'})

print(f"Setup complete. Tenants: {Tenant.objects.count()}, Users: {User.objects.count()}")
print(f"Demo Logins:")
print(f"  - saurav / demo1234 (Admin)")
print(f"  - rahul / demo1234 (Analyst)")
print(f"  - shivang / demo1234 (Analyst)")
print(f"  - analyst / demo1234 (Analyst)")
print(f"  - admin / admin1234 (Admin)")

