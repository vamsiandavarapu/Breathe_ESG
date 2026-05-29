from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from .models import Tenant


class LoginView(APIView):
    permission_classes = []
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if not user:
            return Response({'error': 'Invalid credentials'}, status=401)
        token, _ = Token.objects.get_or_create(user=user)
        tenants = Tenant.objects.filter(user=user)
        return Response({
            'token': token.key,
            'user': {'id': user.id, 'username': user.username, 'email': user.email},
            'tenants': [{'id': t.id, 'name': t.name, 'role': t.role} for t in tenants],
        })


class TenantListView(APIView):
    def get(self, request):
        tenants = Tenant.objects.filter(user=request.user)
        return Response([{
            'id': t.id, 'name': t.name,
            'industry': t.industry, 'country': t.country,
            'reporting_year': t.reporting_year, 'role': t.role,
        } for t in tenants])
