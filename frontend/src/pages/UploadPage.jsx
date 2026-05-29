import React, { useState, useEffect } from 'react';
import axios from 'axios';
import '../styles/UploadPage.css';
import API_BASE_URL from '../apiConfig';

const UploadPage = ({ token, tenant }) => {
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [sourceType, setSourceType] = useState('SAP_FUEL');
  const [uploadMessage, setUploadMessage] = useState('');
  const [jobs, setJobs] = useState([]);
  const [loadingJobs, setLoadingJobs] = useState(true);

  useEffect(() => {
    if (tenant?.id) {
      fetchJobs();
    }
  }, [tenant, token]);

  const fetchJobs = async () => {
    try {
      setLoadingJobs(true);
      const headers = { Authorization: `Token ${token}` };
      const response = await axios.get(`${API_BASE_URL}/ingest/jobs/?tenant_id=${tenant.id}`, { headers });
      setJobs(response.data);
    } catch (err) {
      console.error('Failed to load ingestion jobs history:', err);
    } finally {
      setLoadingJobs(false);
    }
  };

  const handleFileSelect = (e) => {
    setSelectedFile(e.target.files[0]);
    setUploadMessage('');
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setUploadMessage('Please select a file');
      return;
    }

    try {
      setUploading(true);
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('source_type', sourceType);
      formData.append('tenant_id', tenant.id);

      const headers = { 
         Authorization: `Token ${token}`,
        'Content-Type': 'multipart/form-data',
      };

      await axios.post(`${API_BASE_URL}/ingest/upload/`, formData, { headers });
      
      setUploadMessage('✓ File uploaded and processed successfully!');
      setSelectedFile(null);
      
      // Auto refresh job history!
      fetchJobs();
      
      // Clear message after 4 seconds
      setTimeout(() => setUploadMessage(''), 4000);
    } catch (err) {
      setUploadMessage('✗ Upload failed: ' + (err.response?.data?.error || err.message));
    } finally {
      setUploading(false);
    }
  };

  const formatSourceType = (src) => {
    switch (src) {
      case 'SAP_FUEL': return '🏭 SAP Procurement (Scope 1)';
      case 'UTILITY_ELECTRICITY': return '⚡ Utility Portal (Scope 2)';
      case 'TRAVEL_CORPORATE': return '✈️ Corporate Travel (Scope 3)';
      default: return src;
    }
  };

  return (
    <div className="page upload-page">
      <h1 className="upload-title">📤 Data Ingestion Engine</h1>
      <p className="upload-subtitle">Onboard, parse, and normalize enterprise emissions data</p>

      <div className="upload-grid">
        {/* Upload Form Panel */}
        <div className="upload-card main-upload-section">
          <h2>Upload Data File</h2>
          
          <div className="source-selector">
             <label>Select Enterprise Source:</label>
             <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
               <option value="SAP_FUEL">🏭 SAP - Fuel & Procurement (Scope 1)</option>
               <option value="UTILITY_ELECTRICITY">⚡ Utility Portal - Electricity (Scope 2)</option>
               <option value="TRAVEL_CORPORATE">✈️ Corporate Travel - Concur/Navan (Scope 3)</option>
             </select>
           </div>
 
           <div className="file-upload-box">
             <input 
               type="file" 
               accept=".csv,.xml,.txt"
               onChange={handleFileSelect}
               id="file-input"
               disabled={uploading}
             />
             <label htmlFor="file-input" className="file-label">
               {selectedFile ? (
                 <span className="selected-file-name">📄 {selectedFile.name}</span>
               ) : (
                 <>
                   <span className="file-icon">📁</span>
                   <span>Choose a file (CSV, XML, TXT) or drag & drop here</span>
                 </>
               )}
             </label>
           </div>

          {uploadMessage && (
            <p className={`message ${uploadMessage.startsWith('✓') ? 'success' : 'error'}`}>
              {uploadMessage}
            </p>
          )}

          <button 
            onClick={handleUpload}
            disabled={!selectedFile || uploading}
            className="btn-upload"
          >
            {uploading ? (
              <>
                <span className="spinner">⏳</span> Parsing & Normalizing...
              </>
            ) : '📤 Ingest Data'}
          </button>
        </div>

        {/* Upload Instructions Panel */}
        <div className="upload-card upload-info-section">
          <h2>📋 File Specifications</h2>
          <div className="info-blocks">
            <div className="info-block">
              <h4>🏭 Scope 1: SAP Fuel</h4>
              <p>Supports flat files (ME2M CSV exports) and IDoc XML files. Detects German locale headers (WERKS, MENGE, BLDAT) and standard SAP segments.</p>
            </div>
            <div className="info-block">
              <h4>⚡ Scope 2: Utility Portal</h4>
              <p>Supports state utility portals (MSEDCL, BESCOM, TSSPDCL). mid-point proration handles cross-month billing periods.</p>
            </div>
            <div className="info-block">
              <h4>✈️ Scope 3: Travel Expense</h4>
              <p>Supports Concur exports. Computes flights via great-circle Haversine formula + routing buffers. Estimates ground missing logs.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Upload Job History Section */}
      <div className="upload-card job-history-section">
        <div className="history-header">
          <h2>Ingestion Pipelines History</h2>
          <button onClick={fetchJobs} className="btn-refresh-jobs" title="Refresh history">🔄 Refresh</button>
        </div>
        
        {loadingJobs ? (
          <p className="loading-text">Loading pipelines history...</p>
        ) : jobs.length === 0 ? (
          <p className="no-data-text">No ingestion jobs have been run for this tenant yet.</p>
        ) : (
          <div className="jobs-table-wrapper">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Source</th>
                  <th>File Name</th>
                  <th>Timestamp</th>
                  <th>Status</th>
                  <th>Ingested Rows</th>
                  <th>Issues & Warnings</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} className={`status-row-${job.status.toLowerCase()}`}>
                    <td>#{job.id}</td>
                    <td>{formatSourceType(job.source_type)}</td>
                    <td className="file-cell" title={job.file_name}>{job.file_name}</td>
                    <td>{new Date(job.uploaded_at).toLocaleString()}</td>
                    <td>
                      <span className={`job-status-badge badge-${job.status.toLowerCase()}`}>
                        {job.status}
                      </span>
                    </td>
                    <td>
                      <div className="counts-breakdown">
                        <span className="count-total" title="Total processed">{job.total_rows} Total</span>
                        <span className="count-success" title="Success rows">✅ {job.success_rows}</span>
                        <span className="count-suspicious" title="Suspicious rows">⚠️ {job.suspicious_rows}</span>
                        <span className="count-failed" title="Failed rows">❌ {job.failed_rows}</span>
                      </div>
                    </td>
                    <td className="errors-cell">
                      {job.status === 'FAILED' && job.error_summary && (
                        <span className="error-text text-danger">{job.error_summary.join('; ')}</span>
                      )}
                      {job.suspicious_rows > 0 && (
                        <span className="warning-text text-warning">Contains suspicious records for audit review</span>
                      )}
                      {job.status === 'DONE' && job.suspicious_rows === 0 && job.failed_rows === 0 && (
                        <span className="success-text text-success">✓ Clean load</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default UploadPage;
