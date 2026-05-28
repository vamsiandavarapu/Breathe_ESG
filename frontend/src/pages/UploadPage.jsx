import React, { useState } from 'react';
import axios from 'axios';
import '../styles/UploadPage.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

const UploadPage = ({ token, tenant }) => {
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [sourceType, setSourceType] = useState('SAP_FUEL');
  const [uploadMessage, setUploadMessage] = useState('');

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
      
      setUploadMessage('✓ File uploaded successfully!');
      setSelectedFile(null);
      
      // Clear message after 3 seconds
      setTimeout(() => setUploadMessage(''), 3000);
    } catch (err) {
      setUploadMessage('✗ Upload failed: ' + (err.response?.data?.error || err.message));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="page upload-page">
      <h1>📤 Upload Data</h1>

      <div className="upload-section">
        <h2>Upload CSV File</h2>
        
        <div className="source-selector">
          <label>Data Source Type:</label>
          <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            <option value="SAP_FUEL">🏭 SAP - Fuel & Procurement (Scope 1)</option>
            <option value="UTILITY_ELECTRICITY">⚡ Utility Portal - Electricity (Scope 2)</option>
            <option value="TRAVEL_CORPORATE">✈️ Corporate Travel - Concur/Navan (Scope 3)</option>
          </select>
        </div>

        <div className="file-upload-box">
          <input 
            type="file" 
            accept=".csv"
            onChange={handleFileSelect}
            id="file-input"
            disabled={uploading}
          />
          <label htmlFor="file-input" className="file-label">
            {selectedFile ? selectedFile.name : '📁 Choose CSV file or drag & drop'}
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
          {uploading ? '⏳ Uploading...' : '📤 Upload File'}
        </button>

        <div className="upload-info">
          <h3>📋 Upload Instructions</h3>
          <ul>
            <li><strong>SAP Fuel:</strong> Use ME2M or SE16N export (German headers: WERKS, MENGE, MEINS, BLDAT, TXZ01)</li>
            <li><strong>Utility:</strong> Download from your portal in CSV format (columns: date, kwh, facility)</li>
            <li><strong>Travel:</strong> Export from Concur/Navan as CSV (columns: date, amount, category)</li>
            <li>All dates should be clear (YYYY-MM-DD preferred)</li>
            <li>Quantities must be numeric</li>
          </ul>
        </div>

        <div className="sample-data">
          <h3>📁 Sample Files Available</h3>
          <p>Check the <code>sample_data/</code> folder in the project for example CSV files you can use to test the system.</p>
        </div>
      </div>
    </div>
  );
};

export default UploadPage;
