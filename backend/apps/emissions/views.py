from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from .models import EmissionRecord, AuditLog


class EmissionRecordListView(APIView):
    def get(self, request):
        tenant_id = request.query_params.get('tenant_id')
        qs = EmissionRecord.objects.filter(tenant_id=tenant_id)
        
        # Filters
        scope = request.query_params.get('scope')
        status = request.query_params.get('review_status')
        source = request.query_params.get('source_type')
        suspicious = request.query_params.get('suspicious')
        
        if scope: qs = qs.filter(scope=scope)
        if status: qs = qs.filter(review_status=status)
        if source: qs = qs.filter(source_type=source)
        if suspicious == 'true': qs = qs.filter(is_suspicious=True)
        
        records = qs.select_related('raw_record', 'reviewed_by').order_by('-activity_date')[:200]
        
        return Response([{
            'id': r.id,
            'scope': r.scope,
            'scope_label': r.get_scope_display(),
            'category': r.category,
            'category_label': r.get_category_display(),
            'source_type': r.source_type,
            'activity_description': r.activity_description,
            'activity_date': r.activity_date.isoformat() if r.activity_date else None,
            'location': r.location,
            'quantity': float(r.quantity),
            'unit': r.unit,
            'quantity_original': float(r.quantity_original) if r.quantity_original else None,
            'unit_original': r.unit_original,
            'emission_factor': float(r.emission_factor),
            'emission_factor_source': r.emission_factor_source,
            'co2e_kg': float(r.co2e_kg),
            'co2e_tonnes': float(r.co2e_tonnes),
            'review_status': r.review_status,
            'is_suspicious': r.is_suspicious,
            'suspicious_reason': r.suspicious_reason,
            'is_locked': r.is_locked,
            'review_note': r.review_note,
            'reviewed_by': r.reviewed_by.username if r.reviewed_by else None,
            'reviewed_at': r.reviewed_at.isoformat() if r.reviewed_at else None,
            'raw_data': r.raw_record.raw_data if r.raw_record else {},
        } for r in records])


class EmissionSummaryView(APIView):
    def get(self, request):
        tenant_id = request.query_params.get('tenant_id')
        qs = EmissionRecord.objects.filter(tenant_id=tenant_id)
        
        total_co2e = qs.aggregate(total=Sum('co2e_kg'))['total'] or 0
        
        by_scope = {}
        for scope in ['SCOPE_1', 'SCOPE_2', 'SCOPE_3']:
            val = qs.filter(scope=scope).aggregate(total=Sum('co2e_kg'))['total'] or 0
            by_scope[scope] = round(float(val), 2)
        
        by_status = {}
        for s in ['PENDING', 'APPROVED', 'FLAGGED', 'REJECTED']:
            by_status[s] = qs.filter(review_status=s).count()
        
        by_source = {}
        for src in ['SAP_FUEL', 'UTILITY_ELECTRICITY', 'TRAVEL_CORPORATE']:
            val = qs.filter(source_type=src).aggregate(total=Sum('co2e_kg'))['total'] or 0
            by_source[src] = round(float(val), 2)
        
        return Response({
            'total_co2e_kg': round(float(total_co2e), 2),
            'total_co2e_tonnes': round(float(total_co2e) / 1000, 3),
            'by_scope': by_scope,
            'by_status': by_status,
            'by_source': by_source,
            'total_records': qs.count(),
            'suspicious_count': qs.filter(is_suspicious=True).count(),
            'pending_count': qs.filter(review_status='PENDING').count(),
        })
