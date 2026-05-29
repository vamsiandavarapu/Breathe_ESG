from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from decimal import Decimal
from apps.tenants.models import verify_tenant_access
from .models import EmissionRecord, AuditLog


class EmissionRecordListView(APIView):
    def get(self, request):
        tenant_id = request.query_params.get('tenant_id')
        
        # Enforce multi-tenancy validation
        is_allowed, membership_or_err = verify_tenant_access(request.user, tenant_id)
        if not is_allowed:
            return Response({'error': membership_or_err}, status=403)
            
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
        
        # Enforce multi-tenancy validation
        is_allowed, membership_or_err = verify_tenant_access(request.user, tenant_id)
        if not is_allowed:
            return Response({'error': membership_or_err}, status=403)
            
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


class EmissionRecordDetailView(APIView):
    """Allows analysts/admins to correct record values before audit lock."""
    
    def post(self, request, record_id):
        return self.update_record(request, record_id)
        
    def patch(self, request, record_id):
        return self.update_record(request, record_id)
        
    def update_record(self, request, record_id):
        try:
            record = EmissionRecord.objects.get(id=record_id)
        except EmissionRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)
            
        # Verify tenant access with mutating permissions (admin or analyst role required)
        is_allowed, membership_or_err = verify_tenant_access(
            request.user, record.tenant_id, allowed_roles=['admin', 'analyst']
        )
        if not is_allowed:
            return Response({'error': membership_or_err}, status=403)
            
        if record.is_locked:
            return Response({'error': 'Record is locked for audit — cannot be edited'}, status=403)
            
        # Gather input
        quantity = request.data.get('quantity')
        description = request.data.get('activity_description')
        date_val = request.data.get('activity_date')
        location = request.data.get('location')
        note = request.data.get('review_note')
        
        changes = {}
        
        if quantity is not None:
            try:
                old_qty = record.quantity
                new_qty = Decimal(str(quantity))
                if new_qty != old_qty:
                    record.quantity = new_qty
                    changes['quantity'] = [float(old_qty), float(new_qty)]
                    
                    # Dynamic carbon calculation recalculation!
                    old_co2e = record.co2e_kg
                    new_co2e = new_qty * record.emission_factor
                    record.co2e_kg = new_co2e
                    changes['co2e_kg'] = [float(old_co2e), float(new_co2e)]
            except Exception:
                return Response({'error': f"Invalid quantity value: '{quantity}'"}, status=400)
                
        if description is not None and description != record.activity_description:
            old_desc = record.activity_description
            record.activity_description = description
            changes['activity_description'] = [old_desc, description]
            
        if date_val is not None:
            try:
                from datetime import datetime
                parsed_date = datetime.strptime(str(date_val).strip(), '%Y-%m-%d').date()
                if parsed_date != record.activity_date:
                    old_date = record.activity_date
                    record.activity_date = parsed_date
                    changes['activity_date'] = [old_date.isoformat(), parsed_date.isoformat()]
            except ValueError:
                return Response({'error': f"Invalid date format: '{date_val}'. Expected YYYY-MM-DD."}, status=400)
                
        if location is not None and location != record.location:
            old_loc = record.location
            record.location = location
            changes['location'] = [old_loc, location]
            
        if note is not None and note != record.review_note:
            old_note = record.review_note
            record.review_note = note
            changes['review_note'] = [old_note, note]
            
        if changes:
            record.edited_by = request.user
            record.save()
            
            # Log action in append-only AuditLog
            AuditLog.objects.create(
                record=record,
                user=request.user,
                action='EDITED',
                changes=changes,
                note=note or "Record edited by analyst",
            )
            
        return Response({
            'status': 'ok',
            'record': {
                'id': record.id,
                'quantity': float(record.quantity),
                'co2e_kg': float(record.co2e_kg),
                'co2e_tonnes': float(record.co2e_tonnes),
                'activity_description': record.activity_description,
                'activity_date': record.activity_date.isoformat(),
                'location': record.location,
                'review_note': record.review_note,
            }
        })

