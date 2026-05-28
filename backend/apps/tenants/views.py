from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from .models import Tenant, TenantMembership


class LoginView(APIView):
    permission_classes = []
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if not user:
            return Response({'error': 'Invalid credentials'}, status=401)
        token, _ = Token.objects.get_or_create(user=user)
        memberships = TenantMembership.objects.filter(user=user).select_related('tenant')
        return Response({
            'token': token.key,
            'user': {'id': user.id, 'username': user.username, 'email': user.email},
            'tenants': [{'id': m.tenant.id, 'name': m.tenant.name, 'role': m.role} for m in memberships],
        })


class TenantListView(APIView):
    def get(self, request):
        memberships = TenantMembership.objects.filter(user=request.user).select_related('tenant')
        return Response([{
            'id': m.tenant.id, 'name': m.tenant.name,
            'industry': m.tenant.industry, 'country': m.tenant.country,
            'reporting_year': m.tenant.reporting_year, 'role': m.role,
        } for m in memberships])
