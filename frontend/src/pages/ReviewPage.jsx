import React, { useState, useEffect } from 'react';
import axios from 'axios';
import '../styles/ReviewPage.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

const ReviewPage = ({ token, tenant }) => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState({
    scope: '',
    status: '',
    source: '',
  });
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [reviewNote, setReviewNote] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    if (tenant?.id) {
      fetchRecords();
    }
  }, [tenant, token, filters]);

  const fetchRecords = async () => {
    try {
      setLoading(true);
      const headers = { Authorization: `Token ${token}` };
      const params = new URLSearchParams({
        tenant_id: tenant.id,
        ...(filters.scope && { scope: filters.scope }),
        ...(filters.status && { review_status: filters.status }),
        ...(filters.source && { source_type: filters.source }),
      });

      const response = await axios.get(
        `${API_BASE_URL}/emissions/?${params}`,
        { headers }
      );
      setRecords(response.data);
      setError('');
    } catch (err) {
      setError('Failed to load records');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleReviewAction = async (recordId, action) => {
    try {
      setActionLoading(true);
      const headers = { Authorization: `Token ${token}` };
      
      await axios.post(
        `${API_BASE_URL}/review/${recordId}/`,
        {
          action,
          note: reviewNote,
        },
        { headers }
      );

      setSelectedRecord(null);
      setReviewNote('');
      await fetchRecords();
    } catch (err) {
      alert('Failed to update record: ' + (err.response?.data?.error || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) return <div className="page"><p>Loading records...</p></div>;

  return (
    <div className="page review-page">
      <h1>📋 Review Emissions Records</h1>

      <div className="filter-bar">
        <select 
          value={filters.scope} 
          onChange={(e) => setFilters({...filters, scope: e.target.value})}
        >
          <option value="">All Scopes</option>
          <option value="SCOPE_1">Scope 1 (Direct)</option>
          <option value="SCOPE_2">Scope 2 (Indirect)</option>
          <option value="SCOPE_3">Scope 3 (Value Chain)</option>
        </select>

        <select 
          value={filters.status} 
          onChange={(e) => setFilters({...filters, status: e.target.value})}
        >
          <option value="">All Status</option>
          <option value="PENDING">Pending</option>
          <option value="APPROVED">Approved</option>
          <option value="FLAGGED">Flagged</option>
          <option value="REJECTED">Rejected</option>
        </select>

        <select 
          value={filters.source} 
          onChange={(e) => setFilters({...filters, source: e.target.value})}
        >
          <option value="">All Sources</option>
          <option value="SAP_FUEL">SAP Fuel</option>
          <option value="UTILITY_ELECTRICITY">Utility</option>
          <option value="TRAVEL_CORPORATE">Travel</option>
        </select>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="records-table">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Scope</th>
              <th>Category</th>
              <th>Description</th>
              <th>Quantity</th>
              <th>CO₂e (kg)</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id} className={`status-${record.review_status.toLowerCase()}`}>
                <td>{record.id}</td>
                <td>{record.scope_label}</td>
                <td>{record.category_label}</td>
                <td title={record.activity_description}>{record.activity_description?.substring(0, 30)}</td>
                <td>{record.quantity} {record.unit}</td>
                <td>{record.co2e_kg.toFixed(2)}</td>
                <td>
                  <span className={`status-badge status-${record.review_status.toLowerCase()}`}>
                    {record.review_status}
                  </span>
                  {record.is_suspicious && <span className="badge-warning">⚠️ Suspicious</span>}
                </td>
                <td>
                  <button 
                    onClick={() => setSelectedRecord(record)}
                    className="btn-small"
                  >
                    Review
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {records.length === 0 && (
        <p className="no-data">No records found matching your filters.</p>
      )}

      {selectedRecord && (
        <div className="modal-overlay" onClick={() => setSelectedRecord(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Review Record #{selectedRecord.id}</h2>
            
            <div className="record-details">
              <div className="detail-row">
                <div className="detail-col">
                  <label>Scope:</label>
                  <p>{selectedRecord.scope_label}</p>
                </div>
                <div className="detail-col">
                  <label>Category:</label>
                  <p>{selectedRecord.category_label}</p>
                </div>
              </div>

              <div className="detail-row">
                <div className="detail-col">
                  <label>Description:</label>
                  <p>{selectedRecord.activity_description}</p>
                </div>
              </div>

              <div className="detail-row">
                <div className="detail-col">
                  <label>Quantity:</label>
                  <p>{selectedRecord.quantity} {selectedRecord.unit}</p>
                </div>
                <div className="detail-col">
                  <label>Emission Factor:</label>
                  <p>{selectedRecord.emission_factor} ({selectedRecord.emission_factor_source})</p>
                </div>
              </div>

              <div className="detail-row">
                <div className="detail-col">
                  <label>CO₂e Emission:</label>
                  <p className="highlight">{selectedRecord.co2e_kg.toFixed(2)} kg = {selectedRecord.co2e_tonnes.toFixed(4)} tonnes</p>
                </div>
              </div>

              {selectedRecord.is_suspicious && (
                <div className="warning-box">
                  <strong>⚠️ Suspicious Alert:</strong> {selectedRecord.suspicious_reason}
                </div>
              )}

              {selectedRecord.raw_data && (
                <div className="raw-data-box">
                  <strong>Raw Source Data:</strong>
                  <pre>{JSON.stringify(selectedRecord.raw_data, null, 2)}</pre>
                </div>
              )}

              <textarea 
                placeholder="Add a review note..."
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
                rows="3"
              />

              <div className="action-buttons">
                <button 
                  onClick={() => handleReviewAction(selectedRecord.id, 'APPROVED')}
                  className="btn-approve"
                  disabled={actionLoading}
                >
                  ✓ Approve
                </button>
                <button 
                  onClick={() => handleReviewAction(selectedRecord.id, 'FLAGGED')}
                  className="btn-flag"
                  disabled={actionLoading}
                >
                  🚩 Flag
                </button>
                <button 
                  onClick={() => handleReviewAction(selectedRecord.id, 'REJECTED')}
                  className="btn-reject"
                  disabled={actionLoading}
                >
                  ✗ Reject
                </button>
                <button 
                  onClick={() => setSelectedRecord(null)}
                  className="btn-cancel"
                  disabled={actionLoading}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ReviewPage;
