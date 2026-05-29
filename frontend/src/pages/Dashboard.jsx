import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import '../styles/Dashboard.css';
import API_BASE_URL from '../apiConfig';

const Dashboard = ({ token, tenant }) => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (tenant?.id) {
      fetchSummary();
    }
  }, [tenant, token]);

  const fetchSummary = async () => {
    try {
      setLoading(true);
      const headers = { Authorization: `Token ${token}` };
      const response = await axios.get(
        `${API_BASE_URL}/emissions/summary/?tenant_id=${tenant.id}`,
        { headers }
      );
      setSummary(response.data);
      setError('');
    } catch (err) {
      setError('Failed to load summary data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="page"><p>Loading dashboard...</p></div>;
  if (error) return <div className="page"><p className="error">{error}</p></div>;
  if (!summary) return <div className="page"><p>No data available</p></div>;

  const scopeData = [
    { name: 'Scope 1', value: summary.by_scope?.SCOPE_1 || 0 },
    { name: 'Scope 2', value: summary.by_scope?.SCOPE_2 || 0 },
    { name: 'Scope 3', value: summary.by_scope?.SCOPE_3 || 0 },
  ];

  const sourceData = [
    { name: 'SAP Fuel', value: summary.by_source?.SAP_FUEL || 0 },
    { name: 'Utility', value: summary.by_source?.UTILITY_ELECTRICITY || 0 },
    { name: 'Travel', value: summary.by_source?.TRAVEL_CORPORATE || 0 },
  ];

  const statusData = [
    { name: 'Pending', value: summary.by_status?.PENDING || 0 },
    { name: 'Approved', value: summary.by_status?.APPROVED || 0 },
    { name: 'Flagged', value: summary.by_status?.FLAGGED || 0 },
    { name: 'Rejected', value: summary.by_status?.REJECTED || 0 },
  ];

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

  return (
    <div className="page dashboard-page">
      <h1>📊 Emissions Dashboard</h1>
      <p className="tenant-info">Tenant: <strong>{tenant.name}</strong></p>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">Total CO₂e Emissions</div>
          <div className="metric-value">{summary.total_co2e_tonnes.toFixed(2)}</div>
          <div className="metric-unit">Tonnes</div>
          <div className="metric-subtext">{summary.total_records} records</div>
        </div>

        <div className="metric-card alert">
          <div className="metric-label">⚠️ Suspicious Records</div>
          <div className="metric-value">{summary.suspicious_count}</div>
          <div className="metric-unit">Need Review</div>
        </div>

        <div className="metric-card pending">
          <div className="metric-label">📋 Pending Approval</div>
          <div className="metric-value">{summary.pending_count}</div>
          <div className="metric-unit">Records</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Total kg CO₂e</div>
          <div className="metric-value">{(summary.total_co2e_kg / 1000).toFixed(0)}</div>
          <div className="metric-unit">k Kilograms</div>
        </div>
      </div>

      <div className="charts-grid">
        <div className="chart-container">
          <h3>Emissions by Scope</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={scopeData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-container">
          <h3>Emissions by Source</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={sourceData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={80}
                paddingAngle={5}
                dataKey="value"
              >
                {sourceData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => `${value.toFixed(2)} kg`} />
              <Legend verticalAlign="bottom" height={36} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-container">
          <h3>Review Status</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={statusData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#82ca9d" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="summary-details">
        <h3>📈 Scope Breakdown</h3>
        <table>
          <tbody>
            <tr>
              <td>Scope 1 (Direct)</td>
              <td className="right">{summary.by_scope?.SCOPE_1?.toFixed(2)} kg</td>
            </tr>
            <tr>
              <td>Scope 2 (Indirect Energy)</td>
              <td className="right">{summary.by_scope?.SCOPE_2?.toFixed(2)} kg</td>
            </tr>
            <tr>
              <td>Scope 3 (Value Chain)</td>
              <td className="right">{summary.by_scope?.SCOPE_3?.toFixed(2)} kg</td>
            </tr>
          </tbody>
        </table>
      </div>

      <button onClick={fetchSummary} className="refresh-btn">🔄 Refresh Data</button>
    </div>
  );
};

export default Dashboard;
